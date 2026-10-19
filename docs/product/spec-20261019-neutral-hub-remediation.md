# SPEC-20261019-01 — NEUTRAL hub & brand page remediation

- **Spec owner:** CPO · **Status:** queued · **Date:** 2026-10-19
- **Consumes:** CTO (pipeline + templates), CQA (bar check + URL Inspection verification)
- **Related:** `docs/product/weekly-2026W42.md` §(b); quality bar defined there item-by-item
- **Why this is the highest-leverage product change:** the 1,000-click milestone is a CTR problem, not a ranking problem. `/ipo/` + `/ipo/upcoming/` hold 25,464 impressions at 0.11% CTR; the 12 GSC-NEUTRAL URLs are the same class of failure. Fixing the template once, across hub/brand/instrument-head pages, converts the largest impression pool on the domain into clicks within one GSC window, and moves every one of the 12 URLs from NEUTRAL to passing, which is the CPO's own KPI.

## 1. Scope (exact URLs in scope, 12)

`/ipo/`, `/ipo/upcoming/`, `/broker/zerodha/`, `/broker/groww/`, `/stock/itc/`, `/etf/niftybees/`, `/news/`, `/about`, `/sources`, `/index/nifty-50/`, `/trade-costs/`, `/compare/`.

Out of scope: per-IPO pages, per-stock long tail, fund/AMC permutations, all-pairs compare (those have their own plans).

## 2. The shared remediation template (one code change, applied per page type)

Today these pages are written by separate functions in `pipeline/publish.py` (`_write_ipo_hub` / `_write_ipo_upcoming` via `pipeline/ipo_engine.render_enhanced_ipo_hub`, `_write_broker_pages` + `_broker_depth`, `_write_stock_pages`, `_write_etf_pages`, `_write_index_pages`, `_write_sources_page`, `_write_about_page`, `_write_calculator_tool_page`, `_write_compare_pages`, news suite in `pipeline/news_engine.py`). They have no common "pass the quality bar" structure. The fix is one shared component plus per-page-type field wiring, not twelve rewrites.

Add a shared builder (suggested name `build_quality_panel(...)`, placed in `pipeline/common.py` next to the existing helpers) that emits, in this order at the end of the main content, just before the footer:

1. **Key-facts / data-block panel.** For each data block the page type provides: a `<section class="data-block">` with (a) a block title, (b) the table/stat-strip rendered from real values (blocks with fewer than 3 populated rows are dropped by the builder, not rendered as empty tables), and (c) a visible source line: `Source: <label> — as of <date>` where `<label>` and `<date>` come from the source record in `config/sources.json` (use the source's `updated`/as-of field; if the source has none, use the ingest date passed in at build time). The builder **fails the build** (not warns) if a block's source key is not present in `config/sources.json` — this is the YMYL rule, it is not a lint.
2. **Related section (≥5 links, ≥3 different families).** Each page type passes a `related=[(family, url, label), ...]` list; the builder renders it as a heading + link list and drops the section if fewer than 5 entries resolve to live built pages (cross-check against the same slug sets the sitemap builder already computes, so a link can never 404).
3. **Primary-source links (≥2).** Same mechanism, family = external; must be URLs whose host is sebi.gov.in, nseindia.com, bseindia.com, or amfiindia.com — the builder rejects others.
4. **Freshness stamp.** `Updated <date>` from the max as-of date of the page's counted blocks. The sitemap `lastmod` for the URL must be set from the same value (pass through to `_write_sitemap`).

Per-page-type wiring (what each function must feed the builder — this is the entire per-URL work):

| URL | Data blocks (≥3 counted) | Related (≥5, ≥3 families) | External (≥2) |
|---|---|---|---|
| `/ipo/` | open-issues table, forthcoming table, recently-listed with day-1 gain table (all already computed in `render_enhanced_ipo_hub`) | 5 per-IPO links to open/most-recent IPOs (ipo family) + /ipo/upcoming/, /ipo/how-to-apply/, /ipo/allotment-status/, /trade-costs/ | SEBI, NSE IPO pages |
| `/ipo/upcoming/` | calendar table of forthcoming issues; "open now" table; T+3 timeline table (SEBI-sourced) | 5 per-IPO links + /ipo/, /ipo/archive/, /calculators/ | SEBI, exchange |
| `/broker/<id>/` (zerodha, groww in scope; template applies to all 48) | regulatory table (SEBI register), active-clients table (NSE UCC), complaint record table, verified-charges table if present (else drop block — never render a pending notice as a block) | /trade-costs/, its two most-clicked /compare/<it>-vs-x/ pages, its SEBI registry entry, /brokers | SEBI registry entry, NSE UCC page |
| `/stock/itc/` | performance snapshot (sessions on file), listing facts, sector peers | peer stock links ×3, /trade-costs/, /calculators/, its compare page if exists | NSE bhavcopy listing page, BSE page |
| `/etf/niftybees/` | NAV table (AMFI), tracked-index block, listing facts | /index/nifty-50/, other Nifty-50-tracking ETFs from index files (already parsed), /etfs, /calculators/ | AMFI NAV file page, NSE listing page |
| `/index/nifty-50/` | index facts (constituent count, base value, from NSE index file), top-10 constituents block, invest-via block (ETFs + index funds tracking it, from index files) | top constituents' /stock/ links, /etf/niftybees/, /etfs, /stocks, /calculators/ | NSE index page, NSE bhavcopy |
| `/news/` | latest-articles table (only if ≥5 articles each link ≥2 entity pages, else the page is demoted per weekly (d) and ships without the panel) | article entity links | exchange/SEBI where an article cites it |
| `/trade-costs/` | statutory-charge table (STT/GST/SEBI fee/stamp duty, each with rule + date), worked-basket table (trade-cost engine), verified per-broker charges table (≥5 brokers with "verified on" dates; else block dropped and the page's pass count comes from the other blocks + calculator links) | /calculators/ hub, 5 per-broker calculator or /broker/ links, /brokers | SEBI fee circular, GST rules page |
| `/compare/` | curated-pairs table (differentiator column from real fields) | /compare/stocks/, /compare/mutual-funds/, 5 pair pages, /brokers | SEBI register |
| `/about`, `/sources` | audit only — verify each already passes; `/sources` must render the `licensing` block per source from `config/sources.json` | existing methodology/editorial-policy/contact links | existing |

## 3. Data sources required

Nothing new is fetched. Every block above uses data the pipeline already ingests (ipo_engine records, broker `built` records, equity_history, index files, AMFI NAV, trade-cost engine output, SEBI register rows) or static rule values (statutory charges), which must be added to `config/sources.json` with their official document URL if not already present — **a source key that does not exist in `config/sources.json` blocks the build**, per §2.1. Statutory charge values (STT %, GST %, SEBI paise-per-lakh, stamp duty per state) are the one likely gap; they are published rules, each needs its own key with the circular/notification URL and an as-of date.

## 4. Titles and freshness (per URL, exact)

- `/ipo/`: "IPOs in India: Open Now, Upcoming & Listing Gains | BrokerLens" + description naming the issues currently open with dates.
- `/ipo/upcoming/`: "Upcoming IPOs in India: Open and Closing Dates | BrokerLens".
- `/broker/<id>/`: keep existing pattern (already entity-specific).
- `/stock/itc/`: keep; ensure description carries the as-of date of the snapshot.
- All 12: `lastmod` = builder freshness stamp (§2.4).

## 5. Done-when criteria (CQA verifies; all must hold before "shipped")

1. All 12 URLs pass the quality bar (`weekly-2026W42.md` §(a) items 1–9) as checked by a script run against the generated `site/` HTML before deploy.
2. Build fails (non-zero exit) on any of: a counted block without a `config/sources.json` source key; a related-link target not in the built page set; an external primary-source link outside the four allowed hosts; banned phrasing (existing guard).
3. `pipeline` run completes and deploys with 0 gate failures (597 QA + 21 VAPT + ad-event tests).
4. CQA re-runs GSC URL Inspection on the 12 URLs within 72h of deploy and records the verdicts in the ledger. Passing bar for this spec: 10 of 12 report non-NEUTRAL (Google inspection lags; 2 may lag one cycle — those two are re-inspected in the following week, spec closes when 12/12).
5. No per-page copy divergence: the shared builder's source/related/freshness markup is byte-identical in structure across the 12 URLs (only values differ) — CQA spot-checks 3 URLs.

## 6. Explicit non-goals / compliance constraints

- No GMP, no predicted listing prices, no "target price" phrasing anywhere in the 12 pages (build guard enforces).
- No ranking/ordering of brokers by economics in `/trade-costs/` or `/compare/` (cheapest-first is already how the calculator sorts — keep it factual, no "best" language).
- `/news` demotion per `weekly-2026W42.md` (d) ships in the same change; it is a sitemap core-list edit, not a content change.
- No new dependencies, no JS changes beyond what the existing templates already load; everything ships server-rendered so crawlers see it (the broker-page Soft-404 lesson: content must survive outside the hydrated `<main>`).

## 7. Effort and schedule

- Shared builder + per-page wiring: M (est. 2–3 build days).
- Statutory-charge source keys: S.
- CQA bar-check script: S (requested, non-blocking — the spec is testable by hand without it).
- Target: in CTO queue this week; shipped and inspected by 2026-10-26. CTO may pull it ahead of any other `docs/{seo,product}` spec; it unblocks O1 directly.
