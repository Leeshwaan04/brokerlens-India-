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


def collect(watchlist=None):
    f = bse()
    return {
        "delivery": delivery_stats(f),
        "corporate_actions": corporate_actions(f),
        "live": live_quotes(f, watchlist),
    }
