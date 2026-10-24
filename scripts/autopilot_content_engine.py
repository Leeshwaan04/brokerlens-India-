#!/usr/bin/env python3
"""CLI & Autonomous Scheduler for Autopilot Content Generation & Expansion.

Mines latest search query trends from Google Search Console, generates
high-intent research and valuation articles, compiles the news hub,
updates RSS and sitemaps, and validates with QA tests.

Usage:
  python3 scripts/autopilot_content_engine.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline.autopilot_keyword_engine import run_autopilot


def main():
    print("[autopilot_content] Running BrokerLens Autopilot Growth & Content Engine...")
    count = run_autopilot()
    print(f"[autopilot_content] Autopilot generation complete. Total active publications: {count}")


if __name__ == "__main__":
    main()

