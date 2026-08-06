"""Pipeline CLI.

  python3 -m pipeline.run seed      write clearly-labelled SAMPLE data
  python3 -m pipeline.run fetch     pull NSE + BSE + MCX + SEBI into data/ (+ _ingest.json)
  python3 -m pipeline.run build     recompute metrics and publish site/data/*
  python3 -m pipeline.run all       fetch + build
  python3 -m pipeline.run pulse     refresh market strip + live quotes, then full rebuild
  python3 -m pipeline.run ticker    refresh ONLY live quotes -> ticker.json (cheapest; run every minute)
  python3 -m pipeline.run refetch-mcx  re-pull MCX quotes into data/_ingest.json (Vercel build retry)

Exit code is non-zero if a source that was expected to return rows returned
none, so cron can alert instead of silently publishing a hollow site.
"""
from __future__ import annotations

import os
import sys
import traceback

from . import publish, seed_sample
from .common import CONFIG, DATA, MANUAL, log, now_iso, read_json, write_json
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


# What each adapter must actually return for the run to count as a success.
# `bool(result)` was useless: every collect() returns a dict with fixed keys, so
# a total upstream blackout still evaluated True and the pipeline exited 0 with
# every source showing green. Each entry is a dotted path into the adapter's
# result that must be non-empty.
EXPECTED_ROWS = {
    "nse": ["pulse.indices", "live.quotes"],
    "bse": ["live.quotes"],
    "mcx": ["quotes.quotes"],
    "sebi": ["registry.commodity_broker", "defaulters"],
}


def _dig(obj, path):
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _shortfalls(key, val):
    """Paths that should have carried rows and did not."""
    missing = []
    for path in EXPECTED_ROWS.get(key, []):
        got = _dig(val, path) if isinstance(val, dict) else None
        if not got:
            missing.append(path)
    return missing


def fetch(sebi_pages=None):
    out = {"_status": {}, "fetched_at": now_iso()}
    problems = []
    wl = _watchlist()

    def run(key, fn, source_ids):
        try:
            val = fn()
            out[key] = val
            missing = _shortfalls(key, val)
            ok = bool(val) and not missing
            status = "ok" if ok else ("empty: %s" % ", ".join(missing) if missing else "empty")
            for sid in source_ids:
                out["_status"][sid] = {"last_run": now_iso(), "status": status}
            if not ok:
                log("%s returned no rows for: %s" % (key, ", ".join(missing) or "everything"), "err")
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


def complaints():
    """Crawl each broker's SEBI Annexure-B disclosure and write the real dataset.

    Writes data/manual/complaints.json with provenance:"sebi_annexure_b", which
    is the same slot the sample data occupies, so the site picks it up with no
    further changes. Brokers that could not be parsed simply get no record; they
    are listed in the run log and in the file's `gaps` block so the coverage is
    always visible rather than implied.
    """
    from .sources import complaints as complaints_src

    res = complaints_src.collect()
    brokers = res.get("brokers") or {}
    if not brokers:
        log("complaints: nothing parsed; leaving the existing file untouched", "err")
        return 1

    months = sorted({r["month"] for rows in brokers.values() for r in rows})
    payload = {
        "provenance": "sebi_annexure_b",
        "source_note": ("Parsed from each broker's own SEBI Annexure-B disclosure. "
                        "Brokers absent from this file did not publish a parseable "
                        "table; they are listed under `gaps`."),
        "generated_at": now_iso(),
        "months": months,
        "coverage": {"parsed": len(brokers), "attempted": res.get("attempted", 0)},
        "gaps": res.get("failures") or {},
        "brokers": brokers,
    }
    write_json(os.path.join(MANUAL, "complaints.json"), payload)
    log("complaints: wrote %d brokers across %d months (%s)"
        % (len(brokers), len(months), months[0] + " to " + months[-1] if months else "-"), "ok")
    return 0


def refetch_mcx():
    """Re-pull MCX quotes only. Used by Vercel build when the first fetch is blocked."""
    wl = _watchlist()
    ingest = read_json(os.path.join(DATA, "_ingest.json"), {}) or {}
    ingest.setdefault("mcx", {})["quotes"] = mcx_src.collect(wl.get("mcx")).get("quotes")
    write_json(os.path.join(DATA, "_ingest.json"), ingest, compact=True)
    n = len(_dig(ingest.get("mcx"), "quotes.quotes") or [])
    if not n:
        log("mcx refetch: still empty", "warn")
        return 1
    log("mcx refetch: %d instruments" % n, "ok")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "all"
    pages = int(os.environ.get("SEBI_MAX_PAGES", "0")) or None

    if cmd == "seed":
        seed_sample.build()
        return 0
    if cmd == "fetch":
        _, problems = fetch(pages)
        return 1 if problems else 0
    if cmd == "refetch-mcx":
        return refetch_mcx()
    if cmd == "build":
        publish.build()
        return 0
    if cmd == "ticker":
        ticker()
        return 0
    if cmd == "complaints":
        return complaints()
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
