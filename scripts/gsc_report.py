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
import re
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


DEMAND_PATH = os.path.join(OUT_DIR, "stock_demand.json")
DEMAND_MIN_IMPRESSIONS = 5
_STOCK_PATH_RE = re.compile(r"^/stock/([a-z0-9-]+)/(?:share-price-target-\d+/?)?$")


def update_stock_demand(token, start, end):
    """Stock slugs with proven search demand, read by publish.py's sitemap writer.

    Wave 1 of the stock sitemap was the 500 most-traded names, but GSC shows this
    site actually wins on small and mid caps that rule leaves out. A slug that took
    at least DEMAND_MIN_IMPRESSIONS on its stock page (or its retired
    share-price-target URL) over 28 days joins wave 1. The set only ever grows:
    the 28-day window slides daily, and letting slugs drop out again would churn
    the sitemap every day, which is its own crawl-trust problem. Leaves the file
    untouched if the API call fails.

    A slug whose retired share-price-target URL took even one impression joins
    too. That URL 308s to the stock (or ETF) page, and the build gives noindex to
    anything outside the sitemap, so leaving the target out throws away whatever
    ranking the redirect carries: on 7 Nov 2026 that was 240 targets."""
    rows, start_row = [], 0
    while True:
        page = _safe(lambda s=start_row: gsc._api(
            "%s/sites/%s/searchAnalytics/query" % (gsc.API_ROOT, SITE_QUOTED), token, "POST",
            {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["page"],
             "rowLimit": 25000, "startRow": s},
        ))
        if not isinstance(page, dict) or "error" in page:
            return None
        batch = page.get("rows", [])
        rows += batch
        if len(batch) < 25000:
            break
        start_row += 25000
    impressions, redirect_targets = {}, set()
    for r in rows:
        path = r["keys"][0].split("brokerlens.in", 1)[-1]
        m = _STOCK_PATH_RE.match(path)
        if m:
            impressions[m.group(1)] = impressions.get(m.group(1), 0) + r.get("impressions", 0)
            if "share-price-target-" in path and r.get("impressions", 0) > 0:
                redirect_targets.add(m.group(1))
    try:
        with open(DEMAND_PATH, encoding="utf-8") as f:
            slugs = set(json.load(f).get("slugs", []))
    except (OSError, ValueError):
        slugs = set()
    slugs |= {s for s, n in impressions.items() if n >= DEMAND_MIN_IMPRESSIONS} | redirect_targets
    with open(DEMAND_PATH, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.date.today().isoformat(), "min_impressions_28d": DEMAND_MIN_IMPRESSIONS,
                   "slugs": sorted(slugs)}, f, indent=1)
    return len(slugs)


PAGE_DEMAND_PATH = os.path.join(OUT_DIR, "page_demand.json")


def update_page_demand(token, start, end):
    """Every page path Google has shown for a real search, read by publish.py's
    sitemap writer so a page that already earns impressions is never noindexed
    by the build's sitemap allowlist. That allowlist, on its first day, silenced
    about 3,200 such pages (registry entities, curated compares, funds, AMC
    hubs). Trade-cost pages and the retired per-year price-target URLs are
    excluded: they stay out on purpose. Grows only, like the stock list."""
    rows, start_row = [], 0
    while True:
        page = _safe(lambda s=start_row: gsc._api(
            "%s/sites/%s/searchAnalytics/query" % (gsc.API_ROOT, SITE_QUOTED), token, "POST",
            {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["page"],
             "rowLimit": 25000, "startRow": s},
        ))
        if not isinstance(page, dict) or "error" in page:
            return None
        batch = page.get("rows", [])
        rows += batch
        if len(batch) < 25000:
            break
        start_row += 25000
    found = set()
    for r in rows:
        path = r["keys"][0].split("brokerlens.in", 1)[-1].split("?", 1)[0].split("#", 1)[0]
        if (r.get("impressions", 0) > 0 and path.startswith("/") and path.endswith("/")
                and "/trade/" not in path and "share-price-target-" not in path):
            found.add(path)
    try:
        with open(PAGE_DEMAND_PATH, encoding="utf-8") as f:
            paths = set(json.load(f).get("paths", []))
    except (OSError, ValueError):
        paths = set()
    paths |= found
    with open(PAGE_DEMAND_PATH, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.date.today().isoformat(), "paths": sorted(paths)}, f, indent=0)
    return len(paths)


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
        # rowLimit was 25 (clicks-descending, GSC's default sort), which structurally could
        # never surface a "striking distance" query - good impressions, poor clicks, ranking
        # just off page 1 - since anything with few clicks never made the top 25 regardless of
        # its impression volume or how close its position is. 250 gives real headroom for that
        # without the report growing unreasonably (API allows up to 25,000).
        {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["query"], "rowLimit": 250},
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
    n_demand = update_stock_demand(token, start, end)
    if n_demand is not None:
        print("stock demand: %d slugs with proven search demand" % n_demand)
    n_pages = update_page_demand(token, start, end)
    if n_pages is not None:
        print("page demand: %d page paths with real impressions" % n_pages)

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
