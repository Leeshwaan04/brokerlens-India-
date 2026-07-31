"""Pipeline CLI.

  python3 -m pipeline.run seed      write clearly-labelled SAMPLE data
  python3 -m pipeline.run fetch     pull NSE + BSE + MCX + SEBI into data/ (+ _ingest.json)
  python3 -m pipeline.run build     recompute metrics and publish site/data/*
  python3 -m pipeline.run all       fetch + build
  python3 -m pipeline.run pulse     refresh market strip + live quotes, then full rebuild
  python3 -m pipeline.run ticker    refresh ONLY live quotes -> ticker.json (cheapest; run every minute)

Exit code is non-zero if a source that was expected to return rows returned
none, so cron can alert instead of silently publishing a hollow site.
"""
from __future__ import annotations

import os
import sys
import traceback

from . import publish, seed_sample
from .common import CONFIG, DATA, log, now_iso, read_json, write_json
from .identity import Resolver
from .sources import bse as bse_src
from .sources import mcx as mcx_src
from .sources import nse as nse_src
from .sources import sebi as sebi_src


def _aliases():
    master = read_json(os.path.join(CONFIG, "brokers_master.json"), {})
    return Resolver(master.get("brokers", [])).alias_index()


def _watchlist():
    return read_json(os.path.join(CONFIG, "watchlist.json"), {}) or {}


def fetch(sebi_pages=None):
    out = {"_status": {}, "fetched_at": now_iso()}
    problems = []
    wl = _watchlist()

    def run(key, fn, source_ids):
        try:
            val = fn()
            out[key] = val
            ok = bool(val)
            for sid in source_ids:
                out["_status"][sid] = {"last_run": now_iso(), "status": "ok" if ok else "empty"}
            if not ok:
                problems.append(key)
            return val
        except Exception as exc:
            log("%s adapter crashed: %s" % (key, exc), "err")
            traceback.print_exc(file=sys.stderr)
            for sid in source_ids:
                out["_status"][sid] = {"last_run": now_iso(), "status": "error: %s" % exc}
            problems.append(key)
            return None

    run("nse", lambda: nse_src.collect(_aliases()),
        ["nse_market_status", "nse_all_indices", "nse_fii_dii", "nse_equity_master",
         "nse_circulars", "nse_cm_bhavcopy", "nse_live_quotes"])
    run("bse", lambda: bse_src.collect(wl.get("bse")),
        ["bse_delivery", "bse_corporate_actions", "bse_live_quotes"])
    run("mcx", lambda: mcx_src.collect(wl.get("mcx")), ["mcx_market_watch"])
    run("sebi", lambda: sebi_src.collect(max_pages=sebi_pages),
        ["sebi_stock_brokers", "sebi_commodity_brokers", "sebi_defaulter_brokers"])

    write_json(os.path.join(DATA, "_ingest.json"), out, compact=True)
    if problems:
        log("sources returning nothing: %s" % ", ".join(problems), "warn")
    return out, problems


def _refresh_quotes(ingest):
    """Live-quote legs only. Cheap enough for a minute-ly cron.

    MCX uses the 4.8KB heatmap, never the 1.28MB market-watch call - see
    config/stream.json for why that distinction matters.
    """
    wl = _watchlist()
    fn = nse_src.nse()
    ingest.setdefault("nse", {})["pulse"] = nse_src.market_pulse(fn, ttl=5)
    ingest["nse"]["live"] = nse_src.live_quotes(
        fn, ttl=5, want_active=True, want_gainers=True, want_losers=True)
    ingest.setdefault("bse", {})["live"] = bse_src.live_quotes(
        bse_src.bse(), wl.get("bse"), ttl=5)
    ingest.setdefault("mcx", {})["quotes"] = mcx_src.heatmap(
        symbols=wl.get("mcx"), ttl=5)
    return ingest


def ticker():
    ingest = read_json(os.path.join(DATA, "_ingest.json"), {}) or {}
    ingest = _refresh_quotes(ingest)
    write_json(os.path.join(DATA, "_ingest.json"), ingest, compact=True)
    publish.build_ticker()


def pulse():
    """Market strip + quotes, then a full republish so aggregates stay in step."""
    ingest = read_json(os.path.join(DATA, "_ingest.json"), {}) or {}
    ingest = _refresh_quotes(ingest)
    ingest.setdefault("bse", {})["corporate_actions"] = bse_src.corporate_actions(bse_src.bse())
    write_json(os.path.join(DATA, "_ingest.json"), ingest, compact=True)
    publish.build()
    log("pulse refreshed", "ok")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "all"
    pages = int(os.environ.get("SEBI_MAX_PAGES", "0")) or None

    if cmd == "seed":
        seed_sample.build()
        return 0
    if cmd == "fetch":
        _, problems = fetch(pages)
        return 1 if problems else 0
    if cmd == "build":
        publish.build()
        return 0
    if cmd == "ticker":
        ticker()
        return 0
    if cmd == "pulse":
        pulse()
        return 0
    if cmd == "all":
        _, problems = fetch(pages)
        publish.build()
        log("done. %s" % ("with gaps: " + ", ".join(problems) if problems else "all sources ok"),
            "warn" if problems else "ok")
        return 1 if problems else 0

    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
