"""Shared HTTP helpers for qa_e2e.py and vapt.py.

Production runs on Vercel static hosting: urllib's default User-Agent can trip
edge WAFs, and SPA rewrites serve index.html for unknown paths. These helpers
detect that mode so active probes skip dev-server-only checks (SSE, /api/health)
and treat SPA fallbacks as blocked, not leaked secrets.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

# Match pipeline/common.py so probes look like a normal browser session.
QA_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# BrokerLens shell marker (index.html uses <main id="app">, not a div).
SPA_SHELL_RE = re.compile(rb'id=["\']app["\']', re.I)

# POST responses that mean "no write surface" on static CDN or dev server.
REFUSED_POST_CODES = frozenset({403, 404, 405})


def http(url, method="GET", data=None, headers=None, timeout=10, retries=2):
    hdrs = {"User-Agent": QA_UA}
    if headers:
        hdrs.update(headers)
    last = (0, b"", {})
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                last = (r.status, r.read(), dict(r.headers))
        except urllib.error.HTTPError as e:
            last = (e.code, e.read(), dict(e.headers))
        except Exception as e:
            last = (0, str(e).encode(), {})
        code = last[0]
        if method == "GET" and code == 403 and attempt < retries:
            time.sleep(0.4 * (attempt + 1))
            continue
        return last
    return last


def is_spa_shell(body: bytes) -> bool:
    return bool(body) and bool(SPA_SHELL_RE.search(body))


def _health_is_live(body: bytes) -> bool:
    try:
        import json
        data = json.loads(body.decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return body.strip() in (b"ok", b'"ok"')


def detect_static_host(base: str) -> bool:
    """True when the target is a static CDN (no devserver API/SSE).

    Vercel rewrites unknown paths to index.html and has no /api/health or SSE.
    """
    base = base.rstrip("/")

    code, body, headers = http(base + "/api/stream",
                               headers={"Accept": "text/event-stream"}, timeout=8)
    ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
    if "text/event-stream" in ctype:
        return False
    if is_spa_shell(body):
        return True

    code, body, headers = http(base + "/api/health", timeout=8)
    if code == 200 and _health_is_live(body):
        return False

    server = {k.lower(): v for k, v in headers.items()}.get("server", "").lower()
    if "vercel" in server:
        return True

    from urllib.parse import urlparse
    host = (urlparse(base).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return False
    return code != 200 or is_spa_shell(body)
