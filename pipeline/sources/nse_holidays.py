"""NSE trading holidays: the exchange's own holiday calendar for the equity
(CM) and equity derivatives (FO) segments.

config/market_timings.json, which drives the Market timings menu, carries
session times but not holidays (pipeline/feeds.py calls them "the known
gap"). This fills it from NSE itself, for /stock-market-holidays/.

A day NSE marks with an asterisk (8 Nov 2026, Diwali Laxmi Pujan) is one
on which a special Muhurat trading session is held; the session's timings
come from a separate NSE circular, so nothing here asserts them.
"""
from __future__ import annotations

from datetime import datetime

from ..common import log, snapshot

HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
SEGMENTS = ("CM", "FO")


def _parse_rows(rows):
    """[{date: YYYY-MM-DD, weekday, name, muhurat}] sorted by date; rows whose
    date does not parse are dropped rather than guessed."""
    out = []
    for r in rows or []:
        try:
            d = datetime.strptime(str(r.get("tradingDate") or ""), "%d-%b-%Y").date()
        except ValueError:
            continue
        name = str(r.get("description") or "").strip()
        out.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%A"),
            "name": name.rstrip("*").strip(),
            "muhurat": name.endswith("*"),
        })
    return sorted(out, key=lambda x: x["date"])


def collect(f_nse):
    """-> {"segments": {"CM": [...], "FO": [...]}} or None. Never raises."""
    try:
        raw = f_nse.get_json(HOLIDAY_URL, ttl=24 * 3600)
        if not isinstance(raw, dict):
            log("nse_holidays: no calendar returned", "warn")
            return None
        segments = {s: _parse_rows(raw.get(s)) for s in SEGMENTS}
        if not segments["CM"]:
            log("nse_holidays: calendar returned no equity (CM) holidays", "warn")
            return None
        log("nse_holidays: %d equity holidays (%s to %s)" % (
            len(segments["CM"]), segments["CM"][0]["date"], segments["CM"][-1]["date"]), "ok")
        snapshot("nse_holidays", segments)
        return {"segments": segments}
    except Exception as exc:
        log("nse_holidays: failed: %s" % exc, "err")
        return None
