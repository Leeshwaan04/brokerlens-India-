# Instrument detail pages: enhancement plan (18 Oct 2026)

Scope: stocks, IPOs (mainboard and SME), mutual funds and AMCs, NFOs, ETFs, indices, plus the other page families (brokers, SEBI registry, crypto, comparisons, calculators, news, hubs).

Rules that every item below must respect: never invent a number (unknown is null, shown as "not on file"); every figure carries a source and an as-of date; no investment advice, targets or tips; no account creation anywhere (no third-party sign-ups, no API keys); thin pages stay noindex until they pass a depth gate.

---

## 1. What the live Pashupati page shows (checked against the code)

| # | Finding | Evidence | Fix |
|---|---|---|---|
| 1 | Two different "change" figures on one page | Chart header "Chg +3.31%" is close vs **open** (`stock-chart.js`); the Last close card says +5.36% vs **previous close** | Show close vs previous close everywhere; if intraday is wanted, label it "Day move (open to close)" |
| 2 | Prices lose their decimals | `_inr_html` prints 0 decimals below Rs 1,000: Rs 85.09 shows as "Rs 85", Rs 82.36 as "Rs 82"; a Rs 0.45 stock would show "Rs 0" | Two decimals below Rs 1,000 (and for any price under Rs 10,000 in tiles); never round a price to a whole rupee |
| 3 | Unadjusted split in the history | Pashupati split 10-for-1 on 17 Apr 2026 (close Rs 1,004 to Rs 99). 37 of 2,925 stocks have a break this size in their window; returns across it were wrong | **Fixed in this release** for breaks of 0.55x or less / 1.9x or more (history kept only after the break, with a note). Smaller breaks (3:2 bonus is 0.67x) need a corporate-action feed, see F2 |
| 4 | Units mixed | Chart says "Vol 31.77 L", tile says "31,77,313" | One convention: Indian grouping with the full number, lakh/crore only in headlines with the unit spelled out |
| 5 | Sector "Not disclosed" | Stocks outside the sector indices have no sector | Fall back to NSE industry from index files; otherwise omit the row rather than print "Not disclosed" |
| 6 | Heavy tile boxes, empty space | Six large boxes under the chart push content down; the right column is mostly one banner | Compact stat strip (two rows of six, small type), sticky section nav, one banner on thin pages |
| 7 | Large single-day wick | A one-day high of Rs 111 then Rs 74 (30 Sep, volume 2.8M): real or a data error cannot be told from the page | Data-quality flag (see F4) and a "what happened" line only when a verified corporate action or circuit explains it |

---

## 2. Shared foundations (build once, every page type benefits)

**F1. Page chassis.** One component for all instrument pages: header strip (name, symbol/ISIN, price, change vs previous close, "as of" time, freshness badge); sticky section nav (Overview, Performance, Fundamentals or Holdings, Corporate actions, Peers, Costs, FAQ, Data and sources); compact stat strips; a "Data and sources" panel at the bottom listing each figure's source and date; "Report an error" mailto; consistent FAQ and JSON-LD built only from fields present. Effort M.

**F2. Price history and corporate actions.**
- Backfill daily history to 5 years from the official daily bhavcopy archive (the pipeline already fetches bhavcopy; archive depth, terms and bot-wall behaviour must be confirmed first).
- Corporate actions: the BSE corporate-actions feed already ingested covers upcoming actions; confirm whether a past-actions endpoint exists. Use it to adjust for splits and bonuses properly, replacing the break heuristic.
- Storage: compact per-symbol files (about 2.9K stocks x 1,250 sessions is roughly 150 MB uncompressed; keep out of git, build-time only).
- Unlocks: real 1y/3y/5y returns, 52-week range, CAGR, drawdown, volatility, delivery-percentage series, and honest "price target" intent coverage without forecasts. Effort L, highest leverage.

**F3. NAV history (funds and ETFs).** Official AMFI historical NAV downloads by date range (no account; confirm format and limits). Unlocks fund returns (1y/3y/5y/since launch), calendar-year returns, rolling returns, category percentile, SIP and lumpsum "what it would have become" for every scheme, ETF premium or discount to NAV. Effort M.

**F4. Data-quality layer.** Per-series checks: break detection, stale-price flag (no trade for N sessions), outlier wicks, zero-volume runs, missing-field counts. A page whose key series fails gets the module hidden and an explicit "not shown: data check failed" note, never a guess. Effort S to M.

**F5. Depth gate and indexing.** A page family is submitted in the sitemap only when its template passes a written minimum: at least N sourced data blocks beyond identity, a unique FAQ, internal links in and out, and a freshness stamp. Pages below it stay reachable but noindex. This is the same wave mechanism already live (`SITEMAP_WAVE`). Effort S.

**F6. Number and copy standards.** A single formatter module (price precision, percent, lakh/crore, dates, "not on file"). Banned-phrase build check (target price, guaranteed, multibagger, best stock to buy). Effort S.

**F7. No-account engagement.** Local watchlist and recently viewed (browser storage only), compare tray, "download this table as CSV", RSS and calendar feeds (IPO feed is live; extend to NFOs and corporate actions). Effort M.

**F8. Monetisation placement.** One neutral "Cost to trade this" module with the real brokerage and charges arithmetic already computed by the trade-cost engine, then a single disclosed broker CTA below it. Never crypto banners beside Indian broker content. One banner above the fold on thin pages, three on rich ones at most. Effort S.

---

## 3. Per page family

### 3.1 Stocks (2,943 pages)

Today: candle chart, OHLCV strip, listing facts, performance snapshot (sessions on file), sector peers, compare links, honest "share price target" FAQ.

Add, in order:
1. Fix findings 1, 2, 4, 5, 6 above (days).
2. Returns 1y/3y/5y, 52-week high/low and distance from them, drawdown, volatility, return vs Nifty and vs sector peers (percentile) once F2 lands. Index history from the official index archive (confirm).
3. Delivery percentage and its trend (the full bhavcopy file carries delivered quantity; free and unique).
4. Risk and surveillance flags: price band, ASM/GSM lists, trade-to-trade segment (official exchange lists; confirm endpoints).
5. Derivatives: F&O eligibility and lot size from the exchange lot file, linking to the derivatives cost pages.
6. Ownership and fundamentals (R&D first): shareholding pattern (promoter, FII, DII, public, pledge), quarterly results, dividend history, upcoming and past corporate actions. Sources are the exchanges' public disclosure endpoints; confirm each URL, format and terms before building. Market cap and P/E only if shares outstanding and EPS come from those disclosures, never estimated.
7. Peers table with the same metrics, and "Cost to trade" module (F8).
8. Related: IPO history if recently listed, news mentions, index memberships with ETFs and index funds that track them.

Indexing: top 500 by volume in wave 1 (live); the rest after depth gate.

### 3.2 IPOs (1,262 pages plus apply, subscription and allotment pages)

Done: stage-aware titles, status banner with the SEBI T+3 timeline, upcoming page, RSS and calendar, listing-day gain only from the real candle.

Add:
1. Real retail lot size and minimum application from the offer documents or the exchange issue page (today the lot is a labelled estimate). Confirm the exchange endpoint carrying it.
2. Category-wise subscription (QIB, NII, retail, employees) from the exchange bid-details data, updated through the open window, with "provisional, as of" time. Confirm endpoint and terms first.
3. Registrar per IPO so the allotment link goes to the right registrar page (today all registrars are listed).
4. Anchor investor and allocation facts from the issue documents where machine-readable.
5. Post-listing track: 1 week, 1 month, 3 months returns (history permits for recent IPOs), vs index.
6. Separate mainboard and SME hubs and a year-wise archive with filters (sector, outcome).
7. No GMP, no predicted listing price (research shows it is unofficial and unreliable).

### 3.3 Mutual funds (3,371 schemes) and AMC hubs (55)

Today: NAV table, category tiles, Direct vs Regular NAV gap, related schemes, compare links.

Add:
1. Returns and risk from F3: 1y/3y/5y/since launch (CAGR), calendar-year returns, rolling-return range, maximum drawdown, volatility; category rank and percentile computed from all schemes in the same SEBI category.
2. SIP and lumpsum simulator per scheme using the real NAV series (clearly "past, not a forecast").
3. Costs and size: expense ratio (AMFI publishes daily TER; confirm access), AUM (AMFI monthly scheme-wise average AUM; confirm file), exit load and minimum investment (scheme documents; parse only what is machine-readable, otherwise link the document).
4. Benchmark and riskometer from the scheme documents (SEBI/AMC); fund manager only if present in a primary document.
5. Portfolio holdings from the monthly disclosure (varies by AMC; scope per AMC after R&D, never scraped from aggregators).
6. Peers: top 10 in category by 3y return with the same columns; curated comparison links (existing).
7. AMC pages: sponsor, trustee and AMC details from the SEBI mutual-fund register, AUM by month (AMFI), category mix and performance summary versus category averages, new launches.

### 3.4 NFOs (new family)

Source chosen earlier: SEBI's own filing index of scheme information documents. Release in two steps:
1. **Pipeline page** (what is verifiable now): scheme name, AMC, category (from the document), filing date, link to the SID/KIM, status "filed" and "open" only when an open and close date is on a primary source. `/nfo/` hub plus per-scheme pages, RSS and calendar feeds like IPOs.
2. **Open-NFO detail**: minimum investment, exit load, benchmark, plan options, allotment date, parsed from the SID only when extraction is reliable; otherwise a clearly labelled link. Each field shows the SID section it came from.
Compliance: no "should you invest" language; the page states facts and links the offer document.

### 3.5 ETFs (351 pages)

Today: AMFI name, AMC, NAV, tracked index, listing facts.

Add:
1. Market price, volume and traded value from daily bhavcopy (ETFs trade as listed securities), with the same history and returns as stocks.
2. **Premium or discount to NAV**: exchange close versus AMFI NAV on the same date. Real, unique, and a genuine investor concern.
3. **Tracking difference** versus the index over 1y/3y (index total-return series from the index provider's public archive; confirm).
4. Expense ratio and AUM (as 3.3).
5. "All ETFs tracking this index" comparison table (price, NAV, premium, volume, expense ratio), which doubles as a hub page per index.
6. Holdings: the index constituents (already on file), weights where the index factsheet is machine-readable.

### 3.6 Indices (25 pages)

Add index performance (1m to 5y), valuation (P/E, P/B, dividend yield from the index provider's published files; confirm), sector weights, top movers inside the index from bhavcopy, and the "how people invest in this index" block linking ETFs, index funds and the futures lot. These are the evergreen head-term pages (for example "Nifty PE ratio").

### 3.7 Brokers (48 profiles)

Done: regulatory table, verify and complain guides, FAQ, cost-page links.

Add: per-broker brokerage and charges calculators with a "verified on" date from the broker's own tariff page and the statutory rates (STT, exchange charges, GST, SEBI fee, stamp duty); complaint record from the SEBI Annexure-B disclosures where crawled; NSE active-client data once the ingest is live; account-opening facts from the broker's own pages with dates; "alternatives to X" built from real fields; compare links.

### 3.8 SEBI registry (1,703 pages)

Best performer by clicks. Add category and state hubs with descriptive links, status and validity blocks, related entities by real relationship, a factual "is X SEBI registered" answer with the verify and complaint steps, and a cross-check against the defaulter list stated as a record, never an opinion. Noindex entities that would show only a name and number.

### 3.9 Crypto (29 pages)

Keep small: price history and returns from the existing feed, the India tax and TDS facts as rules with dates, no affiliate banners near Indian broker content.

### 3.10 Comparison pages

Only the curated sector and category pairs stay indexable. Enrich with side-by-side returns, risk and costs from F2 and F3. The all-pairs pages stay noindex and out of every sitemap.

### 3.11 Calculators

Per-broker brokerage calculators (above), SIP and lumpsum by actual scheme, tax calculators for capital gains using the statutory rates with the financial-year stamp.

### 3.12 News and hubs

Entity-linked market wraps (each instrument mentioned links to its page, and its page lists recent mentions), a clear byline and corrections policy, and A to Z and category hubs so every instrument is within three clicks.

---

## 4. Data sources: confirmed vs to verify

| Need | Source | Status |
|---|---|---|
| Daily prices, volume, delivery | Exchange bhavcopy (in use, last ~120 sessions) | In use; archive depth and redistribution terms to confirm |
| Listings, ETFs, indices | Exchange listed-securities, ETF and index files | In use |
| Upcoming corporate actions | BSE corporate-actions feed | In use; past actions to confirm |
| Fund NAV and category | AMFI daily NAV file | In use |
| Fund NAV history, TER, AUM | AMFI downloads | To verify (format, limits) |
| Index history, valuation, TRI | Index provider public archive | To verify |
| Shareholding, results, dividends | Exchange public disclosure endpoints | To verify |
| IPO lot size, category bids, registrar | Exchange issue pages and bid-details | To verify |
| NFO filings | SEBI scheme-document index | Partly probed earlier |
| ASM/GSM, price bands, F&O lots | Exchange published lists | To verify |

Every "to verify" item gets a short R&D note (URL fetched, fields, size, terms) before any build. Anything needing an account or key is excluded.

---

## 5. Phasing

| Phase | Weeks | Scope | Gate to start next |
|---|---|---|---|
| 0 | this week | Findings 1, 2, 4, 5, 6; F6 formatter; split-break trim (done) | QA clean |
| 1 | 2 to 3 | F2 5-year history, F3 NAV history, F4 quality layer; returns/CAGR/drawdown on stocks, funds, ETFs, indices; ETF premium to NAV; fund category percentile | Returns match an independent spot check on 20 instruments |
| 2 | 3 to 4 | F1 chassis, delivery %, ASM/GSM flags, F&O lots, index valuation, ETF same-index hubs, TER and AUM, NFO pipeline pages and feeds | Wave-1 pages indexing |
| 3 | 3 to 4 | Fundamentals and ownership (after R&D), IPO lot size, category subscription, registrar mapping, SID-parsed NFO fields | Source terms confirmed |
| 4 | ongoing | No-account tools (watchlist, compare tray, CSV), per-broker calculators, registry hubs, US and GCC equivalents on the same chassis | n/a |

## 6. Success measures (from Search Console, no new tools)

Indexed share per sitemap wave (promote the next wave at 50 percent or more); clicks and CTR per page family against the baseline in `docs/GROWTH_PLAN_2026-10.md`; count of pages failing the data-quality layer (target zero shown with bad data); share of pages with at least five sourced data blocks.

## 7. Risks and open questions

- **Data terms.** Exchange and AMFI terms on redistributing historical data must be read before the 5-year backfill ships. If restrictive, show computed metrics (returns, ranges) and link to the source rather than republishing raw series.
- **Bot walls.** Exchange sites throttle automated access; the backfill must be paced and cached outside git, and a failed day must never break the build.
- **Build time.** More series and more modules lengthen the build; budget and cache per symbol.
- **Scope discipline.** Each module ships behind its depth gate and QA tests; nothing is submitted to Google before the previous wave indexes.
