# QA and VAPT report

Run date: 2026-07-31. Target: this repository, local deployment.

```bash
make qa      # 129 functional checks
make vapt    # 60 security checks
```

Both exit non-zero on failure, so CI can gate on them.

| Suite | Result |
|---|---|
| QA (`tests/qa_e2e.py`) | **129 passed, 0 failed** |
| VAPT (`tests/vapt.py`) | **60 passed, 0 findings** (5 findings found and fixed) |

Scope note: this is an assessment of our own stack — the static site, the lead
API, the SSE stream and the ingestion pipeline. Nothing here probes NSE, BSE,
MCX or SEBI; those are read-only data sources accessed through their public
endpoints.

---

## Defects found and fixed

### 1. Reliability confidence was always "high" — MEDIUM, correctness

Caught by QA, not by review, and the most consequential defect found.

`reliability_score()` computed coverage as `wsum / sum(weights.values())`, but
`weights` only ever contained the components that were actually populated. The
ratio was therefore **always exactly 1.0**, so every broker was published with
`confidence: "high"` regardless of how little data backed the score. A broker
with one input out of five looked as well-evidenced as one with all five.

On a site whose entire proposition is honest, checkable data, silently
overstating confidence is worse than a crash.

Fixed by measuring coverage against the full `RELIABILITY_WEIGHTS` schedule and
publishing the coverage ratio alongside the label:

```
before:  sparse input -> score 100.0, confidence "high"
after:   sparse input -> score 100.0, coverage 0.20, confidence "low"
```

### 2. `javascript:` URLs would execute from third-party data — HIGH, XSS

`href="${esc(url)}"` appeared in two places: broker websites and **circular PDF
links taken straight from NSE's feed**. `esc()` prevents attribute breakout but
leaves the scheme intact, so `javascript:alert(1)` survives escaping and fires
on click. The circular URL is fully third-party controlled.

Fixed with `safeUrl()` in `store.js`, which allowlists `http`/`https` (plus
`mailto` where explicitly requested) and rejects `javascript:`, `data:`,
`vbscript:`, protocol-relative `//evil.example`, and control-character bypasses
such as `java\tscript:`. The VAPT suite now fails the build if any `href="${…}"`
interpolation does not pass through it.

### 3. Unbounded response reads — MEDIUM, DoS

`Fetcher._raw()` called `resp.read()` with no ceiling. A compromised source, a
misconfiguration, or an error page that streams forever would be pulled entirely
into memory. Added `MAX_RESPONSE_BYTES` (64 MB), checked against both the
declared `Content-Length` and the actual read, because a lying header must not
be trusted either.

### 4. Zip decompression bomb — MEDIUM, DoS

`get_zip_member()` inflated archives with no size limit; BSE's delivery archive
is fetched daily. A small crafted zip expands to gigabytes. Now the declared
`file_size` is checked *before* reading, the expansion ratio is checked after,
and the read itself is capped (`MAX_UNZIPPED_BYTES`, `MAX_COMPRESSION_RATIO`).

### 5. Server version banner — LOW, information disclosure

Responses advertised `SimpleHTTP/0.6 Python/3.9.6`, handing an attacker a CVE
shortlist. Suppressed via `server_version` / `sys_version`.

### 6. Pollers started before the socket bound — MEDIUM, resource leak

Found while running the suites. `main()` started nine polling threads and *then*
bound the port. On `EADDRINUSE` the process died while its threads kept hammering
NSE, BSE and MCX from a doomed process — a good way to earn an IP ban. The bind
now happens first, and `POOL.stop()` runs in a `finally` block for clean shutdown.

---

## Hardening now in place

**Stream (`server/quotes.py`)**

| Control | Behaviour |
|---|---|
| Circuit breaker | Per source. Opens after 4 consecutive failures, exponential backoff 5s→300s, half-open probe. |
| Bandwidth budget | Rolling 60s accounting per source and overall. A source that cannot fit its `max_mb_per_min` has its interval *stretched* rather than the budget ignored. Global brake doubles all intervals when the total cap is exceeded. |
| Closed-market backoff | All intervals ×20 outside session hours. Verified live: MCX at 1s while open, NSE at 20s while closed. |
| Jitter | ±12%, so nine workers never fire in the same instant. |
| Watchdog | Supervisor restarts any worker thread that dies. |
| Subscriber caps | 200 total, 6 per IP, 60-deep queue each. A client that stops draining is dropped, never blocks the poller. |
| Instrument cap | 400 per feed, so a runaway upstream cannot grow the snapshot without bound. |
| Graceful shutdown | SIGINT/SIGTERM stop workers and close the socket. |

**HTTP server (`server/devserver.py`)**

CSP (`default-src 'self'`, no `unsafe-inline` script), `X-Frame-Options: DENY`,
`nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP. Method allowlist
(GET/HEAD/POST/OPTIONS → 405 otherwise). Directory listings disabled. Internal
paths blocked (`/config`, `/pipeline`, `/server`, `/tests`, `/data/_ingest`,
dotfiles). 20s socket timeout against slowloris. In-memory rate limiting: 10
lead posts and 30 stream connects per IP per 5 minutes. 16 KB request body cap.

**Pipeline (`pipeline/common.py`)**

Response and decompression caps as above. Lead storage accepts only an explicit
field allowlist — unknown keys (`admin`, `__proto__`, `constructor`) are dropped,
not stored.

**Data placement**

`_ingest.json` (1 MB of raw scraped state) used to sit in `site/data/`, which is
world-readable once deployed. Moved to `data/`, outside the served root, and the
VAPT suite asserts it stays there.

---

## What the suites cover

**QA — 129 checks.** Config integrity (unique ids, url-safe slugs, every stream
source declaring a feed and a budget, broker stocks referencing real profiles);
identity resolution including the fail-closed cases; metrics arithmetic
(pct change, cost basket, complaint rates, reliability weighting and coverage);
published-payload invariants (unique ranks, shares summing to 100, every
leaderboard actually sorted, no NaN/Infinity, profile files present for every
indexed broker); ticker feeds (all seven present, no duplicate symbols, positive
prices, broker stocks carrying `broker_id` and `relation`); hub logic (delta
detection, per-IP cap, slow-subscriber drop, instrument cap, breaker states,
bandwidth accounting); all ten HTTP routes; the lead API validation matrix; and a
real SSE connection parsed down to the snapshot frame.

**VAPT — 60 checks.** Path traversal (9 encodings), internal file exposure,
directory listings, injection into the lead endpoint, malformed-request handling,
oversized bodies, method fuzzing including TRACE reflection, security headers,
CORS, rate limiting, SSE connection exhaustion, slowloris plus a
responsiveness-under-load check, front-end XSS sink analysis, published-JSON
safety (prototype-pollution keys, leaked filesystem paths, PII in the public
directory), and pipeline input hardening.

---

## Residual risks — not fixed, know about them

1. **Rate limiting is per-process and in-memory.** It resets on restart and does
   not coordinate across instances. Fine for one box; put a real limiter
   (Cloudflare, nginx, Redis) in front of a production deployment.
2. **No authentication anywhere.** Correct today — everything served is public —
   but the moment a broker can edit their own profile, that needs real authn/authz
   and this suite must grow to cover it.
3. **Leads are stored as plaintext JSONL on disk.** They are personal data under
   the DPDP Act 2023. Production needs encryption at rest, a retention policy, a
   deletion path and a privacy notice. The consent flag is captured; the lifecycle
   around it is not built.
4. **The browser has not been driven.** All front-end findings come from static
   analysis of the JS. Chart rendering, filter/sort interaction and form wiring
   remain unverified in a real browser, and a headless run was declined earlier.
5. **No TLS in the dev server.** Terminate TLS at the edge; HSTS is already set in
   `site/_headers`.
6. **Dependency risk is near zero** — stdlib only, no npm, no build step — but
   that also means no automated CVE scanning is meaningful here. Revisit if
   dependencies are ever added.
7. **`site/_headers` applies only on Cloudflare Pages / Netlify.** On any other
   host the headers must be reproduced in the web-server config; the dev server
   now sends the same set so drift is visible locally.
