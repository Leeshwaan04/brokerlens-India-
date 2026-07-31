"""NSE adapters.

NSE gates its /api/ paths behind cookies issued by an HTML page load, which the
Fetcher handles. Archive files on nsearchives.nseindia.com are ungated.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone

from ..common import (
    Fetcher,
    log,
    nse,
    nse_archives,
    snapshot,
    strip_tags,
    to_num,
)

API = "https://www.nseindia.com/api"
ARCH = "https://nsearchives.nseindia.com"


def market_pulse(f: Fetcher, ttl=None):
    """Live-ish market context for the site header. Cheap, safe to poll."""
    out = {"exchange": "NSE", "status": None, "indices": [], "breadth": None}

    ms = f.get_json("%s/marketStatus" % API, ttl=60 if ttl is None else ttl)
    if ms:
        segs = []
        for s in ms.get("marketState", []) or []:
            segs.append(
                {
                    "market": s.get("market"),
                    "status": s.get("marketStatus"),
                    "index": s.get("index"),
                    "last": to_num(s.get("last")),
                    "change": to_num(s.get("variation")),
                    "change_pct": to_num(s.get("percentChange")),
                    "trade_date": s.get("tradeDate"),
                }
            )
        out["status"] = segs

    ai = f.get_json("%s/allIndices" % API, ttl=120 if ttl is None else ttl)
    if ai:
        want = {
            "NIFTY 50", "NIFTY NEXT 50", "NIFTY BANK", "NIFTY FIN SERVICE",
            "NIFTY MIDCAP 100", "NIFTY SMLCAP 100", "INDIA VIX",
            "NIFTY IT", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY FMCG",
            "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY", "NIFTY PSU BANK",
            "NIFTY 100", "NIFTY 500",
        }
        adv = dec = unc = 0
        for idx in ai.get("data", []) or []:
            name = (idx.get("index") or "").upper()
            adv += to_num(idx.get("advances")) or 0
            dec += to_num(idx.get("declines")) or 0
            unc += to_num(idx.get("unchanged")) or 0
            if name in want:
                out["indices"].append(
                    {
                        "name": idx.get("index"),
                        "last": to_num(idx.get("last")),
                        "change": to_num(idx.get("variation")),
                        "change_pct": to_num(idx.get("percentChange")),
                        "open": to_num(idx.get("open")),
                        "high": to_num(idx.get("high")),
                        "low": to_num(idx.get("low")),
                        "year_high": to_num(idx.get("yearHigh")),
                        "year_low": to_num(idx.get("yearLow")),
                    }
                )
        # NIFTY 50 first, then by name, so the header order is stable
        out["indices"].sort(key=lambda i: (i["name"] != "NIFTY 50", i["name"] or ""))
        if adv or dec:
            out["breadth"] = {"advances": adv, "declines": dec, "unchanged": unc}

    snapshot("nse_market_pulse", out)
    return out


LIVE_REFERER = {"Referer": "https://www.nseindia.com/market-data/live-equity-market"}
VAR_REFERER = {"Referer": "https://www.nseindia.com/market-data/top-gainers-losers"}


def _variation(f: Fetcher, index, ttl=45, limit=15):
    """Top gainers / losers.

    NSE spells the losers parameter "loosers" - `?index=losers` returns an empty
    52-byte stub, which is easy to mistake for "no movers today".
    """
    data = f.get_json("%s/live-analysis-variations?index=%s" % (API, index),
                      ttl=ttl, headers=VAR_REFERER)
    if not isinstance(data, dict):
        return []
    grp = data.get("NIFTY") or data.get("allSec") or data.get("SecGtr20") or {}
    out = []
    for r in (grp.get("data") or [])[:limit]:
        ltp, prev = to_num(r.get("ltp")), to_num(r.get("prev_price"))
        out.append({
            "symbol": r.get("symbol"),
            "last": ltp,
            "change_pct": to_num(r.get("perChange")),
            "change": (ltp - prev) if ltp is not None and prev is not None else None,
            "volume": to_num(r.get("trade_quantity")),
        })
    return [q for q in out if q["symbol"] and q["last"] is not None]


def most_active(f: Fetcher, by="volume", ttl=45):
    data = f.get_json("%s/live-analysis-most-active-securities?index=%s" % (API, by),
                      ttl=ttl, headers=LIVE_REFERER)
    out, stamp = [], None
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        stamp = data.get("timestamp")
        for r in data["data"]:
            if not r.get("symbol"):
                continue
            out.append({
                "symbol": r.get("symbol"),
                "last": to_num(r.get("lastPrice")),
                "change": to_num(r.get("change")),
                "change_pct": to_num(r.get("pChange")),
                "volume": to_num(r.get("totalTradedVolume")),
                "high": to_num(r.get("dayHigh")),
                "low": to_num(r.get("dayLow")),
            })
    return out, stamp


def live_quotes(f: Fetcher, ttl=45, want_active=True, want_gainers=True, want_losers=False):
    """Live equity quotes for the ticker.

    /api/equity-stockIndices 404s and /api/quote-equity 403s even with full
    browser client hints, but the live-analysis endpoints answer with a warmed
    session and carry exactly what a ticker needs.

    The selector flags exist so the stream poller can hit one endpoint per tick
    at its own cadence instead of refetching everything.
    """
    out = {"exchange": "NSE", "quotes": [], "gainers": [], "losers": [],
           "timestamp": None, "note": None}

    if want_active:
        out["quotes"], out["timestamp"] = most_active(f, "volume", ttl=ttl)
    if want_gainers:
        out["gainers"] = _variation(f, "gainers", ttl=ttl)
    if want_losers:
        out["losers"] = _variation(f, "loosers", ttl=ttl)

    if want_active and not out["quotes"]:
        out["note"] = "NSE live-analysis endpoints returned nothing on this run."
    log("nse live: %d active, %d gainers, %d losers"
        % (len(out["quotes"]), len(out["gainers"]), len(out["losers"])),
        "ok" if (out["quotes"] or out["gainers"] or out["losers"]) else "warn")
    return out


def fii_dii(f: Fetcher):
    """Daily institutional flows - the macro context strip."""
    data = f.get_json("%s/fiidiiTradeReact" % API, ttl=3600)
    if not data:
        return None
    rows = []
    for r in data if isinstance(data, list) else []:
        rows.append(
            {
                "category": r.get("category"),
                "date": r.get("date"),
                "buy": to_num(r.get("buyValue")),
                "sell": to_num(r.get("sellValue")),
                "net": to_num(r.get("netValue")),
            }
        )
    snapshot("nse_fii_dii", rows)
    return rows


def equity_universe(fa: Fetcher):
    """Count of tradable equity symbols + the listed brokers among them."""
    text = fa.get_text("%s/content/equities/EQUITY_L.csv" % ARCH, ttl=86400)
    if not text:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    key = None
    for k in (rows[0].keys() if rows else []):
        if k.strip().upper() == "NAME OF COMPANY":
            key = k
            break
    names = [(r.get(key) or "").strip() for r in rows] if key else []
    out = {"symbol_count": len(rows), "company_names": names}
    snapshot("nse_equity_universe", {"symbol_count": len(rows)})
    return out


def member_circulars(f: Fetcher, broker_aliases):
    """Scan NSE's circular feed for member-name mentions.

    Circulars naming a specific trading member are usually disciplinary
    (penalty, suspension, non-compliance). Surfacing them is a genuine
    differentiator - nobody else puts this next to the marketing copy.
    """
    data = f.get_json("%s/circulars" % API, ttl=6 * 3600)
    if not data:
        return {}

    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}

    hits = {}
    for c in items:
        # field names per the live payload: sub, circCategory, circCompany,
        # circDepartment, circDisplayNo, circFilelink
        blob = " ".join(
            str(c.get(k) or "")
            for k in ("sub", "circCompany", "circCategory", "circDepartment", "circDisplayNo")
        ).lower()
        if not blob.strip():
            continue
        for bid, aliases in broker_aliases.items():
            for a in aliases:
                if len(a) >= 6 and a in blob:
                    hits.setdefault(bid, []).append(
                        {
                            "date": c.get("cirDisplayDate") or c.get("cirDate"),
                            "subject": strip_tags(c.get("sub"))[:220],
                            "category": c.get("circCategory"),
                            "department": c.get("circDepartment"),
                            "ref": c.get("circDisplayNo"),
                            "url": c.get("circFilelink"),
                        }
                    )
                    break
    for bid in hits:
        hits[bid] = hits[bid][:10]
    snapshot("nse_member_circulars", hits)
    log("nse circulars: %d brokers mentioned across %d circulars" % (len(hits), len(items)))
    return hits


def cm_turnover(fa: Fetcher, days_back=7):
    """Market-wide CM turnover for the last N trading days, from bhavcopy."""
    series = []
    day = datetime.now(timezone.utc).date()
    tried = 0
    while len(series) < days_back and tried < days_back * 3:
        tried += 1
        day = day - timedelta(days=1)
        if day.weekday() >= 5:
            continue
        stamp = day.strftime("%Y%m%d")
        url = "%s/content/cm/BhavCopy_NSE_CM_0_0_0_%s_F_0000.csv.zip" % (ARCH, stamp)
        text = fa.get_zip_member(url, ttl=7 * 86400, retries=1)
        if not text:
            continue
        turnover = 0.0
        trades = 0
        rows = 0
        for r in csv.DictReader(io.StringIO(text)):
            rows += 1
            turnover += to_num(r.get("TtlTrfVal")) or 0
            trades += to_num(r.get("TtlNbOfTxsExctd")) or 0
        series.append(
            {
                "date": day.isoformat(),
                "turnover_inr": turnover,
                "trades": trades,
                "instruments": rows,
            }
        )
    series.sort(key=lambda r: r["date"])
    if series:
        snapshot("nse_cm_turnover", series)
    return series


def collect(broker_aliases):
    f = nse()
    fa = nse_archives()
    out = {
        "pulse": market_pulse(f),
        "live": live_quotes(f),
        "fii_dii": fii_dii(f),
        "universe": equity_universe(fa),
        "circulars": member_circulars(f, broker_aliases),
        "turnover": cm_turnover(fa),
    }
    return out
