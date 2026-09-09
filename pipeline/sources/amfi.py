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
            # A bare line is either a category banner or an AMC name banner -
            # AMFI's own convention is that every AMC section header ends
            # with the literal words "Mutual Fund".
            if line.lower().endswith("mutual fund"):
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

    log("amfi nav master: %d scheme rows across %d AMCs"
        % (len(rows), len(set(r["amc"] for r in rows))), "ok" if rows else "warn")
    snapshot("amfi_nav_master", {"row_count": len(rows)})
    return rows


def collect():
    return {"schemes": nav_master(amfi())}
