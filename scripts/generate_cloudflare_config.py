#!/usr/bin/env python3
"""Generate Cloudflare Pages _redirects and _headers from vercel.json.

Ensures all 308 redirects, CSP, HSTS, X-Robots-Tag, and cache rules
function natively on Cloudflare Pages without em or en dashes.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    vj_path = os.path.join(ROOT, "vercel.json")
    site_dir = os.path.join(ROOT, "site")
    if not os.path.isfile(vj_path) or not os.path.isdir(site_dir):
        return

    with open(vj_path, "r", encoding="utf-8") as f:
        v = json.load(f)

    # 1. _redirects
    r_lines = [
        "# Cloudflare Pages Redirects",
        "# Auto-generated from vercel.json",
        "",
    ]
    for r in v.get("redirects", []):
        src = r.get("source", "")
        dst = r.get("destination", "")
        status = 308 if r.get("permanent") else 302
        if src and dst:
            r_lines.append(f"{src} {dst} {status}")

    redirects_path = os.path.join(site_dir, "_redirects")
    with open(redirects_path, "w", encoding="utf-8") as f:
        f.write("\n".join(r_lines) + "\n")
    print(f"[cloudflare] Wrote {len(v.get('redirects', []))} redirects to {redirects_path}")

    # 2. _headers
    h_lines = [
        "# Cloudflare Pages Headers",
        "# Auto-generated from vercel.json",
        "",
    ]
    for h in v.get("headers", []):
        src = h.get("source", "/*")
        # Translate Vercel route syntax to Cloudflare Pages splat syntax
        src = src.replace("(.*)", "*").replace(":broker", "*")
        h_lines.append(src)
        for kv in h.get("headers", []):
            h_lines.append(f"  {kv['key']}: {kv['value']}")
        h_lines.append("")

    headers_path = os.path.join(site_dir, "_headers")
    with open(headers_path, "w", encoding="utf-8") as f:
        f.write("\n".join(h_lines) + "\n")
    print(f"[cloudflare] Wrote headers to {headers_path}")


if __name__ == "__main__":
    main()
