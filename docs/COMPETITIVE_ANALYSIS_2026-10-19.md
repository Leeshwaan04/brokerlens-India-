# BrokerLens competitive analysis, gap plan and content automation (19 Oct 2026)

Scope: Indian broker comparison, SEBI registry, IPO and market-data reference site (brokerlens.in, about 239K static pages, new domain). Primary goal: user traction and lead inflow (sponsored broker banners, broker onboarding clicks).

## How to read the numbers

- **Measured** means it comes from our own Search Console pull (`scratchpad/gsc_audit.json`, 90 day window to 17 Oct, daily rows start 3 Sep) or from pages fetched during the audit.
- **Not measured** means we have no tool for it in this setup. Competitor backlink counts and Core Web Vitals need a paid link index and a field-data run. They are marked "not measured" and never estimated.
- Search research ran from a US vantage point, so India rank order is inferred, not observed.
- "Traffic potential" below is stated as impressions already on file or as a demand signal. It is not a forecast of clicks.

## Where we stand (measured)

| Metric | Value |
|---|---|
| Clicks / impressions, 90d window | 463 / about 62K (site CTR about 0.75%) |
| India share of clicks | 456 of 463 |
| Mobile vs desktop | 317 clicks at position 12.2 vs 142 clicks at position 23.0 |
| Daily clicks | about 5 on 4 Oct, 47 to 69 on 15 to 17 Oct |
| Sitemap | 114,996 URLs submitted, Search Console "indexed" counter reads 0 (unreliable, use per-URL inspection) |
| URL inspection, 24 sample URLs | 11 indexed, 7 unknown to Google, 4 discovered not indexed, 1 crawled not indexed, 1 soft 404 (`/broker/zerodha/`) |

| Page family | Pages in top 5000 rows | Clicks | Impressions | CTR | Avg position |
|---|---|---|---|---|---|
| `/stock/*/share-price-target-*` (now 308 redirected) | 1,143 | 280 | 10,306 | 2.72% | 6.8 |
| `/sebi-registry/*` | 982 | 117 | 14,559 | 0.80% | 9.1 |
| `/ipo/*` | 1,079 | 27 | 25,464 | 0.11% | 17.6 |
| `/stock/*` (other) | 672 | 13 | 5,594 | 0.23% | 48.4 |
| `/compare/*` | 372 | 8 | 649 | 1.23% | 10.8 |
| `/broker/*` | 388 | 3 | 1,009 | 0.30% | 34.0 |
| `/fund/*` | 272 | 4 | 1,273 | 0.31% | 39.9 |
| Calculators (all) | 2 | 0 | 14 | 0% | 5 to 90 |

### Three findings that change the plan

1. **About 60% of all clicks (280 of 463) came from the share-price-target pages, and they are now redirected.** `vercel.json` sends `/stock/:symbol/share-price-target-:year` to the stock page with a permanent redirect, and production confirms it (308). Those clicks will decay, and the stock pages they land on rank around position 48. The pages were retired because year-by-year price targets are speculative, which is a YMYL risk. Whether to bring back an honest version is **your decision** (options in Phase 1).
2. **IPO pages have the impressions but not the clicks.** 25,464 impressions, 27 clicks, and 0 clicks across positions 1 to 7 (841 impressions). The demand is for price, date and listing facts on past issues. Our titles lead with "Latest Close, % since issue" instead. Registry pages at positions 4 to 7 earn about 1.09% CTR, so snippet fit matters more than rank.
3. **Indexation is the ceiling.** Hub pages (`/ipo/`, `/ipo/upcoming/`, `/news/`, `/trade-costs/`, `/index/nifty-50/`) are unknown to Google, and several stock and compare pages are "discovered, not indexed". More pages will not help until Google crawls the ones we have.

---

## SECTION 1: Competitor landscape

### Direct competitors (same queries, same intent)

| Competitor | Architecture and content strategy | Technical SEO (backlinks, Core Web Vitals) | Funnel and monetisation | Where it wins or loses against us |
|---|---|---|---|---|
| **Chittorgarh** | Deep URL families by topic and broker (`/ipo_allotment_status/`, `/broker/<slug>/<topic>/<id>/`, broker complaint pages). IPO pages have about 17 sections with an "Updated on" date. | Backlinks and Core Web Vitals: not measured. Brokerage pages observed with stale dates ("last updated 4 Oct 2024" under a 2026 title). | Referral links on almost every CTA, sidebar banners, an advertising block. | Wins on depth, history and authority. Loses on freshness and on thin disclosure. |
| **InvestorGain** | Broker compare tables and IPO pages. | Not measured. | Affiliate CTAs, promo copy, one-line "commissions do not affect rankings". | Tables contradict each other (one broker's demat AMC shown as two different amounts on the same site). Loses on internal consistency. |
| **Upstox / 5paisa / Groww (IPO pages and blogs)** | Broker-owned IPO detail pages with timeline, issue size, lot size, 3-year financials, 10 FAQs, registrar and lead manager contacts. | Not measured. | Content exists to feed account opening. | Win on completeness and brand. Cannot be neutral about their own fees. |
| **Zerodha (calculator, Varsity, Support)** | Official brokerage calculator across all segments, sample contract notes. | Not measured. | Owner of the head term "zerodha brokerage calculator". | Unbeatable on its own brand. Shows only its own fees, no cross-broker view. |
| **Finology, Tradebrains, stockcalc.in** | Calculator and screener tools. | Not measured. | Tool to subscription or lead. | stockcalc.in sample output showed "NaN" turnover. Data quality varies. |
| **esi.in (registry style pages)** | Registration snapshot, "what investors should verify", FAQs, "SEBI list dated" freshness note. | Not measured. | Informational. | Beats our registry pages on structure. We beat it on coverage (982 pages already ranking). |
| **Screener, Tickertape, Trendlyne, Moneycontrol, Value Research** | Stock and fund data hubs. | Not measured, general knowledge only: strong authority. | Subscriptions, ads, broker referrals. | Not winnable on stock or fund heads for a new domain. Included for completeness, not as targets. |

### Indirect and adjacent

| Adjacent player | Role | Implication for us |
|---|---|---|
| AMC and bank sites (Kotak, Federal Bank, Jio BlackRock) | Own "sip calculator" and "open demat account online" SERPs | Do not target the SIP head term. |
| Press (Outlook Business, Inc42, Business Today) | "zerodha vs groww" and IPO allotment explainers | Editorial, dated, no live data. A data page can sit beside them on long-tail pairs. |
| BankBazaar and CB Insights style aggregators | Comparison tables | Same as above. |
| Exchanges and SEBI | Primary sources for registry and complaints | We cite them, we do not compete with them. |
| Zerodha Support articles | STT explainers | Incumbent snippets disagree on STT (0.05% vs 0.1% per side), which is an opening for a dated, sourced worked example. |

**What wins in this niche, from what we observed:** head terms are owned by brokers and tool vendors. Long-tail identifier queries (DP ID, SEBI registration, INZ numbers) are cheap wins. Competitor data is often stale or inconsistent, so "sourced, dated, internally consistent" is our real differentiator.

---

## SECTION 2: Gap and opportunity analysis

Customer case studies and integration pages do not apply (no customers, no product). The equivalent assets for a data site are original data reports and downloadable datasets.

| # | Missing or weak asset | Gap or keyword cluster it fills | Why it moves traffic and leads |
|---|---|---|---|
| 1 | One **entity page per legal company** in the registry (all registrations in one table, broker registration primary) | RLP Securities has 3 URLs, Econo Broking 2, Aristro 2. Google ranks the DP page for "rlp securities". Impressions are split. | Concentrates 4,460 registry query impressions that are split today. Fixes cannibalisation. |
| 2 | Registry page rebuild: direct answer line, registration snapshot, how to verify, 3 FAQs with FAQPage schema, register-as-of date | Legitimacy queries such as "is X SEBI registered" and entity-name queries | Registry already converts at 0.8%. Parity with esi.in structure. |
| 3 | **Per-broker "calculator and charges" page** (delivery, intraday, F&O, currency, commodity, DP charge, worked example on Rs 1 lakh) for 8 to 10 smaller brokers | Queries like "prostocks / alice blue / samco / fyers brokerage calculator" now land on random stock cost pages at positions 50 to 100 | Gives Google one page to rank per broker. Realistic top-20 for small brokers. Leads: sits next to the sponsored banner. |
| 4 | **Per-broker identifiers page** (DP ID, SEBI registration, exchange member codes) | "12083400 dp id" already ranks position 2 to 6 for us | Cheapest wins in the whole data set. |
| 5 | **IPO facts card**: timetable, price band, lot size (only when sourced), listing-day open/high/low/close, registrar | "price", "date", "listing" queries: about 7,800 impressions, 2 clicks | Fixes the biggest impression to click gap on the site. |
| 6 | **IPO title and meta rewrite** (date, price band, lot size, listing date, not "latest close") | Same cluster, zero template work | Fastest lever. |
| 7 | **Time-boxed allotment page** for live IPOs only (registrar link, dates, steps) | Allotment demand is in the live window. Our old-issue sub-pages got 15 impressions in total. | Avoids thin pages and targets the demand spike. |
| 8 | **STT, stamp duty and exchange charges calculator** with dated statutory rates and a worked example | Competing snippets disagree on STT. India SERP unverified. | Open lane, fits our cost data. |
| 9 | **Curated broker-vs-broker pages** (about 30 pairs with real demand) | Second-tier pairs like "dhan vs fyers". All-pairs stay noindex. | Pair-level long tail is thin. Positions 3 to 11 already for niche pairs. |
| 10 | **Share price target replacement** (decision needed) | The 280-click cluster | See Phase 1. |
| 11 | **Branch page verification** | Branch pages rank top 10 but app-only brokers have no verified branch | Protects the one broker-family page type already ranking. |
| 12 | **Original data reports and CSV downloads** (SEBI register snapshot, IPO listing outcomes) | Link magnets, since backlinks are our real long-term gap | Authority is the 6 to 12 month bottleneck. |
| 13 | **Pillar and cluster guides** ("how to check if a broker is SEBI registered", "how to read a brokerage statement", "how IPO allotment works") | Informational layer that links down into data pages | Builds topical authority and internal links. |
| 14 | **Indexation fixes**: hub pages unknown to Google, `/broker/zerodha/` soft 404 | Technical | Nothing else compounds without this. |

---

## SECTION 3: Prioritised roadmap

Effort: S under 2 days, M under 1 week, L over 1 week. "Potential" is impressions on file or a demand signal, not a forecast.

### Phase 1: 0 to 30 days

| Page or change | Keyword cluster | Intent | Potential (measured or signal) | Effort | Why now |
|---|---|---|---|---|---|
| Fix IPO template bugs (contradictory "not listed yet" FAQ, the word "Disclosed" in a number slot, band mismatch) | IPO pages | Trust | Whole IPO cluster, 25,464 impressions | S | Wrong facts on YMYL pages. Ship before any promotion. |
| IPO title and meta A/B split | "{name} ipo date, price, lot size, listing" | Informational | 8 to 10 position band: 3,463 impressions at 0.09% CTR | S | Cheapest lever on the biggest cluster. |
| Registry title and meta (proper-case name, registration number) | "is {name} sebi registered" | Informational | Positions 8 to 10: 1,952 impressions at 0.10% CTR | S | Same logic, already converting at positions 4 to 7. |
| Registry dedupe: one entity page per company, fix "Commodity broker" label | Registry entity names | Informational | Top names have 300 to 560 impressions each | M | Data-correctness fix on a YMYL family. |
| Per-broker calculator, charges and identifiers pages for 8 to 10 smaller brokers | "{broker} brokerage calculator / charges / dp id" | Informational, tool | 68 impressions today, positions 42 to 100, plus DP ID queries ranking 2 to 6 | M | Gives Google one page per broker. Link from the 2,462 stock cost pages. |
| Indexation hygiene: investigate `/broker/zerodha/` soft 404, push hub pages, internal links to `/ipo/` and `/news/` | Site-wide | Technical | 7 of 24 sampled URLs unknown to Google | S | Everything depends on being crawled. |
| Branch pages: keep only where an address is verifiable, noindex or rewrite the rest | "{broker} office in {city}" | Local | A handful of pages at positions 4 to 10 | S | Protects against doorway risk. |
| **Decision: share price target** | "{stock} share price target {year}" | Informational | 10,306 impressions, 280 clicks | S to M | Options below. |

**Share price target options (you decide):**
- **A. Keep retired.** Lowest risk, accept the loss of about 60% of current clicks over time.
- **B. Replace with an honest section on each stock page.** An H2 matching the query, "What is a share price target", exchange-published 52 week range, and a user-input what-if growth calculator with the assumption stated. No year-by-year forecast numbers. This recaptures the query without publishing speculation. Recommended.
- **C. Restore the old pages.** Fastest click recovery, highest YMYL and quality risk. Not recommended.

### Phase 2: 31 to 90 days

| Page | Keyword cluster | Intent | Potential | Effort | Rationale |
|---|---|---|---|---|---|
| IPO facts card (timetable, listing-day OHLC, registrar) | "polycab listing price", "bse ipo date" | Informational | Listing and date queries: about 4,800 impressions, 0 clicks | L | Needs exchange history for the listing date, then the title test results decide the pattern. |
| Time-boxed live-IPO allotment pages | "{ipo} allotment status" | Informational, transactional | Demand spikes inside allotment week | M | Build once the IPO calendar feed is reliable. |
| STT and charges calculator | "stt calculator", "stamp duty on trade" | Tool | Unverified from US vantage, check from an India IP first | M | Open lane with sourced, dated rates. |
| Curated broker pair pages (about 30 pairs) | "{broker} vs {broker}" | Comparison | Niche pairs already rank 3 to 11 at 1 to 5 impressions each | M | Wait for per-broker pages so pairs can reuse their data. |
| Complaint tables per broker (exchange-published data only) | "{broker} complaints" | Informational | No measured demand yet | M | Chittorgarh uses this. Omit rows where we hold no data. |
| Prune SIP permutations to amounts people search | "5000 per month for 10 years" | Tool | 940 pages, 145 impressions, 0 clicks | S | Crawl budget. |
| GMP section on IPO pages (state GMP is unofficial, show verified listing outcome) | "ipo gmp" | Informational | About 770 impressions, 0 clicks | S | Converts a refusal into a data answer. |

### Phase 3: 91 to 180 days

| Page | Keyword cluster | Intent | Potential | Effort | Rationale |
|---|---|---|---|---|---|
| Original reports with CSV downloads (register snapshot, IPO listing outcomes) | Brand and press | Link earning | Authority, not direct traffic | M | Backlinks are the long-term bottleneck. |
| Pillar guides and cluster hubs (SEBI registration, IPO process, brokerage statements) | Informational heads | Informational | Unmeasured | M | Built after data pages so the guides link to ranking assets. |
| Fund and stock quality layer (5 year history, NAV history) | "{fund} nav", "{stock} share price" | Informational | Funds 1,273 and stocks 5,594 impressions at poor positions | L | See `docs/INSTRUMENT_PAGES_PLAN.md`. |
| Head terms ("zerodha vs groww", "best demat account") | Heads | Comparison | Owned by brokers and press | L | Only attempt with backlink support. |
| US and GCC expansion | New markets | Mixed | Not researched (earlier research failed) | L | Only after India indexation is proven. |

---

## SECTION 4: Autonomous content operations pipeline

Design principle: this site is data-driven. LLMs write framing text and titles. **Every number comes from a data record**, and a gate rejects any number in the output that is not in the source record. That is how "never invent a number" survives automation.

### Agent architecture

| # | Agent | Role | Hands off to |
|---|---|---|---|
| 1 | Monitor | Reads Search Console and the competitor sitemap diffs, scores decay and gaps, writes task tickets | Planner |
| 2 | Planner | Ranks tickets by impressions on file and effort, assigns page type and template | Research |
| 3 | Research | Collects the source record per page (SEBI register row, exchange IPO row, broker fee schedule) with source URL and as-of date | Drafter |
| 4 | Drafter | Fills template slots and writes titles, meta and FAQ text from the record only | Editor |
| 5 | Editor | Checks tone, no advice language, no vendor names, no em or en dashes, reading level | SEO/QA |
| 6 | SEO and QA | Schema validity, title length and uniqueness, internal links, numeric grounding check, noindex rules | Publisher |
| 7 | Publisher | Opens a pull request, runs the offline QA and VAPT gate, triggers the deploy | Monitor |

Seven roles, but only 3 to 4 run in parallel per page batch (research, drafting, editing). Handoffs are JSON files in the repo (record, draft, gate report), not chat messages.

### Tools and integrations (using what is already in place, no new accounts)

| Layer | Choice | Reason |
|---|---|---|
| Orchestration | GitHub Actions scheduled workflow (the repo is already on GitHub) | No new account. n8n or Zapier would need one. |
| Build and publish | Existing Python pipeline and Vercel deploy, wave-based | Already built and gated. |
| Search data | Search Console API via the existing read-only service account | Already working. |
| Models | Largest model for planning and final review of new templates, mid-size model for drafting and editing, smallest model for classification checks (Fable 5.1, Sonnet 5.5, Haiku 5.5) | Match cost to difficulty. |
| Competitor tracking | Gentle fetch of public sitemaps, robots-respecting, once a week | No paid tool. Backlink data stays "not measured" until you choose a tool. |
| Notifications | GitHub issues and pull request comments | No new channel needed. |
| Click analytics | `api/ad-event.js` logs today. Durable storage needs a Vercel Blob store or Web Analytics. | Lead attribution depends on this. |

### Triggers and data sources

| Trigger | Data feed | Action |
|---|---|---|
| Weekly schedule | Search Console page and query tables | Refresh title tests, flag decay |
| Page drops out of top 10 or impressions fall week over week | Search Console | Ticket: refresh content and data |
| New IPO on the exchange calendar | IPO feed | Create IPO facts card, switch on allotment page at close date |
| SEBI register update | Register fetch | Rebuild affected entity pages |
| Broker fee schedule change | Fee schedule source | Rebuild cost and calculator pages |
| Competitor publishes a new page type | Sitemap diff | Ticket for review, never auto-copy |

### Quality gates (all must pass)

| Gate | Check |
|---|---|
| Numeric grounding | Every number in the page text exists in the source record |
| Source and date | Source name and as-of date present on the page |
| Originality | No copied competitor text (similarity check against fetched competitor pages) |
| Schema | JSON-LD parses, FAQ text equals visible text |
| Titles | Unique, within length, matches the test pattern |
| Copy rules | No advice wording, no vendor names, no dashes, banner placement rules respected |
| Regression | Existing offline QA (603 checks) and VAPT (21 checks) pass |
| Brand voice | Style check against a short reference set |

### Human approval

| Step | Human required? | Why |
|---|---|---|
| Title and meta within an approved pattern, data refreshes, sitemap changes, internal links | No | Low risk, reversible, gated |
| New template family (for example the entity page rebuild) | Yes, once per family | First instance sets the standard |
| Anything about enforcement orders, name changes, complaints for a named entity | Yes, every time (and legal review) | Entity-specific YMYL |
| Disclosure and sponsored-banner copy | Yes | Compliance risk (the referral-fee sentence was removed, so this needs a counsel view) |
| Retiring or redirecting pages | Yes | The share-price-target case shows the click cost |
| Spend on paid tools or new accounts | Yes | Standing rule |

### Monitoring and feedback loop

Dashboard fields per page: impressions, clicks, CTR, average position, indexed status (URL inspection sample), banner impressions and clicks (once storage exists), data as-of date, days since refresh.

| Alert | Proposed threshold (starting default, tune after 4 weeks) |
|---|---|
| CTR drop | More than 30% below the page family median for 14 days with stable position |
| Position loss | Out of the top 10 for 7 days |
| Decay | No refresh for 90 days on pages with live data |
| Index loss | Sampled URL moves from indexed to not indexed |
| Zero return | Page with 0 impressions after 60 days is flagged for noindex or merge |

Flagged pages go to a weekly review issue: revise, merge, or retire (retire needs the human step above).

### Scaling

| Concurrent page tasks | Approach |
|---|---|
| 10 | Single batch, sequential gates, one pull request |
| 50 | Parallel research and drafting in groups of about 10, one pull request per page family |
| 200 | Queue with a worker cap sized to the account's model rate limits, per-run token budget, retry with backoff (3 tries) then park the ticket |

The real bottleneck is not model throughput. Pages are template plus data, so the constraint is the 10 to 25 minute full build and the deploy. Ship in waves, as the sitemap tiers already do, and publish only pages that pass every gate. Rate limit values come from the account, not from this document.

---

## What I need from you

1. **Share price target:** keep retired (A), honest replacement (B, recommended), or restore (C).
2. **Search Console "Request indexing"** on about 10 key URLs (`/ipo/`, `/ipo/upcoming/`, `/news/`, `/trade-costs/`, `/broker/groww/`, `/etf/niftybees/`, `/index/nifty-50/`). Only you can do this.
3. **Durable click storage** (Vercel Blob or Web Analytics) so banner leads can be measured.
4. **Competitor backlink and speed data** needs a paid tool or a field-data run. Say if you want it, and which.
5. **Disclosure line:** a counsel view on running sponsored banners with only the "Sponsored" tag.
