# SPEC — 20261019 — IPO price/GMP zero-click cluster rescue

**From:** SEO Strategist · **To:** CTO (self-select, pull model) · **Date:** 2026-10-19
**Type:** On-page title/meta intent alignment + internal-link suggestions (title/meta changes ship as CTO edits; internal links as CTO template edits)
**KPI addressed:** O1 clicks (buffer) + charter KPI "zero-click-cluster rescue rate" (cluster ≥5 clicks within 30 days of fix shipping)
**Constraint compliance:** No grey-market/GMP figures published. GMP *intent* is served by the legal substitutes already on the page (issue price / listing price / last close). YMYL: every figure below is **already present in the built page** — this spec re-surfaces existing numbers in titles, it invents none.

---

## Why (the leverage)

- The **IPO family is the worst-CTR family on the site: 1,079 pages / 27 clicks / 25,464 imps = 0.11% CTR.** It holds the largest zero-click impression base.
- The single top queries for these pages are `"<name> ipo price"`, `"<name> ipo"`, `"<name> ipo gmp"`, `"<name> listing date"` — i.e. **price intent**, but the current `<title>` leads with the *current close* and a %-change, which does not match the query and ranks pos 6–12 at 0 clicks.
- These pages already rank pos 5–12 (in-band). Per the CTR-by-position data, **moving them from pos 6–10 into band 1–5 (CTR 2.3–6.3%) is the highest-leverage play on the click side.** A title/meta that matches the exact query is the cheapest way to nudge position up.
- **GMP constraint:** GSC shows the GMP query `uti amc ipo grey market premium` = 261 imps (the largest single zero-click query in the cluster). We **cannot** publish a GMP figure (grey-market constraint + it's a 308-redirected intent class). The correct move is to let the *listing price / issue price* title answer the underlying "how did it do" intent, and **not** chase the GMP string. We accept we lose the literal GMP SERP; we win the price/listing SERP that dominates the cluster.

## What changes (exact, per URL)

Format: **URL → new `<title>` + new `meta description` + why + internal links to add.**
All numbers are read from the *current built page* (verified against `site/ipo/<slug>/index.html`). `| BrokerLens` suffix kept on all.

### A1. `https://www.brokerlens.in/ipo/lauruslabs/`  (378 imps, pos 8.2, 0 clicks)
- **New title:** `Laurus Labs IPO: Issue Price Rs 428, Listing Price & Current Price | BrokerLens`
- **New meta:** `Laurus Labs IPO (LAURUSLABS): issued at Rs 428 per equity. Listing price, post-listing gain, and latest close from NSE/BSE disclosures, with dates and subscription.`
- **Why:** Query is `laurus labs ipo price` (142i) / `laurus labs ipo` (38i) / `laurus labs listing date` (11i). Current title leads with `Latest Close Rs 1,984 (+363.6%)` — matches none of those queries. New title front-loads "Issue Price" + "Listing Price" to capture the price/listing intent.
- **Internal links to add (on this page):** → `/stock/lauruslabs/` (exists) as "Laurus Labs — NSE listing details" link in the header/below the price block; → `/ipo/archive/` ("More listed IPOs"); keep existing → `/ipo/`.

### A2. `https://www.brokerlens.in/ipo/bandhanbnk/`  (317 imps, pos 7.9, 0 clicks)
- **New title:** `Bandhan Bank IPO: Issue Price Rs 375, Listing Price & Current Price | BrokerLens`
- **New meta:** `Bandhan Bank IPO (BANDHANBNK): issued at Rs 375 per equity. Listing price, post-listing performance, latest close and issue dates from NSE/BSE disclosures, with lot size and subscription.`
- **Why:** Query is `bandhan bank ipo price` (94i) / `bandhan bank ipo` (16i) / `bandhan bank ipo date` (23i). Current title `Latest Close Rs 176 (-53.1%)` — the negative % actively *deters* clicks on a price query. New title drops the %-change from the SERP and leads with issue price.
- **Internal links to add:** → `/stock/bandhanbnk/` (exists) "Bandhan Bank — NSE listing details"; → `/ipo/archive/`; keep → `/ipo/`.

### A3. `https://www.brokerlens.in/ipo/utiamc/`  (286 imps, pos 12.2, 0 clicks) — **GMP query page**
- **New title:** `UTI AMC IPO: Issue Price Rs 554, Listing Price & Current Price | BrokerLens`
- **New meta:** `UTI Asset Management Company (UTIAMC) IPO: issued at Rs 554 per equity. Listing price, post-listing gain and latest close from NSE/BSE disclosures, with issue dates and subscription.`
- **Why:** Top query is `uti amc ipo grey market premium` (261i, pos 9.6) — the **largest single zero-click query in the cluster**. We do **not** publish a GMP figure (constraint). The title targets the *legal substitute* (issue price / listing price) that satisfies the "how did it do" intent behind the GMP search. This page is currently *just outside* band 1–10 (pos 12.2); the matching title is what should pull it into band 1–5.
- **Do NOT:** add any "GMP today" / "grey market premium" string or number to title, meta, or body. (QA VAPT will flag it.)
- **Internal links to add:** → `/stock/utiamc/` (exists) "UTI AMC — NSE listing details"; → `/ipo/archive/`; keep → `/ipo/`.

### A4. `https://www.brokerlens.in/ipo/khadim/`  (167 imps, pos 6.5, 0 clicks)
- **New title:** `Khadim India IPO: Issue Price Rs 750, Listing Price & Current Price | BrokerLens`
- **New meta:** `Khadim India IPO (KHADIM): issued at Rs 750 per equity. Listing price, post-listing performance, latest close and issue dates from NSE/BSE disclosures, with lot size and subscription.`
- **Why:** Query is `khadim ipo price` (126i). Current title leads `Latest Close Rs 108 (-85.5%)` — worst % in the cluster, suppresses CTR on a price query. Same pattern as bandhan.
- **Internal links to add:** → `/stock/khadim/` (exists) "Khadim India — NSE listing details"; → `/ipo/archive/`; keep → `/ipo/`.
- **Note (308 class):** `khadim share price target 2030` (2i) is a share-price-target intent — already 308-redirected. Out of scope; do not re-title toward it.

### A5. `https://www.brokerlens.in/ipo/gml/`  (156 imps, pos 8.1, 0 clicks) — **closed IPO, "gml ipo" query**
- **New title:** `Galaxy Medicare (GML) IPO: Issue Price, Allotment & Listing | BrokerLens`
- **New meta:** `Galaxy Medicare Limited (GML) IPO closed 12 Sep 2025. Issue price, how to check allotment, expected listing timeline and price band, from NSE/BSE disclosures.`
- **Why:** Query is `gml ipo` (142i, pos 7). The page is a *closed, pre-listing* IPO (title already says "IPO Closed"). The intent is "what was the price / is it allotted / when does it list". Current title is close but `Subscription`-led; re-ordering to **Issue Price → Allotment → Listing** better matches the `gml ipo` + `gml ipo gmp` (n/a) cluster. **Do not** add a GMP figure (constraint); the page has no post-listing price to show, which is correct — leave it as a closed-IPO page.
- **Note:** `/stock/gml/` **does not exist** (GML not listed / no stock page). So for this page the internal link is → `/ipo/archive/` + keep → `/ipo/`; **no** stock cross-link (verified missing — do not add a dead link).

### A6. `https://www.brokerlens.in/sebi-registry/aristro-capital-markets-limited/`  (170 imps, pos 5.1, 1 click) — **intent mismatch**
- **New title:** `Aristro Capital Markets: SEBI Registration (Commodity Broker) | BrokerLens`
- **New meta:** `Aristro Capital Markets Limited SEBI registration — category Commodity broker, number INZ000219238, exchange memberships and validity, from SEBI's recognised-intermediary register.`
- **Why:** The driving query is `aristro capital markets limited` (136i, pos 5.1) — a *registry* intent, and the page is the correct registry page, already at pos 5.1 with 1 click. This is the one cluster page already on the right intent; it just needs a **clearer title** (drop the generic ": SEBI Registration", add the category so the SERP differentiates from the *other* Aristro registration) and the category pulled into the title. **Do not** attempt to make it rank for "aristro ipo" — that would be the wrong entity (it's a broker, not the IPO issuer). This is a small CTR/position polish, not a rescue.
- **Internal links to add:** → `/registry` hub (already in breadcrumb); add a "Brokers tracked in depth → `/brokers`" line if not present.

### A7 (PARKED — see CONFLICT). `https://www.brokerlens.in/sebi-registry/fourdegreewater-services-private-limited/`  (809 imps, pos 9.3, 0 clicks)
- **STATUS: BLOCKED — the page is NOT in the current build or any sitemap.** `site/sebi-registry/fourdegreewater-services-private-limited/` does not exist; no `site/sitemaps/*.xml` lists it. GSC still reports 809 imps because the URL was indexed earlier and is now serving the SPA `/* → /index.html 200` fallback (soft-404).
- **I cannot ship a title/meta change to a page that isn't built, and I cannot add an indexed URL to the sitemap without CTO ack (charter).** Filed **CONFLICT** → CTO: (a) restore the page to build + `sitemap-registry.xml` (then apply the A-pattern title below), or (b) confirm intentional removal.
- **Title to apply once restored:** `Four Degree Water Services: SEBI Registration | BrokerLens` + meta with its category/number, plus → `/registry` + → `/brokers` links. Highest single zero-click page on the site — restoring it is worth +12–24 clicks/30d if it re-indexes at pos ~5–9.

## Internal-link pattern (apply across A1–A5, template-level)

On every *listed* IPO page, add a consistent "Related" block (template change, not per-page copy):
1. `→ /stock/<symbol>/` "Company — NSE listing details" (only where the stock page exists — verified for lauruslabs, bandhanbnk, utiamc, khadim; **not** gml).
2. `→ /ipo/archive/` "More listed IPOs".
3. `→ /ipo/` hub (already present — keep).

Rationale: this creates a bidirectional, query-relevant link between the IPO page and the stock page, which (a) distributes the already-strong STOCK family authority (1,815p/293c, 1.84% CTR — the best family) into the weak IPO family, and (b) gives the crawler two in-band paths so the IPO page's indexation is reinforced.

## Expected metric outcome (30-day, conservative)

- A1–A5 (5 IPO pages, ~1,304 imps in-band at pos 6–12): if 2–3 of them move into band 1–5 (CTR 2.3–6.3%), expected **+15–35 clicks/30d**, flipping those clusters past the ≥5-click rescue threshold.
- A6 (aristro, 170i @5.1): **+1–5 clicks/30d** (position polish).
- A7 (fourdegreewater, 809i @9.3): **+12–24 clicks/30d** *only if* CTO restores it (CONFLICT-dependent).
- **Total spec A (A1–A6, excluding A7): +16–40 clicks/30d.** With A7: +28–64 clicks/30d.
- Impressions: ~0 net change (pages already indexed with impressions). This spec is a **click** lever, not an impression lever (see weekly report §1).

## Rollback / QA guardrails

- CQA VAPT must confirm **no GMP/grey-market string or number** appears in any A1–A6 title/meta/body (the `uti amc gmp` cluster is the risk page — A3).
- CQA must confirm the 308-redirect for any `*share price target*` intent is intact (khadim A4 note).
- If, after 2 consecutive weekly GSC windows post-ship, a given cluster shows <2% CTR improvement, per charter I mark it **abandoned** in the ledger and re-target — CTO should not chase further title variants on it.
- These are on-page edits only; no robots/canonical/sitemap change in this spec (sitemap/indexation is spec C).
