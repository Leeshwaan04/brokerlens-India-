"""AMFI (Association of Mutual Funds in India) adapter.

AMFI's own NAVAll.txt is the industry-standard master NAV file: every open
scheme, every plan/option, published daily. amfiindia.com 302-redirects to
portal.amfiindia.com for this exact file; the shared Fetcher's redirect
handler follows it automatically, so the portal URL is used directly here to
skip the extra hop.

The file is not a clean CSV: scheme rows are semicolon-delimited, but
interspersed with bare category headers ("Open Ended Schemes(...)") and bare
AMC name headers ("Axis Mutual Fund"), with blank lines as separators. This
adapter parses it as a small stateful line scanner rather than forcing it
through csv.DictReader.
"""
from __future__ import annotations

import re

from ..common import amfi, log, snapshot, to_num

URL = "https://portal.amfiindia.com/spages/NAVAll.txt"

# AMFI's real NAVAll.txt has carried 14,000+ scheme rows for years. A 200
# response under an interstitial/anti-bot/error page, or a truncated body,
# still parses to a handful of matching rows (or zero) and used to be logged
# and published as a plain "ok" - identical to a full file - because the only
# check here was "is the list non-empty". That let a broken fetch silently
# replace the entire ~3,400-page mutual fund section with a near-empty one
# for over a week with no alert (see data/raw/amfi_nav_master/2026-10-16
# onward: row_count collapsed from ~14,300+ to exactly 3 and stayed there).
# This floor is well below any real file (which has never dropped under
# ~14,000) and well above a blocked/broken response, so it can't be crossed
# by ordinary AMFI data churn.
MIN_PLAUSIBLE_ROWS = 5000


def _clean_name(name):
    """AMFI's own file re-types the same scheme name slightly differently
    across refreshes - extra internal spaces, a stray trailing '-' or '..'.
    Confirmed against a live pull: collapsing whitespace and trimming
    trailing punctuation merges these back into the one real scheme they
    are, rather than splitting a single fund into near-duplicate pages."""
    name = re.sub(r"\s+", " ", name or "").strip()
    name = re.sub(r"[\s\-.]+$", "", name)
    return name


def nav_master(f):
    text = f.get_text(URL, ttl=43200)
    if not text:
        return None

    rows = []
    category = None
    amc = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ";" not in line:
            # A bare line is either a category banner or an AMC name banner.
            # Category banners always read "<Open|Close> Ended Schemes(...)" or
            # "Interval Fund Schemes(...)"; every AMC banner carries the
            # words "Mutual Fund". Matching "ends with Mutual Fund" missed
            # AMFI's "IL&FS Mutual Fund (IDF)" banner (trailing "(IDF)"), which
            # then overwrote the running category for ~2,500 following rows
            # and left IL&FS's own schemes filed under the previous AMC.
            low = line.lower()
            is_category = bool(re.match(r"^(open ended|close ended|interval fund)\b", low))
            if "mutual fund" in low and not is_category:
                amc = line
            else:
                category = line
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) != 8 or not parts[0].isdigit():
            continue  # the column header row itself, or a malformed line
        if not amc:
            continue  # a data row before any AMC banner has been seen
        scheme_code, isin_growth, isin_div, name, plan, option, nav, date = parts
        rows.append({
            "scheme_code": scheme_code,
            "isin_growth": isin_growth if isin_growth and isin_growth != "-" else None,
            "isin_div_reinvest": isin_div if isin_div and isin_div != "-" else None,
            "name": _clean_name(name),
            "plan": plan,
            "option": option,
            "nav": to_num(nav),
            "nav_date": date,
            "amc": amc,
            "category": category,
        })

    snapshot("amfi_nav_master", {"row_count": len(rows)})
    log("amfi nav master: %d scheme rows across %d AMCs"
        % (len(rows), len(set(r["amc"] for r in rows))), "ok" if rows else "warn")
    return rows


def collect():
    rows = nav_master(amfi())
    if rows is not None and len(rows) < MIN_PLAUSIBLE_ROWS:
        # Implausibly small for a real NAVAll.txt pull - treat it the same as
        # no data at all so pipeline.run's EXPECTED_ROWS gate sees "schemes"
        # as empty, logs "err", and the run exits non-zero instead of
        # silently publishing a near-empty mutual fund section as a success.
        # (The floor lives here, not in nav_master(), so unit tests can still
        # call nav_master() directly with small fixtures.)
        log("amfi nav master: only %d scheme rows parsed (expected 14,000+) "
            "- treating as a failed fetch, not publishing" % len(rows), "err")
        rows = None
    return {"schemes": rows}
