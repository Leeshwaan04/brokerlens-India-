# SPEC — 20261019 — "Econo broking" cluster: disambiguation (VETO on the 301-merge premise)

**From:** SEO Strategist · **To:** CTO (self-select) · **Date:** 2026-10-19
**Type:** Title/meta disambiguation + internal-link suggestion (CTO template edits). **No redirect is requested.**
**KPI addressed:** charter KPI "Cannibalisation count — target: 0 unresolved clusters of ≥100 impressions" + O1 click buffer.
**IMPORTANT:** This spec **VETOs the merge** implied by the brief ("which of the 3 URLs is canonical, what the other 2 become"). The verification below shows the merge would be a YMYL data-correctness violation. The correct action is disambiguation, not consolidation.

---

## Why the brief's premise is wrong (verified ground truth)

The brief describes "econo broking … cannibalised across 3 URLs." I checked `site/`, all `site/sitemaps/*.xml`, and the GSC `by_page`/`page_query` matrix. Findings:

1. **Only TWO live "econo broking" pages exist** (both in `sitemap-registry.xml` and built):
   - `https://www.brokerlens.in/sebi-registry/econo-broking-private-limited/` — 731 imps, pos 10.0, 0 clicks. Category: **Commodity broker**. SEBI reg shown: `INZ…` (truncated in page). Validity "Aug 23 – Perpetual". Memberships: NSE, MCX, MCX-CCIL, NSE Clearing, BSE.
   - `https://www.brokerlens.in/sebi-registry/econo-broking-private-limited-332019/` — 190 imps, pos 9.5, 0 clicks. Category: **Depository participant (CDSL)**. SEBI reg shown: `IN-DP-433-…`. Validity "Aug 30 – Perpetual". Memberships: not disclosed.
2. **They are two distinct SEBI registrations of the same company name** — different registration number, **different category** (Commodity broker vs Depository participant), different validity date. This is a legitimate, common SEBI situation (one firm, multiple registrations across categories).
3. **A 301 from one slug to the other would publish a single regulator record for two different registrations** — i.e. it would make the site *assert* "Econo Broking is only a commodity broker" (or only a DP) and drop the other. That is a **data-correctness / YMYL violation** (we would be misstating SEBI registration facts). I am **VETO**ing the merge on that basis.
4. **The "3rd URL" is a false positive.** The only other "econo"-matching surface is `site/fund/edelweiss-mutual-fund-edelweiss-bse-internet-economy-index-fund/` (1 impression, pos 44) — a **different entity** (an Edelweiss index fund); it matches "econo" only by substring ("internet **econo**my"). It is *not* part of this cluster and is not cannibalising it. Do not redirect or change it.
5. **There is no real `econo` broker page** (`site/broker/`, `site/brokers-by/` — none). The two registry pages ARE the cluster.

**Conclusion:** the "cannibalisation" is two valid, distinct registration pages that currently *look* near-duplicate to Google (near-identical template + similar name) and split the "econo broking" query's 921 impressions at ~pos 10 between them, so neither gets a click. The fix is to make Google see them as **distinct, each correctly labelled**, so the *primary* one (commodity broker, which is what "econo broking" as a *broker* refers to) consolidates the generic-brand query, while the DP page keeps its own (category-specific) relevance. No redirect, no drop.

## What changes (exact, per URL)

### B1. `https://www.brokerlens.in/sebi-registry/econo-broking-private-limited/` — **the primary / canonical-for-the-brand**
- **New title:** `Econo Broking: SEBI-Registered Commodity Broker | BrokerLens`
- **New meta:** `Econo Broking Private Limited — SEBI-registered commodity broker. Registration number, exchange memberships (NSE, MCX, BSE) and validity, from SEBI's recognised-intermediary register.`
- **Why:** The generic query `econo broking` (492i, pos 10.6) and `econo broking pvt ltd`/`private limited` (86i) are *brand* lookups → they should land on the *commodity broker* page (that is what "Econo Broking" the firm is, publicly). Front-loading the **category (Commodity Broker)** into the title (a) matches the "econo broking" brand intent and (b) is the differentiator that lets Google pick this page for the generic query over the DP page.
- **Internal links to add:** → `/registry` (hub, already in breadcrumb — keep) + a **sibling cross-link** "Econo Broking — Depository Participant registration →" pointing to B2's URL. Add → `/brokers` ("Brokers tracked in depth") if not present.
- **Do NOT change:** canonical (stays self), no redirect, no drop from sitemap.

### B2. `https://www.brokerlens.in/sebi-registry/econo-broking-private-limited-332019/` — **the secondary / DP registration**
- **New title:** `Econo Broking: SEBI-Registered Depository Participant (CDSL) | BrokerLens`
- **New meta:** `Econo Broking Private Limited — SEBI-registered depository participant (CDSL). Registration number and validity, from SEBI's recognised-intermediary register.`
- **Why:** The DP registration should *not* compete for the generic "econo broking" brand query (that's B1's job). Putting **"Depository Participant (CDSL)"** in the title narrows its relevance to DP-specific queries and stops it siphoning the brand query. This is what actually *de-cannibalises*: two pages with two clearly-distinct, category-labelled titles instead of two near-identical "SEBI Registration" titles.
- **Internal links to add:** → `/registry` (keep) + **sibling cross-link** "Econo Broking — Commodity Broker registration →" to B1. 
- **Do NOT change:** canonical (stays self), no redirect, no drop from sitemap.

### The "3rd URL" — `site/fund/edelweiss-...-internet-economy-index-fund/`
- **No action.** Different entity, 1 impression, not part of the cluster. Listed here only to close out the brief's "3 URLs" claim so CTO does not "resolve" it by mistake.

## Net effect on the cannibalisation KPI

- Pre-fix: one query family ("econo broking", 921 imps) split 731/190 across two visually-identical pages at ~pos 10 → 0 clicks.
- Post-fix: two clearly-distinct titles; the commodity-broker page becomes the single relevance owner of the generic-brand query (its 492-i `econo broking` + the brand-tail queries consolidate), the DP page owns DP-specific intent. Google can consolidate ranking for the brand query onto B1 → B1's effective position/CTR improves.
- The charter KPI "0 unresolved clusters of ≥100 impressions" is satisfied by *resolving the ambiguity* (distinct intent per URL), which is the correct resolution when the "duplicates" are legitimately distinct entities. **A merge is the wrong fix and would create a compliance defect** — I am filing that as a VETO in the ledger.

## Expected metric outcome (30-day)

- B1 consolidating the generic brand query: **+6–14 clicks/30d** (if it moves from pos ~10 → band 1–5 on the 492-i brand query).
- B2: ~0 net (its traffic is small and DP-specific); its job is to stop *costing* B1 the brand query.
- **Total spec B: +6–16 clicks/30d**, CTR on the "econo broking" query family 0% → ~1–3%.
- Impressions: ~0 net change (both pages already indexed with impressions).

## CTO notes / guardrails

- **No redirect, no sitemap drop, no canonical change.** These are title/meta + two cross-link template edits only. (Dropping an indexed URL would also require CTO ack per charter and is *not* recommended here — both registrations are legitimate and indexable.)
- **Data-completeness flag for CQA/CPO (out of scope for me):** both pages show *truncated* SEBI registration numbers (`INZ…`, `IN-DP-433-…`). The disambiguation leans on the **category** field, which is complete, so the fix does not depend on the reg-number display. But the truncated reg number is a separate data-pipeline defect — I am **not** asking to fix it here; flagging so CQA can open a `DEFECT` if the source feed is truncated.
- **YMYL:** titles assert only the category and that a registration exists — both already true on the page. No new claim, no invented number.
