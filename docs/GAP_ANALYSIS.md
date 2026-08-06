# BrokerLens India: end-to-end gap analysis

**Date:** 2026-08-01
**Method:** four parallel code audits (pipeline/data, server/security, frontend/UX/SEO/a11y,
tests/docs/ops), plus direct verification of every CRITICAL and HIGH finding against the
running system. Findings marked **[VERIFIED]** were reproduced by executing code or
attacking the live server, not inferred by reading it.

**Verdict: not production ready.** The engineering is sound and unusually careful in places
(response caps, zip-bomb guards, cookie scoping, atomic writes, an honest sample-data
banner). The blockers are not sloppiness; they are a small number of composed defects that
each look minor alone and together defeat the safeguards the project documents about itself.

---

## 0. Executive summary

Three things must be fixed before this site can be shown to the public under its own claims:

1. **The numbers are wrong, not just sample.** Beyond the known placeholder data, the cost
   engine inverts the pricing convention of the entire Indian discount-brokerage market
   (6.7x overstatement on Zerodha, verified), a broker with no data scores 100/100 on
   reliability and tops that leaderboard, and growth percentages are computed positionally
   so a 16-month gap publishes as "month-on-month".
2. **The site can silently publish fabricated or half-year-old data labelled as regulator
   sourced.** Three separate defects compose: provenance defaults to "NSE"/"SEBI" for
   anything not literally flagged sample; the pipeline's success check is always true so a
   total upstream blackout exits 0; and the stale-cache fallback has no age ceiling.
3. **Adverse claims about named firms rest on substring matching.** A 0.9-confidence
   "contains" rule with no ambiguity margin drives both the SEBI defaulter flag and the
   disciplinary-circular flag. One false positive is live right now against a real company.

Two more are launch blockers for reach rather than correctness: **there is no mobile
navigation** (the site forces a 679px viewport on a 375px phone) and **every page declares
the homepage as its canonical URL**, which would collapse all 56 URLs into one in search.

Resolved during this audit: all personal-data collection was removed (see §6).

---

## 1. CRITICAL: data correctness

### 1.1 Cost basket inverts the Indian pricing convention **[VERIFIED]**
`pipeline/metrics.py:112-127` uses `max(per_order, flat)`. Every Indian discount broker
prices as "Rs20 or 0.03%, **whichever is lower**". Executed against the published Zerodha
charge structure:

| leg | site publishes | correct under "whichever is lower" |
|---|---|---|
| intraday | **Rs200/mo** | Rs30/mo |
| monthly total | **Rs425** | Rs255 |

This drives the cost calculator, the "cheapest basket/delivery/F&O" leaderboards and the
"Low cost" badge. It does not merely inflate: it makes a flat-Rs20 broker and a
0.03%-capped-at-Rs20 broker score identically when they differ ~6x in reality, so the
rankings are wrong in order, not just in magnitude.

### 1.2 A broker with zero data scores 100/100 reliability **[VERIFIED]**
`pipeline/metrics.py:195-201` adds the `regulatory` component unconditionally, with no data
required. `reliability_score({"id":"x","profile":{}}, [])` returns **score 100.0**,
coverage 0.2. Absence of evidence is scored as a perfect regulatory record. The compact
broker index (`publish.py:292`) publishes only `reliability` and drops `coverage` and
`confidence`, and the reliability leaderboard applies no minimum-coverage filter. The least
known broker on the site therefore ranks first, with no caveat visible to the reader.

### 1.3 Period arithmetic is positional, so gaps corrupt every growth figure **[VERIFIED]**
`pipeline/metrics.py:39-42` indexes by list position and assumes a contiguous monthly
series. Regulator files skip months. Verified: a series of Jan-2025, Feb-2025, Jun-2026
publishes `mom_pct: 81.82` for a 16-month gap, and `publish.py` turns exactly that into an
RSS headline reading "+81.82% month-on-month". Nothing sorts or validates the series, so a
hand-edited file with newest-first ordering silently inverts every growth sign on the site.

### 1.4 Complaint metrics mislabel and misnormalise **[VERIFIED]**
- **Short windows labelled as 12 months.** 3 months of disclosures publishes
  `received_12m: 300`, so a broker with a short history scores ~4x better on the
  0.40-weighted complaint rate that dominates reliability.
- **Flat records published as doubling.** 18 months of a perfectly flat 100
  complaints/month yields `trend_pct: +100.0` (compares 12 months against a 6-month
  partial window). The bug vanishes at exactly 24 months, so it only ever hits newly
  onboarded brokers.
- **Resolution rate uncapped.** 10 received / 50 resolved publishes **500.0%**.
- **Non-disclosure scores as zero complaints**, so the worst-behaved broker gets the best
  rate. Flow is also divided by a stock (12 months of complaints over the *latest* client
  count), understating a fast-growing broker's rate by roughly its growth multiple.

### 1.5 Market share is share-of-48, presented as share of the NSE market **[VERIFIED]**
`publish.py:204-206` builds the denominator by summing only the ~48 curated brokers, yet
the site renders `total_active_clients` (currently **46,515,000**) as "Total active clients"
with a green NSE provenance dot, and `metrics.py:294` labels the board "share of total NSE
active clients". HHI and top-5 concentration inherit the same inflated base. Related: if
brokers report through different months, the denominator silently changes per month and the
resulting jump is published as a real 12-month share gain.

---

## 2. CRITICAL: the site can publish untrue data with every safeguard green

These three compose into one failure mode.

### 2.1 Provenance defaults to "regulator sourced" **[VERIFIED by inspection]**
`publish.py:246-251`: anything whose `provenance` is not literally `"sample"` is stamped
`"nse"` or `"sebi_annexure_b"`. No ingest path writes these manual files. So a hand-typed
number, or a file whose flag is renamed to `"manual"`/`"partial"`/`"estimate"`, publishes
as a SEBI-mandated regulatory disclosure with a green provenance dot. Provenance is also
file-level, so the realistic migration state (real data for 10 brokers, sample for 38) has
no representable form: either it lies about 38 or understates 10.

### 2.2 The documented exit-code contract does not work **[VERIFIED]**
`run.py:42-58` uses `ok = bool(val)`, but every source's `collect()` returns a dict with
fixed keys regardless of outcome. `bool({"pulse":{}, "live":{}, ...})` is `True`. A total
blackout of NSE, BSE, MCX and SEBI produces exit code 0, all sources green. **This is live
right now:** `sebi_stock_brokers` reports `status: "ok"` while returning **0 rows**, and
the `/sources` page shows it green.

### 2.3 Stale-cache fallback has no age ceiling **[VERIFIED by inspection]**
`common.py:202-207` returns any cached body on failure, bypassing the TTL check entirely,
and `run()` then stamps a fresh `last_run` and `status: "ok"`. A registry cached six months
ago is served as a successful regulator pull, with no `stale` marker in the payload.
`data/canonical/` exists to hold last-known-good values per the docstring; it is empty and
nothing writes to it, so the documented safety property does not exist.

---

## 3. CRITICAL: adverse claims from substring matching

### 3.1 A live false positive is on the site now **[VERIFIED]**
`nse.py:225-238` scans circular text for any alias of 6+ characters with a plain substring
test, no word boundary. The only current hit:

> `motilal-oswal` flagged by: *"Availability of Motilal Oswal BSE Midcap 150 Momentum 30
> Index Fund NFO on NSE MF Invest Platform"*

A routine mutual-fund product listing. Motilal Oswal is consequently the **only** broker
with `flagged: true`, takes an 8-point regulatory penalty, and shows a regulatory-flag
block on its profile. Registered aliases that are ordinary words and clear the 6-char
filter include `choice`, `goodwill`, `ventura`, `bonanza`, `espresso`, `shoonya`, `arihant`.

### 3.2 "Contains" matching resolves unrelated companies at 0.9 confidence **[VERIFIED]**
`identity.py:74-78` accepts any single 5+ character alias appearing as a substring, with no
token check and no runner-up margin (the careful threshold logic elsewhere in the file is
bypassed). Executed against the live resolver:

| input | resolved to | confidence |
|---|---|---|
| `ARIHANT ACADEMY LIMITED` | `arihant` | contains, 0.90 |
| `VENTURA TEXTILES LIMITED` | `ventura` | contains, 0.90 |
| `CHOICE FINSTOCK PRIVATE LIMITED` | `choice` | contains, 0.90 |

The same `resolve()` maps the **SEBI defaulter list** (445 records) onto broker profiles,
producing a "SEBI defaulter" tag and a zeroed regulatory score. Today 445/445 happen to
miss. That is luck, not a guarantee, and the cost of one hit is a defamation exposure
against a named, regulated firm. There is no stricter threshold for adverse attributions
than for filling in a city name.

---

## 4. HIGH: launch blockers for reach

### 4.1 No mobile navigation at any breakpoint **[VERIFIED]**
No media query in `app.css` targets `.nav`, `.nav-links`, `.brand` or `.mega-toggle`.
Measured in a headless browser at a 375px viewport: **`document.body.scrollWidth` = 679px**
on both `/` and `/brokers`. Every page scrolls horizontally on a phone. For an Indian
retail-investor audience this is the most consequential UX defect on the site.

### 4.2 Every page declares the homepage as canonical **[VERIFIED by inspection]**
`index.html:8` hardcodes `<link rel="canonical" href="/">` and nothing updates it on route
change. All 56 URLs, including 48 broker profiles, tell search engines they are duplicates
of `/`. This is self-inflicted mass de-indexing of exactly the pages meant to earn traffic.

### 4.3 Sitemap and RSS point at `example.invalid` **[VERIFIED]**
`publish.py:34` defaults `SITE_URL` to `https://example.invalid`; the checked-in
`site/sitemap.xml` and `site/feed.xml` contain it on every entry. Nothing validates it and
the build exits 0. `SITE_URL` is documented nowhere: not in the README, the Makefile, the
cron block, or a `.env.example`.

### 4.4 Zero server-rendered content
All content is client-rendered into `<main id="app">`. Non-JS crawlers, social unfurlers
and LLM crawlers see an empty page. For a site whose value proposition is being the
primary-source reference for Indian broker data, being invisible to those crawlers is a
strategic loss rather than a technical nit. Also missing: `robots.txt`, per-route meta
descriptions (they leak across navigations), `og:url`/`og:image`, and `/registry` is absent
from the sitemap despite being the highest-unique-content page.

### 4.5 Deploying `site/` from a clone ships an empty site
`.gitignore` excludes `site/data/`, `sitemap.xml` and `feed.xml` (correct: they are
generated), but the README says to deploy `site/` as a static directory with no mention of
a build step. Following it literally deploys a shell that renders skeletons forever.
Compounding: `config/algo_platforms.json` and `config/market_timings.json` are **untracked**,
and both publishers degrade to empty output rather than failing, so a fresh clone silently
builds a site with no algo directory and no market timings.

---

## 5. HIGH: security and robustness

Verified clean: 62/62 VAPT checks, 120/120 QA checks, path traversal, directory listing,
method fuzzing, CORS, security headers, response-size caps, gzip-ratio guards, zip-member
guards, TLS verification, cookie scoping.

| # | Finding | Status |
|---|---|---|
| 5.1 | **`site/.DS_Store` will be published.** 6148 bytes, present now. Blocked locally by the dotfile rule so it never shows in testing, but Cloudflare Pages and Netlify serve existing files before rewrites. It is a binary directory index leaking every filename in `site/`, and it is the first thing automated scanners request. | Open |
| 5.2 | **Request smuggling / desync.** `Transfer-Encoding` is never handled and rejected bodies do not set `close_connection`, so a chunked body is reparsed as a pipelined request. `protocol_version = HTTP/1.1` (required for SSE) is what makes it exploitable behind a CDN. | Open |
| 5.3 | **SSE response has neither `Content-Length` nor `Transfer-Encoding`.** The handler hand-writes chunk framing without declaring it. It survives in browsers only because the SSE line parser discards the hex sizes as unknown fields. Any conforming intermediary will desync. | Open |
| 5.4 | **SSE connection caps are bypassable.** A client that stops reading is evicted from the subscriber set but its socket, thread and FD stay alive, so it counts zero against both the global 200 and per-IP 6 limits. Repeat to exhaust FDs. The test suite drains headers, so it exercises only the well-behaved path. | Open |
| 5.5 | **Bandwidth budget measures a config constant, not reality.** Every poll returns `spec["wire_bytes"]` instead of actual bytes. If MCX starts returning its 1.28MB payload on the light endpoint, the poller keeps firing at 1s and reports 4.7 KB/min while pulling ~76 MB/min. The global 12 MB/min brake cannot trip. `common.py` already has `len(body)` in hand. | Open |
| 5.6 | **Circuit breaker cannot open for three sources.** `Fetcher.get` returns `None` rather than raising, and three poll handlers tolerate it, so `breaker.ok()` resets the failure count every cycle. Each "successful" cycle costs 3 retries plus a fresh NSE warm-up, i.e. ~6 requests, forever, at full cadence: the exact inverse of the documented backoff guarantee. | Open |
| 5.7 | **Thread leak in the BSE fan-out.** `join(timeout=10)` abandons threads that are never reaped; worst case per scrip is ~93s against a 2s poll interval, accumulating hundreds of live threads and sockets. | Open |
| 5.8 | **`/assets/*` is cached `immutable, max-age=31536000` on unversioned filenames.** A JavaScript security fix cannot reach returning visitors for up to a year. Dev uses `max-age=300`, so this never surfaces in testing. | Open |
| 5.9 | **Production CSP is weaker than dev**: `_headers` omits `object-src`, COOP and CORP that the dev server sends, despite a comment claiming they match. The VAPT suite only tests dev, so the drift is invisible by construction. | Open |
| 5.10 | **Inline JSON-LD violates the site's own CSP** (`script-src 'self'`, no hash/nonce). SEO is unaffected but it proves the CSP was never validated in a browser, and it will drown any future violation reporting. | Open |
| 5.11 | **`SIGTERM`/`SIGINT` leave the server listening.** The handlers stop the workers but never close the socket, so the process serves a permanently frozen snapshot until `SIGKILL`. | Open |
| 5.12 | Unescaped `innerHTML` in the chart tooltip (`chart.js:175`), fed by broker brand names on `/compare`. The one hole in an otherwise disciplined escaping regime. `script-src 'self'` limits it to defacement rather than script execution. | Open |
| 5.13 | `safeUrl()` treats `/\evil.example` as same-origin: it does not start with `//`, so the protocol-relative guard misses it, and browsers normalise the backslash. | Open |
| 5.14 | Rate limiter memory is unbounded in practice (buckets are only evicted when empty, and one-shot IPs never revisit), and it is keyed on the socket IP, so behind any CDN the whole internet shares one bucket. | Open |
| 5.15 | `/api/health` is unauthenticated and unrated: it exposes poll cadence, breaker state, subscriber counts and raw upstream error text, i.e. a live oracle telling an attacker their DoS is working. | Open |
| 5.16 | Unbounded growth: `data/cache` is 9.7MB after two days with no eviction (date-keyed URLs mint a new file daily, forever), `data/raw` ~1.1MB/day with no rotation. `make clean` targets a path that no longer exists. | Open |

---

## 6. RESOLVED during this audit: personal-data collection removed

The lead-capture form was removed at the user's direction after these were **[VERIFIED]** by
attacking the running server:

| Attack | Before | After |
|---|---|---|
| Cross-site forged consent via a `text/plain` form (CORS-simple, no preflight), stamped with the victim's real IP | **201 Created** | 405 |
| `"consent": "false"` accepted as valid consent | **201 Created** | 405 |
| Generic `enquiry` kind bypassing the consent gate entirely | **201 Created** | 405 |
| Type confusion (`{"kind":{}}`) crashing the connection | **connection killed** | 405 |

PII was also being written to unrotated stderr logs (with newline-injection from the
attacker-controlled name field) and to a world-readable `leads.jsonl`.

Removed: the form and its wiring, `submitLead`/`leadEndpoint`, the entire `do_POST` handler
and validator, and the stored data. Both suites now enforce the invariant: no POST accepted
anywhere, no lead store on disk, no input element in the shell. **This eliminates the
project's entire DPDP Act 2023 surface**: no consent records to defend, no erasure path, no
retention policy, no breach exposure.

---

## 7. MEDIUM: accessibility, correctness of presentation, hygiene

- **Keyboard and touch users cannot reach core functionality.** Sortable table headers are
  click-only (no `tabindex`, `role`, `aria-sort`, or keydown handler). The metric tooltips,
  which carry the definition of every number on the site, are `:hover`-only pseudo-elements:
  unreachable by keyboard, touch and screen readers simultaneously. The mega menu cannot be
  closed by keyboard on desktop. No focus management or announcement on route change; no
  skip link.
- **`--text-faint` (#96968d on #fbfbfa) is ~2.6:1**, below the 4.5:1 minimum, and is used
  for every provenance footnote and the legal disclaimer.
- **Empty states look broken rather than intentional.** With sample data removed, charts
  render blank sized boxes (the guard runs after canvas setup), the reliability canvas
  becomes an unsized 150px rectangle, and 48 empty sparkline slots appear. The donut renders
  "Everyone else 100.0%" from all-null shares.
- **Developer copy is user-facing**: four separate error paths tell visitors to run
  `python3 -m pipeline.run all`.
- **`/calculator` has no sample-data banner**, though it is the one page producing a
  personalised money figure from sample charges.
- **Session status for BSE and MCX is fabricated from NSE's status field.** The MCX `as_of`
  is also parsed with the timezone discarded, publishing a timestamp **71 minutes in the
  future** relative to fetch time. Given the licensing posture depends on an accurate "as
  of", this is compliance-relevant.
- **Archive fetchers start at yesterday**, so today's bhavcopy is never ingested; turnover
  and delivery are structurally at least one day stale. No holiday calendar, so a long
  holiday silently returns a short series and still reports ok.
- **Read-modify-write race** on `data/_ingest.json` between the minutely ticker cron and
  the nightly full run: the ticker can clobber a fresh SEBI/NSE/BSE fetch. No lock file.
- **The cron block in the README is unusable**: no timezone (a UTC server runs the "market
  hours" job entirely outside the session), no working directory, no env, no failure
  alerting despite the exit-code contract being sold as the reason it exists.
- **Registry duplicates**: firms holding both a broking and a DP registration appear twice
  with identical name and slug, so any `/registry/:slug` route collides.
- **Dead code from removed features**: the entire monetisation surface (ad slots, featured
  and claimed badges, promoted rows) can no longer trigger but still ships, along with
  orphaned tier/pricing CSS and a stale comment describing paid placement behaviour.
- **Tests that pass without running**: several VAPT assertions were gated on a lead
  submission that now 422s, an `XSS_SINK` regex is defined and never used, and one QA check
  compares an expression to itself (`abs(x - x) < 1e-9`) so it asserts nothing. The suites
  do not drive a browser at all, so charts, the mega menu, tooltips and the theme toggle
  have no coverage.
- **Missing standard files**: no LICENSE, no privacy policy or terms, no `robots.txt`, no
  `404.html` (every unknown URL returns HTTP 200 with "not found" content), no
  `security.txt`, no CI config. There is now no contact address anywhere on the site.
- **Git hygiene**: 14 modified files and 3 untracked entries sit uncommitted on a
  single-commit repo, including the two config files the new pages depend on.

---

## 8. Recommended order of work

**Phase 1, correctness (nothing ships before this):**
1. Fix the cost basket to "whichever is lower" and add a regression test per pricing shape.
2. Gate the reliability score on minimum coverage; publish `confidence` alongside it and
   exclude low-coverage brokers from the leaderboard.
3. Make period arithmetic calendar-aware; sort and validate series on ingest.
4. Fix the complaint window, cap the resolution rate, and distinguish "no disclosure" from
   "zero complaints".
5. Rename market share to what it measures, or compute a real denominator.

**Phase 2, truthfulness of the pipeline:**
6. Make provenance explicit and per-record; refuse to publish an unrecognised provenance
   value rather than defaulting to a regulator label.
7. Make the exit-code contract real: assert expected row counts per source.
8. Bound the stale-cache fallback by age and propagate a `stale` flag into the payload.
9. Require a word-boundary plus an ambiguity margin for all adverse matching; retire the
   0.9 "contains" rule for defaulter and circular attribution. Remove the live Motilal
   Oswal false positive.

**Phase 3, launch mechanics:**
10. Mobile navigation; per-route canonical, title and description; `SITE_URL` enforced at
    build time; `robots.txt`; strip `.DS_Store` in the build; commit the two config files.
11. Decide the exchange-data licensing posture before any public launch.
12. Then, and only then, remove the sample-data banner once real UCC and Annexure-B
    ingestion exists.

**Phase 4, hardening and ops:** items in §5 not already covered, cache and snapshot
retention, cron correctness, log rotation, and browser-level tests so the UI has coverage
at all.
