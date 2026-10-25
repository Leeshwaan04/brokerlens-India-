#!/usr/bin/env python3
"""Automated Real-Time News, Blogs & Articles Generation CLI.

Fetches live exchange disclosures (NSE Pulse, Indices, Live IPO subscriptions)
and compiles:
  1. Real-time Market Wraps and Sectoral Pulses (/news/indian-stock-market-wrap-*/)
  2. Live IPO Bidding Bulletins (/news/ipo-*-live-subscription-*/)
  3. Educational Blogs & Practical Investor Guides (/news/*-guide/)
  4. Empirical Research & Industry Analysis Articles (/news/*-study/)
  5. News Hub (/news/index.html) with category tabs and live search
  6. Client-Side JSON API Feed (site/data/news.json)
  7. RSS 2.0 Feed (site/feed.xml)

Usage:
  python3 scripts/generate_news.py         # Generate from existing ingested disclosures
  python3 scripts/generate_news.py --live  # Fetch live quotes & IPO data from NSE first
"""
import argparse
import os
import sys

# Ensure repository root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline.news_engine import run_live_generation, write_news_suite
import json


def main():
    parser = argparse.ArgumentParser(description="Generate real-time news, blogs and articles for BrokerLens")
    parser.add_argument("--live", action="store_true", help="Fetch live quotes and IPO subscription data from NSE")
    parser.add_argument("--site-url", default=os.getenv("SITE_URL", "https://www.brokerlens.in"), help="Site URL for canonicals")
    args = parser.parse_args()

    print("[generate_news] BrokerLens News & Blog Automation Engine starting...")
    if args.live:
        count = run_live_generation(args.site_url)
    else:
        ingest_path = os.path.join(ROOT, "data", "_ingest.json")
        ingest_data = {}
        if os.path.exists(ingest_path):
            with open(ingest_path, "r", encoding="utf-8") as f:
                ingest_data = json.load(f)
        count, _articles = write_news_suite(ingest_data, args.site_url)
        print("[generate_news] Compiled %d news articles, blogs and guides." % count)

    print("[generate_news] Completed successfully. Outputs updated:")
    print("  - Articles: site/news/<slug>/index.html")
    print("  - Hub:      site/news/index.html")
    print("  - JSON API: site/data/news.json")
    print("  - RSS Feed: site/feed.xml")


if __name__ == "__main__":
    main()
