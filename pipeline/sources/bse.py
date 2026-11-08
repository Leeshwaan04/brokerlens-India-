"""BSE adapters.

BSE's api.bseindia.com 302-redirects and drops requests without a Referer -
both handled by the shared Fetcher's bse() preset.

CORRECTION NOTE: /BSEDATA/gross/<yyyy>/SCBSEALL<ddmm>.zip is *scrip-wise*
delivery data (DATE|SCRIP CODE|DELIVERY QTY|DELIVERY VAL|DAY'S VOLUME|DAY'S
TURNOVER|DELV. PER.), not member-wise turnover. It is still worth ingesting -
market-wide delivery percentage is a genuine sentiment stat for the homepage -
but it says nothing about individual brokers, and is not used as one.

BSE does not appear to publish member-wise activity at a stable open endpoint.
Per-broker BSE presence therefore comes from the SEBI registry (which segments
a broker is registered for), not from turnover files.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone

from ..common import Fetcher, bse, log, snapshot, to_num

API = "https://api.bseindia.com/BseIndiaAPI/api"
WWW = "https://www.bseindia.com"


def live_quotes(f: Fetcher, watchlist, ttl=45):
    """Live BSE quotes, one request per scrip.

    getScripHeaderData is the only open BSE quote endpoint that works: it returns
    CurrRate{LTP, Chg, PcChg} plus Cmpname{FullN}. There is no bulk equivalent,
    which is why the watchlist is deliberately short - each entry costs a round
    trip on every ticker refresh.
    """
    out = {"exchange": "BSE", "quotes": [], "note": None}
    for item in watchlist or []:
        scrip = item.get("scrip")
        if not scrip:
            continue
        d = f.get_json(
            "%s/getScripHeaderData/w?Debtflag=&scripcode=%s&seriesid=" % (API, scrip),
            ttl=ttl, retries=1,
        )
        if not isinstance(d, dict):
            continue
        rate = d.get("CurrRate") or {}
        name = (d.get("Cmpname") or {}).get("FullN") or item.get("label")
        last = to_num(rate.get("LTP"))
        if last is None:
            continue
        out["quotes"].append({
            "symbol": item.get("label") or str(scrip),
            "name": (name or "").strip(),
            "scrip": scrip,
            "last": last,
            "change": to_num(rate.get("Chg")),
            "change_pct": to_num(rate.get("PcChg")),
        })
    if not out["quotes"]:
        out["note"] = "No BSE scrip quotes returned on this run."
    log("bse live quotes: %d of %d scrips" % (len(out["quotes"]), len(watchlist or [])),
        "ok" if out["quotes"] else "warn")
    return out


def corporate_actions(f: Fetcher, limit=40):
    """Upcoming ex-dates from BSE's DefaultData feed.

    CORRECTION NOTE: /api/DefaultData/w is a corporate-actions feed
    (scrip_code, short_name, Ex_date, Purpose, RD_Date, payment_date), not an
    index feed. Every plausible BSE index endpoint tried - SensexData,
    IndexMovement, MktRtrnData, GetIndexData, MarketWatchTable, Indexhighlight,
    MktCapitalisation - returns an error page. BSE does not appear to expose
    index levels openly, so index levels on the site come from NSE only and the
    BSE contribution is delivery statistics plus this actions calendar.
    """
    data = f.get_json("%s/DefaultData/w" % API, ttl=1800)
    if not isinstance(data, list):
        return []
    rows = []
    for r in data:
        if not isinstance(r, dict):
            continue
        rows.append({
            "scrip_code": r.get("scrip_code"),
            "symbol": r.get("short_name"),
            "company": r.get("long_name") or r.get("short_name"),
            "ex_date": r.get("Ex_date") or r.get("exdate"),
            "purpose": r.get("Purpose"),
            "record_date": r.get("RD_Date"),
            "payment_date": r.get("payment_date"),
        })
    rows = rows[:limit]
    if rows:
        log("bse corporate actions: %d upcoming" % len(rows), "ok")
        snapshot("bse_corporate_actions", rows)
    return rows


def delivery_stats(f: Fetcher, days_back=5):
    """Market-wide delivery vs traded turnover from the scrip-wise gross archive.

    Delivery percentage is one of the cleanest free sentiment indicators in the
    Indian market: high delivery = investors taking positions, low = churn.
    """
    day = datetime.now(timezone.utc).date()
    series, tried = [], 0
    while len(series) < days_back and tried < days_back * 3:
        tried += 1
        day = day - timedelta(days=1)
        if day.weekday() >= 5:
            continue
        url = "%s/BSEDATA/gross/%s/SCBSEALL%s.zip" % (WWW, day.strftime("%Y"), day.strftime("%d%m"))
        text = f.get_zip_member(url, ttl=7 * 86400, retries=1)
        if not text:
            continue
        agg = _aggregate_delivery(text)
        if agg:
            agg["date"] = day.isoformat()
            series.append(agg)
    series.sort(key=lambda r: r["date"])
    if series:
        log("bse delivery: %d days, latest delivery %.1f%%"
            % (len(series), series[-1]["delivery_pct"]), "ok")
        snapshot("bse_delivery", series)
    else:
        log("bse delivery: no parseable file in the last %d weekdays" % days_back, "warn")
    return series


def _aggregate_delivery(text):
    reader = csv.reader(io.StringIO(text), delimiter="|")
    rows = list(reader)
    if len(rows) < 2:
        return None
    header = [c.strip().upper().strip('"') for c in rows[0]]
    try:
        i_dval = next(i for i, h in enumerate(header) if "DELIVERY VAL" in h)
        i_turn = next(i for i, h in enumerate(header) if "TURNOVER" in h)
        i_dqty = next(i for i, h in enumerate(header) if "DELIVERY QTY" in h)
        i_vol = next(i for i, h in enumerate(header) if "VOLUME" in h)
    except StopIteration:
        log("bse delivery: unexpected header %s" % header, "warn")
        return None

    dval = turn = dqty = vol = 0
    scrips = 0
    for r in rows[1:]:
        if len(r) <= max(i_dval, i_turn, i_dqty, i_vol):
            continue
        t = to_num(r[i_turn]) or 0
        if not t:
            continue
        scrips += 1
        dval += to_num(r[i_dval]) or 0
        turn += t
        dqty += to_num(r[i_dqty]) or 0
        vol += to_num(r[i_vol]) or 0
    if not turn:
        return None
    return {
        "scrips_traded": scrips,
        "turnover_inr": turn,
        "delivery_value_inr": dval,
        "delivery_pct": round(dval / turn * 100, 2),
        "delivery_qty_pct": round(dqty / vol * 100, 2) if vol else None,
    }


BHAVCOPY_URL = WWW + "/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_%s_F_0000.CSV"
SCRIP_MASTER_URL = API + "/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active"

# BSE's main-board equity groups. X holds companies listed only on BSE and XT the
# same companies settled trade-for-trade; A, B and T also carry BSE-only names.
# Z (companies that have not met BSE's listing compliances) is kept: a liquid
# Z-group stock is still bought and sold every day, and its page says plainly
# which group BSE has put it in. Left out: the SME platform (M, MT) and anything
# that is not an equity share (fund units, debt, rights entitlements).
MAINBOARD_GROUPS = ("A", "B", "T", "X", "XT", "Z")

# A BSE-only stock gets its own /stock/ page only once it is genuinely traded:
# present on at least 75% of the sessions fetched, with an average daily traded
# value of at least Rs 10 lakh across all of them (a missed session counts as zero).
LIQUID_MIN_SESSION_SHARE = 0.75
LIQUID_MIN_AVG_VALUE_INR = 1_000_000


def is_equity_isin(isin):
    """INE + 4-character issuer code + "01" (equity shares) + serial + check digit."""
    isin = (isin or "").strip().upper()
    return len(isin) == 12 and isin.startswith("INE") and isin[7:9] == "01"


def isin_issuer_key(isin):
    """The part of an equity ISIN that survives a split or bonus.

    A face-value split re-issues the ISIN with a new serial (Bansal Wire went from
    INE0B9K01025 to INE0B9K01033), so comparing full ISINs across exchanges, or
    across dates, wrongly treats one company as two."""
    isin = (isin or "").strip().upper()
    return isin[:9] if is_equity_isin(isin) else None


def scrip_master(f: Fetcher):
    """BSE's own list of active equity scrips: full company name, scrip code,
    ticker, group, face value, ISIN and market capitalisation (Rs crore). The
    daily bhavcopy cuts names at 30 characters, so names come from here."""
    data = f.get_json(SCRIP_MASTER_URL, ttl=86400, retries=1)
    if not isinstance(data, list):
        log("bse scrip master: no list returned", "warn")
        return {}
    out = {}
    for r in data:
        if not isinstance(r, dict) or (r.get("Status") or "").strip() != "Active":
            continue
        code = str(r.get("SCRIP_CD") or "").strip()
        isin = (r.get("ISIN_NUMBER") or "").strip().upper()
        if not code or not is_equity_isin(isin):
            continue
        out[code] = {
            "code": code,
            "symbol": (r.get("scrip_id") or "").strip(),
            "name": _display_name(r.get("Issuer_Name"), r.get("Scrip_Name")),
            "group": (r.get("GROUP") or "").strip().upper(),
            "face_value": to_num(r.get("FACE_VALUE")),
            "isin": isin,
            "mktcap_cr": to_num(r.get("Mktcap")),
            "bse_url": (r.get("NSURL") or "").strip() or None,
        }
    log("bse scrip master: %d active equity scrips" % len(out), "ok" if out else "warn")
    return out


def _display_name(issuer, short):
    """The issuer's registered name, else BSE's short name, whichever is not
    written in capitals; title-casing is the last resort because it mangles
    acronyms ("BMW" becomes "Bmw")."""
    names = [" ".join((raw or "").split()) for raw in (issuer, short)]
    names = [n for n in names if n]
    for name in names:
        if not name.isupper():
            return re.sub(r" (limited|ltd\.?)$", lambda m: " " + m.group(1).capitalize(), name)
    return names[0].title() if names else ""


def bse_only_history(f: Fetcher, nse_issuer_keys, keep_codes=(), days_back=120):
    """Daily OHLCV for BSE main-board equities that are not listed on NSE.

    Built from BSE's own daily bhavcopy, the same way nse.equity_history() reads
    NSE's. nse_issuer_keys is the set of isin_issuer_key() values for everything
    NSE lists (main board and SME); a stock NSE also lists already has an NSE
    page and is skipped. Without that set nothing can be called BSE-only, so this
    returns None rather than guess.

    History is kept only for stocks that pass the liquidity rule above or are
    already in keep_codes (stocks that already have a page), which keeps the
    ingest file small. Returns {"asof", "sessions", "scrips": {code: {...,
    "candles": [...], "liquid": bool}}} keyed by BSE scrip code, which unlike
    the ISIN does not change on a split.
    """
    if not nse_issuer_keys or len(nse_issuer_keys) < 1500:
        log("bse-only history skipped: NSE's listed-securities list was not available", "warn")
        return None
    master = scrip_master(f)
    keep_codes = set(keep_codes or ())
    by_code, last_seen, stats = {}, {}, {}
    day = datetime.now(timezone.utc).date()
    tried = sessions = 0
    asof = None
    while sessions < days_back and tried < days_back * 2:
        tried += 1
        day = day - timedelta(days=1)
        if day.weekday() >= 5:
            continue
        text = f.get_text(BHAVCOPY_URL % day.strftime("%Y%m%d"), ttl=30 * 86400, retries=1)
        if not text:
            continue
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows or "ClsPric" not in rows[0]:
            continue
        sessions += 1
        asof = asof or day.isoformat()
        for r in rows:
            isin = (r.get("ISIN") or "").strip().upper()
            group = (r.get("SctySrs") or "").strip().upper()
            if group not in MAINBOARD_GROUPS or not is_equity_isin(isin) or isin_issuer_key(isin) in nse_issuer_keys:
                continue
            code = (r.get("FinInstrmId") or "").strip()
            close = to_num(r.get("ClsPric"))
            if not code or close is None:
                continue
            if code not in last_seen:   # walking backwards, so the first row seen is the latest
                last_seen[code] = {"symbol": (r.get("TckrSymb") or "").strip(),
                                   "name": " ".join((r.get("FinInstrmNm") or "").split()),
                                   "group": group, "isin": isin,
                                   "lot": to_num(r.get("NewBrdLotQty"))}
            s = stats.setdefault(code, [0, 0.0])
            s[0] += 1
            s[1] += to_num(r.get("TtlTrfVal")) or 0
            by_code.setdefault(code, []).append({
                "date": day.isoformat(), "open": to_num(r.get("OpnPric")), "high": to_num(r.get("HghPric")),
                "low": to_num(r.get("LwPric")), "close": close, "volume": to_num(r.get("TtlTradgVol")),
            })
    if not sessions:
        log("bse-only history: no bhavcopy file reachable", "warn")
        return None
    scrips = {}
    for code, candles in by_code.items():
        n, value = stats[code]
        liquid = n >= LIQUID_MIN_SESSION_SHARE * sessions and value / sessions >= LIQUID_MIN_AVG_VALUE_INR
        if not liquid and code not in keep_codes:
            continue
        meta = dict(last_seen[code])
        m = master.get(code)
        if m and isin_issuer_key(m["isin"]) in nse_issuer_keys:
            continue
        if m:
            meta.update({k: m[k] for k in ("symbol", "name", "group", "face_value", "isin", "mktcap_cr", "bse_url")
                         if m.get(k) not in (None, "")})
        # "master": the name and facts came from BSE's scrip list, not the bhavcopy's
        # 30-character name; only such a record may name a page (see bse_only.py).
        meta.update({"code": code, "liquid": liquid, "master": bool(m), "sessions_traded": n,
                     "avg_value_inr": round(value / sessions), "candles": sorted(candles, key=lambda p: p["date"])})
        scrips[code] = meta
    log("bse-only history: %d stocks kept (%d pass the liquidity rule), %d sessions to %s"
        % (len(scrips), sum(1 for s in scrips.values() if s["liquid"]), sessions, asof), "ok")
    return {"asof": asof, "sessions": sessions, "scrips": scrips}


def collect(watchlist=None, nse_issuer_keys=None, keep_codes=()):
    f = bse()
    out = {
        "delivery": delivery_stats(f),
        "corporate_actions": corporate_actions(f),
        "live": live_quotes(f, watchlist),
    }
    try:
        out["bse_only"] = bse_only_history(f, nse_issuer_keys, keep_codes)
    except Exception as exc:   # an enrichment; never let it cost the rest of BSE's data
        log("bse-only history failed: %s" % exc, "warn")
        out["bse_only"] = None
    return out
