"""MCX adapter — live commodity futures quotes.

VERIFIED WORKING 2026-07-30. Two things had to be right:

1. **The endpoint.** MCX's market-watch page loads data through a generic helper
   in /assets/customjs/data.js:

       url = location.origin + location.pathname + MethodName

   so the real call is a **GET** to

       /market-data/market-watch/GetMarketWatch?culture=en

   not a POST to /backpage.aspx/GetMarketWatch. That path returns MCX's 404 page
   with a 200 status, which is easy to mistake for a working endpoint.

2. **The headers.** Akamai Bot Manager fronts mcxindia.com and scores requests on
   client hints and Sec-Fetch metadata. With only a User-Agent it returns
   403 Access Denied; with the full Chrome set (sec-ch-ua, sec-ch-ua-platform,
   Sec-Fetch-*) it returns data. Handled centrally in common.Fetcher.

   The HTML page still 403s from a plain client while the JSON endpoint answers,
   so warm-up failure is expected and harmless — do not treat it as fatal.

Returns 2,238 contracts, of which ~112 are FUTCOM (futures); the rest are
OPTFUT (options). Only futures are surfaced, one contract per product, choosing
the most-traded expiry because that is the liquid one a reader would recognise.
"""
from __future__ import annotations

import json
import re

from ..common import Fetcher, log, to_num

BASE = "https://www.mcxindia.com"
PAGE = BASE + "/market-data/market-watch"
WATCH = PAGE + "/GetMarketWatch?culture=en"

# Light endpoints for the fast loop. Same origin and header requirements, but the
# heatmap carries the 16 major futures (GOLD, SILVER, CRUDEOIL, NATURALGAS,
# COPPER, ZINC, ALUMINIUM, LEAD, NICKEL, MENTHAOIL + mini/petal variants) with
# LTP, OHLC, volume and open interest in 4,795 bytes - versus 1,277,049 bytes for
# GetMarketWatch, which returns the entire option chain uncompressed.
#
# Note the response shape differs: the heatmap returns {Summary, Data} at the top
# level, while GetMarketWatch nests it under {data: {Summary, Data}}.
HEATMAP_PAGE = BASE + "/market-data/heatmap"
HEATMAP = HEATMAP_PAGE + "/GetTopHeatMap"
GAINERS_PAGE = BASE + "/market-data/top-gainers"
GAINERS = GAINERS_PAGE + "/GetTopGainers"

# .NET serialises as /Date(millis)/ or /Date(millis+0530)/ — the offset is optional.
_DOTNET_DATE = re.compile(r"/Date\((-?\d+)(?:[+-]\d{4})?\)/")


def fetcher():
    return Fetcher("mcx", referer=PAGE, warm_urls=[PAGE], timeout=40)


def _as_on(summary):
    """MCX serialises timestamps as ASP.NET /Date(millis)/."""
    raw = (summary or {}).get("AsOn")
    m = _DOTNET_DATE.search(str(raw or ""))
    if not m:
        return None
    ms = int(m.group(1))
    if ms <= 0:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds")


def live_quotes(f: Fetcher = None, symbols=None):
    f = f or fetcher()
    out = {"exchange": "MCX", "quotes": [], "as_of": None, "note": None}
    wanted = {s.upper() for s in (symbols or [])}

    # MCX's own call is a jQuery $.ajax with contentType "application/json" and
    # the X-Requested-With header. Akamai checks for both: without them the same
    # URL returns 403 even with correct client hints.
    payload = f.get_json(
        WATCH,
        ttl=45,
        retries=2,
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": PAGE,
        },
    )
    if not payload:
        out["note"] = "MCX did not respond on this run."
        log("mcx: no response", "warn")
        return out

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            out["note"] = "MCX response was not JSON."
            return out

    data = payload.get("data") if isinstance(payload, dict) else None
    rows = (data or {}).get("Data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        out["note"] = "MCX response had no row list."
        log("mcx: unexpected shape", "warn")
        return out

    out["as_of"] = _as_on((data or {}).get("Summary"))

    # Futures only, and keep the most-traded expiry per product.
    best = {}
    for r in rows:
        if not isinstance(r, dict) or r.get("InstrumentName") != "FUTCOM":
            continue
        product = (r.get("ProductCode") or "").strip().upper()
        if not product or (wanted and product not in wanted):
            continue
        last = to_num(r.get("LTP"))
        if not last:  # 0.0 means the contract has not traded
            continue
        vol = to_num(r.get("Volume")) or 0
        cur = best.get(product)
        if cur is None or vol > cur["_vol"]:
            best[product] = {
                "symbol": product,
                "expiry": r.get("ExpiryDate"),
                "unit": r.get("Unit"),
                "last": last,
                "change": to_num(r.get("AbsoluteChange")),
                "change_pct": to_num(r.get("PercentChange")),
                "volume": vol,
                "open_interest": to_num(r.get("OpenInterest")),
                "high": to_num(r.get("High")),
                "low": to_num(r.get("Low")),
                "last_traded": r.get("LTTValue"),
                "_vol": vol,
            }

    # Watchlist order first (so GOLD/SILVER/CRUDEOIL lead the ticker), then the
    # rest alphabetically.
    wl = [s.upper() for s in (symbols or [])]
    order = [s for s in wl if s in best] + sorted(k for k in best if k not in set(wl))
    out["quotes"] = [{k: v for k, v in best[s].items() if k != "_vol"} for s in order]

    if not out["quotes"]:
        out["note"] = "MCX responded but no matching traded futures were found."
    log("mcx live quotes: %d products (of %d rows)" % (len(out["quotes"]), len(rows)),
        "ok" if out["quotes"] else "warn")
    return out


_XHR = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}


def _rows(payload):
    """Both shapes: {Summary,Data} and {data:{Summary,Data}}."""
    if not isinstance(payload, dict):
        return [], None
    inner = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    rows = inner.get("Data")
    return (rows if isinstance(rows, list) else []), _as_on(inner.get("Summary"))


def heatmap(f: Fetcher = None, symbols=None, ttl=1, retries=2):
    """The fast MCX loop: 16 major futures in ~4.8KB.

    This is what makes MCX viable at a 1s cadence. Prefer it over live_quotes()
    for anything on a hot path - pass retries=1 there.

    Default is 2, not 1: the only current caller is the one-shot build/ticker
    refresh (run.py), not a hot loop, and Akamai's bot-scoring on this endpoint
    is probabilistic - a request that gets blocked once often succeeds on an
    immediate retry (confirmed by hand: a failed run followed seconds later by
    a clean 200). With retries=1 a single blocked request meant MCX showed zero
    instruments for an entire Vercel deployment's lifetime, since a fresh build
    has no prior cache to fall back on.
    """
    f = f or fetcher()
    out = {"exchange": "MCX", "quotes": [], "as_of": None, "note": None}
    payload = f.get_json(HEATMAP, ttl=ttl, retries=retries,
                         headers=dict(_XHR, Referer=HEATMAP_PAGE))
    if not payload:
        out["note"] = "MCX heatmap did not respond."
        return out

    rows, as_on = _rows(payload)
    out["as_of"] = as_on
    wanted = {s.upper() for s in (symbols or [])}

    got = {}
    for r in rows:
        sym = str(r.get("Symbol") or "").strip().upper()
        last = to_num(r.get("LTP"))
        if not sym or not last:
            continue
        got[sym] = {
            "symbol": sym,
            "expiry": r.get("ExpiryDate"),
            "last": last,
            "change": to_num(r.get("AbsoluteChange")),
            "change_pct": to_num(r.get("PercentChange")),
            "volume": to_num(r.get("TotalQtyTraded")),
            "open_interest": to_num(r.get("OpenInterest")),
            "high": to_num(r.get("High")),
            "low": to_num(r.get("Low")),
            "open": to_num(r.get("Open")),
        }

    # Watchlist order first so GOLD/SILVER/CRUDEOIL lead, then whatever else traded.
    wl = [s.upper() for s in (symbols or [])]
    order = [s for s in wl if s in got] + sorted(k for k in got if k not in set(wl))
    out["quotes"] = [got[s] for s in order]
    if not out["quotes"]:
        out["note"] = "MCX heatmap returned no traded futures."
    return out


def top_gainers(f: Fetcher = None, ttl=2):
    """~1.9KB. Second band for the ticker."""
    f = f or fetcher()
    payload = f.get_json(GAINERS, ttl=ttl, retries=1,
                         headers=dict(_XHR, Referer=GAINERS_PAGE))
    rows, as_on = _rows(payload)
    out = []
    for r in rows:
        sym = str(r.get("Symbol") or r.get("EngSymbol") or "").strip().upper()
        last = to_num(r.get("LTP"))
        if not sym or not last:
            continue
        out.append({
            "symbol": sym,
            "expiry": r.get("ExpiryDate"),
            "last": last,
            "change": to_num(r.get("AbsoluteChange")),
            "change_pct": to_num(r.get("PercentChange")),
        })
    return {"quotes": out, "as_of": as_on}


def collect(symbols=None):
    """Pipeline-level collect: light heatmap for prices, full watch for coverage."""
    f = fetcher()
    light = heatmap(f, symbols, ttl=45)
    if not light.get("quotes"):
        # fall back to the heavy call rather than publishing an empty MCX tab
        light = live_quotes(f, symbols)
    return {"quotes": light, "gainers": top_gainers(f, ttl=45), "full": live_quotes(f, symbols)}
