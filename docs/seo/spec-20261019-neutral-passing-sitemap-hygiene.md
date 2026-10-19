# SPEC — 20261019 — NEUTRAL→passing batch + sitemap hygiene (the impression-milestone lever)

**From:** SEO Strategist · **To:** CTO (self-select) · **Date:** 2026-10-19
**Type:** Sitemap generation + canonical/URL-string normalisation + re-request-indexing + 2 on-page title fixes. All are CTO-owned surfaces (sitemaps, robots/indexing, template). I am only specifying *what* and *expected outcome*.
**KPI addressed:** **O1 impressions (the +28% gap — the binding constraint)** + CPO KPI "% of NEUTRAL inspection URLs → passing" + O2 (indexed wave-1).
**Priority note for CTO queue:** Group 1 (`/etf/` add) is the single largest impression unlock and should ship first. Group 2 (slash mismatch) is a 30-minute change. Groups 3–4 are smaller. Within Group 4, prioritise money URLs; `/about`+`/sources` are deprioritised.

---

## Context: what "NEUTRAL" actually means (root-caused from the `inspection` export)

"NEUTRAL" in GSC URL Inspection is **not one condition** — it has **four distinct coverageStates**, each with a different fix. Mapping the 12 NEUTRAL URLs to their actual state:

| URL | coverageState (from inspection) | Sitemap? | Canonical matches sitemap string? | Root cause | Group |
|---|---|---|---|---|---|
| `/etf/niftybees/` | URL is unknown to Google | **NO** (`/etf/` family in 0 sitemaps) | — | **Never submitted** | G1 |
| `/ipo/` | URL is unknown to Google | YES, as `/ipo` (no slash) | NO (page canonical = `/ipo/`) | **sitemap↔canonical slash mismatch** | G2 |
| `/news/` | URL is unknown to Google | YES, as `/news` (no slash) | NO (canonical = `/news/`) | slash mismatch | G2 |
| `/about` | Discovered – currently not indexed | YES, as `/about` | YES | not-indexed (indexation state) | G4 |
| `/sources` | Discovered – currently not indexed | YES, as `/sources` | YES | not-indexed | G4 |
| `/ipo/upcoming/` | URL is unknown to Google | YES, as `/ipo/upcoming/` (slashed) | YES | not-yet-crawled/unknown (broad indexation state) | G4 |
| `/index/nifty-50/` | URL is unknown to Google | YES (slashed) | YES | not-yet-crawled (broad indexation state) | G4 |
| `/trade-costs/` | URL is unknown to Google | YES (slashed) | YES | not-yet-crawled (broad indexation state) | G4 |
| `/broker/groww/` | URL is unknown to Google | YES (`sitemap-brokers.xml`, slashed) | YES | not-yet-crawled (broad indexation state) | G4 |
| `/broker/zerodha/` | **Soft 404** | YES | YES | **false soft-404** (content is full) | G3 |
| `/stock/itc/` | Crawled – currently not indexed | YES | YES | thin title / dedup hold (sibling `/stock/tcs/` PASSES) | G3 |
| `/compare/stocks/itc-vs-hindunilvr/` | Discovered – currently not indexed | NO (not in sitemap) | — | not submitted + low value | G4 (deprior) |
| `/news/indian-stock-market-wrap-2026-10-15/` | Discovered – currently not indexed | YES (slashed) | — | not-indexed (fresh article) | G4 (deprior) |

**Key insight:** the "URL is unknown to Google" cases split two ways — (a) **never submitted** (`/etf/`), and (b) **submitted but the sitemap URL string ≠ the page's canonical** (`/ipo`, `/news`). For (b), Google sees the *submitted* URL and the *canonical* URL as two different URLs, so it never confirms the submitted one as indexed → "unknown to Google." This is a pure string-normalisation fix, not a content problem.

**De-risk note (matches weekly §0/§5):** the sitemap *panel* "114,996 / 0 indexed" is **lag**, not truth — URL Inspection shows a real "Submitted and indexed" (PASS) subset. So these NEUTRALs are fixable at the edge (sitemaps/canonical/re-crawl), not blocked by a total indexation failure. Group 4's "unknown/not-indexed" URLs that are already correctly submitted are simply waiting on crawl budget + O2 scale — they improve as indexation scales; the fixes below only *nudge* them.

---

## Group 1 — Add the `/etf/` family to the sitemap (BIGGEST lever, ship first)

**Fact (verified):** `site/etf/` has **351 built pages**; `grep "brokerlens.in/etf/" site/sitemaps/*.xml` → **0 matches in all 7 sub-sitemaps.** The `/etfs` hub is in `sitemap-core.xml` but the 351 ETF detail pages are in **no sitemap**. That is the direct cause of `/etf/niftybees/` "URL is unknown to Google."
**Why it matters:** 351 indexable, data-first pages (NAV, ISIN, benchmark, market lot — all from NSE/AMFI) that have *never been told to Google*. This is the largest SEO-controllable impression unlock on the site and directly attacks the +15,341-impression gap.
**Exact change (CTO — sitemap generation logic, CTO-owned):**
1. Generate a new `site/sitemaps/sitemap-etf.xml` listing all 351 `https://www.brokerlens.in/etf/<slug>/` URLs that are **indexable** (not `noindex`). Use the same `<lastmod>` convention as the other sub-sitemaps.
2. Register it in `site/sitemap.xml` (the sitemap **index**) as an 8th `<sitemap>` entry: `<sitemap><loc>https://www.brokerlens.in/sitemaps/sitemap-etf.xml</loc></sitemap>`.
3. Only include pages whose canonical matches the sitemap string (i.e. slashed URLs — verified `/etf/niftybees/` canonical is slashed, so emit slashed).
4. On deploy, GSC will auto-detect the new sitemap (no manual re-submit needed if `robots.txt`/panel already points at `/sitemap.xml` — verified `robots.txt` has `Sitemap: https://www.brokerlens.in/sitemap.xml`).
**Expected outcome:** +351 candidate URLs. Conservative 30-day indexation (ETF detail pages are niche; assume 30–60% index within 30 days) → **+500–1,500 impressions/30d** (at ~1–3 imps/page for mid/low-freq ETFs; NIFTYBEES and top ETFs will pull more). This is the main contribution of spec C toward the impression milestone. Flips `/etf/niftybees/` NEUTRAL→(eventually) PASS as it gets crawled.
**Guardrail:** do **not** add the `/etf/` pages if they are currently gated behind the held-back/`noindex` tier — verify the 351 are in the *indexable* set before emitting. If any are `noindex`, leave them out (I am not changing `noindex` policy — that needs Owner per charter).

## Group 2 — Normalise sitemap↔canonical URL strings (30-min fix, high reliability)

**Fact (verified):** in `sitemap-core.xml`, four URLs are emitted **without** a trailing slash while each page's `<link rel=canonical>` and `og:url` use the trailing-slash form:
- `sitemap-core.xml`: `https://www.brokerlens.in/ipo` → page canonical `https://www.brokerlens.in/ipo/`
- `https://www.brokerlens.in/news` → canonical `https://www.brokerlens.in/news/`
- `https://www.brokerlens.in/about` → canonical `https://www.brokerlens.in/about` *(these two are already slashed-consistent — see below)*

**Exact change:** make the **sitemap URL string exactly equal the page canonical** for every core URL. Concretely, in `sitemap-core.xml` emit `https://www.brokerlens.in/ipo/` and `https://www.brokerlens.in/news/` (trailing slash) to match their canonicals. *(Note: `/about` and `/sources` canonicals are the **unslashed** form, so they are already consistent — leave them unslashed in the sitemap to match. The rule is "match the canonical," not "always slash.")*
**Why:** the mismatch means the *submitted* URL and the *canonical* URL are two distinct URLs in Google's eyes → the submitted one is "unknown to Google" and the page's real indexation signal is orphaned. Aligning them lets the already-working indexation (the PASS subset proves indexing functions) attach to these hubs.
**Expected outcome:** `/ipo/` and `/news/` move from "URL is unknown to Google" toward "Submitted and indexed" once recrawled. `/ipo/` is a **money hub** (the IPO family hub) — indexing it properly is both a CPO NEUTRAL KPI win and a real impression win (hub pages accrue broad impressions). Low risk (string change only).
**Guardrail:** after the change, the sitemap URL and the page `<link rel=canonical>` and `og:url` must be **byte-identical** for every URL in the sitemap (not just these). CQA can add a cheap check: "every sitemap URL == that page's canonical."

## Group 3 — False soft-404 (`/broker/zerodha/`) + thin title (`/stock/itc/`)

**3a. `/broker/zerodha/` — "Soft 404" (FALSE):**
- **Fact (verified):** the page renders **full, valid, real content** (active clients 7,900,000; complaints 1.62/10k; cost Rs 255; SEBI `INZ000031633`; reliability 97.2; comparison chips). It is **not** a soft-404 in substance. Google flagged it soft-404 because it was previously fetched as the SPA `/* → /index.html 200` fallback (which returns a 200 with a generic/404-equivalent body) or due to near-template similarity.
- **Exact change (CTO):**
  1. Ensure `/broker/zerodha/` (and all `/broker/<name>/`) return **200 with the real broker HTML at the edge** (Vercel), not the SPA fallback — i.e. the pre-rendered file is served at that exact path. (The pre-rendered `site/broker/zerodha/index.html` exists; the issue is the edge route falling through to `/index.html`.)
  2. Re-request indexing on `/broker/zerodha/` via GSC URL Inspection (CTO owns GSC read; the re-request is a CTO/Owner action — if CTO cannot trigger it from the pipeline, flag for the Owner's GSC session).
  3. **Content uniqueness:** confirm the per-broker page carries at least 2–3 **broker-unique** facts that differ from sibling `/broker/<other>/` pages (client count, complaint rate, cost, SEBI reg — all present, good). This is what stops "templated → soft-404" reclassification.
- **Why/expected:** `/broker/zerodha/` is a **top money URL** (head broker brand). Removing the soft-404 and getting it indexed restores a high-traffic broker page. Expected: flips NEUTRAL→PASS + reclaims the impressions that are currently wasted on the soft-404. (Do **not** add new content beyond what's present — no grey-market, YMYL figures already sourced.)

**3b. `/stock/itc/` — "Crawled – currently not indexed" (thin title / dedup hold):**
- **Fact (verified):** crawled **today** (2026-10-19 05:20), robots ALLOWED, indexing allowed, fetch successful. Sibling `/stock/tcs/` PASSES. So it is **not** blocked — it's a **dedup/quality hold**: the title `ITC Limited (ITC): NSE Listing Details` is generic and, among 1,815 stock pages, looks templated/duplicative.
- **Exact change (on-page title — CTO edit, same as spec A pattern):**
  - **New title:** `ITC Limited (ITC): Share Price, Sector & NSE Listing Details | BrokerLens`
  - **New meta:** keep the existing NSE-sourced meta (last close, sector, listing facts) — it's already good and YMYL-sourced. The title is the differentiator.
- **Why/expected:** differentiating the title against the 1,800 sibling stock pages reduces the "templated → not indexed" hold so itc indexes like tcs does. Expected: NEUTRAL→PASS within 1–2 crawl cycles. (This is a single-URL example; CTO may generalise the title pattern across the not-indexed stock subset — but only where it improves uniqueness, not filler.)

## Group 4 — "Not-yet-crawled / not-indexed" that is already correctly submitted (lower value; indexation-state)

These are already in the sitemap with correct (canonical-matching) strings; their NEUTRAL state is simply **"not yet crawled/indexed"** — they will resolve as indexation scales (O2/Group 1 pull more crawl budget and the panel lag clears). No content fix is required; the only action is **re-request-indexing on the money ones** and prioritising them.

**Prioritised (CTO/Owner GSC re-request where possible):**
- `/trade-costs/` — **money page** (trading-cost calculator hub, 74KB, high intent). Re-request indexing.
- `/index/nifty-50/` — money-ish (index constituents, 281i across index family, 0 clicks — but a data hub that should index).
- `/ipo/upcoming/` — **money hub** (open/opening-soon IPOs). Re-request. *(Note: title/meta currently say "0 IPOs open for bidding, 0 upcoming" — that zero-state is fine for YMYL accuracy; do NOT stuff it. Its indexation is the issue, not its copy.)*
- `/broker/groww/` — money (head broker brand). Re-request (same treatment as 3a if it also soft-404s).

**Deprioritised within Group 4 (fix only after the above land):**
- `/about`, `/sources` — trust/E-E-A-T pages, non-money. They help site-wide E-E-A-T but are not O1-critical. Re-request only if crawl budget allows.
- `/compare/stocks/itc-vs-hindunilvr/` — **not in any sitemap** (discovered only). Optional: add the compare pages to a sitemap (there are 193 compare URLs in sitemaps; this specific one is missing — a generator gap). Low value single URL; note for CTO's compare-sitemap audit, not a 15-day priority.
- `/news/indian-stock-market-wrap-2026-10-15/` — fresh daily article, not-indexed because it's new; it will index on normal crawl. No action.

**Expected outcome (Group 4, 30-day):** mostly **panel-lag clearing + re-crawl** rather than new impressions — but `/trade-costs/`, `/ipo/upcoming/`, `/index/nifty-50/` are hubs that, once indexed, each accrue hundreds of impressions/30d. Combined: **+200–800 imps/30d** (modest, mostly dependent on O2 indexation scaling).

## Sitemap hygiene checklist for CQA (add to gate, cheap)

1. Every URL in `sitemap.xml`'s sub-sitemaps has a corresponding **byte-identical** `<link rel=canonical>` on the built page (catches Group 2 class of bug site-wide).
2. Every built **indexable** page in a family is present in a sub-sitemap (catches Group 1 class — the `/etf/` gap would have been caught).
3. No `noindex` page is listed in a sub-sitemap.
4. Sitemap URL count per family matches the built-page count for that family (delta alerts on drift).

## Rollback / constraints

- Sitemap + canonical changes are CTO-owned; no `noindex` policy change, no robots change (robots.txt is already correct: `Allow: /`, Sitemap line present), no legal/SEBI copy change. YMYL-safe.
- Re-request-indexing actions require a GSC session; if CTO's pipeline cannot call it, flag to Owner's GSC session (note in ledger) — do **not** assume it's done.
- Group 1 must only emit **indexable** ETF pages; do not surface held-back/`noindex` ones.
