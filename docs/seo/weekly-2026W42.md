# SEO Weekly Cluster Report — 2026-W42

**Role:** SEO Strategist · **Date:** 2026-10-19 · **Cadence:** day-1 + weekly loop (first weekly)
**Data window:** 90-day GSC export 2026-07-19 → 2026-10-17 (`gsc_audit.json`; `by_date`, `by_page`, `by_query`, `page_query`, `inspection`, `sitemaps`)
**North star (O1):** 1,000 clicks / 100,000 impressions by **2026-11-03** (15-day hard milestone) — then 2,500 clicks / 90K by quarter end.

---

## 0. Bottom line (read this first)

- **Clicks are ON trajectory.** The trailing-30 window that closes on 2026-11-03 is **Oct 4 – Nov 3**. The known portion (Oct 4–17, 14 days) already has **361 clicks**. To reach 1,000 we need 639 more over 17 unknown days = **37.6/day**. The last-3 run-rate is **56.7 clicks/day** and the last-6 is 47.2/day — both clear 37.6. Flat-run projection: **1,324 clicks (last-3) / 1,163 (last-6)**. Click milestone is the easy half and is likely to be met without any new lever.
- **Impressions are the hard half and are NOT on trajectory.** Same window, known portion = **30,531 imps**. To reach 100,000 we need 69,469 more over 17 days = **4,086 imps/day**. Current run-rate is **3,184/day (last-3) / 2,898 (last-6)**. Flat-run projection: **84,659 imps (last-3) / 79,797 (last-6)** → **short by 15,341 (last-3) to 20,203 (last-6)**.
- **The gap to close: +902 imps/day (last-3 basis) = +28.3% over current**, sustained for 17 days. This is the binding constraint on O1.
- **Root cause of the impression gap is indexation, not CTR.** The sitemap *panel* reads **114,996 submitted / 0 indexed** — but that panel figure is **lag/artifact, not truth**: GSC URL Inspection independently shows a meaningful subset as **"Submitted and indexed" (PASS)** for `/`, `/brokers`, `/ipo/kfintech/`, `/stock/tcs/`, `/fund/hdfc-...`, `/funds-by/hdfc...`, `/registry`, `/sebi-registry/...`, `/calculators/sip-calculator/`, `/crypto/btc/`, `/methodology`. So the site *does* index; the panel aggregate simply hasn't caught up (a known GSC sitemap-panel lag). The real gap is that **indexation has not yet scaled** — wave-1 is 3,943, ~144K are `noindex`, 88,672 held back, and **the entire `/etf/` family (351 built pages) is in no sitemap at all**. CTR plays (my specs A and B) convert *existing* impressions into clicks — they do not create new impressions. The +28% impression gap is an **indexation-scaling** problem (CTO O2), which SEO can *accelerate* via sitemap hygiene (my spec C: add the never-submitted `/etf/` family, fix canonical↔sitemap URL mismatches, re-request-indexing on the tracked NEUTRAL money URLs). **See §5.**
- **Good news on the trend:** daily impressions are *rising*, not flat — Oct 14: 3,261 → Oct 15: 3,425 → Oct 16: 3,497 (+60% since Oct 12's 1,995). If that growth curve (not a flat run-rate) continues, the window clears 100K. My job this week is to *keep that curve steepening* (specs A/B/C) so the impression target lands even if the CTO indexation unlock is slower than hoped.

---

## 1. Impression-gap analysis vs the 15-day milestone (quantified)

**Window mechanics.** GSC reports a 30-day trailing window. The window that closes on the milestone date 2026-11-03 is **2026-10-04 → 2026-11-03 (30 days)**. 14 days are in the export (Oct 4–17); 17 days are not (Oct 18 – Nov 3).

| Measure | Known (Oct 4–17) | Need to 100K/1000 | Rate required (17d) | Current run-rate | Flat-run projection | Gap |
|---|---|---|---|---|---|---|
| Clicks | 361 | 639 | **37.6/day** | 56.7/d (3d), 47.2/d (6d) | **1,324** / 1,163 | **+324** / +163 (PASS) |
| Impressions | 30,531 | 69,469 | **4,086/day** | 3,184/d (3d), 2,898/d (6d) | **84,659** / 79,797 | **−15,341** / −20,203 (FAIL) |

**What must change, by how much (impressions):**
1. **+902 imps/day** over the next 17 days (flat last-3 basis) = **+28.3%** vs today.
2. That +902/day must come from *newly-indexed surfaces* (indexation unlock — CTO O2) and from *steeper indexation growth* already in evidence (spec C accelerates it). CTR/position work (spec A/B) contributes ~0 to impressions (those pages already have impressions at 0 clicks) — it protects the click side and feeds the "rescue-rate" KPI.
3. **Attribution of the +15.3K impression shortfall:**
   - **~70–85% = indexation unlock** (wave-1 un-noindex + the missing `/etf/` family + canonical/sitemap fixes). This is the dominant, and largely CTO-owned, lever.
   - **~15–30% = position recovery on already-indexed pages** (a page moving 11→4 doesn't add impressions; but pages currently *just* under the fold and the held-back tier getting promoted do add impressions via more query coverage).
   - **~0% = CTR changes alone** (they re-weight clicks, not impressions).

**Honest risk statement (feeds §5 escalation):** indexation *does* work (URL Inspection proves a real subset is "Submitted and indexed" — the "0 indexed" panel is lag, not truth). The risk is **scale + timing**: the 100K-impression target needs indexation to *scale up* (wave-1 un-noindex + the never-submitted `/etf/` family + held-back tier) to land inside 15 days. If that unlock is slower than the impression growth curve, 100K imps may miss even though clicks (1,000) land. This is a cross-role dependency on CTO (O2) — I am filing an **ESCALATION** (O1 impression target depends on O2 indexation-scaling, day-7 checkpoint 2026-10-26) and a **CONFLICT** (fourdegreewater orphan, §4).

---

## 2. Cluster priority ranking (with expected click / impression deltas)

Ranked by O1 contribution (click buffer first, then the impression-milestone lever, then clean mechanical wins). Deltas are 30-day estimates at band-1–5 CTR (2.3–6.3%) applied to the cluster's in-band impressions; "rescue" = cluster crossing ≥5 clicks/30d (the charter KPI).

| # | Cluster (spec) | Imps | Pos | 0-click? | Lever | Expected Δ (30d) | Rationale |
|---|---|---|---|---|---|---|---|
| **1** | **IPO price/GMP cluster** (spec A): laurus 378, bandhan 317, utiamc 286, khadim 167, gml 156 + registry aristro 170, fourdegreewater 809 | ~2,283 | 5.1–12.2 | yes (0–1) | **clicks** | **+20–45 clicks**, flips 4–6 of 7 clusters to ≥5 | Biggest zero-click impression base; worst-CTR family (IPO 0.11%). Title/meta intent fix + internal links push pos 6–10 → 1–5. GMP intent re-served as *listing price* (no grey-market). |
| **2** | **NEUTRAL→passing + `/etf/` sitemap** (spec C): 351 etf pages + 10 hub/brand URLs | 351 pages (new) + hub imps | unknown/soft-404/not-indexed | n/a | **impressions** (the +28% lever) | **+500–1,500 imps** once indexed; flips 10 NEUTRAL→PASS | The *only* SEO-controllable lever on the impression gap. Adds the never-submitted `/etf/` family and fixes canonical↔sitemap mismatches on the "unknown to Google" hubs. |
| **3** | **Econo broking** (spec B): clean 731 + `-332019` 190 | 921 | ~10 | yes (0) | **clicks** + KPI | **+8–20 clicks**, CTR 0→1–3% | Mechanical dedup/disambiguation + title fix. **Corrects the "merge" premise:** the two slugs are *two distinct SEBI registrations* — a 301 merge is a YMYL violation (see spec B VETO). Kills the charter cannibalisation KPI. |
| 4 | (hold) fourdegreewater restore | 809 | 9.3 | yes (0) | clicks | +12–24 clicks **if** CTO restores it to build+sitemap | Highest single zero-click page, but the page is **absent from the current build and sitemap** — blocked on CTO (filed CONFLICT). Parked in spec A §D. |
| 5 | (hold) Branch pages (doorway-risk), per-broker "stock cost" pages (pos 50–100, wrong intent) | — | 50–100 | — | — | — | **Abandoned this week** (see §3). Wrong intent + doorway risk per prior SERP audit; not 15-day winnable. |

**Top-3 opportunities (the ones I am shipping as specs):**
1. **IPO price/GMP cluster rescue** → **+20–45 clicks/30d**, rescues the worst-CTR family.
2. **NEUTRAL→passing + `/etf/` sitemap add** → **+500–1,500 imps/30d** (gated on indexation) + flips 10 tracked URLs to PASS; this is the lever on the +28% impression gap.
3. **Econo broking disambiguation** → **+8–20 clicks/30d**, CTR 0→1–3%, removes a charter cannibalisation KPI.

Combined conservative 30-day: **+28–65 clicks** (buffer on top of the already-passing click projection) and **+500–1,500 imps** (a real but *partial* step toward the +15.3K impression gap — the rest is O2/CTO).

---

## 3. What I am abandoning / deprioritising this week

- **Head broker terms** ("zerodha", "groww" as pure brand lookups at scale) — prior SERP audit: not winnable in 90 days vs incumbents. I am *not* chasing brand-lookup volume; I am only fixing the *indexation* of `/broker/zerodha/` and `/broker/groww/` (spec C) so they stop soft-404'ing / stay unknown.
- **Per-broker "stock cost" pages at pos 50–100** — wrong intent (SERP audit), no 15-day path to band 1–10. Abandoned as a target; left in the index as-is.
- **Branch pages** — rank top-10 but are **doorway-risk**; not promoting them, and I will not write title/meta expansion for them this week (would amplify doorway signal). Holding.
- **Fund / Broker families** (Fund 272p/4c/1,273i 0.16%; Broker 388p/3c/1,009i 0.29%) — small, low-CTR, no band-6–10 cluster to rescue at scale. No spec this week. Revisit monthly.
- **"share price target" content** — out of scope by charter constraint (those pages are 308-redirected); I will not create or re-title toward that intent.
- **Grey-market / GMP price content** — out of scope by constraint. Spec A serves the *legal substitute* (issue price / listing price / close) for GMP queries and explicitly does **not** publish GMP figures.
- **`/about`, `/sources`, `/compare/…` "Discovered – not indexed"** — lowest O1 value (non-money, trust/E-E-A-T pages). Included in spec C but explicitly **deprioritised** within it (fix only if the higher-value NEUTRALs land first).

---

## 4. Conclusions that change the plan vs the premise (data-verified)

These are where my ground-truth read of `site/`, `site/sitemaps/*`, and `inspection` diverges from the brief, and where specs differ from the naive reading:

1. **"econo broking … cannibalised across 3 URLs" — the 3rd URL is a false positive, and the two real ones must NOT be 301-merged.**
   - The two live pages are **two distinct SEBI registrations**: `/sebi-registry/econo-broking-private-limited/` = *Commodity broker*, reg shown as `INZ`, valid "Aug 23 – Perpetual"; `/sebi-registry/econo-broking-private-limited-332019/` = *Depository participant (CDSL)*, reg `IN-DP-433-`, valid "Aug 30 – Perpetual". Different registration number, different category, different validity.
   - The "3rd URL" is `site/fund/edelweiss-mutual-fund-edelweiss-bse-internet-economy-index-fund/` — it matches "econo" only by substring and is a **different entity** (1 impression). No cannibalisation with it.
   - **A 301 from one slug to the other would publish a wrong regulator record (YMYL data-correctness violation).** Spec B VETOs the merge; the correct fix is *disambiguation* (distinct titles/targeting + mutual cross-links), not consolidation.

2. **`fourdegreewater` (the single biggest zero-click page, 809 imps / pos 9.3) is not in the current build or any sitemap.** GSC still reports it (809 imps) but `site/sebi-registry/fourdegreewater-services-private-limited/` does not exist and no sitemap lists it. If it was removed, the URL now serves the SPA `/* → /index.html 200` fallback → **soft-404**, silently wasting 809 impressions. I **cannot** recommend a title/meta change to a page that isn't built, and I **cannot** unilaterally add it to the sitemap (drop/add of indexed URLs needs CTO ack per charter). Filed as **CONFLICT** (restore vs intentional-removal decision) — spec A §D parks it.

3. **`/etf/` (351 built pages) is entirely absent from the sitemaps** — zero `https://www.brokerlens.in/etf/…` URLs in any `site/sitemaps/*.xml`. That is the direct cause of `/etf/niftybees/` "URL is unknown to Google". This is the largest single impression-unlock available to SEO. Spec C.

4. **"URL is unknown to Google" on sitemap-listed hubs = canonical↔sitemap URL string mismatch.** `/ipo`, `/news`, `/about`, `/sources` are in `sitemap-core.xml` *without* trailing slash, while each page's `<link rel=canonical>` and `og:url` use the trailing-slash form (`/ipo/`, `/news/`, …). The submitted URL and the canonical don't match → Google never confirms the submitted URL. Spec C normalises this. (`/ipo/upcoming/` and `/index/nifty-50/` and `/trade-costs/` are already slashed in the sitemap — their "unknown" is the broader 0-indexed state, not the slash.)

5. **`/broker/zerodha/` "Soft 404" is a false soft-404** — the page renders full, valid, real content (active clients 7.9M, complaints 1.62/10k, cost Rs 255, SEBI `INZ000031633`, reliability 97.2). Google flagged it soft-404 most likely because it was previously fetched as the SPA fallback (404-equivalent) or because the page is a near-template duplicate. Spec C addresses 200-at-edge + content uniqueness.

6. **`/stock/itc/` "Crawled – currently not indexed" while `/stock/tcs/` PASSES** — itc was crawled today (2026-10-19 05:20) and is allowed; it's a dedup/quality hold, not a robots/canonical block. Title is thin ("NSE Listing Details", no price/sector). Spec C: differentiate title + ensure the unique per-stock fact block is present.

---

## 5. Escalations / conflicts filed this cycle (detail in ledger)

- **ESCALATION (O1 impression target depends on O2 indexation-scaling → Owner + CTO):** the 100,000-impression half of the 15-day milestone depends on indexation *scaling up* — wave-1 un-noindex, adding the never-submitted `/etf/` family (351 pages) to the sitemap, and held-back tier promotion (O2/CTO). The sitemap panel's "114,996 / 0 indexed" is **lag, not truth** (URL Inspection shows a real indexed subset), so the site indexes — the question is whether indexation scales fast enough inside 15 days to reach 100K imps. Clicks (1,000) remain on trajectory independent of this. **Day-7 checkpoint (2026-10-26):** re-pull GSC, recompute the Oct 4–26 window, verify impressions run-rate ≥4,086/day. If not → formal gap-analysis escalation (charter-mandated), not a new target.
- **CONFLICT (fourdegreewater orphan → CTO ack):** `/sebi-registry/fourdegreewater-services-private-limited/` is live in GSC (809 imps) but absent from the current build + sitemap. Either (a) restore it to build + sitemap (I supply the title/meta spec, A §D), or (b) confirm intentional removal — in which case it is soft-404'ing 809 imps and I will re-spec around it. Blocking CTO confirmation; I proceed on all other clusters.

---

## 6. Next cadence

- **Day-7 checkpoint (2026-10-26):** re-pull GSC, recompute the Oct 4–26 window, verify impressions run-rate ≥4,086/day. If not → formal gap-analysis escalation (per §5).
- **Weekly (next Monday):** 1 cluster report + up to 2 new fix specs; re-score the "rescue-rate" KPI on spec A/B clusters (target: ≥5 clicks/30d per rescued cluster).
- **Money-page list for CBO:** top-20 URLs by clicks attached to the ledger each Friday (CBO interface).

*All specs in `docs/seo/spec-20261019-*.md` are self-contained for CTO execution. No page content, sitemap, code, or pipeline file was modified — direction only.*
