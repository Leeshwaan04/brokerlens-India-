# Competitive benchmark and scale strategy

**Date:** 2026-09-09. Grounds every recommendation in either (a) live research on
named competitors, cited, or (b) the actual current state of this codebase,
verified by reading it — not generic SEO-playbook advice.

**How this relates to the other four strategy docs already in `docs/`:**
this one does not repeat them. `SEO_KEYWORD_STRATEGY.md` owns the keyword-to-page
mapping. `GROWTH_AND_MONETIZATION_IDEAS.md` owns the 100 feature/monetization
ideas. `ROADMAP.md` owns feature sequencing. `CRYPTO_VERTICAL.md` owns the
VaspLens plan. This document owns the pieces those four don't cover: the
competitor benchmark itself, information architecture, technical SEO and
schema, Core Web Vitals, analytics/measurement, backlink strategy, E-E-A-T,
and the synthesis of where this can structurally beat the competitors named
below rather than resemble them.

---

## 1. Competitor benchmark, with sources

### Chittorgarh.com / InvestorGain.com (India, IPO + broker referral)
Page types confirmed live: a dedicated page per IPO (date, price band, live
subscription, GMP, allotment, listing performance, "analysis and review"), a
Mainboard IPO Dashboard, a standalone GMP performance tracker report, broker
review and comparison pages, a brokerage calculator, and long-form
"book-chapter" explainer pages (e.g. its GMP/Kostak/Sauda glossary chapter).
[chittorgarh.com](https://www.chittorgarh.com/), [IPO GMP tracker](https://webreactjs.chittorgarh.com/report/ipo-gmp-performance-tracker/377/all/), [GMP glossary chapter](https://www.chittorgarh.com/book-chapter/ipo-grey-market-gmp/28/)

**The structural weakness this site cannot fix**: it's referral-funded (confirmed
in the earlier monetization research in this project — tracked broker links to
IIFL, Paytm Money, ICICI Direct, Kotak, and others). Every page that recommends
a broker sits next to a link that pays Chittorgarh for the click. This is not
fixable without abandoning the business model, which is the exact gap
BrokerLens is built to exploit.

### CoinMarketCap (global crypto, data aggregator)
Confirmed page/feature inventory: a page per coin (live price, historical
OHLCV back to 2010, market pairs, supply metrics), a page per exchange
(rankings, volume, market pairs, proof-of-reserves where disclosed), watchlists,
ranked screeners, a Fear & Greed index, global market metrics, and a large
educational "Academy" content library, all backed by a tiered, documented
public API. [CoinMarketCap API docs](https://coinmarketcap.com/api/documentation/), [Academy](https://coinmarketcap.com/academy/)

**The structural weakness**: it is a price/data aggregator, not a regulatory
verifier. It ranks and lists assets and exchanges without checking whether the
exchange is actually licensed anywhere — the "is this legitimate" question
(which is precisely the question VaspLens exists to answer) is outside its
model entirely.

### CoinGecko (global crypto, data aggregator with a trust layer)
The one competitor with something structurally close to what this project
does: a **Trust Score**, scoring each exchange across seven weighted factors
(liquidity 4/10, cybersecurity 2/10, scale of operations 1/10, past incidents
1/10, proof of reserves 1/10, team presence 0.5/10, API coverage 0.5/10).
[CoinGecko Trust Score methodology, via Coin Bureau review](https://coinbureau.com/review/coingecko-review)
Also: category/sector pages (DeFi, Layer 2, meme coins) with aggregate stats,
an NFT tracker CoinMarketCap doesn't match, and a Learn/glossary layer.

**The structural weakness**: the Trust Score is a *composite opinion metric*
built from a mix of self-reported and estimated inputs, not a primary-source
regulatory registry lookup. It's the right idea, built on the wrong foundation
- exactly the gap VaspLens's CASP-register-first approach is designed to close.

### Moneycontrol (India, general financial portal)
The single most important data point found in this research: **Moneycontrol's
"stockpricequote" page template alone drives roughly 32.6M of its 62M+ monthly
visits** - one page type, replicated across every listed company, dominating
the traffic of an entire large financial portal. The stated reason: the pages
carry general company data that "many reputed websites link to," i.e. they
became the citable reference for a fact (a stock's current price/data) that
needed a canonical home. [Moneycontrol SEO case study](https://buildd.co/marketing/moneycontrol-seo-strategy)

**Why this matters directly for BrokerLens**: this is the exact mechanism
already put in motion with the 1,029 SEBI-registry entity pages shipped this
week. Moneycontrol is the proof, at a much larger scale, that one well-designed
page template replicated across a full universe of entities - not clever
content marketing - is what actually produces market-leading organic traffic.
The registry pages should be treated as the single highest-leverage asset on
the site, not a side feature.

### Groww (India, broker + content)
Confirmed: ~50M users, and its content operation (AMC/mutual fund pages,
calculators, research tools, a glossary) is backed by roughly **15,000
referring domains**, with links from top-tier outlets including Moneycontrol,
Economic Times and Business Standard. [Groww case study](https://www.nicodigital.com/case-studies/groww-digital-marketing-case-study/)

This is the backlink-profile benchmark to measure BrokerLens against as it
scales (see section 10), and confirmation that the calculator + glossary
content cluster (already partly planned) is a proven pattern, not a guess.

---

## 2. What actually drove each of these to scale, extracted

Stripping the five benchmarks down to mechanisms, not features:

1. **One page template, replicated across a complete universe of entities**
   (Moneycontrol's stock pages, CoinMarketCap's coin pages, Chittorgarh's IPO
   pages, and now BrokerLens's registry pages). This is the single strongest,
   most consistently observed growth mechanism across every competitor
   researched, and it's programmatic SEO's real justification, not a
   euphemism for spam - the pages exist because there's genuine per-entity
   information demand.
2. **A composite trust/quality score that becomes the site's namesake metric**
   (CoinGecko's Trust Score, and this project's own reliability score). The
   lesson from CoinGecko specifically: publish the *formula*, not just the
   number - this project already does that on `/methodology`, which CoinGecko
   does not do as transparently, and that is a real, citable advantage.
3. **Free tools that generate backlinks as a side effect of being useful**
   (Groww's calculators, Chittorgarh's GMP tracker). Nobody links to a
   marketing page; people link to a tool they used and want to reference again.
4. **A large low-competition long-tail** (CoinMarketCap indexes every coin
   down to the most obscure; Moneycontrol indexes every listed company, not
   just the large-caps). BrokerLens's 1,774-entity SEBI registry is exactly
   this kind of long tail, and today only ~48 get anything beyond registry
   facts - the other ~1,700 are underexploited relative to what the pattern
   above predicts they're worth.
5. **A documented, tiered API** as the monetization backbone underneath a free
   consumer layer (CoinMarketCap, CoinGecko). Neither monetizes the consumer
   product directly; both monetize the data pipe. This validates the B2B-API
   line from `GROWTH_AND_MONETIZATION_IDEAS.md` as the correct model, not an
   invented compromise.

None of the five competitors combine primary-source regulatory verification
with a referral-free, non-advice-giving posture. That combination is the
actual competitive gap - not a missing feature, a missing category.

---

## 3. Information architecture: a scalable site structure

Current state (verified): `/`, `/brokers`, `/broker/:id` (48), `/compare`,
`/leaderboards`, `/calculator`, `/registry` (search) + `/sebi-registry/:slug/`
(1,029 static pages, shipped this week), `/algo`, `/methodology`, `/sources`.
1,086 URLs in the sitemap today.

Proposed structure, layering hub pages onto the existing entity pages rather
than replacing anything:

```
/                          Home (hub)
/brokers                   Directory hub (48 tracked in depth)
/brokers/type/discount     NEW: category hub (discount / full-service / bank-backed)
/brokers/segment/commodity NEW: category hub (by trading segment)
/brokers/city/mumbai       NEW: city hub, generated from hq field already on file
/broker/:id                Existing profile (48) - NEEDS JSON-LD, see section 7
/broker/:id/vs/:id2        NEW: auto-generated from real /compare usage
/registry                  Existing interactive search
/sebi-registry/:slug/      Existing static entity pages (1,029) - the core asset
/sebi-registry/defaulters/ NEW: the 445-record defaulter archive as its own hub
/verify                    NEW: the "verify a broker" tool (growth idea B7)
/algo                      Existing algo-platform directory
/glossary/:term            NEW: split /methodology into individually indexable terms
/guides/:slug              NEW: long-form explainers (Chittorgarh's book-chapter pattern)
/calculator                Existing
/leaderboards              Existing
/methodology, /sources     Existing
/about, /privacy, /terms   MISSING - see section 11 (E-E-A-T)
```

The city/segment/type hub pages cost nothing to build - the data
(`hq`, `type`, `segments`) is already on every profile. They are also exactly
the kind of mid-tail page (more specific than `/brokers`, broader than one
entity) that both Moneycontrol and CoinGecko use to capture searches that
don't name a specific entity.

---

## 4. Programmatic SEO and data-driven page opportunities (beyond the existing 100)

The `GROWTH_AND_MONETIZATION_IDEAS.md` document already lists twelve
programmatic ideas (A1-A12). Adding, specifically inspired by what the
competitor research surfaced that wasn't already captured:

- **A "stockpricequote"-equivalent cross-link**: several tracked brokers have
  a *listed parent company* (Angel One, Motilal Oswal, IIFL, Nuvama). A page
  showing "this broker's listed parent's real-time share price" (pulled from
  the exact NSE/BSE feeds already ingested) is the direct BrokerLens analog of
  Moneycontrol's highest-traffic template, applied to the handful of entities
  where it's factually available.
- **Category/sector pages as first-class indexable URLs**, not just client-side
  filter chips (CoinGecko's category pages are indexable; BrokerLens's `type`
  and `segment` filters currently are not, they're query-string state on
  `/brokers`).
- **A GMP-tracker-equivalent for VaspLens**: a "newly authorised CASP entities
  this month" page, updated on the same cadence as the registry ingest,
  mirroring the update-frequency habit-loop that makes Chittorgarh's GMP
  tracker a daily-return destination.
- **Long-form glossary/book-chapter pages** (Chittorgarh's pattern): split
  `/methodology`'s content into individually indexable terms
  (`/glossary/complaint-resolution-rate`, `/glossary/reliability-score`), each
  short, each answering one query precisely.

---

## 5. Keyword universe and keyword-to-page mapping

Owned by `docs/SEO_KEYWORD_STRATEGY.md`. One addition worth logging here since
it came directly out of the competitor research: Moneycontrol and
CoinMarketCap both rank heavily on bare entity-name queries with no qualifier
("Zerodha", "Bitcoin") because their entity pages are the single best answer
to the bare name. BrokerLens's broker profile pages should be evaluated
against this standard - can `/broker/zerodha` credibly compete for the query
"Zerodha" itself, not just "Zerodha SEBI registration"? Today, given zero
server-rendered content on that route (section 8), the honest answer is: not
yet, and that gap is worth more organic traffic than most of the long-tail
work combined.

---

## 6. Topical authority and content cluster strategy

Propose three explicit pillar clusters, each anchored by one hub page that
doesn't yet exist, linking down to pages that mostly already do:

**Pillar: SEBI registration and verification.**
Hub: `/verify` (new). Links to: every `/sebi-registry/:slug/` page, `/registry`
search, the defaulter archive, `/glossary/sebi-registration`. This cluster
directly targets the single richest keyword intent identified in the SEO
strategy doc (verification-intent queries) and is the cluster with the least
competition, because it requires data no referral-funded competitor has
structured.

**Pillar: cost and comparison.**
Hub: `/calculator`. Links to: `/compare`, `/broker/:id/vs/:id2` pages (new),
`/leaderboards`, `/glossary/brokerage-calculation`. Currently the weakest
cluster because charges are still sample-gated in production (per
`GAP_ANALYSIS.md`) - finishing that ingestion is what actually unlocks this
pillar's search volume, not additional content around it.

**Pillar: algo trading compliance.**
Hub: `/algo`. Links to: the market-timings mega menu content, a new
`/glossary/sebi-algo-framework` explainer, and (per `CRYPTO_VERTICAL.md`) a
future cross-link to VaspLens where a platform touches both markets. This is
the least-contested pillar of the three - no competitor researched here
addresses SEBI's 2025 retail algo framework in structured form at all.

---

## 7. On-page SEO, schema, canonicals, sitemaps, internal linking, crawlability

**Confirmed by reading the code, not assumed:**

- **CRITICAL, still open**: `grep` across `site/assets/js/pages.js` for
  `ld+json` or `FinancialService` returns nothing. The 48 broker profile pages
  - the actual money pages of the site - carry zero structured data, while
  the newer `/sebi-registry/:slug/` pages (shipped this week) do. This is the
  single highest-priority technical SEO fix available: add `Organization` (or
  `FinancialService`, schema.org's more specific type for a regulated
  financial firm) JSON-LD to every broker profile, with `identifier` set to
  the SEBI registration number, mirroring exactly what the registry pages
  already do.
- Canonical tags: fixed earlier (per-route, alias-aware) - confirmed still
  correct.
- Sitemap: one flat file, 1,086 URLs today, well under the 50,000-URL
  protocol limit. Recommend segmenting into `sitemap-core.xml`,
  `sitemap-brokers.xml`, `sitemap-registry.xml` under a `sitemap_index.xml`
  regardless - not because of the limit, but because a segmented sitemap lets
  Search Console report indexing health per section, which matters once the
  registry section is 1,700+ URLs and the future glossary/hub pages add more.
  This also scales cleanly into the regional-language expansion (5x the URLs)
  already planned in the growth doc.
- `robots.txt`: correct, allows everything except `/api/` and `/data/`,
  declares the sitemap. No change needed.
- Internal linking: the registry pages currently link only to `/registry`,
  `/brokers` and `/`. Once the city/segment/type hub pages in section 3 exist,
  every registry entity page should also link to its relevant hub(s) - this
  is what actually distributes link equity across the long tail instead of
  concentrating it all on three top-level pages.
- Breadcrumb (`BreadcrumbList`) schema is entirely absent and is a fast,
  mechanical addition once the hub pages exist to breadcrumb against.

---

## 8. Core Web Vitals, technical SEO, performance, mobile

**Confirmed by reading the code:** zero `<img>` tags anywhere in the shell or
page templates, no custom web fonts (system font stack throughout), no
render-blocking third-party scripts. This is a genuinely strong CWV starting
position - most competitors researched here (all five) are far heavier,
image- and ad-laden pages by comparison. Don't compromise this by adding
tracking scripts carelessly (section 9) or images without real justification.

**The real gap**: every route except the new `/sebi-registry/:slug/` pages is
100% client-rendered. This has a direct, measurable Core Web Vitals cost, not
just an SEO one - LCP on `/broker/:id` is gated on JS execution and a
follow-on JSON fetch, whereas a server-rendered page's LCP is gated on the
HTML response alone. The registry-page pattern (plain static HTML, zero
script dependency, shipped this week) is the template to extend to the 48
broker profiles next - both for the SEO reason in section 5 and for the CWV
reason here. This is the highest-leverage single technical investment
available on the whole site.

Mobile: the mobile-navigation regression (375px forcing a 679px viewport) was
found and fixed earlier in this project. No new mobile-specific issues found
in this pass.

---

## 9. GA4, GSC, GTM, event tracking, and conversion measurement

**This is a real, current gap**: there is no analytics of any kind on the site
today - confirmed by grepping the entire codebase for `gtag`, `googletagmanager`,
`google-analytics`, and finding nothing. GSC verification exists (done
earlier), but nothing measures on-site behavior.

**The tension to resolve explicitly, not skip past**: the CSP is
`script-src 'self'; connect-src 'self'` with a comment stating the whole
design is "no third-party requests at all." That principle has been actively
defended multiple times in this project (it's why the site has no ad
network, no tracking pixels, no lead-capture telemetry). Standard GA4 + GTM
requires loading `googletagmanager.com` and sending beacons to
`google-analytics.com` - a direct contradiction of that stated design, not a
minor exception.

**Recommendation, in order of preference:**

1. **Cloudflare Web Analytics or a self-hosted first-party analytics
   instance (Plausible/Umami), proxied under `brokerlens.in`'s own origin.**
   No cookies, no cross-site tracking, no CSP violation if proxied same-origin,
   and it answers the actual questions that matter for a DIY-conversion site:
   which pages get traffic, which tools get used, where people drop off before
   completing a calculator or comparison. This is consistent with everything
   already decided about privacy on this project.
2. **If GA4 specifically is required** (e.g. for compatibility with a future
   ads/marketing team's existing tooling), load it via GTM with the CSP
   explicitly widened to allow exactly `googletagmanager.com` and
   `*.google-analytics.com`, and document that widening as a deliberate,
   reviewed exception - not silently. This should be a decision made with full
   knowledge of the tradeoff, not a default.

**Event taxonomy**, designed for a site with no login and no lead capture -
every event should describe self-directed usage, never anything that could be
joined back to an individual:
`search_used`, `filter_applied` (type/segment/city), `compare_added`,
`calculator_completed`, `registry_page_viewed`, `outbound_broker_link_clicked`,
`tool_shared` (permalink copied), `glossary_term_viewed`, and, once the B2B
API ships, `api_signup_started` / `api_key_generated`. These map directly onto
the DIY-journey conversion funnels in `GROWTH_AND_MONETIZATION_IDEAS.md`
without requiring any personal data.

---

## 10. Backlink and domain authority growth

Grounded in the two real numbers found in this research: Groww's ~15,000
referring domains, and Moneycontrol's citation-driven traffic from being the
canonical source for a fact other sites needed to link to. Both point to the
same tactic, already listed in `GROWTH_AND_MONETIZATION_IDEAS.md` section L,
strengthened here with three concrete, high-authority-specific targets that
came out of this research pass:

- **Wikipedia citations**: every SEBI-registered entity is exactly the kind of
  primary-source citation Wikipedia's financial-company articles need and
  currently often lack. A `/sebi-registry/:slug/` page is a better citation
  than most of what's currently used on Indian company Wikipedia pages. This
  is a concrete, actionable outreach target, not a vague "get backlinks" idea.
- **Open-data and developer directories**: submission to `data.gov.in`-adjacent
  and "awesome-india-apis" / "awesome-fintech" style GitHub lists once the B2B
  API ships - the exact audience most likely to link to and use it.
  developer-audience backlinks (dev.to, Hacker News) already listed in the
  growth doc are the same play; add these two more specific, high-authority
  targets to that list.
- **Journalist-facing dataset packages** (already idea #91 in the growth doc)
  - the enforcement/defaulter archive is the strongest of these, and should be
  the first one actually pitched once it exists, since it's the dataset with
  no existing free equivalent.

---

## 11. E-E-A-T, trust signals, and credibility (this is YMYL content)

Financial information sits squarely inside Google's "Your Money or Your Life"
category, where E-E-A-T (Experience, Expertise, Authoritativeness,
Trustworthiness) is weighted more heavily than for most other content types.
Confirmed gaps by checking the actual site:

- **No `/about` page and no named authorship anywhere.** Zero occurrences of
  "author," "reviewed by," or similar on `/methodology` or anywhere else. For
  YMYL content, Google's own quality-rater guidelines explicitly look for who
  is responsible for the content. A short, honest `/about` page (what
  BrokerLens is, how the pipeline works, who runs it) is a real ranking-
  relevant gap, not a formality.
- **No privacy policy, no terms page** - already flagged as a compliance gap
  in `GAP_ANALYSIS.md`; it is also an E-E-A-T gap independently, since its
  absence is itself a trust signal Google's raters are trained to notice.
- **What the site already does right for E-E-A-T**, worth preserving
  deliberately as it scales: the provenance dot on every figure, the
  published methodology with real formulas (not just "we score reliability"),
  the "not investment advice" disclaimer on every page, and now the
  regulator-sourced JSON-LD on the registry pages. These are genuinine
  trust-signal advantages over all five competitors researched, none of which
  publish their scoring methodology as transparently.
- **Missing**: a visible correction/changelog history (proposed as growth
  idea #70) is exactly the kind of radical-transparency artifact that
  compounds E-E-A-T over time and that no competitor here does at all.

---

## 12. Competitor gap analysis: where this can structurally outperform, not just compete

The point of this section is the actual strategic answer, not a feature list.

| Dimension | Chittorgarh | CoinMarketCap | CoinGecko | This project |
|---|---|---|---|---|
| Revenue model touching rankings | Referral-funded | Neutral (API) | Neutral (API) | Neutral (API), by design |
| Primary-source regulatory verification | No | No | Partial (Trust Score, not a registry) | Yes - direct SEBI/CASP registry data |
| Published, checkable methodology | No | No | Partial | Yes, on every figure |
| Long-tail entity coverage vs. total universe | Partial (large caps + active IPOs) | Near-complete for tokens | Near-complete for tokens | 1,774 of 1,774 SEBI entities reachable, ~1,030 already live |
| Server-rendered/crawlable entity pages | Yes | Yes | Yes | Only the registry pages so far - the broker profiles are not (section 8) |
| Structured data completeness | Unknown/partial | Partial | Partial | Registry pages: yes. Broker profiles: no (critical gap) |

The gap that matters is not any single feature - it's that **no competitor
researched here can adopt the "referral-free, primary-source-verified, and
methodology-published" combination without abandoning the revenue model that
built them.** That combination is durable specifically because it is
economically costly for them to copy. The execution gap that currently limits
it is narrower and mechanical: extend the static, server-rendered,
structured-data pattern already proven on the 1,029 registry pages to the 48
broker profiles, and the site's most valuable pages stop being the ones most
invisible to the crawlers and answer engines that increasingly decide what
gets found at all.
