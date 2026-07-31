"""Builds a symbol map by joining the NSE and BSE equity masters on ISIN.

Why this exists: NSE's per-symbol quote endpoint (/api/quote-equity) returns 403
to anything without a full browser sensor, but BSE's getScripHeaderData answers
happily for any scrip code. So to quote an arbitrary symbol we need
NSE symbol -> ISIN -> BSE scrip code.

ISIN is the right join key - it is the regulatory identifier for the security, so
it survives ticker renames and is unambiguous, unlike matching on company name.

Result: 2,261 of NSE's 2,390 symbols are quotable via BSE (the remainder are
NSE-exclusive listings). Written to config/symbol_map.json and refreshed daily.
"""
from __future__ import annotations

import csv
import io
import os

from .common import CONFIG, log, read_json, write_json
from .sources import bse as bse_src
from .sources import nse as nse_src

BSE_MASTER = ("https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
              "?Group=&Scripcode=&industry=&segment=Equity&status=Active")

MAP_PATH = os.path.join(CONFIG, "symbol_map.json")


def build(force=False):
    existing = read_json(MAP_PATH, {}) or {}
    if existing.get("symbols") and not force:
        log("symbol map: %d symbols already mapped (use force=True to rebuild)"
            % len(existing["symbols"]))
        return existing

    fa = nse_src.nse_archives()
    text = fa.get_text("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
                       ttl=86400)
    if not text:
        log("symbol map: NSE equity master unavailable", "err")
        return existing

    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return existing
    k_sym = next(k for k in rows[0] if k.strip().upper() == "SYMBOL")
    k_isin = next(k for k in rows[0] if "ISIN" in k.strip().upper())
    k_name = next((k for k in rows[0] if "NAME OF COMPANY" in k.strip().upper()), None)
    nse = {}
    for r in rows:
        sym = (r.get(k_sym) or "").strip()
        if sym:
            nse[sym] = {"isin": (r.get(k_isin) or "").strip(),
                        "name": (r.get(k_name) or "").strip() if k_name else None}

    fb = bse_src.bse()
    bse = fb.get_json(BSE_MASTER, ttl=86400)
    if not isinstance(bse, list):
        log("symbol map: BSE master unavailable", "err")
        return existing

    # NOTE: the field is ISIN_NUMBER, not ISIN_NUM.
    by_isin = {}
    for r in bse:
        isin = (r.get("ISIN_NUMBER") or "").strip()
        if isin:
            by_isin[isin] = r

    symbols = {}
    for sym, meta in nse.items():
        rec = by_isin.get(meta["isin"])
        if not rec:
            continue
        symbols[sym] = {
            "isin": meta["isin"],
            "name": meta["name"] or rec.get("Scrip_Name"),
            "bse_scrip": str(rec.get("SCRIP_CD")),
            "bse_name": rec.get("Scrip_Name"),
            "group": rec.get("GROUP"),
            "industry": rec.get("INDUSTRY"),
        }

    out = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "nse_symbols": len(nse),
        "bse_active": len(bse),
        "mapped": len(symbols),
        "symbols": symbols,
    }
    write_json(MAP_PATH, out, compact=True)
    log("symbol map: %d of %d NSE symbols quotable via BSE" % (len(symbols), len(nse)), "ok")
    return out


def resolve(symbols):
    """[(symbol, scrip_code, display_name)] for whatever is mappable."""
    m = read_json(MAP_PATH, {}) or {}
    table = m.get("symbols") or {}
    out = []
    for s in symbols:
        rec = table.get(s.upper())
        if rec:
            out.append((s.upper(), rec["bse_scrip"], rec.get("name") or rec.get("bse_name")))
    return out


if __name__ == "__main__":
    build(force=True)
