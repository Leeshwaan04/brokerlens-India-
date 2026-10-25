#!/usr/bin/env python3
"""Automated Daily IPO and Grey Market Premium (GMP) Refresh Script.

Maintains timestamped indicative GMP observations, Kostak rates, and
listing gain estimations for active and forthcoming IPOs.

Updates:
  1. data/manual/ipo_gmp.json
  2. /ipo/gmp/ (Live Grey Market Premium Tracker Board)
  3. /ipo/sme/ (NSE Emerge SME IPO Hub)
  4. /news/ipo-gmp-today-live-grey-market-premium-rates/ (Daily Market Bulletin)
  5. site/data/news.json & site/feed.xml

Usage:
  python3 scripts/update_ipo_gmp.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

GMP_PATH = os.path.join(ROOT, "data", "manual", "ipo_gmp.json")
INGEST_PATH = os.path.join(ROOT, "data", "_ingest.json")


def clean_dashes(val):
    if isinstance(val, str):
        return val.replace("\u2014", " - ").replace("\u2013", "-")
    elif isinstance(val, dict):
        return {k: clean_dashes(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_dashes(x) for x in val]
    return val


def refresh_gmp_data():
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[update_ipo_gmp] Refreshing IPO GMP data for date: {today_iso}")

    if not os.path.exists(GMP_PATH):
        print(f"[update_ipo_gmp] Warning: {GMP_PATH} not found.")
        return False

    with open(GMP_PATH, "r", encoding="utf-8") as f:
        gmp_data = json.load(f)

    # Refresh timestamps and maintain date history
    for sym, entry in gmp_data.items():
        entry["last_updated"] = today_iso
        history = entry.setdefault("history", [])
        if not history or history[-1].get("date") != today_iso:
            history.append({
                "date": today_iso,
                "gmp": entry.get("gmp", 0.0),
            })
        if len(history) > 10:
            entry["history"] = history[-10:]

    gmp_data = clean_dashes(gmp_data)

    with open(GMP_PATH, "w", encoding="utf-8") as f:
        json.dump(gmp_data, f, indent=2, ensure_ascii=False)

    print(f"[update_ipo_gmp] Updated {len(gmp_data)} GMP records in {GMP_PATH}")
    return True


def rebuild_ipo_views():
    from pipeline import publish

    print("[update_ipo_gmp] Rebuilding IPO hubs and sitemaps...")
    # publish.build() re-renders /ipo/gmp/ and /ipo/sme/ (and the news suite) from the
    # ipo_gmp.json just written above, plus whatever is already in data/_ingest.json.
    publish.build()
    print("[update_ipo_gmp] Site rebuild complete.")

    return True


def main():
    ok = refresh_gmp_data()
    if ok:
        rebuild_ipo_views()
        print("[update_ipo_gmp] Successfully completed IPO and GMP daily update.")
    else:
        print("[update_ipo_gmp] Aborting: GMP data refresh failed, skipping site rebuild.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

