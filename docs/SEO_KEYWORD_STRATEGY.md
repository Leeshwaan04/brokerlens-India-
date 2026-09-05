# SEO keyword strategy: India broking + global crypto verification

A literal list of "top keywords" goes stale in a month and misses the actual
lever, which is search *intent* mapped to a *page BrokerLens/VaspLens can
uniquely answer with regulator-sourced facts*. Structured that way instead.

Every cluster below follows the same rule already built into the product:
factual, sourced, no verdicts. A keyword strategy that leads with "best X"
content pulls the whole site toward advice-giving, which is the one line
neither product should cross.

---

## India: BrokerLens (brokerlens.in)

### 1. Verification intent (highest trust value, near-zero competition)
This is the cluster nobody else owns, because it requires the SEBI registry
data BrokerLens already has for 1,774+ entities:
- "is [broker] sebi registered"
- "[broker] sebi registration number"
- "[legal entity name] sebi registration" — one query per registry entity;
  48 brokers get real traffic, the other ~1,700 entities get near-zero
  competition long-tail traffic that compounds across the whole registry
- "[broker] sebi defaulter"
- "how to check if a stock broker is registered"
- "sebi expelled brokers list [year]"

**Action:** every one of the 1,774 registry pages needs its own indexable
URL with the legal name, registration number and status in the title/H1 —
this is pure programmatic SEO on data you already have (see growth idea #1).

### 2. Cost/comparison intent (high volume, needs the calculator to rank)
- "[broker] brokerage charges"
- "[broker A] vs [broker B] brokerage"
- "lowest brokerage discount broker india"
- "intraday brokerage calculator"
- "f&o brokerage calculator"
- "demat account charges comparison"

**Blocker:** this cluster is currently weak because charges data is still
sample-gated in production. Real charges (broker-supplied, verified) unlock
this entire cluster — it's the single biggest SEO reason to finish that
ingestion, independent of the trust reason already documented.

### 3. Complaint/trust intent (unlocked by the Annexure-B crawler)
- "[broker] complaints"
- "[broker] customer complaints sebi"
- "sebi investor complaint redressal"
- "how to file complaint against stock broker"
- "[broker] scam or genuine"

This cluster is high-intent (someone about to have a bad experience, or
already having one) and currently entirely unservable until the complaints
crawler (in progress) produces real data.

### 4. Regulatory-explainer intent (evergreen, low maintenance)
- "sebi algo trading rules 2025" / whatever the current year is
- "what is a sebi registered stock broker"
- "difference between broking licence and depository participant licence"
- "what is annexure b sebi"
- "nse vs bse vs mcx trading hours"

Already partly served by `/methodology`, `/algo`, and the market-timings mega
menu — these pages should be the landing targets for this cluster, not
buried behind app routes that crawlers may not render (see the frontend
audit's server-rendering gap — this cluster is the concrete revenue reason
to fix it).

### 5. Market-reference intent (already served, needs indexability)
- "nse trading hours today"
- "mcx market open or closed"
- "market holidays [year] nse bse"
- "muhurat trading time [year]"

### 6. Regional-language long tail (large, currently untouched)
Hindi, Tamil, Telugu, Marathi and Gujarati versions of clusters 1-3 are a
huge, almost entirely uncontested surface — most competitors (Chittorgarh,
Groww's own content) are English-first. "[broker] sebi registration हिंदी
में", "सेबी रजिस्टर्ड ब्रोकर कैसे चेक करें", etc.

---

## Global: VaspLens (proposed)

### 1. Verification intent (the whole point of the product)
- "is [exchange] regulated"
- "[exchange] MiCA license"
- "[exchange] CASP status"
- "[exchange] FCA registered"
- "is [exchange] licensed in EU"
- "[legal entity name] CASP authorisation" — same long-tail pattern as the
  SEBI registry, across 331+ ESMA-listed entities

### 2. Regulatory-explainer intent (evergreen, high search volume, no
   comparison-site currently owns this cleanly)
- "what is MiCA regulation"
- "CASP license explained"
- "MiCA vs FCA vs FinCEN crypto regulation"
- "is crypto regulated in Europe"
- "what happens if a crypto exchange is not licensed"

### 3. Jurisdiction-comparison intent (factual, not "best exchange")
- "which countries regulate crypto exchanges"
- "safest countries for crypto exchange licensing"
- "MiCA passporting explained"

### Deliberately not targeting at launch
- "best crypto exchange [country]" — this is the referral-saturated cluster
  every competitor already owns via affiliate spend; competing here pulls
  the product toward the model it exists to avoid.
- Any "should I use [exchange]" phrasing — that's advice, not verification.

---

## Cross-cutting: optimizing for AI answer engines, not just Google

A growing share of "is [broker] sebi registered" and "is [exchange]
regulated" queries now get answered inside ChatGPT, Perplexity, and Claude
rather than as a list of blue links. Structured data and clean server-
renderable facts are what those systems cite. Concretely:

- Ship the JSON-LD `Organization`/`FinancialService` structured data already
  identified as missing in the frontend audit — this is what LLM crawlers and
  answer engines parse most reliably.
- Fix the zero-server-rendered-content gap (also from that audit) — a
  crawler that can't render JS can't cite the page at all, for Google's
  non-JS path or any LLM crawler.
- Keep the "provenance dot" and source citations on every figure — answer
  engines preferentially cite pages that show their sourcing, which is a
  structural advantage BrokerLens already has over every referral-funded
  competitor that doesn't cite anything.
