# CPO roadmap delta — 2026-W42 (week of 2026-10-19)

Owner: CPO. Cadence: Tuesday weekly. This file supersedes nothing; it is the delta for the week.
Milestone context: O1 hard target 1,000 GSC clicks / 100,000 impressions by 2026-11-03. Baseline (17 Oct): 630 clicks / 62,005 impressions, 90-day; daily clicks 28–69, impressions ~688/day. At current run-rate the 100K-impressions leg is reachable; the 1,000-clicks leg is not, without fixing CTR on pages that already hold ~25.5K IPO impressions at 0.11% CTR.

## (a) Quality bar — what a "high-quality page" is (binding, effective this week)

A page is **high-quality (passing)** if and only if ALL of the following hold in the rendered HTML (not in JSON-LD alone, not in JS-only output):

1. **≥3 rendered data blocks with values.** A data block is a table, stat strip, or key-facts panel populated with real values. Rows reading "Not disclosed", "not on file", "–", or a pending/placeholder notice do not count. Example that passes: broker regulatory table + active-clients table + complaint counts table. Example that fails: one table plus two empty stat cards.
2. **Source + as-of on every data block.** Each counted block carries a visible source line naming a source key that exists in `config/sources.json` (or a named primary document) and a date (feed as-of date or "verified on" date).
3. **≥5 internal links to live site pages**, at least 3 of which are to different page families than the current page (e.g. a broker profile must link to a calculator, a compare page, and the registry). Orphan pages fail by definition.
4. **≥2 outbound links to primary sources** (sebi.gov.in, nseindia.com, bseindia.com, amfiindia.com) from the body, not just the footer.
5. **Body ≥600 words of unique, entity-specific or stage-specific content** (excluding nav, footer, shared disclosures). "Unique" = not the same paragraph verbatim across the page family.
6. **Unique title and meta description.** Title must name the specific entity, stage, or outcome (not a family-generic title). No two pages in the same family may share a title pattern with only the entity name swapped in a way that produces identical snippets at length.
7. **Freshness stamp visible in the body** ("Updated <date>", "As of <date>"), and `lastmod` in the sitemap consistent with the last data change.
8. **JSON-LD matches visible content** (FAQPage only for FAQs actually on the page; ItemList only for visible lists).
9. **Zero banned phrasing**: no "guaranteed", "target price", "assured returns", "multibagger", "best stock to buy", no GMP figures, no predicted listing prices. (CQA owns the build-time guard check; CPO owns this rule.)

CQA: please add a scriptable check per item 1, 2, 3, 8, 9 against a URL list; it makes my secondary KPI (conversion of NEUTRAL pages to passing, and % of GSC-click pages that are high-quality) measurable. The current NEUTRAL list is the test set: the 12 URLs in (b) below must fail the bar today and pass after remediation; `/ipo/kfintech/`, `/stock/tcs/`, `/calculators/sip-calculator/`, `/registry`, `/sebi-registry/qe-securities-llp/` must already pass it. If a "passing" GSC page fails this bar, tell me which item fails — I will re-scope, not argue.

## (b) NEUTRAL → passing remediation plan, ordered by traffic potential

For each URL: what it must contain to pass the bar. Full template details and done-when criteria live in `docs/product/spec-20261019-neutral-hub-remediation.md` (this is the execution spec; this table is the CPO decision).

| # | URL | Family traffic | What it must contain to pass |
|---|-----|----------------|------------------------------|
| 1 | `/ipo/` | IPO: 1,079p / 27c / 25,464i (0.11% CTR, worst) | Currently renders open/forthcoming/recently-listed tables. Add: (i) a key-facts panel on every row-linked IPO (price band, lot size, dates, registrar) with "per RHP, subject to change" label and source line; (ii) a "how to read this page" explainer ≥150 words; (iii) a dated status legend (Open / Allotment / Listed) with SEBI T+3 timeline sourced to SEBI; (iv) ≥5 links out to per-IPO pages of currently open or most recent IPOs; (v) title rewritten to lead with what is open now and the dates; (vi) freshness stamp = last data pull. No GMP anywhere. |
| 2 | `/ipo/upcoming/` | same family, the "upcoming ipo" head term | Distinct from `/ipo/` (no duplicate tables): a calendar view of every forthcoming IPO with open/close dates, price band where published, lot size where published, each row linking to its per-IPO page; a 4-step "how an IPO moves from open to listed" explainer (sourced, dated); the RSS/ICS feed links; FAQPage for 3–5 real upcoming-IPO questions (what "forthcoming" means, how to check dates, SME Rs 2 lakh minimum stated as current rule); title = "Upcoming IPOs in India: Open and Closing Dates | BrokerLens". |
| 3 | `/broker/zerodha/` | Broker: 388p / 3c; previously Soft 404 | Already enriched (regulatory table, verify/complain guides, FAQ). Gap vs bar: outbound primary-source links must be in-body (SEBI registry entry, NSE UCC client-count page); add a "costs" data block showing verified charges or an honest pending notice (a pending notice does not count as a data block, so if zerodha has no verified charges it must carry ≥3 other counted blocks: regulatory, active clients, complaints); related links to /trade-costs/, the zerodha-vs-5paisa and zerodha-vs-angel-one compare pages, and the registry entry. |
| 4 | `/broker/groww/` | same family | Same template fix as zerodha; groww additionally must show its actual registration categories from the SEBI register (it is not a full-service broker — the page must state the registered categories as a data block, which is what makes the page unique vs zerodha's). |
| 5 | `/stock/itc/` | Stock: 1,815p / 293c (best stock performer) | Must match the TCS passing bar: performance snapshot from sessions on file, listing facts, sector peers, honest target FAQ, cost-to-trade links. Add as-of date on the snapshot block and a source line (NSE bhavcopy). If ITC currently renders fewer than 3 populated blocks, fix data ingestion for that symbol rather than the template. |
| 6 | `/etf/niftybees/` | ETF: 443i family; niftybees is the head ETF | Add: NAV table block (AMFI, as-of date), tracked-index block linking /index/nifty-50/, listing facts block (exchange, ISIN, IPO date from NSE file), a one-paragraph "what Nifty BeES tracks" explainer sourced to the index file, links to all ETFs tracking Nifty 50 (data already in index files) and /etfs hub. Premium/discount to NAV is the instrument-plan feature F3/F5-ETF — request it as the second wave for this URL, not in this fix. |
| 7 | `/index/nifty-50/` | head-term index page ("nifty" queries) | Add: index facts block (number of constituents, index date, base value from NSE index file, as-of date), top-10 constituents by weight if weights are machine-readable (otherwise by name with the existing constituent list), a "how people invest in this index" block linking ETFs and index funds that track it, a how-to-read explainer. Valuation (P/E etc.) is instrument-plan §3.6 — second wave, gated on index-provider file terms. |
| 8 | `/news/` | small today; trust surface | See (d) — demoted from wave-1 sitemap this week. To re-earn indexing it needs: ≥5 articles each linking ≥2 entity pages (stock/IPO/broker/registry), a named byline (real person or "BrokerLens editorial") + corrections-policy line on every article, a freshness stamp per article. Until then: noindex-eligible, held out of the core sitemap. |
| 9 | `/trade-costs/` | direct CTO traction surface | Must carry ≥3 populated cost data blocks: statutory-charge table (STT, GST, SEBI fees, stamp duty — sourced to the respective circulars/rules with dates), the worked-example basket table (already computed by the trade-cost engine), and a per-broker verified-charges table (every broker that has a verified rate card, with "verified on" dates). Until the verified-charges table is populated with ≥5 brokers, this page is the CTO's first traction deliverable — see (c). |
| 10 | `/compare/` (and top compare pairs) | compare: 232i / 3c, pos 9.0 | The bare `/compare` hub is in the core sitemap. It must list the curated pairs with a one-line factual differentiator each (from real fields), link /compare/stocks/ and /compare/mutual-funds/, and carry the quality bar via the hub variant of item (a) (data block = the comparison table itself). All-pairs permutations stay noindex, out of sitemap (already so — confirmed). |
| 11 | `/about` | trust/E-E-A-T | Already a comprehensive E-E-A-T page. Verify it passes the bar as-is (byline/authorship statement, links to methodology/sources/editorial-policy, contact). Expected fix: zero or one missing item. |
| 12 | `/sources` | trust/E-E-A-T | Must pass the bar as-is or be flagged to me: it should list every source with URL, what we take from it, as-of cadence, and a per-source license/terms note (the `licensing` block in `config/sources.json` should render). If the licensing note renders, this page passes on data-block strength alone. |

Sequencing: 1–2 ship in week 1 (they are the CTR fix, not the indexing fix — fastest path to the 1,000-click milestone). 3–7 week 2. 8–12 in the same cycle as the spec. CQA to re-run URL Inspection evidence after each batch ships.

## (c) Product-side priority list for CTO traction-page development (this month)

CTO target: ≥10 lead-bearing pages/week from 2026-10-20. Each page below counts if it ships with a lead/capture surface (calculator, cost tool, or onboarding CTA) and passes the (a) bar. Order is my priority order, not a queue CTO must consume serially:

1. **Per-broker brokerage calculators** (5 URLs: zerodha, 5paisa, angel-one, groww, upstox): formula shown, statutory charges with source+date, "verified on" stamp per broker, broker CTA below. Doubles as the broker-profile uniqueness fix and populates the /trade-costs/ table in (b)#9. Instrument plan §3.7/§3.11, growth plan item 8.
2. **`/trade-costs/` enrichment** (b)#9 — same data, hub URL.
3. **`/open-demat-account`**: KYC checklist, per-broker UTM links (IBSL tag per CBO), one-line affiliate + risk disclosure. Growth plan item 7. Lead surface = the outbound broker links; this is the highest-intent page we can build this month.
4. **Capital-gains tax calculator** (`/calculators/capital-gains/`): statutory rates with financial-year stamp; static, formula-based, low risk.
5. **Index valuation pages** (`/index/nifty-50/` P/E/PB/yield, then Nifty Bank): gated on index-provider file terms — if R&D says no by 2026-10-27, skip and take #6. Instrument plan §3.6.
6. **ETF premium/discount to NAV** for the 10 most-traded ETFs: exchange close vs AMFI NAV same date. Genuinely unique data, no terms risk. Instrument plan §3.5.
7. **`/ipo/how-to-apply/`** enrichment: step-by-step with demat CTA at the natural moment (not a popup).
8. **Registry category hubs** (stock brokers, research analysts, investment advisers, portfolio managers): A-to-Z plus category, plain links. Our best-ranking family (pos 7.4) needs the spine. Growth plan item 4.
9. **Top-10 funds by 3y return with category percentile** (needs F3 NAV history — if F3 not landed by 2026-10-27, swap with #8's letter hubs).
10. **`/ipo/allotment-status/`** enrichment: registrar deep links, T+3 timeline table (per-IPO registrar mapping lands with instrument plan phase 3; hub page can ship generic-but-correct first).

Do NOT build (CPO veto, binding): broker "fit" quiz or "best broker" rankings (advertisement-code risk); GMP or predicted-listing-price pages of any form; embeddable calculator widgets (link-value trap, and we have no distribution); any page whose data is not in `config/sources.json` or a named primary document.

## (d) Cut / demote this week (with rationale)

1. **`/news` demoted out of the core sitemap (wave-1 → held) effective this week's build.** Rationale: the news corpus today has no consistent bylines or corrections policy, so on a YMYL domain it is net trust-negative and is one of the 12 NEUTRAL URLs. It is an unindexed-quality hold, not a content kill: articles keep being generated, and the URL re-enters the sitemap the day it satisfies (b)#8. This is within CPO authority (unindexed URL, noindex/held-back tier policy). CQA: please confirm via URL Inspection that /news/ is not currently indexed before the next deploy that ships this change; if it is indexed, hold the change and I will re-decide. **No page with >10 monthly clicks is cut or demoted this week.** `/news` is flagged here for CBO awareness (it is not in the current money-page set; if CBO's weekly list puts any demoted URL over 10 clicks/month, that demotion voids and I re-decide within 48h).
2. **Not cut, explicitly parked:** all fund (3,371), ETF (351), AMC, and all-pairs compare permutations stay in their current wave-2/noindex state. No demotions of the 88,672 held-back URLs this week — the instrument-plan data work (F2/F3) is the only thing that earns them indexing; cutting them would destroy the path to O2's 80% wave-1-plus-tail target.
3. **Cut from CTO's candidate backlog if it appears:** "broker comparison by commission" ranking pages — they would require ordering brokers by economics, which the growth plan's do-not-do list already forbids. Flagged so it does not come back as a CTO-originated page.

## Decisions needing ack (tracked in ledger)

- CBO: awareness ack requested on the `/news` sitemap demotion (no expected revenue impact; it carries an IBSL banner). 48h SLA, silence = approved.
- CQA: quality-bar check script per (a) — requested, not blocking.
