"""Pipeline CLI.

  python3 -m pipeline.run seed             write clearly-labelled SAMPLE data
  python3 -m pipeline.run fetch            pull NSE + BSE + MCX + SEBI into data/ (+ _ingest.json)
  python3 -m pipeline.run build            recompute metrics and publish site/data/*
  python3 -m pipeline.run all              fetch + build
  python3 -m pipeline.run pulse            refresh market strip + live quotes, then full rebuild
  python3 -m pipeline.run ticker           refresh ONLY live quotes -> ticker.json (cheapest; run every minute)
  python3 -m pipeline.run branches         generate broker branch directory
  python3 -m pipeline.run ipo-apply        generate IPO how-to-apply and allotment guides
  python3 -m pipeline.run ipo-subscription generate IPO live bidding and subscription hubs
  python3 -m pipeline.run trade-costs      generate stock x broker transaction cost breakdown
  python3 -m pipeline.run sip              generate SIP compounding calculator suites
  python3 -m pipeline.run fund-compare     generate mutual fund 1v1 comparisons
  python3 -m pipeline.run stock-compare    generate stock 1v1 comparisons
  python3 -m pipeline.run engines          run all programmatic engines
  python3 -m pipeline.run report1c         pull NSE's own broker-wise active-clients report

Exit code is non-zero if a source that was expected to return rows returned
none, so cron can alert instead of silently publishing a hollow site.
"""
from __future__ import annotations

import os
import sys
import traceback

from . import publish, seed_sample
from . import common
from .common import CONFIG, DATA, MANUAL, log, now_iso, read_json, write_json
from .identity import Resolver
from .sources import amfi as amfi_src
from .sources import bse as bse_src
from .sources import crypto as crypto_src
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
    "amfi": ["schemes"],
    "crypto": ["coins"],
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
    common.reset_stale_tracking()

    def run(key, fn, source_ids):
        before_stale = common.stale_fetcher_names()
        try:
            val = fn()
            out[key] = val
            missing = _shortfalls(key, val)
            ok = bool(val) and not missing
            status = "ok" if ok else ("empty: %s" % ", ".join(missing) if missing else "empty")
            # A Fetcher that fell back to a stale cache still returns a
            # structurally-valid, non-empty result - without this, a 1-3 day
            # old cached body is published exactly like a true live fetch,
            # with no trace beyond a single stderr log line during the run.
            new_stale = common.stale_fetcher_names() - before_stale
            for sid in source_ids:
                out["_status"][sid] = {"last_run": now_iso(), "status": status}
                if new_stale:
                    out["_status"][sid]["stale"] = True
            if new_stale:
                log("%s served stale cached data for: %s" % (key, ", ".join(sorted(new_stale))), "warn")
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
    run("amfi", lambda: amfi_src.collect(), ["amfi_nav_master"])
    run("crypto", lambda: crypto_src.collect(), ["binance_prices", "coingecko_markets"])

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
    # Crypto price-only refresh: cheap (one request), skips the slower-moving
    # CoinGecko identity/supply facts a full fetch() call pulls. Binance is
    # tried first but is geo-blocked (HTTP 451) from every automated
    # environment this runs in (Vercel and GitHub Actions are both
    # US-hosted) - CoinGecko's markets endpoint is the real fallback, not a
    # rare edge case, so it's only skipped when Binance actually answers.
    fcx = crypto_src.crypto()
    prices = crypto_src.binance_prices(fcx, ttl=5)
    coins = ingest.get("crypto", {}).get("coins") or []
    if any(c["symbol"] not in prices for c in coins):
        cg_prices = crypto_src.coingecko_prices(fcx, ttl=60)
    else:
        cg_prices = {}
    for c in coins:
        sym = c["symbol"]
        if sym in prices:
            c.update(prices[sym])
            c["price_source"] = "binance"
        elif sym in cg_prices:
            c.update(cg_prices[sym])
            c["price_source"] = "coingecko"
    ingest.setdefault("crypto", {})["coins"] = coins
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


def _merge_exchange_totals(existing, as_of, total):
    """NSE's exchange-wide active clients by month, the denominator for every
    market share (see publish._market_totals). Accumulated like each broker's
    series: only on top of a prior real run, never the sample file. A month
    whose total was not parsed is left out rather than stored as a gap."""
    totals = dict(existing.get("exchange_active_clients") or {}) if existing.get("provenance") == "nse_ucc" else {}
    if isinstance(total, int) and total > 0:
        totals[as_of] = total
    return dict(sorted(totals.items()))


def report1c():
    """Pull NSE's own Report 1C and fold real active-client counts into
    data/manual/active_clients.json, under provenance:"nse_ucc" - the real
    source that field's existing "sample" placeholder was always meant to
    be replaced by (see that file's own source_note). Matching a broker
    name to a tracked id is NOT an adverse attribution (unlike the
    defaulter flag below), so the ordinary fuzzy resolver is fine here;
    only the DEFAULTER column gets the strict, exact-match-only treatment
    defamation-risk data always gets in this codebase.

    Each run adds one more real monthly data point for every tracked
    broker NSE's own file names - it does not invent history, so trend
    figures (month-over-month, year-over-year) only become real once
    enough real months have accumulated this way.
    """
    from .sources import nse_report1c

    data = nse_report1c.collect(common.nse_archives())
    if not data:
        log("report1c: nothing parsed; leaving the existing file untouched", "err")
        return 1

    master = read_json(os.path.join(CONFIG, "brokers_master.json"), {})
    resolver = Resolver(master.get("brokers", []))

    existing = read_json(os.path.join(MANUAL, "active_clients.json"), {}) or {}
    # Only accumulate on top of a PRIOR real run of this same function - never
    # on top of the sample-provenance placeholder file. That file's series
    # are fabricated per-month figures invented to look like a real trend;
    # carrying them forward under provenance:"nse_ucc" would publish fake
    # history as if NSE itself had reported it.
    brokers = dict(existing.get("brokers") or {}) if existing.get("provenance") == "nse_ucc" else {}
    as_of = data["as_of"]
    matched, unmatched = 0, 0
    defaulters = {}
    for row in data["rows"]:
        bid, _method, _score = resolver.resolve(row["name"])
        if not bid:
            unmatched += 1
            continue
        matched += 1
        series = {m: v for m, v in brokers.get(bid, [])}
        series[as_of] = row["active_clients"]
        brokers[bid] = sorted(series.items())
        if row["defaulter"]:
            strict_bid, _m, _s = resolver.resolve(row["name"], strict=True)
            if strict_bid == bid:
                defaulters[bid] = row["name"]

    if not matched:
        log("report1c: fetched %d real rows but matched none of them to a tracked broker"
            % len(data["rows"]), "err")
        return 1

    months = sorted({m for series in brokers.values() for m, _v in series})
    payload = {
        "provenance": "nse_ucc",
        "unit": "clients",
        "months": months,
        "source_note": ("NSE's own Report 1C (broker-wise active clients), pulled monthly. "
                        "A broker's history here only covers the months this pipeline has "
                        "actually run since - NSE itself keeps no public monthly archive."),
        "exchange_active_clients": _merge_exchange_totals(existing, as_of, data.get("exchange_active_clients")),
        "generated_at": now_iso(),
        "brokers": brokers,
    }
    if defaulters:
        payload["defaulters_this_run"] = defaulters
    write_json(os.path.join(MANUAL, "active_clients.json"), payload)
    log("report1c: matched %d of %d real trading members to tracked brokers (%d unmatched, "
        "expected - most of NSE's 263 members aren't brokers this site tracks); as of %s"
        % (matched, len(data["rows"]), unmatched, as_of), "ok")
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
    if cmd == "build":
        publish.build()
        return 0
    if cmd == "ticker":
        ticker()
        return 0
    if cmd == "complaints":
        return complaints()
    if cmd == "report1c":
        return report1c()
    if cmd == "pulse":
        pulse()
        return 0
    if cmd == "all":
        _, problems = fetch(pages)
        publish.build()
        log("done. %s" % ("with gaps: " + ", ".join(problems) if problems else "all sources ok"),
            "warn" if problems else "ok")
        return 1 if problems else 0
    if cmd == "branches":
        from . import broker_branch_engine
        broker_branch_engine.generate_all()
        return 0
    if cmd == "ipo-apply":
        from . import ipo_apply_engine
        ipo_apply_engine.build_ipo_apply_suite()
        return 0
    if cmd == "ipo-subscription":
        from . import ipo_subscription_engine
        ipo_subscription_engine.build_ipo_subscription_suite()
        return 0
    if cmd == "trade-costs":
        from . import trade_cost_engine
        trade_cost_engine.build_trade_cost_pages()
        return 0
    if cmd == "sip":
        from . import sip_calculator_engine
        sip_calculator_engine.build_sip_calculator_suite()
        return 0
    if cmd == "fund-compare":
        from . import fund_compare_engine
        fund_compare_engine.generate_all()
        return 0
    if cmd == "stock-compare":
        from . import stock_compare_engine
        stock_compare_engine.build_stock_compare_suite()
        return 0
    if cmd == "engines":
        from . import (
            broker_branch_engine,
            fund_compare_engine,
            ipo_apply_engine,
            ipo_subscription_engine,
            sip_calculator_engine,
            stock_compare_engine,
            trade_cost_engine,
        )
        log("running all programmatic engines...", "info")
        broker_branch_engine.generate_all()
        ipo_apply_engine.build_ipo_apply_suite()
        ipo_subscription_engine.build_ipo_subscription_suite()
        trade_cost_engine.build_trade_cost_pages()
        sip_calculator_engine.build_sip_calculator_suite()
        fund_compare_engine.generate_all()
        stock_compare_engine.build_stock_compare_suite()
        log("all programmatic engines completed successfully", "ok")
        return 0

    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
