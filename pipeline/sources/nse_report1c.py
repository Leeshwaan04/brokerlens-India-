"""NSE Report 1C: broker-wise active clients, UCC counts and a defaulter
flag for every trading member, published monthly as NSE's own disclosure
of investor-complaint redressal (hence the file's own name).

This is NSE's own authoritative count of each broker's active clients -
previously the only number this site could publish for that field came
from a provenance:"sample" placeholder, dropped entirely in production
rather than shown as real (see pipeline/publish.py's PRODUCTION-mode drop
rule, and data/manual/active_clients.json's own source_note: "replace with
NSE member-wise UCC ingest"). This is that real source, confirmed live via
nseindia.com/invest/arbitration-status (the per-fiscal-year index page
listing every isc_report1C_<FY>.xls back to FY2008-09).

Legacy binary .xls (BIFF/OLE2), not xlsx or CSV - the one documented
exception to this project's otherwise stdlib-only policy (see
pipeline/requirements.txt). xlrd 2.x is used specifically because it dropped xlsx
support in 2020 to focus only on this older, narrower format.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..common import log, snapshot

# /invest/arbitration-status (the page that lists every fiscal year's file)
# turned out to be the same client-rendered SPA shell NSE serves for every
# route - a plain fetch returns generic boilerplate ("Corporate Filings
# Unitholding Patterns...") for this URL regardless of path, with the real
# listing drawn in by JavaScript after load. Scraping it would need a real
# browser, which this project's Fetcher deliberately isn't (same stdlib-only
# stance pipeline/requirements.txt's one xlrd exception doesn't extend to). India's
# fiscal year (1 April - 31 March) is fixed and public, so the file name is
# computed directly from today's date instead - confirmed live:
# isc_report1C_2627.xls (FY2026-27, 2-digit+2-digit, no separator).
ARCHIVE_HOST = "https://nsearchives.nseindia.com"
FILE_URL = ARCHIVE_HOST + "/miscellaneous/ArbitrationReports/isc_report1C_%s.xls"


def _current_fy_code(today=None):
    today = today or datetime.now(timezone.utc)
    start_year = today.year if today.month >= 4 else today.year - 1
    return "%02d%02d" % (start_year % 100, (start_year + 1) % 100)


def _prior_fy_code(fy_code):
    start = int(fy_code[:2])
    return "%02d%02d" % ((start - 1) % 100, start % 100)

# Row/column layout verified against a real, live-fetched file
# (isc_report1C_2627.xls, FY2026-27): one header block (rows 0-8), then one
# data row per trading member starting at row 9, ending at the first row
# whose name is blank or literally "Total" (row 272 in that file - 263 real
# members). Column positions are fixed by NSE's own template, not inferred.
DATA_START_ROW = 9
COL_NAME = 1
COL_DEFAULTER = 2
COL_UCC_START = 3
COL_ACTIVE_CLIENTS = 9

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def fetch_current_file(f_archives):
    """The current fiscal year's Report 1C bytes, computed from today's date
    (see _current_fy_code). Falls back one fiscal year if the computed one
    doesn't respond yet - NSE's own file for a new fiscal year isn't live
    from day one, so the window right after April 1 would otherwise find
    nothing even though last year's (still-recent) file is right there."""
    fy = _current_fy_code()
    body = f_archives.get(FILE_URL % fy, ttl=12 * 3600, retries=2)
    if body:
        return body, fy
    prior = _prior_fy_code(fy)
    body = f_archives.get(FILE_URL % prior, ttl=12 * 3600, retries=2)
    return (body, prior) if body else (None, None)


def _parse_as_of(title_text):
    """'2026-09' from 'Report 1C: ... Last Updated on 30-September-2026'."""
    m = re.search(r"Last Updated on\s+(\d{1,2})-([A-Za-z]+)-(\d{4})", title_text or "")
    if not m:
        return None
    _day, month_name, year = m.groups()
    mnum = _MONTH_NAMES.get(month_name.lower())
    return "%s-%02d" % (year, mnum) if mnum else None


def parse_report1c(xls_bytes):
    """-> {"as_of": "YYYY-MM", "exchange_active_clients": int, "rows": [...]}
    or None if the bytes can't be read as the expected shape.

    Each row: {"name": str, "defaulter": bool, "ucc_start_of_year": int,
    "active_clients": int}. A member whose active-clients cell isn't a
    clean number is skipped, not coerced - this is a real total other
    numbers (market share) divide against, so a wrong one is worse than
    a gap."""
    import xlrd  # the one documented stdlib-dependency exception; see pipeline/requirements.txt

    book = xlrd.open_workbook(file_contents=xls_bytes)
    sh = book.sheet_by_index(0)
    if sh.nrows < DATA_START_ROW:
        return None

    as_of = _parse_as_of(str(sh.cell_value(0, 0)))
    exchange_total = _exchange_total(sh)
    rows = _member_rows(sh)
    if not rows or not as_of:
        return None
    return {"as_of": as_of, "exchange_active_clients": exchange_total, "rows": rows}


def _exchange_total(sh):
    """The 'Total number of active clients' figure from the header block.
    Searched across every header row, not a fixed few, so a title line added
    above it does not lose the denominator every market share divides by."""
    for r in range(min(DATA_START_ROW, sh.nrows)):
        label = str(sh.cell_value(r, COL_NAME)).strip().lower()
        if label.startswith("total number of active clients"):
            try:
                return int(sh.cell_value(r, COL_NAME + 1))
            except (ValueError, TypeError):
                return None
    return None


def _member_rows(sh):
    """One dict per member row, from DATA_START_ROW to the closing 'Total' row.

    `sh` is anything with nrows and cell_value(r, c), an xlrd sheet in use.
    A blank row is skipped, not taken as the end: a spacer inside the member
    list would otherwise silently drop every member below it."""
    rows = []
    for r in range(DATA_START_ROW, sh.nrows):
        name = str(sh.cell_value(r, COL_NAME)).strip()
        if not name:
            continue
        if name.lower() == "total":
            break  # footnote text follows the closing Total row
        try:
            active_raw = sh.cell_value(r, COL_ACTIVE_CLIENTS)
            active = int(active_raw) if active_raw not in ("", None) else None
        except (ValueError, TypeError):
            active = None
        if active is None:
            continue
        try:
            ucc_raw = sh.cell_value(r, COL_UCC_START)
            ucc = int(ucc_raw) if ucc_raw not in ("", None) else None
        except (ValueError, TypeError):
            ucc = None
        defaulter_raw = str(sh.cell_value(r, COL_DEFAULTER)).strip().lower()
        rows.append({
            "name": name,
            "defaulter": defaulter_raw == "yes",
            "ucc_start_of_year": ucc,
            "active_clients": active,
        })
    return rows


def collect(f_archives):
    """Fetch and parse the current Report 1C. Returns the parse_report1c()
    shape, or None on any failure - never raises, since one bad run here
    must not break the broader daily pipeline (same tolerance as every
    other source adapter)."""
    try:
        xls_bytes, fy = fetch_current_file(f_archives)
        if not xls_bytes:
            log("nse_report1c: neither this nor last fiscal year's file responded", "warn")
            return None
        data = parse_report1c(xls_bytes)
        if not data:
            log("nse_report1c: fetched FY%s but found no parseable rows" % fy, "warn")
            return None
        log("nse_report1c: %d trading members, as of %s (exchange total %s)"
            % (len(data["rows"]), data["as_of"],
               format(data["exchange_active_clients"] or 0, ",")), "ok")
        snapshot("nse_report1c", data)
        return data
    except ImportError:
        log("nse_report1c: xlrd not installed (pip install -r pipeline/requirements.txt) - skipping", "err")
        return None
    except Exception as exc:
        log("nse_report1c: parse failed: %s" % exc, "err")
        return None
