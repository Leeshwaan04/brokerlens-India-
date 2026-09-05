# A second product: global crypto-exchange verification

**Status:** proposed, not started. This is the plan for the "additionally build for
crypto" decision. Nothing here has been built yet.

## The one decision that shapes everything else

**This must not be the same brand as BrokerLens, and it must not run on referral
commissions.** Both were deliberate, hard-won decisions on BrokerLens (lead
capture was removed twice after real compliance exposure was found), and the
entire competitive landscape in crypto comparison runs on exactly the model
BrokerLens rejected. If this new product quietly re-adopts referral revenue,
it is a different business with different incentives, and it should not share
a brand with a site whose entire premise is "our rankings are never for sale."

Recommended name: **VaspLens** (`vasplens.com` and `vasplens.io` are both
available today, checked live). VASP (Virtual Asset Service Provider) is the
term regulators actually use, which is also the exact phrase compliance-minded
searchers type. Alternative: `exchangelens.io` (`.com` is taken).

## What it actually is

Not a "best exchange" comparison site — that space is saturated and entirely
referral-funded (Binance, Coinbase, Bybit, KuCoin, Bitget all pay 40-50%
lifetime revenue share on trading fees; every existing site is built to
capture that). Competing there means competing on affiliate payout, which is
a race BrokerLens's whole model says not to run.

Instead: **the regulator-verification layer that doesn't exist globally.**
"Is this exchange actually licensed, where, and under what regime" is
currently answered by scattered blog listicles, not a structured, sourced,
continuously-checked registry. The exact same insight that built BrokerLens's
SEBI registry page, applied to crypto's fragmented regulatory landscape.

## Start with one regulator, exactly like BrokerLens started with one

BrokerLens did not start by solving NSE + BSE + MCX + SEBI simultaneously with
perfect identity resolution — it built the SEBI registry first, got identity
resolution right on one clean dataset, then added exchanges. Do the same here.

**First target: EU MiCA / CASP register.** Reasons:
- Single, official, digitized register (ESMA), not a patchwork
- 331 authorised providers as of the most recent check — a real, sizeable,
  citable dataset from day one
- Full authorization regime (not just AML registration like the UK's FCA list),
  so "CASP licensed" is a meaningful, checkable claim
- Comparable in shape to the SEBI registry: legal entity, licence number,
  services authorised, competent authority, validity

**Explicitly defer, in this order, until the first product proves out:**
1. UK FCA cryptoasset register (weaker regime — AML registration, not full
   authorization; the page must say this plainly, the way BrokerLens flags
   commodity-vs-equity registration differences)
2. US — FinCEN MSB is federal-only; state money-transmitter licensing is a
   50-state patchwork with no unified feed. This is a multi-month project on
   its own and should not block launch.
3. Singapore MAS, Canada FINTRAC, India FIU-IND (no public list exists at all
   for FIU-IND — that one may never be fully coverable without a FOI-style
   request)

A product that does one regulator well and is honest about not covering the
rest yet is more trustworthy than one that fakes broad coverage.

## What NOT to copy from BrokerLens

- Do not reuse the SEBI-specific identity-resolution logic verbatim — EU legal
  entity naming conventions, LEI codes, and multi-jurisdiction trade names are
  a different matching problem. Reuse the *pattern* (exact match → strict
  fallback → never guess on adverse claims), not the code.
- Do not carry over Indian-market assumptions (INR formatting, IST timings,
  lakh/crore) into shared utilities — this product is explicitly global from
  day one.

## What TO reuse

- The pipeline architecture: stdlib HTTP client with retry/backoff/stale-cache
  ceiling, atomic JSON writes, a `PUBLISH_MODE=production` gate that drops
  anything not sourced from the regulator itself.
- The provenance-dot pattern on every figure.
- The "adverse claims need an exact match, informational fields can be fuzzy"
  rule from the identity resolver — this matters even more here, since an
  incorrectly-flagged "not licensed" against a real, licensed EU firm is a
  bigger legal exposure than the Indian defaulter-list case ever was.

## Suggested v0.1 scope

1. Ingest the ESMA CASP register (structure TBD — check if there's a machine-
   readable export before building an HTML scraper).
2. One page per CASP-authorised entity: name, licence number, home competent
   authority, services authorised, validity.
3. A "Verify an exchange" search box, keyword-optimised around "is
   [exchange] regulated", "[exchange] MiCA license", "[exchange] CASP status".
4. No comparison rankings, no "best exchange" content, no referral links,
   at all, at launch. Prove the verification product first.

## Monetization, consistent with the no-referral rule

Same B2B model already recommended for BrokerLens: API access for compliance
teams, exchanges, and researchers who need to check CASP status
programmatically (this is a real, already-paid-for need — Chainalysis and
Elliptic sell exactly this to institutions, at institutional prices). Consumer
side stays free and referral-free, for the same trust reasons as BrokerLens.
