# Growth plan and Search Console R&D, 17 Oct 2026

Source data: Search Console API (90 days to 14 Oct 2026, read-only, via scripts/gsc_client.py) plus five parallel market-research streams (competitors, IPO/SME search behaviour, lead generation, SEO quality for new domains, link building), synthesised against our own numbers. Research claims are the researchers' and should be spot-checked before anything irreversible is built on them; the Search Console figures are ours.

## 1. What Search Console says

| Metric | Value |
|---|---|
| Clicks (90d) | ~293 |
| Impressions (90d) | ~51.7K |
| CTR | 0.56% |
| Average position | 18.6 (mobile 13.3, desktop 22.7) |
| Country | India 97% of clicks |
| Device | Mobile 60% of clicks |
| Sitemap | ~255K submitted, Google reports 0 indexed |

Daily clicks are rising fast (51 on 13 Oct vs about 5 on 2 Oct), almost all from two sources below.

| Page family | Clicks | Impressions | Pages | Avg position |
|---|---|---|---|---|
| sebi-registry (entity names) | 109 | 2,998 | 83 | 7.4 |
| retired share-price-target pages | 126 | 2,241 | 89 | 6.0 |
| ipo/kfintech | 5 | 1,227 | 1 | 8.9 |
| fund | 4 | 1,018 | 201 | 36.8 |
| funds-by (AMC) | 0 | 564 | 14 | 56.8 |
| etf | 1 | 443 | 25 | 10.2 |
| broker | 1 | 334 | 140 | 16.7 |
| compare | 3 | 232 | 146 | 9.0 |

Spot checks: home, /brokers, methodology, SIP calculator and BTC are indexed; stock, ETF and brokers-by pages are 'Discovered, currently not indexed'; /sources is unknown to Google; /broker/zerodha/ was flagged Soft 404 (thin page, since enriched, see section 3).

Query buckets: IPO / GMP / allotment 448 queries and 2,780 impressions but 7 clicks; broker and entity names 17 clicks; '<company> share price target' 43 clicks from 860 impressions. Many impressions sit at position 5 to 10 with CTR below 1%, which is a snippet and freshness problem more than a ranking problem.

## 2. Diagnoses

- Index and quality trust, not ranking: Google shows 0 of ~255K sitemap URLs indexed, yet SEBI entity pages already earn clicks at pos 7.4. So the problem is that we ask a new, zero-authority domain to index a mass of near-identical templated pages (stock, ETF, fund, AMC, compare, brokers-by) that sit in 'Discovered, not indexed' and drag down site-level trust. Broker/zerodha as a Soft 404 confirms thin pages even on our core commercial URLs. A single flat sitemap also hides which templates Google accepts.
- We win where the query is a named entity or event, and we lose the CTR game where we already rank: IPO pages sit at pos 8 to 13 with 1,000+ impressions at ~0.2% CTR (generic titles, no stage or freshness signal, no 'upcoming IPO' head page), and the retired 'share price target' pages proved 126 clicks of demand that we now serve with nothing compliant. Fund/AMC pages at pos 37 to 64 have no differentiated data.
- No owned audience and no authority loop: zero email capture, a thin internal link spine (stock/ETF pages are discovered but not prominent), no earned backlinks, and monetisation that is not tied to high-intent moments (allotment, how-to-apply). At ~100 organic clicks a month, nothing compounds, so every visit currently leaves and never returns.

## 3. Already shipped from this analysis (17 Oct)

- Broker profiles: real regulatory table from the SEBI register, how to verify, how to complain (SEBI SCORES, SMART ODR), links to cost pages, FAQ with FAQPage data. Placed outside the interactive area so it survives hydration (targets the Soft 404).
- Stock pages: performance snapshot computed only from the sessions on file, and an honest 'share price target' FAQ with no forecast number (serves the real demand without fabricating).
- Listed IPO pages: titles and descriptions now lead with the real outcome (issue price, listing gain), and a fixed price shows one number.
- AMC, ETF and fund pages enriched earlier the same day.

## 4. Ranked 90-day roadmap

### 1. Tiered sitemaps plus a minimum-value gate (prune before you grow)
- Why: 0 of 255K indexed, stock/ETF/brokers-by in 'Discovered, not indexed', Soft 404 on broker/zerodha. Google treats quality at site level, and sitemaps are only hints. Our proven demand is entity pages, IPO pages and broker profiles, so give Google only those first and use per-type sitemaps to see which template it rejects.
- First week: Sitemap index with one child sitemap per page type (SEBI entities, 48 brokers, IPO, calculators, news, top stocks, funds/ETFs/compare). Submit only Wave 1 (home, brokers, IPO, calculators, news, top ~1K to 3K entity pages by GSC impressions). Noindex and drop from sitemaps all fund, ETF, AMC and compare permutations plus any template failing a written content-depth rule. Inspect broker/zerodha with live URL test and rendered screenshot, and fix the root cause (likely thin or JS-dependent body), then give all 48 broker profiles real fee, account-opening and complaint-data blocks.
- Effort / impact: S to M (about 3 to 5 days for tiering and noindex; broker page fixes ongoing) / High (unblocks everything else; expect indexed counts to appear per sitemap in 2 to 6 weeks)
- KPI: Indexed count per child sitemap in Search Console (weekly), Wave 1 indexed rate (target above 60%), Soft 404 count, impressions growth
- Risk and compliance: Do not pad pages with filler or fabricated numbers to pass the gate; pages that cannot be given real sourced data stay noindexed. Re-add fund/ETF pages only as unique data coverage improves. Add 'source and as-of date' on every data block.

### 2. IPO lifecycle template and CTR rewrite (upcoming-IPO hub plus per-IPO stable URLs)
- Why: IPO pages already rank pos 8 to 13 with 1,000+ impressions at ~0.2% CTR, so this is the cheapest traffic we can get (CTR and freshness, not ranking). Chittorgarh's biggest asset is the 'upcoming ipo' head page plus per-IPO name pages. All fields are from SEBI/NSE/BSE primary sources.
- First week: Rewrite titles and meta descriptions on the top 20 IPO pages by impressions to stage patterns such as '<Company> IPO: dates, price band, lot size, allotment status' and '<Company> IPO Subscription Status Day n: QIB, NII, Retail'. Add an 'Updated at' stamp, a status badge (Open, Allotment, Listed), a key-facts block (price band, lot, issue size, registrar, exchange, dates labelled 'per RHP, subject to change') and FAQ schema where accurate. Publish an /upcoming-ipo hub with a calendar. Keep one URL per IPO across stages.
- Effort / impact: M / High
- KPI: CTR and clicks per IPO page group (baseline 0.2%; target 1% or more in 4 weeks per batch), impressions for 'upcoming ipo' and '<name> ipo' queries
- Risk and compliance: No GMP and no predicted listing price. SME minimum application is Rs 2 lakh until SEBI notifies the Rs 1 lakh proposal, so state it as current rule only. No copy naming data vendors or fallback mechanics. No em dashes in UI copy.

### 3. Allotment-status and listing-result pages (registrar deep links, T+3 timeline)
- Why: Allotment is the highest-intent IPO moment, and the lookup needs PAN on the registrar site, so a per-IPO page with the right registrar link and dates answers the query without handling personal data. Broker blogs rank with generic guides, so a precise per-IPO page is a gap we can fill.
- First week: Add registrar_name, registrar_allotment_url and bse_allotment_url fields to each IPO record in pipeline/ipo_engine.py. Render a 3-step 'how to check' block with expected basis-of-allotment, refund and listing dates (T, T+1, T+2, T+3) and a post-listing table (issue price, listing price, gain %, day-1 close from exchange data). Verify every link before its allotment date.
- Effort / impact: S / High (seasonal spikes, strong conversion to email and demat CTAs)
- KPI: Clicks and impressions on 'allotment status' query group, outbound registrar click-through, time on page
- Risk and compliance: Never ask for or store PAN or application numbers. Listing gain is a reported historical fact only, not a signal. Label SME allotments as lottery-based.

### 4. SEBI registry entity hubs and internal link spine
- Why: Entity pages are our best performer (109 clicks, pos 7.4) and queries are plain entity names. Google finds and weights pages through crawlable links, and stock/ETF pages are 'discovered' only, which signals weak internal prominence. Strengthening what already ranks is cheaper than adding pages.
- First week: Category hubs (stock brokers, research analysts, investment advisers, portfolio managers, A to Z) with plain `<a href>` links. On each entity page add a registration status, category, validity, address and 'last updated' block, a link to the relevant hub, related entities by real relationship (same category or registrant type), and links to the matching broker profile or calculator. Crawl the site for orphans and click depth over 3.
- Effort / impact: S to M / Medium to high
- KPI: Clicks and avg position for entity queries (baseline 109 clicks, pos 7.4), Wave 2 indexed rate, internal links per Wave 1 and Wave 2 page, orphan count (target 0)
- Risk and compliance: Present registry status as factual and dated; no editorial commentary on whether an entity is good or bad. Noindex near-empty entity pages.

### 5. Compliance and trust layer (disclosure, DPDP notice, wording guard, authorship)
- Why: Our broker partners are SEBI-regulated and cannot associate with anyone making advice or return claims, so compliance protects revenue. It is also the E-E-A-T trust fix for a YMYL new domain. Needed before any email capture, and DPDP duties land around May 2027.
- First week: Ship a referral and advertising disclosure page and a visible 'we may earn a referral fee' line above every affiliate banner (not only the footer), rel="sponsored" on all affiliate links, a standalone privacy and consent notice (data, purpose, withdrawal, grievance contact), Organization JSON-LD, per-data-family methodology pages (SEBI registry, broker costs, IPO data), and a build-time wording guard in the publish pipeline that fails on 'guaranteed', 'target price', 'assured returns', 'multibagger', 'best stock to buy'.
- Effort / impact: S / Medium (protects revenue, supports indexing trust)
- KPI: Zero wording-guard failures in production, disclosure present on 100% of affiliate placements, methodology page linked from every data template
- Risk and compliance: Have counsel confirm disclosure wording against ASCI influencer guidance and SEBI's Jan 2025 FAQs, and read the 8 Oct 2026 Common Advertisement Code from sebi.gov.in (only a single secondary source so far). Bylines must be real people or a clearly labelled editorial team. Never name data vendors in public copy. Keep crypto affiliate content away from Indian broker pages.

### 6. Free IPO and regulatory-events email digest (first owned audience)
- Why: We have no lead capture, and few trackers offer alerts. IPO pages (1,000+ impressions) and registry pages (pos 7.4) are the capture surfaces, and facts-only alerts need no advice. At ~100 organic clicks a month, volume will be single digits at first, so the aim is a working compliant pipe now that scales when indexing improves.
- First week: Single inline email field (no popups) on IPO, allotment and SEBI entity pages, double opt-in, consent timestamp and notice version stored, one-click unsubscribe, and a first template generated from pipeline/ipo_engine.py data (IPO opens, closes, allotment date, listing date, SEBI registry changes). Confirm free-tier limits and deliverability of the ESP (Hostinger Reach is already connected) before launch.
- Effort / impact: M / High over 90 days, low in week 1
- KPI: Signups per 1,000 IPO page views by placement (stretch benchmark 2%), double opt-in rate, unsubscribe rate, repeat visits from email
- Risk and compliance: Only dated facts; no GMP, no 'apply' or 'avoid', no targets. Email only, no PAN or phone. Do not run exit-intent or countdown patterns. Depends on initiative 5 being live.

### 7. Demat handoff CTA at post-intent moments
- Why: Users who need a demat account to apply to an IPO are the converting audience, and we already hold Zerodha, 5paisa and Angel One referral links. Today banners are not tied to those moments. Revenue per session matters more than sessions at our size.
- First week: A neutral 'Open a demat account to apply for IPOs' module with a one-line affiliate and risk disclosure on upcoming-IPO, how-to-apply, allotment and listing-day pages, plus a /open-demat-account page with a KYC checklist and per-broker UTM links. Track outbound clicks per 1,000 sessions by page stage.
- Effort / impact: S / Medium
- KPI: Outbound affiliate clicks per 1,000 sessions by page type, click-to-account rate reported by brokers
- Risk and compliance: Indian broker banners only, never crypto affiliates nearby. No cashback or reward language of our own, no 'apply now' or 'guaranteed'. Do not collect PAN, Aadhaar, bank or phone. Ask each broker's affiliate team in writing what referrers may say.

### 8. Per-broker brokerage and charges calculators (plus SIP and CAGR second wave)
- Why: Calculators are the largest organic category among Indian finance leaders, and broker-cost tools have proven demand (competitors copy Zerodha's). We already own trade-cost calculators and 48 broker profiles, and affiliate placement is natural here. It also gives each broker profile unique content to fix Soft 404 risk.
- First week: Five per-broker URLs (Zerodha, 5paisa, Angel One and the two largest others) such as 'Zerodha brokerage calculator', with the formula shown, statutory charges (STT, exchange fees, GST, SEBI fee, stamp duty) sourced to circulars, and a dated 'verified on' stamp from each broker's published tariff. Link from the broker profile and trade-cost pages.
- Effort / impact: M / High (medium-term, query-specific)
- KPI: Impressions and clicks on '<broker> brokerage calculator' queries, calculator-to-broker-page click rate, affiliate clicks
- Risk and compliance: Label as 'illustrative, not a return projection'. Show every broker on equal terms, never ordered by commission. Add 'verified on' dates and refresh when tariffs change. Affiliate banners on broker-cost pages only.

### 9. Index-level indicator pages (Nifty PE, PB, dividend yield; FII and DII daily activity)
- Why: Single head pages with daily recurring intent and no entity-count requirement; competitors rank first for 'nifty pe ratio'. Data comes from NSE files, so it is verifiable and non-advisory.
- First week: A Nifty 50 PE, PB and dividend yield page with a history chart, 'as of' date, a 'how to read this' explainer and daily static regeneration in the pipeline. Check NSE file terms of use first.
- Effort / impact: S / Medium
- KPI: Impressions and avg position for 'nifty pe ratio' and related head terms, returning-visitor share
- Risk and compliance: Describe values only; never label them cheap, expensive, buy or sell. Add a disclaimer. Skip if NSE terms bar automated reuse.

### 10. Live category-wise subscription tables (gated on exchange terms)
- Why: Subscription status is a query peak during every IPO window, and the data is exchange-published. It adds freshness that lifts the IPO template, but it carries the highest operational burden and terms uncertainty.
- First week: Confirm NSE and BSE public bid-detail pages and their terms of use in writing. If allowed, a 30-minute scheduled job on open days writing JSON per IPO (QIB, sNII, bNII, retail, total) with a 'Provisional, as published by the exchanges, as of <time>' line. If not, a manual last-day update only.
- Effort / impact: M / Medium to high during IPO windows
- KPI: Clicks on 'subscription status' queries, share of IPO page traffic during open days, update latency
- Risk and compliance: Never estimate missing figures. Do not scrape logged-in pages. Do not name vendors or fallback mechanics in copy.

### 11. Factual stock pages for the top 300 to 500 names, with an evergreen 'why we do not publish price targets' explainer
- Why: The 126 clicks on retired target pages show real '<company> share price' intent, and stock pages are currently thin ('Discovered, not indexed'). Serve the factual half with a limited set rather than 2.6K thin pages. This is the largest build, so it follows initiatives 1 and 4.
- First week: Pilot 25 large-cap stock pages with shareholding pattern, corporate actions, results calendar, listing details, delivery and bulk or block deals (NSE and BSE files), each with an as-of date and a plain-language data block. Publish one evergreen explainer on why we do not publish targets, linking to the SEBI registered research analyst registry pages. Noindex the remaining stock pages.
- Effort / impact: L / High long term, low in 90 days
- KPI: Indexed rate for the pilot set, impressions for '<company> share price' queries, clicks per stock page versus the noindexed set
- Risk and compliance: No targets, forecasts, ratings or 'top picks' and no per-company target pages. Counsel to review how recent price data is shown against SEBI's 30-day lag rule for educational content (8 May 2026 circular, secondary source) and the July 2025 research-analyst FAQs. Start with non-price data blocks if unsure.

### 12. Citable data assets and journalist outreach (SEBI registry monthly changes, then a broker-cost report)
- Why: A zero-authority domain needs real editorial links, and the only compliant route is publishing original primary-source data that reporters and compliance newsletters cite. The registry pipeline (pipeline/publish.py) already diffs sources, so a monthly dataset is cheap and builds on our best-ranking page type.
- First week: A 'SEBI registry changes, <month>' hub page with new, cancelled and penalised entities, a CSV download and a methodology note citing SEBI on every number. Build a shortlist of 15 named beat reporters (ET, Moneycontrol, Mint, Business Standard, Inc42, YourStory) and send 5 pitches of under 150 words, each built on one number, with one follow-up after a week.
- Effort / impact: M / Medium to high (compounds over quarters, expect 1 to 5 links per campaign)
- KPI: Referring domains in Search Console Links (monthly), branded query impressions, referral sessions from press
- Risk and compliance: Factual only, no editorialising, no 'best broker' framing. All earned or rel=sponsored links only, no exchanges or paid placements. Have counsel read the report before sending. The broker-cost report can follow in month 3 once calculators are live.

## 5. Do not do

- Do NOT publish GMP, predicted listing prices or any grey-market figures: unofficial, often wrong (the NSE IPO listed at 0.84% against a higher implied premium) and it puts our SEBI-regulated broker referrals at risk. Serve the same intent with official listing results and a 'GMP explained' evergreen page.
- Do NOT rebuild per-company 'share price target' or forecast pages, buy/sell views, 'top picks' or return claims in any form. These are the exact pattern of SEBI's unregistered-advice rules and Google's scaled-content policy.
- Do NOT submit all ~255K URLs or keep generating thin stock, ETF, fund, AMC and compare permutations. Noindex or remove them until each has real unique sourced data.
- Do NOT run Telegram or WhatsApp channels, exit-intent popups with countdowns or false urgency, or YouTube Shorts market commentary yet. These are the highest SEBI enforcement and dark-pattern risk for the least payoff at our list size. Revisit a one-way, facts-only channel once the email list has a few hundred subscribers and counsel approves.
- Do NOT build the 'broker fit' quiz or any 'best broker' ranking now: it sits close to the recommendation line and the new advertisement code restricts ranking claims. Revisit as a transparent feature comparison after counsel review.
- Do NOT buy links, run link exchanges, partner-page cross-links, PBN or expired-domain schemes, or mass-distribute widgets with keyword anchors. Embeddable calculators are low value (brand-name nofollow anchor only, never counted in link KPIs). Wikipedia editing is not an SEO lever.
- Do NOT scrape behind logins or ignore exchange terms of use. Do NOT collect PAN, Aadhaar, bank details or phone numbers on our domain, and do not offer our own cashback or rewards for demat opening.
- Do NOT name data vendors or fallback mechanics in public copy, do not use em or en dashes in UI copy, and do not place crypto affiliate banners beside Indian broker content.
- Do NOT make large investments in Reddit or X until the live subreddit rules are read and mods are contacted; treat those links as brand and referral signals, not ranking links.
