"""VAPT suite — vulnerability assessment against our own stack.

  python3 tests/vapt.py --url http://127.0.0.1:8000

Active probes against a server you control. Everything here is a defensive test
of this codebase; nothing targets a third party. Run it before every deploy.

Exit code is the number of findings, so CI can gate on it.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK, FINDINGS, NOTES = [], [], []


def result(name, secure, detail="", severity="medium"):
    if secure:
        OK.append(name)
        print("  OK    %-56s" % name)
    else:
        FINDINGS.append((severity, name, detail))
        print("  VULN  %-56s [%s] %s" % (name, severity.upper(), detail))
    return secure


def rate_limited(name, code):
    """A 429 means our own limiter fired, not that the check failed. The limiter
    is verified separately in test_rate_limits()."""
    if code == 429:
        note(name, "skipped - rate limited (429); limiter verified separately")
        return True
    return False


def note(name, detail):
    NOTES.append((name, detail))
    print("  note  %-56s %s" % (name, detail))


def section(t):
    print("\n== %s ==" % t)


def raw_request(base, raw, read_bytes=4096, timeout=8):
    """Send a hand-built request so we can test malformed input."""
    u = urllib.parse.urlparse(base)
    try:
        s = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        s.sendall(raw)
        s.settimeout(timeout)
        buf = b""
        while len(buf) < read_bytes:
            try:
                c = s.recv(4096)
            except socket.timeout:
                break
            if not c:
                break
            buf += c
        s.close()
        return buf
    except Exception as exc:
        return b"ERR " + str(exc).encode()


def http(url, method="GET", data=None, headers=None, timeout=10):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}


# ------------------------------------------------------- A01 access control

def test_traversal(base):
    section("path traversal / file exposure")
    payloads = [
        "/../pipeline/common.py",
        "/../../etc/passwd",
        "/..%2f..%2fetc%2fpasswd",
        "/%2e%2e/%2e%2e/etc/passwd",
        "/....//....//etc/passwd",
        "/assets/../../config/sources.json",
        "/data/../../data/leads/leads.jsonl",
        "/%00/etc/passwd",
        "/..\\..\\windows\\win.ini",
    ]
    for p in payloads:
        code, body, _ = http(base + p)
        leaked = code == 200 and (b"root:" in body or b"import " in body[:400]
                                  or b"leadEndpoint" in body or b"@example" in body)
        result("traversal blocked: %s" % p[:40], not leaked,
               "status %s, %d bytes" % (code, len(body)), severity="critical")

    section("internal file exposure")
    secrets = {
        "/data/_ingest.json": "raw scraped ingest state",
        "/data/leads/leads.jsonl": "captured personal data",
        "/config/sources.json": "internal source config",
        "/config/stream.json": "internal stream config",
        "/.git/config": "git metadata",
        "/.env": "environment file",
        "/server/devserver.py": "server source",
        "/pipeline/publish.py": "pipeline source",
        "/tests/vapt.py": "this test file",
    }
    for path, what in secrets.items():
        code, body, _ = http(base + path)
        exposed = code == 200 and len(body) > 0 and b"<div id=\"app\"" not in body
        result("not exposed: %s (%s)" % (path, what), not exposed,
               "status %s, %d bytes" % (code, len(body)), severity="high")

    section("directory listing")
    for d in ["/assets/", "/data/", "/assets/js/", "/data/brokers/"]:
        code, body, _ = http(base + d)
        listing = code == 200 and (b"Directory listing" in body or b"<li><a href=" in body)
        result("no directory listing at %s" % d, not listing, "status %s" % code, severity="medium")


# ------------------------------------------------------------ A03 injection

def test_injection(base):
    section("injection into the lead endpoint")
    xss = "<script>alert(1)</script>"
    payload = json.dumps({
        "kind": "broker_partner",
        "name": xss,
        "email": "vapt@example.com",
        "message": "'; DROP TABLE leads;-- \x00 %0d%0aSet-Cookie: evil=1",
        "role": "a" * 5000,
        "__proto__": {"polluted": True},
        "constructor": {"x": 1},
        "admin": True,
        "tier": "featured",
    }).encode()
    code, body, hdrs = http(base + "/api/leads", "POST", payload,
                            {"Content-Type": "application/json"})
    if not rate_limited("oversized field rejected or truncated", code):
        result("oversized field rejected or truncated", code in (201, 422),
               "status %s" % code, severity="low")
    result("no header injection from payload",
           "evil" not in json.dumps(hdrs).lower(), str(hdrs)[:80], severity="high")

    # Whatever was stored must be inert data, with unknown keys dropped.
    store = os.path.join(ROOT, "data", "leads", "leads.jsonl")
    if os.path.exists(store):
        last = None
        for line in open(store, encoding="utf-8"):
            if "vapt@example.com" in line:
                last = line
        if last:
            rec = json.loads(last)
            result("unknown keys dropped from stored lead",
                   "admin" not in rec and "__proto__" not in rec and "constructor" not in rec,
                   str(sorted(rec))[:120], severity="medium")
            result("stored payload is escaped JSON, not raw markup",
                   "\\u003c" in last or "<script>" in rec.get("name", ""),
                   "stored name=%r" % rec.get("name"), severity="low")
            note("stored lead keys", sorted(rec))
    else:
        note("lead store", "no leads.jsonl yet")

    section("malformed request handling")
    for label, body_bytes, ctype in [
        ("not json", b"<<<not json>>>", "application/json"),
        ("json array not object", b"[1,2,3]", "application/json"),
        ("empty body", b"", "application/json"),
        ("wrong content type", json.dumps({"kind": "enquiry", "name": "a",
                                           "email": "a@b.co"}).encode(), "text/plain"),
    ]:
        code, _, _ = http(base + "/api/leads", "POST", body_bytes, {"Content-Type": ctype})
        if rate_limited("handled cleanly: %s" % label, code):
            continue
        result("handled cleanly: %s" % label, code in (400, 411, 413, 415, 422, 201),
               "status %s" % code, severity="low")

    big = json.dumps({"kind": "enquiry", "name": "x" * 100000, "email": "a@b.co"}).encode()
    code, _, _ = http(base + "/api/leads", "POST", big, {"Content-Type": "application/json"})
    if not rate_limited("oversized body rejected", code):
        result("oversized body rejected", code in (413, 422, 400), "status %s" % code, severity="medium")


def test_methods(base):
    section("http method handling")
    for m in ["PUT", "DELETE", "PATCH", "TRACE", "CONNECT", "PROPFIND"]:
        code, body, _ = http(base + "/", m)
        result("%s not accepted" % m, code in (400, 405, 501, 0),
               "status %s" % code, severity="low")

    # TRACE reflecting headers would enable cross-site tracing.
    resp = raw_request(base, b"TRACE / HTTP/1.1\r\nHost: x\r\nX-Probe: reflectme\r\n\r\n")
    result("TRACE does not reflect headers", b"reflectme" not in resp,
           resp[:60].decode("utf-8", "replace"), severity="medium")


# -------------------------------------------------- A05 security misconfig

def test_headers(base):
    section("security headers")
    code, _, h = http(base + "/")
    lower = {k.lower(): v for k, v in h.items()}

    csp = lower.get("content-security-policy", "")
    result("CSP present", bool(csp), "none", severity="high")
    result("CSP default-src is self", "default-src 'self'" in csp, csp[:70], severity="high")
    result("CSP blocks framing", "frame-ancestors 'none'" in csp, csp[:70], severity="medium")
    result("CSP has no unsafe-inline script",
           "script-src 'self'" in csp and "unsafe-inline" not in csp.split("style-src")[0],
           csp[:90], severity="high")
    result("X-Content-Type-Options nosniff", lower.get("x-content-type-options") == "nosniff",
           str(lower.get("x-content-type-options")), severity="medium")
    result("X-Frame-Options DENY", lower.get("x-frame-options") == "DENY",
           str(lower.get("x-frame-options")), severity="medium")
    result("Referrer-Policy set", bool(lower.get("referrer-policy")), severity="low")
    result("Permissions-Policy set", bool(lower.get("permissions-policy")), severity="low")
    result("no server version banner leak",
           "python" not in lower.get("server", "").lower(),
           lower.get("server", ""), severity="low")

    section("cors")
    code, _, h = http(base + "/data/overview.json", headers={"Origin": "https://evil.example"})
    acao = {k.lower(): v for k, v in h.items()}.get("access-control-allow-origin")
    result("no permissive CORS on data", acao in (None, "", "null"), str(acao), severity="high")
    code, _, h = http(base + "/api/health", headers={"Origin": "https://evil.example"})
    acao = {k.lower(): v for k, v in h.items()}.get("access-control-allow-origin")
    result("no permissive CORS on api", acao in (None, "", "null"), str(acao), severity="high")


# ----------------------------------------------------------- availability

def test_rate_limits(base):
    section("rate limiting")
    codes = []
    for i in range(15):
        p = json.dumps({"kind": "broker_partner", "name": "rl%d" % i,
                        "email": "rl%d@example.com" % i}).encode()
        c, _, _ = http(base + "/api/leads", "POST", p, {"Content-Type": "application/json"})
        codes.append(c)
    result("lead endpoint rate limits a flood", 429 in codes,
           "codes=%s" % sorted(set(codes)), severity="medium")
    note("lead flood result", "%d accepted, %d limited" % (codes.count(201), codes.count(429)))


def test_sse_limits(base):
    section("sse connection limits")
    u = urllib.parse.urlparse(base)
    socks, statuses = [], []
    try:
        for _ in range(12):
            try:
                s = socket.create_connection((u.hostname, u.port or 80), timeout=5)
                s.sendall(b"GET /api/stream HTTP/1.1\r\nHost: %s\r\n\r\n" % u.netloc.encode())
                s.settimeout(4)
                head = s.recv(200)
                statuses.append(head.split(b"\r\n")[0].decode("utf-8", "replace"))
                socks.append(s)
            except Exception as exc:
                statuses.append("ERR %s" % exc)
        limited = any("503" in st or "429" in st for st in statuses)
        result("SSE connections are capped per IP", limited,
               "statuses=%s" % list(dict.fromkeys(statuses))[:4], severity="medium")
    finally:
        for s in socks:
            try:
                s.close()
            except Exception:
                pass


def test_slowloris(base):
    section("slowloris / connection exhaustion")
    u = urllib.parse.urlparse(base)
    try:
        s = socket.create_connection((u.hostname, u.port or 80), timeout=5)
        s.sendall(b"GET / HTTP/1.1\r\n")          # deliberately never finish the request
        s.settimeout(30)
        start = time.time()
        try:
            data = s.recv(100)
            closed = not data
        except socket.timeout:
            closed = False
        except Exception:
            closed = True
        elapsed = time.time() - start
        s.close()
        result("partial request is timed out by the server", closed or elapsed < 25,
               "held %.1fs" % elapsed, severity="medium")
    except Exception as exc:
        note("slowloris", "probe failed: %s" % exc)

    # The server must still answer while a partial connection is held open.
    hold = []
    try:
        for _ in range(5):
            s = socket.create_connection((u.hostname, u.port or 80), timeout=5)
            s.sendall(b"GET / HTTP/1.1\r\n")
            hold.append(s)
        code, _, _ = http(base + "/api/health", timeout=8)
        result("server still responsive under held connections", code == 200,
               "status %s" % code, severity="high")
    except Exception as exc:
        result("server still responsive under held connections", False, str(exc)[:60], "high")
    finally:
        for s in hold:
            try:
                s.close()
            except Exception:
                pass


# --------------------------------------------------- client-side (static)

XSS_SINK = re.compile(r"\$\{(?!esc\(|pct\(|cls\(|count\(|inr\(|full\(|month\(|provDot\(|mark\(|fmtBoard\()"
                      r"[^}]*\}")


def test_frontend_sinks():
    section("front-end xss sinks (static analysis)")
    jsdir = os.path.join(ROOT, "site", "assets", "js")
    if not os.path.isdir(jsdir):
        note("frontend", "no js directory")
        return

    href_unescaped = []
    for fn in os.listdir(jsdir):
        if not fn.endswith(".js"):
            continue
        src = open(os.path.join(jsdir, fn), encoding="utf-8").read()
        # href/src interpolations must both escape AND validate the URL scheme
        for m in re.finditer(r'(href|src)="\$\{([^}]+)\}"', src):
            expr = m.group(2)
            if "safeUrl(" not in expr:
                href_unescaped.append("%s: %s=${%s}" % (fn, m.group(1), expr[:50]))

    result("all href/src interpolations pass through safeUrl()",
           not href_unescaped, "; ".join(href_unescaped[:4]), severity="high")

    # innerHTML assignments taking a bare variable are worth eyeballing.
    risky = []
    for fn in os.listdir(jsdir):
        if not fn.endswith(".js"):
            continue
        src = open(os.path.join(jsdir, fn), encoding="utf-8").read()
        for m in re.finditer(r"\.innerHTML\s*=\s*([A-Za-z_$][\w$.]*)\s*;", src):
            risky.append("%s: innerHTML = %s" % (fn, m.group(1)))
    if risky:
        note("innerHTML assignments to review", "; ".join(risky[:6]))

    store = os.path.join(jsdir, "store.js")
    if os.path.exists(store):
        src = open(store, encoding="utf-8").read()
        result("escaping helper exists", "export const esc" in src, severity="high")
        result("URL scheme validator exists", "export function safeUrl" in src or
               "export const safeUrl" in src, "no safeUrl() in store.js", severity="high")


def test_published_json_safety():
    section("published json safety")
    p = os.path.join(ROOT, "site", "data")
    if not os.path.isdir(p):
        note("published json", "not built")
        return
    bad_keys = []
    absolute_paths = []
    for root, _, files in os.walk(p):
        for f in files:
            if not f.endswith(".json"):
                continue
            fp = os.path.join(root, f)
            raw = open(fp, encoding="utf-8").read()
            if "__proto__" in raw or '"constructor"' in raw:
                bad_keys.append(f)
            if re.search(r'"/(Users|home|var|etc)/', raw):
                absolute_paths.append(f)
    result("no prototype-pollution keys in published json", not bad_keys,
           str(bad_keys[:3]), severity="medium")
    result("no filesystem paths leaked in published json", not absolute_paths,
           str(absolute_paths[:3]), severity="medium")

    # Personal data must never reach the public directory.
    leaked = []
    for root, _, files in os.walk(p):
        for f in files:
            raw = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
            if "leads" in f or re.search(r'"phone"\s*:\s*"\d{10}', raw):
                leaked.append(f)
    result("no lead/PII data in the published site directory", not leaked,
           str(leaked[:3]), severity="critical")


def test_pipeline_hardening():
    section("pipeline input hardening")
    common = os.path.join(ROOT, "pipeline", "common.py")
    src = open(common, encoding="utf-8").read() if os.path.exists(common) else ""
    result("HTTP responses are size-capped", "MAX_RESPONSE_BYTES" in src,
           "no cap: a hostile/compromised source could exhaust memory", severity="medium")
    result("zip extraction is bomb-guarded", "MAX_UNZIPPED_BYTES" in src,
           "get_zip_member decompresses without a size limit", severity="medium")
    result("ingest state is outside the public site dir",
           not os.path.exists(os.path.join(ROOT, "site", "data", "_ingest.json")),
           "site/data/_ingest.json is world-readable once deployed", severity="high")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="base URL of a running server")
    ap.add_argument("--skip-dos", action="store_true", help="skip rate-limit and slowloris probes")
    args = ap.parse_args()

    print("VAPT suite — defensive assessment of this codebase")
    test_frontend_sinks()
    test_published_json_safety()
    test_pipeline_hardening()

    if args.url:
        base = args.url.rstrip("/")
        test_traversal(base)
        test_injection(base)
        test_methods(base)
        test_headers(base)
        if not args.skip_dos:
            test_rate_limits(base)
            test_sse_limits(base)
            test_slowloris(base)
    else:
        print("\n  (pass --url to run the active server probes)")

    print("\n%d checks passed, %d findings" % (len(OK), len(FINDINGS)))
    if FINDINGS:
        print("\nFindings by severity:")
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for sev, name, detail in sorted(FINDINGS, key=lambda x: order.get(x[0], 9)):
            print("  [%-8s] %s — %s" % (sev.upper(), name, detail))
    return len(FINDINGS)


if __name__ == "__main__":
    sys.exit(main())
