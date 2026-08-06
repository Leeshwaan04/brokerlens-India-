"""SEBI Annexure-B investor-complaint disclosures, crawled from each broker.

Every SEBI-registered broker is REQUIRED to publish, monthly, on its own
website, the number of investor complaints received, resolved and pending, in
SEBI's prescribed Annexure-B format. It is public, mandated, free, and nobody
publishes it in a comparable form. It is also the dataset that makes the whole
comparison honest, which is why it is worth crawling properly rather than
approximating.

DESIGN RULES, learned from the 2026-08-01 audit:

  1. NEVER GUESS. Each broker lays the table out differently. If a page cannot
     be parsed with confidence the broker gets NO record, and the failure is
     logged. A gap is publishable; a wrong complaint count attached to a named,
     regulated firm is not.
  2. Numbers must come from a row we positively identified as the total, not
     from "the last row" or "the biggest number on the page".
  3. Every record carries the URL and the fetch date, so any figure on the site
     can be traced back to the broker's own disclosure.
  4. Months are normalised to YYYY-MM. A row whose period cannot be determined
     is dropped rather than assigned to "probably last month".

Output slots straight into data/manual/complaints.json with
provenance:"sebi_annexure_b", which is the shape publish.py already expects.
"""
from __future__ import annotations

import os
import re

from ..common import CONFIG, Fetcher, log, snapshot, strip_tags, tables, to_num

# Column headers, lowercased, that identify each quantity. Brokers word these
# differently; these are the forms actually seen in the wild.
_RECEIVED = ("received during the month", "received during month", "no. of complaints received",
             "complaints received", "received")
_RESOLVED = ("resolved during the month", "resolved during month", "no. of complaints resolved",
             "complaints resolved", "resolved", "disposed")
_PENDING = ("pending at the end of the month", "pending at end of month", "pending at the end",
            "total pending", "pending")

# The row that carries the month's totals. Brokers label it inconsistently.
_TOTAL_ROW = ("grand total", "total")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "for the month of March 2026", "March, 2026", "Mar-26", "01-03-2026"
_MONTH_PATTERNS = (
    re.compile(r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\-]+(?P<yr>20\d{2})", re.I),
    re.compile(r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*[\-/]\s*(?P<yr2>\d{2})\b", re.I),
    re.compile(r"\b\d{1,2}[\-/](?P<mnum>0?[1-9]|1[0-2])[\-/](?P<yr3>20\d{2})\b"),
)


def _parse_month(text):
    """'YYYY-MM' from free text, or None. Never falls back to 'now'."""
    if not text:
        return None
    for pat in _MONTH_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        g = m.groupdict()
        if g.get("mon") and g.get("yr"):
            return "%s-%02d" % (g["yr"], _MONTHS[g["mon"][:3].lower()])
        if g.get("mon") and g.get("yr2"):
            return "20%s-%02d" % (g["yr2"], _MONTHS[g["mon"][:3].lower()])
        if g.get("mnum") and g.get("yr3"):
            return "%s-%02d" % (g["yr3"], int(g["mnum"]))
    return None


def _match_column(header_cells, candidates):
    """Index of the first column whose header matches one of `candidates`.

    Longest candidate first, so "received during the month" wins over the bare
    "received" when both would match.
    """
    best = None
    for idx, cell in enumerate(header_cells):
        h = re.sub(r"\s+", " ", (cell or "").strip().lower())
        for cand in sorted(candidates, key=len, reverse=True):
            if cand in h:
                # prefer the most specific match found anywhere in the row
                if best is None or len(cand) > best[1]:
                    best = (idx, len(cand))
                break
    return best[0] if best else None


def parse_annexure_b(html, url=""):
    """Extract [{month, received, resolved, pending}] from a disclosure page.

    Returns (rows, reason_if_empty). Anything ambiguous yields no rows and a
    reason, so the caller can log a gap instead of publishing a guess.
    """
    if not html:
        return [], "empty response"

    page_month = _parse_month(strip_tags(html)[:4000])
    out, saw_table = [], False

    for rows in tables(html):
        if len(rows) < 2:
            continue
        header = rows[0]
        i_recv = _match_column(header, _RECEIVED)
        i_res = _match_column(header, _RESOLVED)
        i_pend = _match_column(header, _PENDING)
        if i_recv is None or i_res is None:
            continue                      # not an Annexure-B table
        saw_table = True

        # A month column makes the table self-describing; otherwise fall back to
        # the month named in the page text.
        i_month = _match_column(header, ("month", "period", "month ended", "for the month"))

        for row in rows[1:]:
            if len(row) <= max(i_recv, i_res):
                continue
            label = re.sub(r"\s+", " ", (row[0] or "").strip().lower())

            month = None
            if i_month is not None and len(row) > i_month:
                month = _parse_month(row[i_month])
            if month is None and any(t == label or label.startswith(t) for t in _TOTAL_ROW):
                month = page_month           # totals row of a single-month table
            if month is None:
                month = _parse_month(row[0])
            if month is None:
                continue

            # Only take a row we positively identified as a total, unless the
            # table is a month-per-row series (which has its own month column).
            is_total = any(t == label or label.startswith(t) for t in _TOTAL_ROW)
            if i_month is None and not is_total:
                continue

            received = to_num(row[i_recv])
            resolved = to_num(row[i_res])
            pending = to_num(row[i_pend]) if i_pend is not None and len(row) > i_pend else None
            if received is None or resolved is None:
                continue

            out.append({
                "month": month,
                "received": int(received),
                "resolved": int(resolved),
                "pending": int(pending) if pending is not None else None,
                "source_url": url,
            })

    if not out:
        return [], ("found an Annexure-B table but no month could be determined"
                    if saw_table else "no Annexure-B table found on the page")

    # One record per month; a later table on the page wins (usually the detailed one).
    dedup = {}
    for r in out:
        dedup[r["month"]] = r
    return [dedup[m] for m in sorted(dedup)], None


def collect(sources=None, ttl=12 * 3600):
    """Crawl every configured broker disclosure page.

    `config/complaint_sources.json` maps broker_id -> the URL where that broker
    publishes its Annexure-B table. The URL is curated because every broker puts
    it somewhere different; the NUMBERS are never curated.
    """
    cfg = sources or (
        __import__("json").load(open(os.path.join(CONFIG, "complaint_sources.json"), encoding="utf-8"))
        if os.path.exists(os.path.join(CONFIG, "complaint_sources.json")) else {}
    )
    entries = cfg.get("brokers") or {}
    if not entries:
        log("complaints: no disclosure sources configured", "warn")
        return {"brokers": {}, "failures": {}, "attempted": 0}

    f = Fetcher("complaints")
    got, failures = {}, {}
    for bid, entry in entries.items():
        url = entry.get("url") if isinstance(entry, dict) else entry
        if not url:
            failures[bid] = "no url configured"
            continue
        try:
            html = f.get_text(url, ttl=ttl, retries=2)
        except Exception as exc:                       # never let one broker kill the run
            failures[bid] = "fetch failed: %s" % str(exc)[:120]
            continue
        if not html:
            failures[bid] = "fetch returned nothing"
            continue
        rows, reason = parse_annexure_b(html, url)
        if rows:
            got[bid] = rows
        else:
            failures[bid] = reason

    log("complaints: parsed %d of %d brokers (%d unparsed)"
        % (len(got), len(entries), len(failures)), "ok" if got else "warn")
    for bid, why in sorted(failures.items())[:8]:
        log("  complaints gap: %s (%s)" % (bid, why), "warn")

    snapshot("broker_complaints", {"brokers": got, "failures": failures})
    return {"brokers": got, "failures": failures, "attempted": len(entries)}
