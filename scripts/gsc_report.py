#!/usr/bin/env python3
"""Daily Search Console snapshot.

Pulls sitemap coverage, 28-day search performance, and a spot-check of
indexing status across every page family, then writes a dated JSON snapshot
plus appends one compact line to a rolling history file. Run on a schedule
by .github/workflows/gsc-report.yml; safe to also run by hand for an
on-demand check.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
import gsc_client as gsc  # noqa: E402

SITE = "sc-domain:brokerlens.in"
SITE_QUOTED = urllib.parse.quote(SITE, safe="")
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.join(ROOT, "reports", "gsc")

# One representative URL per page family - a family-wide indexing problem
# (e.g. every stock page stuck on "Crawled - currently not indexed") shows up
# here long before it would surface in the sitemap report's single aggregate
# number.
SPOT_CHECK_URLS = [
    "https://www.brokerlens.in/",
    "https://www.brokerlens.in/brokers",
    "https://www.brokerlens.in/sources",
    "https://www.brokerlens.in/methodology",
    "https://www.brokerlens.in/broker/zerodha/",
    "https://www.brokerlens.in/stock/20microns/",
    "https://www.brokerlens.in/etf/niftybees/",
    "https://www.brokerlens.in/calculators/sip-calculator/",
    "https://www.brokerlens.in/brokers-by/type/",
    "https://www.brokerlens.in/crypto/btc/",
]


def _safe(fn, *args):
    try:
        return fn(*args)
    except SystemExit as e:
        return {"error": str(e)}


def main():
    token = gsc.get_access_token()
    today = datetime.date.today().isoformat()

    sitemaps = _safe(lambda: gsc._api(
        "%s/sites/%s/sitemaps" % (gsc.API_ROOT, SITE_QUOTED), token,
    ))

    end = datetime.date.today() - datetime.timedelta(days=3)
    start = end - datetime.timedelta(days=28)
    perf_by_query = _safe(lambda: gsc._api(
        "%s/sites/%s/searchAnalytics/query" % (gsc.API_ROOT, SITE_QUOTED),
        token, "POST",
        {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["query"], "rowLimit": 25},
    ))
    perf_totals = _safe(lambda: gsc._api(
        "%s/sites/%s/searchAnalytics/query" % (gsc.API_ROOT, SITE_QUOTED),
        token, "POST",
        {"startDate": start.isoformat(), "endDate": end.isoformat(), "rowLimit": 1},
    ))

    spot_checks = {}
    for url in SPOT_CHECK_URLS:
        body = {"inspectionUrl": url, "siteUrl": SITE}
        result = _safe(lambda b=body: gsc._api(gsc.INSPECTION_URL, token, "POST", b))
        status = (result or {}).get("inspectionResult", {}).get("indexStatusResult", {})
        spot_checks[url] = {
            "coverageState": status.get("coverageState"),
            "verdict": status.get("verdict"),
            "lastCrawlTime": status.get("lastCrawlTime"),
            "pageFetchState": status.get("pageFetchState"),
            "robotsTxtState": status.get("robotsTxtState"),
        }

    sitemap_summary = []
    for sm in (sitemaps or {}).get("sitemap", []):
        contents = sm.get("contents", [{}])
        sitemap_summary.append({
            "path": sm.get("path"),
            "lastDownloaded": sm.get("lastDownloaded"),
            "warnings": sm.get("warnings"),
            "errors": sm.get("errors"),
            "submitted": (contents[0] if contents else {}).get("submitted"),
            "indexed": (contents[0] if contents else {}).get("indexed"),
        })

    snapshot = {
        "date": today,
        "sitemaps": sitemap_summary,
        "performance_28d": {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "totals": (perf_totals or {}).get("rows", [{}])[0] if (perf_totals or {}).get("rows") else None,
            "top_queries": (perf_by_query or {}).get("rows", []),
        },
        "spot_checks": spot_checks,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "%s.json" % today), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    indexed_total = sum(int(s["indexed"] or 0) for s in sitemap_summary if s.get("indexed") not in (None, ""))
    submitted_total = sum(int(s["submitted"] or 0) for s in sitemap_summary if s.get("submitted") not in (None, ""))
    not_indexed_spots = [u for u, s in spot_checks.items() if s.get("coverageState") not in ("Submitted and indexed",)]
    line = {
        "date": today,
        "submitted": submitted_total,
        "indexed": indexed_total,
        "clicks_28d": (snapshot["performance_28d"]["totals"] or {}).get("clicks", 0),
        "impressions_28d": (snapshot["performance_28d"]["totals"] or {}).get("impressions", 0),
        "spot_check_not_indexed": not_indexed_spots,
    }
    history_path = os.path.join(OUT_DIR, "history.jsonl")
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")

    print(json.dumps(line, indent=2))
    if not_indexed_spots:
        print("NOT INDEXED: %d of %d spot-checked URLs:" % (len(not_indexed_spots), len(SPOT_CHECK_URLS)))
        for u in not_indexed_spots:
            print("  %s -> %s" % (u, spot_checks[u].get("coverageState")))


if __name__ == "__main__":
    main()
