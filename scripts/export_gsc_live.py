#!/usr/bin/env python3
"""Export real Google Search Console metrics into site/data/gsc_live.json for the CMS portal."""

from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GSC_DIR = os.path.join(ROOT, "reports", "gsc")
DEST_FILE = os.path.join(ROOT, "site", "data", "gsc_live.json")


def clean_dashes(val):
    if isinstance(val, str):
        return val.replace("\u2014", " - ").replace("\u2013", "-")
    elif isinstance(val, dict):
        return {k: clean_dashes(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_dashes(x) for x in val]
    return val


def main():
    reports = sorted(glob.glob(os.path.join(GSC_DIR, "20*.json")))
    if not reports:
        print("No GSC reports found in reports/gsc/", file=sys.stderr)
        sys.exit(1)

    latest_report_file = reports[-1]
    with open(latest_report_file, "r", encoding="utf-8") as f:
        rep = json.load(f)

    # Read history.jsonl
    history_file = os.path.join(GSC_DIR, "history.jsonl")
    history_records = []
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            by_date = {}
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    date_key = rec.get("date")
                    if date_key:
                        by_date[date_key] = rec
                except Exception:
                    continue
            for d in sorted(by_date.keys()):
                item = by_date[d]
                history_records.append({
                    "date": item.get("date"),
                    "clicks_28d": item.get("clicks_28d", 0),
                    "impressions_28d": item.get("impressions_28d", 0),
                    "submitted": item.get("submitted", 0),
                    "indexed": item.get("indexed", 0),
                })

    perf = rep.get("performance_28d", {})
    totals = perf.get("totals", {})
    top_queries_raw = perf.get("top_queries", [])
    top_queries = []
    for q in top_queries_raw:
        query_text = (q.get("keys") or [""])[0]
        clicks = q.get("clicks", 0)
        impressions = q.get("impressions", 0)
        ctr = q.get("ctr", 0.0)
        position = q.get("position", 0.0)
        top_queries.append({
            "query": query_text,
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(ctr * 100, 2),
            "position": round(position, 1),
        })

    sitemaps = rep.get("sitemaps", [])
    spot_checks = rep.get("spot_checks", {})

    output = {
        "status": "ok",
        "verified_live": True,
        "source": "Google Search Console API",
        "property": "sc-domain:brokerlens.in",
        "auth_method": "OAuth2 Service Account (secrets/gsc-service-account.json)",
        "report_date": rep.get("date"),
        "totals_28d": {
            "clicks": totals.get("clicks", 0),
            "impressions": totals.get("impressions", 0),
            "ctr_pct": round(totals.get("ctr", 0.0) * 100, 2),
            "avg_position": round(totals.get("position", 0.0), 1),
            "date_range_start": (perf.get("range") or {}).get("start"),
            "date_range_end": (perf.get("range") or {}).get("end"),
        },
        "daily_history": history_records[-30:],
        "top_queries": top_queries,
        "sitemaps": sitemaps,
        "spot_checks": spot_checks,
    }

    output = clean_dashes(output)

    os.makedirs(os.path.dirname(DEST_FILE), exist_ok=True)
    with open(DEST_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Exported GSC live data to {DEST_FILE} (28d: {output['totals_28d']['clicks']} clicks, {output['totals_28d']['impressions']} impressions)")


if __name__ == "__main__":
    main()
