# Path to 60,000-70,000 pages: India and global

**Date:** 2026-09-09. Current live count: 1,107 pages (verified against the live
sitemap the same day this was written).

## Read this before anything else in this document

There are two ways to get from 1,107 to 60,000 pages. One of them will get
this site penalized; the other is exactly what Moneycontrol, Groww,
CoinGecko and CoinMarketCap actually did.

**The wrong way**: combinatorial/faceted URL generation - every broker x
every month x every metric, every city x every segment x every type, thin
auto-assembled pages with no independent reason to exist. Google's spam
policies have a named category for this - "scaled content abuse" - and it is
enforced at the level of entire sites losing rankings, not individual pages.
This document does not propose any of that, and nothing in it should be
implemented in a way that does.

**The right way, confirmed by this project's own competitor research**:
every one of the five benchmarked sites reaches six-figure page counts by
covering a **complete real-world universe of entities that already exist**
(every listed stock, every coin, every mutual fund scheme) with **one
well-built template per entity type**, sourced from data that would be
published with or without the page existing. That is the only path proposed
here.

The number 60,000-70,000 is achievable this way. It requires expanding
*which real-world universes* this pans across, not multiplying the existing
one.

---

## Part 1: India (BrokerLens) - the real universes, with real numbers

| Universe | Realistic page count | Data status |
|---|---|---|
| SEBI-registered broking/DP entities | 1,774 total (1,030 live today) | **Already the current pipeline.** Finishing this is just completing the existing SEBI pagination sweep. |
| NSE-listed equities | **2,570**, confirmed live right now | **Already ingested, zero new pipeline.** `pipeline/sources/nse.py` downloads NSE's full `EQUITY_L.csv` today and uses it only to print a symbol count. Every one of those 2,570 symbols can become a real page (name, ISIN, listing date, sector, live price snapshot, corporate actions - all from data this pipeline already pulls) with no new ingestion at all. |
| BSE-listed equities not already on NSE | Roughly 2,000-3,000 (BSE lists several thousand companies, many SME/regional, with limited NSE overlap) | New: needs a BSE company-master ingestion (bhavcopy gives daily trading data per symbol; a master list needs a separate BSE endpoint, to be identified - moderate effort, same trust tier as everything else already pulled from BSE). |
| Mutual fund schemes | **8,000-12,000+** across all AMCs, growth/direct/regular variants | New data source: AMFI (the mutual fund industry body) publishes scheme-level NAV data free and daily, the same primary-source tier as SEBI/NSE/BSE. This is the single largest lever available on the India side - it's also confirmed as the backbone of Groww's own content operation. |
| IPO archive (mainboard + SME, historical + ongoing) | 2,000-3,000+ | New: SEBI DRHP filings + NSE/BSE listing announcements, primary-source (never the aggregator sites the licensing rules already forbid). |
| Corporate bonds / NCDs | 500-1,000 | New, smaller lift, same SEBI/exchange sourcing. |
| Index pages (Nifty 50, Sensex, sectoral indices) | 40-60 | New, small, high search value, built from constituent data the exchanges already publish. |
| Category hub pages (type/segment/city) | Already 20, room for maybe 50-100 total kept deliberately non-combinatorial | **Already shipped.** Do not expand this into a faceted-search-style explosion - see the warning above. |
| Glossary / methodology terms | 100-150 | Already partly written as prose on `/methodology`; splitting it is mechanical. |
| Broker profiles | 48 (near-fixed ceiling) | Already shipped. |

**Subtotal, India, English, real primary-source content: roughly 17,000-21,000
pages.** That is the honest ceiling of the India-only, single-language
universe - a real, large, legitimate number, and still short of 60,000 on
its own.

### The multiplier that closes the gap on the India side: regional languages

Once the highest-value subset of the above exists in English (the SEBI
registry, the top stock and mutual-fund pages by search volume, the
glossary), translating that subset into Hindi, Tamil, Telugu, Marathi and
Gujarati - already flagged in `SEO_KEYWORD_STRATEGY.md` and
`GROWTH_AND_MONETIZATION_IDEAS.md` as a near-uncontested opportunity -
can plausibly add another 15,000-30,000 pages, **provided it is real
localisation, not machine-spun duplicate text.** Google's quality systems
increasingly detect low-effort translation the same way they detect
low-effort English content; this only counts toward the target if it's done
with genuine per-language review, even lightweight.

---

## Part 2: Global (VaspLens) - this requires an explicit scope decision

`CRYPTO_VERTICAL.md` deliberately scoped VaspLens's first version narrow: the
EU MiCA/CASP register alone, roughly **331 entities today**. That was the
right call for proving the model - it mirrors exactly how BrokerLens itself
started with just the SEBI registry. But 331 pages, even added to every other
jurisdiction's registry (UK FCA, US state-by-state, Singapore MAS, Canada
FINTRAC), realistically tops out somewhere in the **1,500-3,000** range across
all regulators combined. That is nowhere near enough to move the 60-70k
target on its own, and it shouldn't be forced to.

**Reaching tens of thousands of pages on the crypto side means VaspLens
becoming a market-data product, not only a verification registry** - the same
shape as CoinGecko (confirmed: ~19,745 coin pages + ~1,496 exchange pages) or
CoinMarketCap (confirmed: ~9,000-10,000+ coin pages + 244 exchange pages).
That is a materially larger build than the CRYPTO_VERTICAL.md v0.1 plan: it
needs real-time and historical price/market-cap ingestion per coin, not just
a regulator lookup.

This is a genuine fork in the road, and it should be a deliberate choice, not
an assumption baked into a page-count target:

- **Option A - stay verification-first.** VaspLens remains the "is this
  exchange actually licensed" layer, tops out in the low thousands of pages,
  and stays the smaller, more defensible, harder-to-copy product described in
  `CRYPTO_VERTICAL.md`. The 60-70k target is then carried almost entirely by
  the India side plus regional languages.
- **Option B - expand into market data.** VaspLens adds a coin/token and
  exchange page layer (price, market cap, historical data) on top of the
  verification layer, which is what actually gets it to CoinGecko-adjacent
  page counts. This is a bigger, separate engineering project - a real-time
  data pipeline, not a registry crawler - and should be scoped and planned on
  its own, not folded silently into "add more pages."

Recommendation: **pursue Option A for VaspLens's own credibility, and treat
Option B as a distinct, later decision** once the verification layer has
proven itself, exactly the same sequencing discipline that made BrokerLens's
registry pages work before the broker profiles were tackled.

---

## Part 3: a phased plan with running totals

| Phase | What ships | Running total (India) | Running total (+global, Option A) |
|---|---|---|---|
| Now | Finish the SEBI registry sweep (1,774 total) | ~1,800 | ~1,800 |
| Phase 1 | NSE-listed equity pages (2,570, already-ingested data) | ~4,400 | ~4,400 |
| Phase 2 | BSE-incremental equities + index pages + IPO archive start | ~7,500 | ~7,500 |
| Phase 3 | AMFI mutual fund scheme pages (the big lever) | ~16,000-19,000 | ~16,500 |
| Phase 4 | VaspLens CASP/regulator pages across jurisdictions (Option A) | same | ~18,500-20,000 |
| Phase 5 | Regional-language translation of the highest-value subset | +15,000-30,000 | **~35,000-50,000** |
| Phase 6 | Corporate bonds/NCDs, remaining glossary, remaining category hubs | +2,000-3,000 | **~40,000-55,000** |

To close the remaining gap to 60-70k credibly, the two levers are: (a) a
deeper regional-language rollout (more languages, or the fuller page set
per language rather than just the top subset), or (b) revisiting the
VaspLens Option A/B decision once the India side has actually proven this
model at ~40-50k pages first. Both are legitimate; neither should be forced
ahead of the data actually existing.

## What this plan deliberately does not do

- It does not propose generating pages for entities that do not exist to pad
  the count (e.g. speculative broker/exchange combinations, synthetic
  city/segment crossings beyond what's already shipped).
- It does not propose machine-translating content without review to hit the
  regional-language numbers faster.
- It does not fold VaspLens into a market-data product by default just
  because that is the faster path to a bigger number - that is Option B
  above, and it should be chosen on its own merits.
- It does not touch the production-mode gating already in place: every new
  page type follows the same rule already enforced everywhere else on this
  site - published only once traced to a primary source, "not published yet"
  otherwise, never estimated.
