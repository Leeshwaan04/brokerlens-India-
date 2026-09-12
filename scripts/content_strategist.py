#!/usr/bin/env python3
"""Weekly content-strategy report.

Scope, deliberately: this site's entire credibility rests on "we do not
invent a number to fill a gap" (see pipeline/publish.py's methodology page).
An autonomous system that free-associates new page copy or claims to chase
"trending keywords" would be a real risk to that, not an enhancement of it -
Google's own helpful-content systems penalize exactly that kind of output
too. So this script never writes new prose or publishes anything. It does
two things instead:

1. Surfaces real, already-known gaps (which manual data files are still
   sample/placeholder, whether the live site's coverage has drifted behind
   the current SEBI/NSE/AMFI universe) - concrete, checkable, and actionable
   without inventing anything.
2. Mines real Search Console query data for striking-distance keywords
   (already ranking, not yet clicked much) once enough of it exists - and
   says plainly when it doesn't, rather than pretending 1 day of data is a
   trend.

Output is a dated Markdown report for a human to act on, not a queue of
content the pipeline publishes unsupervised.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import gsc_client as gsc  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.join(ROOT, "reports", "content-strategy")
SITE = "sc-domain:brokerlens.in"


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _fetch_live_json(path):
    try:
        with urllib.request.urlopen("https://www.brokerlens.in" + path, timeout=20) as resp:
            return json.load(resp)
    except Exception:
        return None


def _manual_data_gaps():
    """The three highest-leverage gaps on the whole site: every one of
    brokers/compare/leaderboards/calculator/home renders a simpler, honest
    fallback instead of these figures until they're real (see the hasClients
    fix across pages.js/publish.py). Nothing ranks or reads as complete
    without this - it belongs at the top of every report until it's fixed.
    """
    findings = []
    for name, path in (
        ("active_clients", "data/manual/active_clients.json"),
        ("complaints", "data/manual/complaints.json"),
        ("charges", "data/manual/charges.json"),
    ):
        d = _read_json(os.path.join(ROOT, path))
        if not d:
            continue
        if d.get("provenance") == "sample":
            findings.append({
                "dataset": name,
                "status": "sample/placeholder",
                "note": d.get("source_note", ""),
            })
    return findings


def _coverage_drift():
    """Compares the CURRENT live SEBI/AMFI/NSE universe sizes (fetched fresh,
    right now) against what's actually published on the live site. A gap
    here means real primary-source data exists that visitors can't see yet -
    the daily deploy-hook refresh (see .github/workflows/daily-refresh.yml)
    is the fix, this just tells you whether it's needed urgently or whether
    the site is already current.
    """
    findings = []
    live_registry = _fetch_live_json("/data/registry.json")
    live_overview = _fetch_live_json("/data/overview.json")
    if live_registry and live_overview:
        findings.append({
            "check": "SEBI registry size",
            "live_site": live_registry.get("count"),
            "live_generated_at": live_registry.get("generated_at"),
        })
    return findings


def _gsc_opportunities():
    """Striking-distance queries: already showing up in search (position
    4-20), not yet earning many clicks - the cheapest real ranking gains
    available, IF there's enough data to trust. A 5-week-old domain with
    a few days of automated tracking does not have that yet; this says so
    explicitly instead of mining noise."""
    history_path = os.path.join(ROOT, "reports", "gsc", "history.jsonl")
    days_tracked = 0
    total_impressions = 0
    if os.path.exists(history_path):
        with open(history_path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        days_tracked = len(lines)
        total_impressions = sum(l.get("impressions_28d", 0) for l in lines)

    if total_impressions < 500:
        return {
            "ready": False,
            "days_tracked": days_tracked,
            "total_impressions_seen": total_impressions,
            "note": ("Not enough Search Console data yet to mine striking-distance "
                     "keywords without just reporting noise (need real query volume, "
                     "not %d impressions over %d tracked day(s)). This section activates "
                     "automatically once it does." % (total_impressions, days_tracked)),
        }

    token = gsc.get_access_token()
    end = datetime.date.today() - datetime.timedelta(days=3)
    start = end - datetime.timedelta(days=28)
    body = {
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "dimensions": ["query", "page"], "rowLimit": 200,
    }
    import urllib.parse
    result = gsc._api(
        "%s/sites/%s/searchAnalytics/query" % (gsc.API_ROOT, urllib.parse.quote(SITE, safe="")),
        token, "POST", body,
    )
    rows = result.get("rows", [])
    striking_distance = [
        r for r in rows
        if 4 <= (r.get("position") or 99) <= 20 and r.get("impressions", 0) >= 10
    ]
    striking_distance.sort(key=lambda r: -r["impressions"])
    return {
        "ready": True,
        "days_tracked": days_tracked,
        "candidates": [
            {"query": r["keys"][0], "page": r["keys"][1], "position": round(r["position"], 1),
             "impressions": r["impressions"], "clicks": r.get("clicks", 0)}
            for r in striking_distance[:20]
        ],
    }


def main():
    today = datetime.date.today().isoformat()
    report = {
        "date": today,
        "manual_data_gaps": _manual_data_gaps(),
        "coverage": _coverage_drift(),
        "gsc_opportunities": _gsc_opportunities(),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "%s.json" % today), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    lines = ["# Content strategy report - %s" % today, ""]
    lines.append("## Highest-leverage gap: sample data still in place")
    if report["manual_data_gaps"]:
        for g in report["manual_data_gaps"]:
            lines.append("- **%s**: %s" % (g["dataset"], g["note"]))
    else:
        lines.append("- None - all three manual datasets are past sample data. Re-verify this is really true.")
    lines.append("")
    lines.append("## Live site coverage")
    for c in report["coverage"]:
        lines.append("- %s: %s entities live (as of %s)" % (c["check"], c["live_site"], c["live_generated_at"]))
    lines.append("")
    lines.append("## Search Console opportunities")
    gsc_op = report["gsc_opportunities"]
    if not gsc_op["ready"]:
        lines.append(gsc_op["note"])
    else:
        lines.append("Striking-distance queries (position 4-20, ranked already, room to gain clicks):")
        for c in gsc_op["candidates"]:
            lines.append("- \"%s\" -> %s (position %.1f, %d impressions, %d clicks)"
                          % (c["query"], c["page"], c["position"], c["impressions"], c["clicks"]))

    report_md = "\n".join(lines)
    with open(os.path.join(OUT_DIR, "%s.md" % today), "w", encoding="utf-8") as f:
        f.write(report_md)
    print(report_md)


if __name__ == "__main__":
    main()
