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
    # Cloudflare Pages / Workers rules ordering requirement:
    # Any rule encountered after a dynamic rule (wildcard or placeholder) is treated as dynamic.
    # Therefore, all static rules MUST precede all dynamic rules.
    # Cloudflare limits: max 2,000 static redirects, max 100 dynamic redirects.
    # Cloudflare's _redirects supports 301, 302, 303, 307 and 308
    # (developers.cloudflare.com/workers/static-assets/redirects/), so this uses the same
    # codes Vercel's own redirect() does for the same `permanent` flag (308, not 301: this
    # project's hard rule is "add a 308" when retiring a page, and a 301 lets a client
    # silently turn a POST into a GET, which 308 does not).
    static_rules = []
    dynamic_rules = []

    for r in v.get("redirects", []):
        src = r.get("source", "")
        dst = r.get("destination", "")
        perm = r.get("permanent", True)
        status = 308 if perm else 307

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
                sub_src = sub_src.replace("(.*)", "*")
                sub_dst = sub_dst.replace("(.*)", ":splat")
                if ":year" in sub_src:
                    for y in ("2026", "2027", "2028", "2030"):
                        y_src = re.sub(r":year", y, sub_src)
                        line = f"{y_src} {sub_dst} {status}"
                        if "*" in y_src or ":" in y_src:
                            dynamic_rules.append(line)
                        else:
                            static_rules.append(line)
                else:
                    line = f"{sub_src} {sub_dst} {status}"
                    if "*" in sub_src or ":" in sub_src:
                        dynamic_rules.append(line)
                    else:
                        static_rules.append(line)
        else:
            sub_src = src.replace("(.*)", "*")
            sub_dst = dst.replace("(.*)", ":splat")
            if ":year" in sub_src:
                for y in ("2026", "2027", "2028", "2029", "2030", "2035", "2040", "2050"):
                    y_src = re.sub(r":year", y, sub_src)
                    line = f"{y_src} {sub_dst} {status}"
                    if "*" in y_src or ":" in y_src:
                        dynamic_rules.append(line)
                    else:
                        static_rules.append(line)
            else:
                line = f"{sub_src} {sub_dst} {status}"
                if "*" in sub_src or ":" in sub_src:
                    dynamic_rules.append(line)
                else:
                    static_rules.append(line)

    r_lines = [
        "# Cloudflare Pages Redirects",
        "# Auto-generated from vercel.json",
        "# Static redirects must precede dynamic redirects to stay within Cloudflare limits",
        "",
        "# Static Redirects",
    ]
    r_lines.extend(static_rules)
    r_lines.append("")
    r_lines.append("# Dynamic Redirects")
    r_lines.extend(dynamic_rules)

    redirects_path = os.path.join(site_dir, "_redirects")
    with open(redirects_path, "w", encoding="utf-8") as f:
        f.write("\n".join(r_lines) + "\n")
    print(
        f"[cloudflare] Wrote {len(static_rules) + len(dynamic_rules)} redirects "
        f"({len(static_rules)} static, {len(dynamic_rules)} dynamic) to {redirects_path}"
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
