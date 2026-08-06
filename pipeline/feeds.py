"""Assembles the ticker feeds that populate the header dropdown.

One place defines what feeds exist, in what order, and what each contains, so the
pipeline and the live stream cannot drift apart.

Feeds are deliberately instrument-only - every row is a tradable thing with a
price. Market breadth, delivery percentage and the site's own aggregates live on
the pages that explain them, not in a price strip.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from .common import CONFIG, read_json

IST = timezone(timedelta(hours=5, minutes=30))


def _session_status(exchange_id):
    """Open/Closed for an exchange, computed from its published session hours.

    MCX status used to be copied from NSE's marketStatus payload, matching on
    the word "commodity". That is NSE's OWN commodity segment, a different
    market with different hours, so MCX showed "Closed" at 3pm on a Monday while
    it was very much trading (MCX runs to 23:30). BSE was copying NSE outright.

    config/market_timings.json is the same source the Market timings menu uses,
    so the strip and the menu can no longer disagree. Exchange holidays are the
    known gap: those come from yearly circulars we do not ingest yet, so an NSE
    API status is still preferred for NSE where it is available.
    """
    cfg = read_json(os.path.join(CONFIG, "market_timings.json"), {}) or {}
    ex = next((e for e in cfg.get("exchanges") or [] if e.get("id") == exchange_id), None)
    if not ex:
        return None
    now = datetime.now(IST)
    if now.weekday() >= 5:                       # Sat/Sun
        return "Closed"
    minutes = now.hour * 60 + now.minute

    def to_min(hhmm):
        try:
            h, m = str(hhmm).split(":")
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return None

    for seg in ex.get("segments") or []:
        for sess in seg.get("sessions") or []:
            if sess.get("kind") != "normal":
                continue
            start, end = to_min(sess.get("start")), to_min(sess.get("end"))
            if start is None or end is None:
                continue
            if start <= minutes < end:
                return "Open"
    return "Closed"

# id -> (label, kind, exchange-for-session-status)
# One feed per exchange plus Indices: the dropdown stays NSE / BSE / MCX / Indices.
FEED_DEFS = [
    ("NSE",      "NSE",      "exchange", "NSE"),
    ("BSE",      "BSE",      "exchange", "BSE"),
    ("MCX",      "MCX",      "exchange", "MCX"),
    ("INDICES",  "Indices",  "derived",  "NSE"),
]

FEED_ORDER = [f[0] for f in FEED_DEFS]
FEED_META = {f[0]: {"label": f[1], "kind": f[2], "exchange": f[3]} for f in FEED_DEFS}


def empty_feeds():
    return {
        fid: {"id": fid, "label": m["label"], "kind": m["kind"], "exchange": m["exchange"],
              "status": None, "as_of": None, "instruments": [], "note": None}
        for fid, m in FEED_META.items()
    }


def build(ingest):
    """Assemble every feed from an ingest payload."""
    feeds = empty_feeds()
    nse_d = ingest.get("nse") or {}
    bse_d = ingest.get("bse") or {}
    mcx_d = ingest.get("mcx") or {}
    pulse = nse_d.get("pulse") or {}
    nse_live = nse_d.get("live") or {}

    # Session status. NSE's own marketStatus is authoritative for NSE because it
    # accounts for trading holidays; BSE keeps the same equity hours and holiday
    # calendar so it follows NSE. MCX is a separate market and must be computed
    # from its own published hours, never borrowed from NSE.
    status = {}
    for s in pulse.get("status") or []:
        mk = (s.get("market") or "").lower()
        if "capital" in mk:
            status["NSE"] = s.get("status")
    status.setdefault("NSE", _session_status("NSE"))
    status.setdefault("BSE", status.get("NSE"))
    status["MCX"] = _session_status("MCX")
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

    return feeds
