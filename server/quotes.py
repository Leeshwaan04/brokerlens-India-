"""Live-quote poller with SSE fan-out. Hardened.

Design constraints, in priority order:
  1. Never hammer a source. Every interval is bounded by a bandwidth budget and a
     circuit breaker; a failing source backs off exponentially instead of
     retrying at 1s forever.
  2. Never die. A source raising, a thread crashing, a client hanging up mid-frame
     - none of it may stop the others. A watchdog restarts dead workers.
  3. Never grow without bound. Subscriber queues, subscriber count, instruments
     per exchange and bytes per minute are all capped.
  4. Push only what changed, so the client can patch in place.

Cadence comes from config/stream.json, measured on real wire sizes. The MCX story
is the interesting one - see that file's comment. Short version: its market-watch
call is 1.28 MB uncompressed with no ETag and no gzip, so the fast loop uses the
4.8 KB heatmap endpoint instead and the heavy call runs every 15 minutes.
"""
from __future__ import annotations

import json
import os
import queue
import random
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline import feeds as feedmod  # noqa: E402
from pipeline.common import log, read_json  # noqa: E402
from pipeline.sources import bse as bse_src  # noqa: E402
from pipeline.sources import mcx as mcx_src  # noqa: E402
from pipeline.sources import nse as nse_src  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_LIMITS = {
    "closed_market_multiplier": 20,
    "jitter_pct": 12,
    "breaker_failures_to_open": 4,
    "breaker_base_backoff_s": 5,
    "breaker_max_backoff_s": 300,
    "max_sse_clients": 200,
    "max_sse_clients_per_ip": 6,
    "subscriber_queue_depth": 60,
    "max_instruments_per_exchange": 400,
    "total_max_mb_per_min": 12,
}


def _cfg():
    c = read_json(os.path.join(ROOT, "config", "stream.json"), {}) or {}
    limits = dict(DEFAULT_LIMITS)
    limits.update(c.get("limits") or {})
    return c.get("sources") or {}, limits


def market_open(exchange):
    """Approximate IST session windows; only used to decide how hard to poll.

    The open/closed flag shown in the UI comes from NSE's own marketStatus, not
    from here.
    """
    t = datetime.now(IST)
    if t.weekday() >= 5:
        return False
    mins = t.hour * 60 + t.minute
    if exchange == "MCX":
        return 9 * 60 <= mins <= 23 * 60 + 30
    return 9 * 60 + 8 <= mins <= 15 * 60 + 40


# --------------------------------------------------------------------- budget


class Bandwidth:
    """Rolling 60s byte accounting, per source and overall."""

    def __init__(self, total_mb_per_min):
        self._lock = threading.Lock()
        self._events = deque()          # (ts, source, bytes)
        self.total_cap = total_mb_per_min * 1e6

    def record(self, source, nbytes):
        now = time.time()
        with self._lock:
            self._events.append((now, source, nbytes))
            self._trim(now)

    def _trim(self, now):
        cut = now - 60
        while self._events and self._events[0][0] < cut:
            self._events.popleft()

    def rate(self, source=None):
        """Bytes in the last 60s."""
        now = time.time()
        with self._lock:
            self._trim(now)
            return sum(b for _, s, b in self._events if source is None or s == source)

    def over_total(self):
        return self.rate() > self.total_cap


class Breaker:
    """Per-source circuit breaker with exponential backoff and a half-open probe."""

    def __init__(self, limits):
        self.fail_threshold = limits["breaker_failures_to_open"]
        self.base = limits["breaker_base_backoff_s"]
        self.cap = limits["breaker_max_backoff_s"]
        self.failures = 0
        self.open_until = 0.0
        self.trips = 0

    def allow(self):
        return time.time() >= self.open_until

    def ok(self):
        if self.failures:
            self.failures = 0
        self.open_until = 0.0

    def fail(self):
        self.failures += 1
        if self.failures >= self.fail_threshold:
            backoff = min(self.cap, self.base * (2 ** (self.failures - self.fail_threshold)))
            self.open_until = time.time() + backoff
            self.trips += 1
            return backoff
        return 0

    @property
    def state(self):
        if not self.allow():
            return "open"
        return "half-open" if self.failures else "closed"


# ------------------------------------------------------------------------ hub


class Hub:
    def __init__(self, limits=None):
        _, default_limits = _cfg()
        self.limits = limits or default_limits
        self._lock = threading.Lock()
        self._subs = {}                  # queue -> ip
        self.started_at = time.time()
        self.frames_sent = 0
        self.rejected_clients = 0
        self.snapshot = {
            "generated_at": None,
            "order": feedmod.FEED_ORDER,
            "feeds": feedmod.empty_feeds(),
        }

    def seed_from_disk(self):
        """Start from the last published ticker.json so the first frame is complete."""
        disk = read_json(os.path.join(ROOT, "site", "data", "ticker.json"))
        if not disk or not isinstance(disk.get("feeds"), dict):
            log("stream: no ticker.json to seed from", "warn")
            return
        with self._lock:
            for fid, f in disk["feeds"].items():
                if fid in self.snapshot["feeds"]:
                    self.snapshot["feeds"][fid].update(f)
            self.snapshot["generated_at"] = disk.get("generated_at")
        log("stream: seeded (%s)" % " ".join(
            "%s=%d" % (k, len(v.get("instruments") or [])) for k, v in disk["feeds"].items()), "ok")

    # ---------------------------------------------------------- subscribers

    def subscribe(self, ip="-"):
        """Returns (queue, snapshot) or (None, reason) when a cap is hit."""
        with self._lock:
            if len(self._subs) >= self.limits["max_sse_clients"]:
                self.rejected_clients += 1
                return None, "server at capacity"
            same_ip = sum(1 for v in self._subs.values() if v == ip)
            if same_ip >= self.limits["max_sse_clients_per_ip"]:
                self.rejected_clients += 1
                return None, "too many connections from this address"
            q = queue.Queue(maxsize=self.limits["subscriber_queue_depth"])
            self._subs[q] = ip
            snap = json.loads(json.dumps(self.snapshot))
        return q, snap

    def unsubscribe(self, q):
        with self._lock:
            self._subs.pop(q, None)

    def subscriber_count(self):
        with self._lock:
            return len(self._subs)

    def _broadcast(self, event, payload):
        msg = (event, payload)
        with self._lock:
            dead = [q for q in self._subs if not self._offer(q, msg)]
            for q in dead:
                self._subs.pop(q, None)
            self.frames_sent += 1
        if dead:
            log("stream: dropped %d slow subscriber(s)" % len(dead), "warn")

    @staticmethod
    def _offer(q, msg):
        try:
            q.put_nowait(msg)
            return True
        except queue.Full:
            return False          # a client that cannot keep up must not block the poller

    # ------------------------------------------------------------- updates

    def apply(self, feed_id, *, instruments=None, status=None, as_of=None, note=None):
        """Merge a feed update; broadcast only instruments whose price moved."""
        cap = self.limits["max_instruments_per_exchange"]
        changed = []
        with self._lock:
            feed = self.snapshot["feeds"].get(feed_id)
            if feed is None:
                feed = self.snapshot["feeds"][feed_id] = {
                    "id": feed_id, "label": feed_id, "kind": "derived",
                    "status": None, "as_of": None, "instruments": [], "note": None,
                }
            if status is not None:
                feed["status"] = status
            if as_of is not None:
                feed["as_of"] = as_of
            if note is not None or "note" not in feed:
                feed["note"] = note

            if instruments is not None:
                def key(x):
                    return str(x.get("symbol") or x.get("name") or "").upper()

                prev = {key(x): x for x in (feed.get("instruments") or [])}
                for q in instruments:
                    k = key(q)
                    if not k:
                        continue
                    old = prev.get(k)
                    if not old or old.get("last") != q.get("last"):
                        changed.append(q)
                    prev[k] = q
                order = [key(q) for q in instruments if key(q)]
                rest = [k for k in prev if k not in set(order)]
                feed["instruments"] = [prev[k] for k in (order + rest)][:cap]

            self.snapshot["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if changed:
            self._broadcast("quotes", {"feed": feed_id, "instruments": changed[:cap],
                                       "as_of": as_of, "status": status})
        return len(changed)

    def set_status_everywhere(self, exchange, status):
        """Session status is per exchange but feeds are finer-grained."""
        for fid, meta in feedmod.FEED_META.items():
            if meta["exchange"] == exchange:
                self.apply(fid, status=status)


# --------------------------------------------------------------------- poller


class Worker(threading.Thread):
    """One thread per source. Owns its own fetcher, breaker and schedule."""

    daemon = True

    def __init__(self, key, spec, hub: Hub, bw: Bandwidth, limits, stop_event):
        super().__init__(name="poll-%s" % key)
        self.key = key
        self.spec = spec
        self.hub = hub
        self.bw = bw
        self.limits = limits
        self.stop_event = stop_event
        self.breaker = Breaker(limits)
        self.exchange = spec.get("exchange", "NSE")
        self.feed = spec.get("feed", self.exchange)
        self.calls = 0
        self.errors = 0
        self.last_ok = None
        self.last_error = None
        self.effective_interval = spec.get("interval", 2)
        self._fetcher = None
        self._bse_watch = None
        self._mcx_watch = None

    # ------------------------------------------------------------ scheduling

    def _interval(self):
        want = max(0.5, float(self.spec.get("interval", 2)))

        # Bandwidth budget: stretch rather than exceed it.
        wire = float(self.spec.get("wire_bytes") or 0)
        budget = float(self.spec.get("max_mb_per_min") or 0) * 1e6
        if wire and budget:
            need = wire * 60.0 / budget
            if need > want:
                want = need

        if not market_open(self.exchange):
            want *= self.limits["closed_market_multiplier"]

        if self.bw.over_total():
            want *= 2                     # global brake

        jitter = self.limits["jitter_pct"] / 100.0
        self.effective_interval = want
        return want * (1 + random.uniform(-jitter, jitter))

    def run(self):
        try:
            self._build()
        except Exception as exc:
            log("stream %s: could not build fetcher: %s" % (self.key, exc), "err")
            return

        # Stagger startup so seven workers do not all fire in the same instant.
        self.stop_event.wait(random.uniform(0, 1.5))

        while not self.stop_event.is_set():
            if not self.breaker.allow():
                self.stop_event.wait(1.0)
                continue
            try:
                nbytes = self._poll()
                self.calls += 1
                self.last_ok = time.time()
                self.breaker.ok()
                if nbytes:
                    self.bw.record(self.key, nbytes)
            except Exception as exc:
                self.errors += 1
                self.last_error = str(exc)[:160]
                backoff = self.breaker.fail()
                if backoff:
                    log("stream %s: breaker OPEN for %.0fs after %d failures (%s)"
                        % (self.key, backoff, self.breaker.failures, self.last_error), "warn")
            self.stop_event.wait(self._interval())

    def _build(self):
        wl = read_json(os.path.join(ROOT, "config", "watchlist.json"), {}) or {}
        self._bse_watch = wl.get("bse") or []
        self._mcx_watch = wl.get("mcx") or []
        if self.exchange == "NSE":
            self._fetcher = nse_src.nse()
        elif self.exchange == "BSE":
            self._fetcher = bse_src.bse()
        else:
            self._fetcher = mcx_src.fetcher()

    # ---------------------------------------------------------------- polls

    def _poll(self):
        fn = getattr(self, "_poll_" + self.key, None)
        if fn is None:
            raise RuntimeError("no poll handler for %r" % self.key)
        return fn() or 0

    def _poll_nse_pulse(self):
        pulse = nse_src.market_pulse(self._fetcher, ttl=0) or {}
        for s in pulse.get("status") or []:
            mk = (s.get("market") or "").lower()
            if "capital" in mk:
                self.hub.set_status_everywhere("NSE", s.get("status"))
                self.hub.set_status_everywhere("BSE", s.get("status"))
        # MCX is a separate exchange with its own hours (non-agri trades to
        # 23:30). Matching NSE's "commodity" segment here reported MCX closed
        # while it was trading. Compute it from MCX's own published sessions.
        self.hub.set_status_everywhere("MCX", feedmod._session_status("MCX"))
        idx = [dict(i, symbol=i.get("name")) for i in (pulse.get("indices") or [])]
        self.hub.apply("INDICES", instruments=idx)
        return self.spec.get("wire_bytes")

    def _poll_nse_active(self):
        rows, stamp = nse_src.most_active(self._fetcher, "volume", ttl=0)
        if not rows:
            raise RuntimeError("NSE most-active returned nothing")
        self.hub.apply("NSE", instruments=rows, as_of=stamp, note=None)
        return self.spec.get("wire_bytes")

    def _fetch_scrips(self, watch):
        """Parallel per-scrip fetch - BSE has no bulk quote endpoint."""
        conc = max(1, int(self.spec.get("concurrency", 4)))
        results, lock = [], threading.Lock()

        def one(item):
            try:
                r = bse_src.live_quotes(self._fetcher, [item], ttl=0)
                with lock:
                    results.extend(r.get("quotes") or [])
            except Exception:
                pass          # one scrip failing must not fail the cycle

        pending = list(watch)
        while pending and not self.stop_event.is_set():
            batch, pending = pending[:conc], pending[conc:]
            threads = [threading.Thread(target=one, args=(i,), daemon=True) for i in batch]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
        return results

    def _poll_bse_quotes(self):
        results = self._fetch_scrips(self._bse_watch)
        if not results:
            raise RuntimeError("no BSE scrip returned a quote")
        want = [i.get("label") for i in self._bse_watch]
        results.sort(key=lambda q: want.index(q["symbol"]) if q.get("symbol") in want else 999)
        self.hub.apply("BSE", instruments=results)
        return self.spec.get("wire_bytes")

    def _poll_mcx_heatmap(self):
        live = mcx_src.heatmap(self._fetcher, self._mcx_watch, ttl=0)
        if not live.get("quotes"):
            raise RuntimeError(live.get("note") or "MCX heatmap empty")
        self.hub.apply("MCX", instruments=live["quotes"], as_of=live.get("as_of"), note=None)
        return self.spec.get("wire_bytes")

    def _poll_mcx_gainers(self):
        g = mcx_src.top_gainers(self._fetcher, ttl=0)
        rows = g.get("quotes") or []
        if rows:
            self.hub.apply("MCX", instruments=rows)
        return self.spec.get("wire_bytes")

    def _poll_mcx_full(self):
        """Slow loop only: complete contract list, units, expiries. 1.28 MB."""
        live = mcx_src.live_quotes(self._fetcher, self._mcx_watch)
        if live.get("quotes"):
            self.hub.apply("MCX", instruments=live["quotes"], as_of=live.get("as_of"))
        return self.spec.get("wire_bytes")

    # --------------------------------------------------------------- health

    def health(self):
        return {
            "source": self.key,
            "label": self.spec.get("label"),
            "exchange": self.exchange,
            "feed": self.feed,
            "alive": self.is_alive(),
            "configured_interval_s": self.spec.get("interval"),
            "effective_interval_s": round(self.effective_interval, 2),
            "calls": self.calls,
            "errors": self.errors,
            "breaker": self.breaker.state,
            "breaker_trips": self.breaker.trips,
            "kb_per_min": round(self.bw.rate(self.key) / 1024, 1),
            "last_ok_age_s": round(time.time() - self.last_ok, 1) if self.last_ok else None,
            "last_error": self.last_error,
        }


class Supervisor(threading.Thread):
    """Restarts a worker whose thread has died. Cheap insurance."""

    daemon = True

    def __init__(self, pool, stop_event):
        super().__init__(name="poll-supervisor")
        self.pool = pool
        self.stop_event = stop_event
        self.restarts = 0

    def run(self):
        while not self.stop_event.is_set():
            self.stop_event.wait(15)
            if self.stop_event.is_set():
                return
            for key, w in list(self.pool.workers.items()):
                if not w.is_alive():
                    log("stream: worker %s died; restarting" % key, "err")
                    self.pool.restart(key)
                    self.restarts += 1


class Pool:
    def __init__(self, hub: Hub, sources, limits):
        self.hub = hub
        self.sources = sources
        self.limits = limits
        self.bw = Bandwidth(limits["total_max_mb_per_min"])
        self.stop_event = threading.Event()
        self.workers = {}
        self.supervisor = None

    def start(self):
        for key, spec in self.sources.items():
            self._spawn(key, spec)
        self.supervisor = Supervisor(self, self.stop_event)
        self.supervisor.start()
        log("stream: %d workers up (%s)" % (
            len(self.workers),
            ", ".join("%s@%ss" % (k, self.sources[k].get("interval")) for k in self.workers)), "ok")

    def _spawn(self, key, spec):
        w = Worker(key, spec, self.hub, self.bw, self.limits, self.stop_event)
        self.workers[key] = w
        w.start()

    def restart(self, key):
        self._spawn(key, self.sources[key])

    def stop(self, timeout=3):
        self.stop_event.set()
        for w in self.workers.values():
            w.join(timeout=timeout)

    def health(self):
        return {
            "uptime_s": round(time.time() - self.hub.started_at, 1),
            "subscribers": self.hub.subscriber_count(),
            "frames_sent": self.hub.frames_sent,
            "rejected_clients": self.hub.rejected_clients,
            "total_kb_per_min": round(self.bw.rate() / 1024, 1),
            "total_budget_kb_per_min": round(self.bw.total_cap / 1024, 1),
            "supervisor_restarts": self.supervisor.restarts if self.supervisor else 0,
            "sources": [w.health() for w in self.workers.values()],
        }


def start(install_signal_handlers=True):
    sources, limits = _cfg()
    if not sources:
        log("stream: config/stream.json has no sources; stream disabled", "err")
        return None, None
    hub = Hub(limits)
    hub.seed_from_disk()
    pool = Pool(hub, sources, limits)
    pool.start()

    if install_signal_handlers:
        def _bye(signum, _frame):
            log("stream: signal %d - shutting workers down" % signum, "warn")
            pool.stop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _bye)
            except (ValueError, OSError):
                pass       # not on the main thread; the caller handles it
    return hub, pool
