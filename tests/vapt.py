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
        print("  OK    %-56s" % name, flush=True)
    else:
        FINDINGS.append((severity, name, detail))
        print("  VULN  %-56s [%s] %s" % (name, severity.upper(), detail), flush=True)
    return secure


def note(name, detail):
    NOTES.append((name, detail))
    print("  note  %-56s %s" % (name, detail), flush=True)


def section(t):
    print("\n== %s ==" % t, flush=True)


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
    """The site has no write endpoint, so the whole injection surface is absent.

    This used to fuzz POST /api/leads. That endpoint was removed along with all
    personal-data collection, so the strongest assertion available is that no
    POST is accepted anywhere and nothing is persisted.
    """
    section("write surface (should not exist)")

    probes = [
        ("lead endpoint", "/api/leads"),
        ("contact endpoint", "/api/contact"),
        ("site root", "/"),
        ("data path", "/data/overview.json"),
    ]
    for label, path in probes:
        code, _, _ = http(base + path, "POST", b'{"name":"x"}',
                          {"Content-Type": "application/json"})
        result("POST refused: %s" % label, code in (404, 405),
               "expected 404/405, got %s" % code, severity="high")

    # A cross-origin form post (text/plain is CORS-simple, so no preflight
    # protects it). Must be refused on the method, not on the body.
    code, _, _ = http(base + "/api/leads", "POST",
                      b'{"kind":"investor_enquiry","consent":true}',
                      {"Content-Type": "text/plain", "Origin": "https://evil.example"})
    result("cross-origin form post refused", code in (404, 405),
           "got %s" % code, severity="high")

    # Malformed and hostile bodies must not crash the connection.
    for label, body, ctype in [
        ("not json", b"<<<not json>>>", "application/json"),
        ("json array", b"[1,2,3]", "application/json"),
        ("empty body", b"", "application/json"),
        ("type confusion", b'{"kind":{},"name":123}', "application/json"),
        ("oversized body", b'{"x":"' + b"A" * 200000 + b'"}', "application/json"),
    ]:
        code, _, _ = http(base + "/api/leads", "POST", body, {"Content-Type": ctype})
        result("no crash on %s" % label, code != 0,
               "connection died (code 0)", severity="high")

    # Nothing may persist to disk.
    result("no lead store exists", not os.path.isdir(os.path.join(ROOT, "data", "leads")),
           "data/leads exists", severity="high")
    for fn in ("store.js", "pages.js"):
        src = ""
        fp = os.path.join(ROOT, "site", "assets", "js", fn)
        if os.path.exists(fp):
            src = open(fp, encoding="utf-8").read()
        bad = [n for n in ("submitLead", "leadEndpoint", "wireLeadForm") if n in src]
        result("no lead-capture code in %s" % fn, not bad,
               "found %s" % bad, severity="medium")


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

def test_sse_limits(base):
    section("sse connection limits")
    u = urllib.parse.urlparse(base)
    socks, statuses = [], []
    # Read the real cap instead of hardcoding a guess that goes stale the
    # next time it's tuned (it already did once: raised 6 -> 40 after real
    # carrier-grade-NAT traffic tripped it in production, see
    # server/quotes.py's DEFAULT_LIMITS comment). +5 guarantees this probe
    # actually exceeds whatever the cap currently is.
    try:
        cfg = json.load(open(os.path.join(ROOT, "config", "stream.json"), encoding="utf-8"))
        cap = (cfg.get("limits") or {}).get("max_sse_clients_per_ip", 6)
    except Exception:
        cap = 6
    attempts = cap + 5
    try:
        for _ in range(attempts):
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
               "cap=%d, %d attempts, statuses=%s" % (cap, attempts, list(dict.fromkeys(statuses))[:4]),
               severity="medium")
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
        # href/src interpolations must either pass through safeUrl() (dynamic,
        # potentially-untrusted values) or resolve to a bare identifier that is
        # itself a hardcoded `data:` literal declared in this same file - a
        # sponsor logo baked in at build time (e.g. ZERODHA_LOGO_DATA_URI) has
        # no attacker-reachable input, so safeUrl() both cannot apply (it
        # rejects the data: scheme outright) and would break the image if it
        # did. Verify the literal, don't just trust the identifier's name.
        for m in re.finditer(r'(href|src)="\$\{([^}]+)\}"', src):
            expr = m.group(2)
            if "safeUrl(" in expr:
                continue
            ident = expr.strip()
            is_hardcoded_data_uri = bool(
                re.match(r'^[A-Z][A-Z0-9_]*$', ident)
                and re.search(r'\bconst\s+%s\s*=\s*[\'"]data:' % re.escape(ident), src)
            )
            if not is_hardcoded_data_uri:
                href_unescaped.append("%s: %s=${%s}" % (fn, m.group(1), expr[:50]))

    result("all href/src interpolations pass through safeUrl() or a verified hardcoded data: literal",
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
    leaked = []
    rx_path = re.compile(r'"/(Users|home|var|etc)/')
    rx_phone = re.compile(r'"phone"\s*:\s*"\d{10}')

    target_files = []
    # Core published data files
    for fn in os.listdir(p):
        fp = os.path.join(p, fn)
        if os.path.isfile(fp) and fn.endswith(".json"):
            target_files.append(fp)

    # Broker data files
    bdir = os.path.join(p, "brokers")
    if os.path.isdir(bdir):
        for fn in os.listdir(bdir):
            if fn.endswith(".json"):
                target_files.append(os.path.join(bdir, fn))

    # Sample history files
    for sub in ("crypto-history", "equity-history"):
        sdir = os.path.join(p, sub)
        if os.path.isdir(sdir):
            sample = sorted(os.listdir(sdir))[:15]
            for fn in sample:
                if fn.endswith(".json"):
                    target_files.append(os.path.join(sdir, fn))

    for fp in target_files:
        f = os.path.basename(fp)
        raw = open(fp, encoding="utf-8", errors="ignore").read()
        if "__proto__" in raw or '"constructor"' in raw:
            bad_keys.append(f)
        if rx_path.search(raw):
            absolute_paths.append(f)
        if "leads" in f or rx_phone.search(raw):
            leaked.append(f)

    result("no prototype-pollution keys in published json", not bad_keys,
           str(bad_keys[:3]), severity="medium")
    result("no filesystem paths leaked in published json", not absolute_paths,
           str(absolute_paths[:3]), severity="medium")
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


def test_ad_surface():
    """Sponsored-banner surface: the beacon endpoint, the tracking script and the outbound links."""
    section("sponsored banners: beacon endpoint, tracking script, outbound links")
    api = os.path.join(ROOT, "api", "ad-event.js")
    src = open(api, encoding="utf-8").read() if os.path.exists(api) else ""
    result("beacon endpoint exists", bool(src), "api/ad-event.js missing", severity="high")
    result("beacon endpoint refuses cross-site and missing Origin", "originAllowed" in src and "if (!originAllowed(req)) return done(res, 403)" in src, severity="high")
    result("beacon endpoint whitelists every field and drops unknown ones",
           all(k in src for k in ("TYPES.has", "ADS.has", "SLOTS.has", "PAGE_TYPES.has", "PATH_RE.test", "HOST_RE.test")), severity="high")
    result("beacon endpoint caps the body and rate-limits per address", "413" in src and "rateLimited(" in src and "429" in src, severity="medium")
    result("beacon endpoint never sends CORS headers and never logs the caller (no ip, user agent or headers)",
           "Access-Control-Allow-Origin" not in src and not re.search(r"console\.log\([^)]*(req\.headers|req\.socket|user-agent|x-forwarded)", src, re.I),
           severity="high")
    nodes = os.system("node %s > /dev/null 2>&1" % os.path.join(ROOT, "tests", "ad_event_test.js"))
    result("beacon endpoint unit tests pass (node tests/ad_event_test.js)", nodes == 0, "exit %s" % nodes, severity="high")

    trk = os.path.join(ROOT, "site", "assets", "js", "ad-track.js")
    ts = open(trk, encoding="utf-8").read() if os.path.exists(trk) else ""
    code = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)   # comments may mention what the script avoids
    result("tracking script stores nothing: no cookies, no localStorage, no sessionStorage, no IndexedDB",
           bool(ts) and not re.search(r"document\.cookie|localStorage|sessionStorage|indexedDB", code), severity="high")
    result("tracking script sends only to the same-origin endpoint", "const ENDPOINT = '/api/ad-event'" in ts and "http://" not in code and "https://" not in code, severity="high")
    result("tracking script never reads personal data (no input values, no navigator fingerprinting)",
           not re.search(r"\.value\b|userAgent|platform|plugins|canvas|getBattery|deviceMemory", code), severity="medium")

    # outbound links on built pages
    site = os.path.join(ROOT, "site")
    bad, seen = [], 0
    for rel in ("index.html", "ipo/upcoming/index.html", "ipo/index.html", "broker/zerodha/index.html",
                "stock/itc/index.html", "calculators/index.html"):
        pth = os.path.join(site, rel)
        if not os.path.exists(pth):
            continue
        h = open(pth, encoding="utf-8").read()
        for m in re.finditer(r"<a ([^>]*)data-ad-click([^>]*)>", h):
            attrs = m.group(1) + m.group(2)
            seen += 1
            href = re.search(r'href="([^"]+)"', attrs)
            ok = (href and href.group(1) == "https://indiabullssecurities.onelink.me/Kaqz/brokerlens"
                  and 'rel="sponsored noopener"' in attrs and 'target="_blank"' in attrs)
            if not ok:
                bad.append(rel)
    result("every sponsored link is the approved https partner URL with rel=sponsored noopener and target=_blank",
           seen > 0 and not bad, "checked %d; bad: %s" % (seen, bad[:3]), severity="high")
    inline = []
    for rel in ("index.html", "ipo/upcoming/index.html", "stock/itc/index.html"):
        pth = os.path.join(site, rel)
        if os.path.exists(pth):
            h = open(pth, encoding="utf-8").read()
            for m in re.finditer(r'<aside class="ad-wrap.*?</aside>', h, re.S):
                if "<script" in m.group(0) or re.search(r"\son\w+=", m.group(0)):
                    inline.append(rel)
    result("banner markup has no inline script or inline event handlers (CSP script-src 'self')", not inline, str(inline), severity="high")
    imgs = re.findall(r'(?:src|srcset)="(https?://[^"]+)"', open(os.path.join(site, "index.html"), encoding="utf-8").read()) if os.path.exists(os.path.join(site, "index.html")) else []
    result("banner images are served from our own origin", not [u for u in imgs if "/assets/img/ads/" in u], str(imgs[:2]), severity="medium")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="base URL of a running server")
    ap.add_argument("--skip-dos", action="store_true", help="skip rate-limit and slowloris probes")
    args = ap.parse_args()

    print("VAPT suite — defensive assessment of this codebase")
    test_frontend_sinks()
    test_published_json_safety()
    test_pipeline_hardening()
    test_ad_surface()

    if args.url:
        base = args.url.rstrip("/")
        test_traversal(base)
        test_injection(base)
        test_methods(base)
        test_headers(base)
        if not args.skip_dos:
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
