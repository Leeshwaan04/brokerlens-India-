#!/usr/bin/env python3
"""Tell IndexNow search engines (Bing, Yandex, Seznam; ChatGPT search and Copilot
read Bing's index) which pages are new or likely changed, right after a deploy.

Two steps, so the diff is taken against what was live before the deploy:

  python3 scripts/indexnow_ping.py snapshot   # before deploy: save live sitemap URLs
  python3 scripts/indexnow_ping.py ping       # after a successful deploy

`ping` submits (a) URLs in the freshly built sitemaps that were not in the live
snapshot, and (b) entries marked <changefreq>daily</changefreq> (hubs, broker
profiles, open and upcoming IPOs), which change every trading day. Without a
snapshot it submits every sitemap URL once, capped at the API's 10,000 per call.

Stdlib only. Reads the live sitemaps with a handful of sequential GETs; never
crawls pages. Exits 0 on network errors so a ping problem never fails a deploy.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_URL = os.environ.get("SITE_URL", "https://www.brokerlens.in").rstrip("/")
HOST = re.sub(r"^https?://", "", SITE_URL)
SNAPSHOT = os.environ.get("INDEXNOW_SNAPSHOT", "/tmp/brokerlens-live-sitemap-urls.json")
ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10000
UA = "BrokerLens-IndexNow/1.0"

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_URL = re.compile(r"<url>(.*?)</url>", re.S)


def _key():
    with open(os.path.join(ROOT, "pipeline", "publish.py"), encoding="utf-8") as fh:
        m = re.search(r'^INDEXNOW_KEY = "([0-9a-f]{32})"', fh.read(), re.M)
    if not m:
        sys.exit("INDEXNOW_KEY not found in pipeline/publish.py")
    return m.group(1)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _local_entries():
    """(url, is_daily) for every <url> in the sitemaps the built index lists."""
    site = os.path.join(ROOT, "site")
    with open(os.path.join(site, "sitemap.xml"), encoding="utf-8") as fh:
        shards = _LOC.findall(fh.read())
    out = []
    for shard in shards:
        rel = shard.replace(SITE_URL, "").lstrip("/")
        path = os.path.join(site, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for block in _URL.findall(fh.read()):
                loc = _LOC.search(block)
                if loc:
                    out.append((loc.group(1), "<changefreq>daily</changefreq>" in block))
    return out


def snapshot():
    urls = set()
    try:
        for shard in _LOC.findall(_get(SITE_URL + "/sitemap.xml")):
            urls.update(_LOC.findall(_get(shard)))
            time.sleep(0.5)
    except Exception as exc:  # live site unreachable: ping will fall back to "submit all"
        print("snapshot skipped: %s" % exc)
        return 0
    with open(SNAPSHOT, "w") as fh:
        json.dump(sorted(urls), fh)
    print("snapshot: %d live sitemap URLs saved to %s" % (len(urls), SNAPSHOT))
    return 0


def ping(dry_run=False):
    key = _key()
    entries = _local_entries()
    live = None
    if os.path.isfile(SNAPSHOT):
        with open(SNAPSHOT) as fh:
            live = set(json.load(fh))
    if live:
        new = [u for u, _ in entries if u not in live]
        daily = [u for u, d in entries if d and u in live]
        urls = list(dict.fromkeys(new + daily))
        print("ping: %d new URLs, %d daily-changing URLs" % (len(new), len(daily)))
    else:
        urls = list(dict.fromkeys(u for u, _ in entries))
        print("ping: no snapshot, submitting all %d sitemap URLs" % len(urls))
    urls = [u for u in urls if u.startswith(SITE_URL + "/")][:MAX_URLS]
    if not urls:
        print("ping: nothing to submit")
        return 0
    body = json.dumps({"host": HOST, "key": key, "keyLocation": "%s/%s.txt" % (SITE_URL, key),
                       "urlList": urls}).encode()
    if dry_run:
        print("dry run: would submit %d URLs, first: %s" % (len(urls), urls[0]))
        return 0
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print("IndexNow: HTTP %s for %d URLs" % (r.status, len(urls)))
    except urllib.error.HTTPError as exc:
        # 202 = accepted pending key check; 403 = key file not reachable yet; 422 = URL/host mismatch; 429 = too many
        print("IndexNow: HTTP %s %s" % (exc.code, exc.read()[:200].decode("utf-8", "replace")))
    except Exception as exc:
        print("IndexNow: request failed: %s" % exc)
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "snapshot":
        sys.exit(snapshot())
    if cmd == "ping":
        sys.exit(ping(dry_run="--dry-run" in sys.argv))
    sys.exit(__doc__)
