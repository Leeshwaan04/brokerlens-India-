#!/usr/bin/env python3
"""Generate Cloudflare Pages _redirects and _headers from vercel.json.

Ensures all redirects, CSP, HSTS, X-Robots-Tag, and cache rules
function natively on Cloudflare Pages without em or en dashes.
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    vj_path = os.path.join(ROOT, "vercel.json")
    site_dir = os.path.join(ROOT, "site")
    if not os.path.isfile(vj_path) or not os.path.isdir(site_dir):
        return

    with open(vj_path, "r", encoding="utf-8") as f:
        v = json.load(f)

    # 1. _redirects
    # Cloudflare Pages limits: max 2,000 static redirects, max 100 dynamic redirects.
    # Static redirects require 301 or 302 (308 is counted as dynamic by Cloudflare).
    # Expanding regex alternations into explicit static rules keeps dynamic count < 30.
    r_lines = [
        "# Cloudflare Pages Redirects",
        "# Auto-generated from vercel.json",
        "",
    ]
    static_count = 0
    dynamic_count = 0

    for r in v.get("redirects", []):
        src = r.get("source", "")
        dst = r.get("destination", "")
        perm = r.get("permanent", True)
        status = 301 if perm else 302

        if not src or not dst:
            continue

        # Expand regex groups like :param(a|b|c) into static lines
        m = re.search(r":([a-zA-Z0-9_]+)\(([^)]+)\)", src)
        if m:
            param_name = m.group(1)
            options = m.group(2).split("|")
            for opt in options:
                sub_src = src.replace(m.group(0), opt)
                sub_dst = dst.replace(f":{param_name}", opt)
                sub_src = re.sub(r":year", "2026", sub_src)
                sub_src = sub_src.replace("(.*)", "*")
                sub_dst = sub_dst.replace("(.*)", ":splat")
                if "*" in sub_src or ":" in sub_src:
                    dynamic_count += 1
                else:
                    static_count += 1
                r_lines.append(f"{sub_src} {sub_dst} {status}")
        else:
            sub_src = src.replace("(.*)", "*")
            sub_dst = dst.replace("(.*)", ":splat")
            sub_src = re.sub(r":year", "2026", sub_src)
            if "*" in sub_src or ":" in sub_src:
                dynamic_count += 1
            else:
                static_count += 1
            r_lines.append(f"{sub_src} {sub_dst} {status}")

    redirects_path = os.path.join(site_dir, "_redirects")
    with open(redirects_path, "w", encoding="utf-8") as f:
        f.write("\n".join(r_lines) + "\n")
    print(
        f"[cloudflare] Wrote {len(r_lines) - 3} redirects ({static_count} static, "
        f"{dynamic_count} dynamic) to {redirects_path}"
    )

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
