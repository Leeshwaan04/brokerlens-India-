"""Assembles the ticker feeds that populate the header dropdown.

One place defines what feeds exist, in what order, and what each contains, so the
pipeline and the live stream cannot drift apart.

Feeds are deliberately instrument-only - every row is a tradable thing with a
price. Market breadth, delivery percentage and the site's own aggregates live on
the pages that explain them, not in a price strip.
"""
from __future__ import annotations

import os

from .common import CONFIG, log, read_json
from .sources import bse as bse_src

# id -> (label, kind, exchange-for-session-status)
FEED_DEFS = [
    ("NSE",      "NSE most active",  "exchange", "NSE"),
    ("BSE",      "BSE watchlist",    "exchange", "BSE"),
    ("MCX",      "MCX commodities",  "exchange", "MCX"),
    ("INDICES",  "Indices",          "derived",  "NSE"),
    ("GAINERS",  "Top gainers",      "derived",  "NSE"),
    ("LOSERS",   "Top losers",       "derived",  "NSE"),
    ("BROKERS",  "Broker stocks",    "derived",  "BSE"),
]

FEED_ORDER = [f[0] for f in FEED_DEFS]
FEED_META = {f[0]: {"label": f[1], "kind": f[2], "exchange": f[3]} for f in FEED_DEFS}


def empty_feeds():
    return {
        fid: {"id": fid, "label": m["label"], "kind": m["kind"], "exchange": m["exchange"],
              "status": None, "as_of": None, "instruments": [], "note": None}
        for fid, m in FEED_META.items()
    }


def broker_stock_defs():
    cfg = read_json(os.path.join(CONFIG, "broker_stocks.json"), {}) or {}
    return cfg.get("stocks") or []


def broker_stocks(f=None, ttl=45):
    """Quote the listed brokers and broker parents via BSE.

    Each row keeps `broker_id` so the ticker can link straight to that broker's
    profile, and `relation` so a parent company is never presented as the broker
    itself.
    """
    defs = broker_stock_defs()
    if not defs:
        return [], "no broker stocks configured"
    f = f or bse_src.bse()
    watch = [{"scrip": d["bse_scrip"], "label": d["symbol"]} for d in defs]
    res = bse_src.live_quotes(f, watch, ttl=ttl)
    by_sym = {q["symbol"]: q for q in (res.get("quotes") or [])}

    out = []
    for d in defs:
        q = by_sym.get(d["symbol"])
        if not q:
            continue
        out.append({
            "symbol": d["symbol"],
            "name": d.get("label") or q.get("name"),
            "last": q.get("last"),
            "change": q.get("change"),
            "change_pct": q.get("change_pct"),
            "broker_id": d.get("broker_id"),
            "relation": d.get("relation"),
        })
    note = None if out else "BSE returned no broker-stock quotes"
    log("broker stocks: %d of %d quoted" % (len(out), len(defs)), "ok" if out else "warn")
    return out, note


def build(ingest, include_broker_stocks=True):
    """Assemble every feed from an ingest payload."""
    feeds = empty_feeds()
    nse_d = ingest.get("nse") or {}
    bse_d = ingest.get("bse") or {}
    mcx_d = ingest.get("mcx") or {}
    pulse = nse_d.get("pulse") or {}
    nse_live = nse_d.get("live") or {}

    # session status, from NSE's own marketStatus
    status = {}
    for s in pulse.get("status") or []:
        mk = (s.get("market") or "").lower()
        if "capital" in mk:
            status["NSE"] = s.get("status")
        elif "commodity" in mk:
            status["MCX"] = s.get("status")
    status.setdefault("BSE", status.get("NSE"))
    for fid, meta in FEED_META.items():
        feeds[fid]["status"] = status.get(meta["exchange"])

    feeds["NSE"]["instruments"] = nse_live.get("quotes") or []
    feeds["NSE"]["as_of"] = nse_live.get("timestamp")
    feeds["NSE"]["note"] = nse_live.get("note")

    bse_live = bse_d.get("live") or {}
    feeds["BSE"]["instruments"] = bse_live.get("quotes") or []
    feeds["BSE"]["note"] = bse_live.get("note")

    mcx_live = mcx_d.get("quotes") or {}
    feeds["MCX"]["instruments"] = mcx_live.get("quotes") or []
    feeds["MCX"]["as_of"] = mcx_live.get("as_of")
    feeds["MCX"]["note"] = mcx_live.get("note")

    feeds["INDICES"]["instruments"] = [
        dict(i, symbol=i.get("name")) for i in (pulse.get("indices") or [])
    ]

    feeds["GAINERS"]["instruments"] = nse_live.get("gainers") or []
    feeds["LOSERS"]["instruments"] = nse_live.get("losers") or []

    if include_broker_stocks:
        rows, note = broker_stocks()
        feeds["BROKERS"]["instruments"] = rows
        feeds["BROKERS"]["note"] = note
    return feeds
