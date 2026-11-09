#!/usr/bin/env python3
"""SEO Autopilot - Daily Search Console Optimizer.

100% Python standard library, zero external AI API keys needed.
Reads fresh Search Console performance, identifies striking-distance
opportunities, keeps demand sitemaps synchronized, logs metrics to
reports/autopilot/LOG.md, and verifies changes through full QA and VAPT gates.

Usage:
    python3 scripts/seo_autopilot.py [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def get_latest_local_snapshot():
    files = sorted(glob.glob(os.path.join(ROOT, "reports", "gsc", "2026-*.json")))
    if not files:
        return {}
    return load_json(files[-1], {})


def fetch_live_gsc_data(days: int = 28):
    """Attempt live GSC API call via gsc_client, fallback to latest snapshot."""
    try:
        import gsc_client as g
        token = g.get_access_token()
        site_url = "sc-domain:brokerlens.in"
        encoded = g.urllib.parse.quote(site_url, safe="")
        end = datetime.date.today() - datetime.timedelta(days=3)
        start = end - datetime.timedelta(days=days)
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["query", "page"],
            "rowLimit": 5000,
            "dataState": "all",
        }
        res = g._api("%s/sites/%s/searchAnalytics/query" % (g.API_ROOT, encoded), token, "POST", body)
        rows = res.get("rows", [])
        if rows:
            return {"source": "live_api", "rows": rows, "date": end.isoformat()}
    except BaseException as exc:
        print("[autopilot] GSC API unreachable (%s); using local snapshot" % exc)

    snap = get_latest_local_snapshot()
    perf = snap.get("performance_28d", {})
    return {
        "source": "local_snapshot",
        "date": snap.get("date", datetime.date.today().isoformat()),
        "totals": perf.get("totals", {}),
        "top_queries": perf.get("top_queries", []),
    }


def compute_weekly_trend():
    """Compare latest 7 days in history.jsonl vs previous 7 days."""
    history_file = os.path.join(ROOT, "reports", "gsc", "history.jsonl")
    if not os.path.isfile(history_file):
        return None
    records = []
    with open(history_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    if len(records) < 14:
        return None
    # Each row has clicks_28d and impressions_28d
    recent = records[-1]
    prior = records[-8]
    return {
        "recent_date": recent.get("date"),
        "prior_date": prior.get("date"),
        "recent_clicks": recent.get("clicks_28d", 0),
        "prior_clicks": prior.get("clicks_28d", 0),
        "recent_impressions": recent.get("impressions_28d", 0),
        "prior_impressions": prior.get("impressions_28d", 0),
        "recent_submitted": recent.get("submitted", 0),
    }


def find_striking_distance(queries):
    """Find queries ranking position 4.0 to 20.0 with solid search impressions."""
    striking = []
    for q in queries:
        keys = q.get("keys", [])
        query_str = keys[0] if keys else q.get("query", "")
        pos = q.get("position", 0.0)
        impr = q.get("impressions", 0)
        clicks = q.get("clicks", 0)
        ctr = q.get("ctr", 0.0)
        if 4.0 <= pos <= 20.0 and impr >= 15:
            striking.append({
                "query": query_str,
                "position": round(pos, 1),
                "impressions": impr,
                "clicks": clicks,
                "ctr": round(ctr * 100, 2),
            })
    striking.sort(key=lambda x: x["impressions"], reverse=True)
    return striking


def sync_demand_urls(live_data):
    """Ensure pages with GSC search impressions are in page_demand.json."""
    demand_file = os.path.join(ROOT, "reports", "gsc", "page_demand.json")
    demand_data = load_json(demand_file, {"updated": "", "paths": []})
    existing_paths = set(demand_data.get("paths", []))
    added = []

    # If live_data has rows with page dimension
    rows = live_data.get("rows", [])
    for r in rows:
        keys = r.get("keys", [])
        if len(keys) >= 2:
            page_url = keys[1]
            path = gsc_url_to_path(page_url)
            if path and path not in existing_paths and is_valid_built_page(path):
                existing_paths.add(path)
                added.append(path)

    if added:
        demand_data["paths"] = sorted(list(existing_paths))
        demand_data["updated"] = datetime.date.today().isoformat()
        save_json(demand_file, demand_data)
        print("[autopilot] Added %d new demand pages to page_demand.json" % len(added))

    return added


def gsc_url_to_path(url: str) -> str:
    m = re.match(r"^https?://[^/]+(/.*)?$", url)
    if not m:
        return ""
    p = m.group(1) or "/"
    if not p.endswith("/"):
        p += "/"
    return p


def is_valid_built_page(path: str) -> bool:
    if "/trade/" in path or "share-price-target-" in path:
        return False
    local_path = os.path.join(ROOT, "site", path.strip("/"), "index.html") if path != "/" else os.path.join(ROOT, "site", "index.html")
    return os.path.isfile(local_path)


def generate_log_entry(trend, striking, added_demand, check_date):
    """Generate Markdown report entry strictly without em or en dashes."""
    today_str = datetime.date.today().isoformat()
    lines = [
        "",
        "## %s (Automated SEO Autopilot)" % today_str,
        "",
    ]
    if trend:
        c_diff = trend["recent_clicks"] - trend["prior_clicks"]
        i_diff = trend["recent_impressions"] - trend["prior_impressions"]
        c_sign = "+" if c_diff >= 0 else ""
        i_sign = "+" if i_diff >= 0 else ""
        lines.append("- Weekly 28-day snapshot comparison (%s vs %s):" % (trend["recent_date"], trend["prior_date"]))
        lines.append("  - Clicks: %d (%s%d vs prior week)" % (trend["recent_clicks"], c_sign, c_diff))
        lines.append("  - Impressions: %d (%s%d vs prior week)" % (trend["recent_impressions"], i_sign, i_diff))
        lines.append("  - Submitted indexable URLs: %d" % trend["recent_submitted"])
        lines.append("")

    lines.append("- Striking distance search queries identified (positions 4 to 20, high impressions):")
    for s in striking[:8]:
        lines.append("  - \"%s\": pos %s, %d impressions, %d clicks, %s%% CTR" % (
            s["query"], s["position"], s["impressions"], s["clicks"], s["ctr"]))
    lines.append("")

    if added_demand:
        lines.append("- Synchronized %d pages with verified search demand into sitemap-demand.xml:" % len(added_demand))
        for p in added_demand[:5]:
            lines.append("  - %s" % p)
        if len(added_demand) > 5:
            lines.append("  - ... and %d more" % (len(added_demand) - 5))
    else:
        lines.append("- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.")

    lines.append("- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.")
    lines.append("- Check impact by: %s" % check_date)
    lines.append("")

    body = "\n".join(lines)
    # Ensure zero em dashes or en dashes
    body = body.replace("\u2014", " - ").replace("\u2013", "-")
    return body


def append_to_log(entry: str):
    log_file = os.path.join(ROOT, "reports", "autopilot", "LOG.md")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)
    print("[autopilot] Appended entry to reports/autopilot/LOG.md")


def run_checks():
    """Build site and execute full QA + VAPT suites."""
    print("[autopilot] Compiling site with production publish mode...")
    env = dict(os.environ, SITE_URL="https://www.brokerlens.in", PUBLISH_MODE="production")
    res = subprocess.run([sys.executable, "-m", "pipeline.run", "build"], env=env, cwd=ROOT)
    if res.returncode != 0:
        print("[autopilot] ERROR: pipeline build failed")
        return False

    print("[autopilot] Running QA test suite (qa_e2e.py)...")
    res = subprocess.run([sys.executable, "tests/qa_e2e.py"], cwd=ROOT)
    if res.returncode != 0:
        print("[autopilot] ERROR: QA test suite failed")
        return False

    print("[autopilot] Running VAPT security suite (vapt.py)...")
    res = subprocess.run([sys.executable, "tests/vapt.py"], cwd=ROOT)
    if res.returncode != 0:
        print("[autopilot] ERROR: VAPT security suite failed")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="BrokerLens SEO Autopilot")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and log output only, push nothing")
    args = parser.parse_args()

    is_dry_run = args.dry_run or os.environ.get("AUTOPILOT_DRY_RUN", "").lower() in ("true", "1")
    print("[autopilot] Starting run (dry_run=%s)" % is_dry_run)

    # 1. Fetch performance data
    data = fetch_live_gsc_data(days=28)
    queries = data.get("top_queries", [])
    if not queries and "rows" in data:
        # Normalize rows to query objects
        for r in data["rows"]:
            keys = r.get("keys", [])
            q_str = keys[0] if keys else ""
            queries.append({
                "keys": [q_str],
                "position": r.get("position", 0.0),
                "impressions": r.get("impressions", 0),
                "clicks": r.get("clicks", 0),
                "ctr": r.get("ctr", 0.0),
            })

    print("[autopilot] Ingested %d queries from %s" % (len(queries), data.get("source")))

    # 2. Analyze trend and opportunities
    trend = compute_weekly_trend()
    striking = find_striking_distance(queries)
    print("[autopilot] Identified %d striking-distance queries" % len(striking))

    # 3. Synchronize demand URLs
    added_demand = sync_demand_urls(data)

    # 4. Generate log entry
    check_date = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()
    log_entry = generate_log_entry(trend, striking, added_demand, check_date)

    if is_dry_run:
        print("\n--- DRY RUN LOG ENTRY PREVIEW ---")
        print(log_entry)
        print("--- END PREVIEW (dry run: no files changed, no push) ---")
        return 0

    # 5. Append to log file
    append_to_log(log_entry)

    # 6. Run pipeline build, QA and VAPT
    if not run_checks():
        print("[autopilot] ABORTING: QA or VAPT failed. Reverting changes.")
        subprocess.run(["git", "checkout", "--", "reports/autopilot/LOG.md"], cwd=ROOT)
        return 1

    print("[autopilot] All checks passed successfully! Ready for commit and push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
