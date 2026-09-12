"""Static server + live-quote stream, for local development.

  python3 server/devserver.py [--port 8000] [--no-stream]

Three jobs:
  1. Serve site/ with SPA fallback - unknown paths return index.html so
     client-side routes like /broker/zerodha work on a hard refresh. Any
     production host needs the same rewrite (Cloudflare Pages: a _redirects
     entry; Netlify: the same; nginx: try_files ... /index.html).
  2. Refuse every POST: the site collects and stores no user data.
  3. Push live quotes over Server-Sent Events at GET /api/stream, backed by the
     poller in server/quotes.py, plus GET /api/ticker for the current snapshot.

DEPLOYMENT NOTE: 1 and 2 are static/serverless-friendly, but 3 needs a
persistent process - a CDN like Cloudflare Pages cannot hold an open
text/event-stream. In production run this (or just the stream half) on a small
always-on host, and if it lives on another origin, widen the CSP in
site/_headers from connect-src 'self' to include that origin. The front end
degrades to polling /data/ticker.json automatically when the stream is absent,
so a static-only deploy still works.

CLOUD RUN NOTE: this same file is the production stream server, deployed as a
container to Cloud Run (see server/Dockerfile) rather than reimplemented for
a serverless platform - Vercel Functions cannot hold this process's in-memory
HUB/subscriber state across invocations (no instance affinity), whereas a
single always-warm Cloud Run instance (min-instances=1, max-instances=1)
behaves exactly like this "small always-on host" this file already assumes.
Only the API surface matters there, not the static file serving (Vercel's own
CDN already serves site/), so the Cloud Run image does not include site/ at
all - non-/api/ routes there just 404, which is correct and harmless.
ALLOWED_ORIGIN and PORT are read from the environment; everything else about
this file is identical between local dev and the deployed service.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")

MAX_BODY = 16 * 1024
REQUEST_TIMEOUT_S = 20          # slowloris: a client gets 20s to finish a request
ALLOWED_METHODS = {"GET", "HEAD", "POST", "OPTIONS"}

# Match production (site/_headers) so dev and prod behave the same. The CSP holds
# because the site makes no third-party requests at all.
#
# style-src needs 'unsafe-inline': the renderers emit style="" attributes and
# without it the browser silently drops them. script-src stays 'self', which is
# the part that actually defends against XSS.
SECURITY_HEADERS = {
    "Content-Security-Policy":
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
        "form-action 'self'; object-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# Nothing under these paths may ever be served, even if a file lands there.
FORBIDDEN_PREFIXES = ("/data/_ingest", "/.git", "/.env", "/config", "/pipeline", "/server", "/tests")

# Simple in-memory rate limiting. Enough for a single-process dev/edge server;
# put a real limiter in front of a production deployment.
RATE_LIMITS = {"/api/stream": (30, 300)}   # (requests, window_s)

# Empty locally (same-origin, no CORS needed). On Cloud Run this is set to the
# Vercel site's own origin, since /api/* is then served cross-origin from the
# static site's point of view - see the CLOUD RUN NOTE above.
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "")


class RateLimiter:
    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def check(self, key, limit, window):
        now = time.time()
        with self._lock:
            bucket = self._hits.setdefault(key, [])
            cut = now - window
            while bucket and bucket[0] < cut:
                bucket.pop(0)
            if len(bucket) >= limit:
                return False, int(bucket[0] + window - now) + 1
            bucket.append(now)
            if len(self._hits) > 5000:          # bound memory under a spray attack
                for k in [k for k, v in self._hits.items() if not v][:1000]:
                    self._hits.pop(k, None)
            return True, 0


LIMITER = RateLimiter()
HUB = None          # set by main() when streaming is enabled
POOL = None
SSE_RETRY_MS = 3000
SSE_HEARTBEAT_S = 15


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # required for a long-lived streaming response
    # Do not advertise the runtime and its version - it hands an attacker a
    # CVE shortlist for free.
    server_version = "brokerlens"
    sys_version = ""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE, **kw)

    def log_message(self, fmt, *args):
        if self.path.split("?")[0] != "/api/stream":
            sys.stderr.write("  %s %s\n" % (self.command, self.path.split("?")[0]))

    # ------------------------------------------------------------------ GET

    timeout = REQUEST_TIMEOUT_S

    def setup(self):
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_S)

    def _client_ip(self):
        # Cloud Run terminates every connection at Google's proxy layer, so
        # client_address is always the proxy's internal address there - every
        # visitor would collapse onto one "IP" for rate limiting and the
        # per-IP subscriber cap, which defeats both. Cloud Run's proxy always
        # sets X-Forwarded-For with the real client first; trusted here only
        # because ALLOWED_ORIGIN (set only in the Cloud Run deployment) is the
        # signal that this header is coming from that trusted proxy, not a
        # spoofable client - locally (no ALLOWED_ORIGIN) the header is ignored
        # and the raw socket peer is used, as before.
        if ALLOWED_ORIGIN:
            fwd = self.headers.get("X-Forwarded-For")
            if fwd:
                return fwd.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "-"

    def _blocked(self, route):
        """Never serve internal state or a directory index."""
        if any(route.startswith(p) for p in FORBIDDEN_PREFIXES):
            return True
        # dotfiles anywhere in the path
        return any(seg.startswith(".") for seg in route.split("/") if seg)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", ", ".join(sorted(ALLOWED_METHODS)))
        self.send_header("Content-Length", "0")
        if ALLOWED_ORIGIN and self.path.split("?")[0].startswith("/api/"):
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        route = self.path.split("?")[0]
        if self._blocked(route):
            self._json(404, {"error": "not found"})
            return
        if route == "/api/stream":
            ok, retry = LIMITER.check("stream:" + self._client_ip(), *RATE_LIMITS["/api/stream"])
            if not ok:
                self.send_response(429)
                self.send_header("Retry-After", str(retry))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._stream()
            return
        if route == "/api/ticker":
            self._json(200, HUB.snapshot) if HUB else self._json(503, {"error": "stream disabled"})
            return
        if route == "/api/health":
            self._json(200, {
                "ok": True,
                "stream": bool(HUB),
                "detail": POOL.health() if POOL else None,
            })
            return
        super().do_GET()

    def do_HEAD(self):
        if self._blocked(self.path.split("?")[0]):
            self._json(404, {"error": "not found"})
            return
        super().do_HEAD()

    # Anything outside the allowlist gets a flat 405 rather than a stack trace.
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (TimeoutError, socket.timeout):
            self.close_connection = True

    def send_error(self, code, message=None, explain=None):
        if code == 501 and getattr(self, "command", None) not in ALLOWED_METHODS:
            code = 405
        super().send_error(code, message, explain)

    def list_directory(self, path):
        """Directory listings leak the file inventory. Never."""
        self.send_error(404, "Not Found")
        return None

    def send_head(self):
        path = self.translate_path(self.path)
        # SPA fallback: a route with no file on disk and no extension -> index.html
        if not os.path.exists(path) and not os.path.splitext(path)[1]:
            self.path = "/index.html"
        return super().send_head()

    # ------------------------------------------------------------------ SSE

    def _stream(self):
        if not HUB:
            self._json(503, {"error": "stream disabled; start without --no-stream"})
            return

        sub, snapshot = HUB.subscribe(self._client_ip())
        if sub is None:
            self._json(503, {"error": snapshot})
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")   # tell nginx not to buffer us
            self.end_headers()

            self._sse_raw("retry: %d\n\n" % SSE_RETRY_MS)
            self._sse("snapshot", snapshot)

            last_beat = time.time()
            while True:
                try:
                    event, payload = sub.get(timeout=1.0)
                    self._sse(event, payload)
                except queue.Empty:
                    pass
                if time.time() - last_beat >= SSE_HEARTBEAT_S:
                    # Comment frame: keeps proxies and phones from closing an idle stream.
                    self._sse_raw(": keep-alive\n\n")
                    last_beat = time.time()
        except (BrokenPipeError, ConnectionResetError):
            pass                                  # the tab was closed; normal
        finally:
            HUB.unsubscribe(sub)

    def _sse(self, event, payload):
        self._sse_raw("event: %s\ndata: %s\n\n" % (event, json.dumps(payload, separators=(",", ":"))))

    def _sse_raw(self, text):
        # Chunked, because HTTP/1.1 with no Content-Length must be chunk-framed.
        body = text.encode("utf-8")
        self.wfile.write(b"%x\r\n%s\r\n" % (len(body), body))
        self.wfile.flush()

    def end_headers(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/"):
            if ALLOWED_ORIGIN:
                self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
                self.send_header("Vary", "Origin")
        elif p.startswith("/data/"):
            # Match the production posture: short shared cache, revalidate.
            self.send_header("Cache-Control", "public, max-age=60, s-maxage=3600, must-revalidate")
        elif p.startswith("/assets/"):
            self.send_header("Cache-Control", "public, max-age=300")
        else:
            self.send_header("Cache-Control", "no-cache")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    # ----------------------------------------------------------------- POST
    #
    # The site collects no personal data. There is deliberately no lead capture,
    # no contact form, and no write endpoint of any kind: nothing to forge, no
    # consent record to defend, nothing in scope for the DPDP Act. Every POST is
    # refused outright.

    def do_POST(self):
        self._json(405, {"error": "method not allowed"})

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    global HUB
    # Cloud Run sets PORT and expects a bind on all interfaces; local dev sets
    # neither, so the safer 127.0.0.1-only default is unaffected there.
    on_cloud_run = "PORT" in os.environ
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default="0.0.0.0" if on_cloud_run else "127.0.0.1")
    ap.add_argument("--no-stream", action="store_true",
                    help="serve static only; the front end falls back to polling")
    args = ap.parse_args()

    # site/ isn't in the Cloud Run image at all (Vercel's own CDN serves it;
    # this deployment is API-only - see the CLOUD RUN NOTE above), so this
    # check would always fire there and is irrelevant noise.
    if not on_cloud_run and not os.path.exists(os.path.join(SITE, "data", "overview.json")):
        sys.stderr.write(
            "!! site/data/overview.json is missing. Run:\n"
            "     python3 -m pipeline.run seed && python3 -m pipeline.run all\n\n"
        )

    # Bind FIRST. Starting the pollers before the socket means a failed bind
    # (port already in use) leaves nine threads hammering the exchanges inside a
    # process that is about to die.
    ThreadingHTTPServer.allow_reuse_address = True
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        sys.stderr.write("!! cannot bind %s:%d - %s\n" % (args.host, args.port, exc))
        return 1

    if not args.no_stream:
        global POOL
        from quotes import start as start_hub   # imported late: pulls in pipeline.*
        HUB, POOL = start_hub()
    sys.stderr.write("serving %s on http://%s:%d  (%s)\n"
                     % (SITE, args.host, args.port,
                        "live stream at /api/stream" if HUB else "stream OFF"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nstopping\n")
    finally:
        if POOL:
            POOL.stop()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
