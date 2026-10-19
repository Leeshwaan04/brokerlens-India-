# QA Report — Week 2026-W42 (first CQA cycle)

**Date:** 2026-10-19 · **HEAD:** `c2d45d6` (IBSL banner referral-fee sentence removed from all caption text)
**Role:** CQA (charter §4) · **Verdict:** **PASS — baseline holds, gate green, 0 hard failures**

## 1. Gate results at HEAD vs baseline (2026-10-17)

| Suite | Command | Baseline | This run | Delta |
|---|---|---|---|---|
| QA e2e | `python3 tests/qa_e2e.py` (offline) | 597 pass / 0 fail / 1 skip | **597 pass / 0 fail / 1 skip** | identical — baseline holds |
| VAPT | `python3 tests/vapt.py` | 21 clean | **21 checks passed, 0 findings** | identical |
| ad-event unit | `node tests/ad_event_test.js` (node v22.20.0) | 15/15 | **15 passed, 0 failed** | identical |

Notes:
- The 1 skip is the `--url` live-server section (http + SSE checks), by design in offline mode.
- `site/` was already built; no pipeline build was required to run the gate.
- The IBSL caption change at HEAD (`c2d45d6`) is covered by existing checks ("the referral-fee sentence is gone", "no banner anywhere has a cancel icon … Sponsored tag is top-right") and both pass.

## 2. Production ad-surface spot check (brokerlens.in, fetched 2026-10-19)

Sample: home `/`, IPO detail `/ipo/gml/`, stock `/stock/itc/`, broker `/broker/zerodha/`, calculator `/calculator/` (307→`/calculators/`), `/news/` hub + one article, legal `/privacy-policy/`.

| Page (final URL) | Banner present & expected? | Sponsored tag | No close/cancel control | ad-track.js chain | IBSL link URL + rel |
|---|---|---|---|---|---|
| `/` (home) | PASS (strip, `data-page-type="home"`) | PASS | PASS | PASS (via search.js import on loaded pages) | PASS `https://stocks-onboarding.indiabullssecurities.com/login` `rel="sponsored noopener"` |
| `/ipo/gml/` | PASS (wide, `ipo`) | PASS | PASS | PASS | PASS (same) |
| `/stock/itc/` | PASS (card, `stock`) | PASS | PASS | PASS (`search.js?v=e1224b2aa0` → `import './ad-track.js?v=7acb3a2f93'`) | PASS (same) |
| `/broker/zerodha/` | PASS (wide, `broker`) | PASS | PASS | n/a (no search widget on page) | PASS (same) |
| `/calculator/` → 307 → `/calculators/` | **PARTIAL — see DEFECT-001**: `/calculators/` hub has the wide banner (`calculator`); the landed calculator page does not | PASS on hub | PASS | PASS | PASS on hub |
| `/news/` hub | PASS — no banner expected on hub; article `/news/demat-account-safety-freeze-guide/` **does** carry the wide `news` banner | PASS | PASS | PASS | PASS |
| `/privacy-policy/` (legal) | PASS — **no banner** (correct exclusion) | n/a | n/a | n/a | n/a |

Additional production probes:
- **BEACON:** `/api/ad-event` — missing Origin → 403, foreign Origin → 403, valid Origin (both hosts) → accepted (400 on minimal test payload is field validation, not rejection). Matches VAPT behaviour.
- **IBSL caption (HEAD change):** alt/caption on sampled pages is now "Indiabulls Securities: Rs 0 account opening charges, Rs 11 per executed order across all segments\*, 20 years of trust. Open your free account now. Terms apply." — referral-fee sentence is **gone** on all sampled pages.
- **SEBI disclosure wording intact:** "Sponsored. Indiabulls Securities Limited, SEBI Reg. INZ000036136 (check the SEBI register), DP IN-DP-423-2019." present on sampled banner pages.
- **All 6 sampled IBSL anchor tags** carry `rel="sponsored noopener"` target=_blank.
- **No page exceeded** 3 sponsored blocks / 2 IBSL banners in the sample (stock page = 1 IBSL + 2 affiliate banners, at the cap, gate-checked globally).

### NOTE-1 (informational, not a defect)
`brokerlens.in` (apex) issues a 307 → `www.brokerlens.in` canonical redirect before serving content. Source of this redirect is not in `site/_redirects` or `vercel.json` (appears to be platform/edge-level). Behaviour is correct (single canonical host, beacon allows both hosts) but the source of truth for the redirect should be documented by CTO; if CTO later edits `vercel.json`/edge config, this redirect must survive the full gate. Logged so nobody "fixes" it blindly.

## 3. YMYL spot check (same sample)

| Page | Grey-market price language | "Share price target" phrasing | Source attribution |
|---|---|---|---|
| `/` | PASS — none | PASS — none | PASS |
| `/ipo/gml/` | PASS — only the **denial** ("Does BrokerLens display GMP? No. Grey Market Premium is not published…") | PASS | PASS — "the page's facts are NSE's own public-issue disclosures" |
| `/stock/itc/` | PASS — none | PASS — only the **denial** FAQ ("What is the share price target of ITC…? BrokerLens does not publish price targets or forecasts…") | PASS — "Source: NSE listed-securities master file (EQUITY_L) and NSE's daily bhavcopy" |
| `/broker/zerodha/` | PASS — none | PASS — none | PASS |
| `/calculators/` | PASS — none | PASS — none | n/a (tool) |
| news article | PASS — none | PASS — none | PASS (Editorial Integrity present) |
| `/privacy-policy/` | PASS — none | PASS — none | n/a |

YMYL **PASS** — no grey-market price values, no target-price claims anywhere in the sample; both "target" and "GMP" occurrences are compliant denial copy. (The single "referral" string on home is the 5paisa affiliate CTA `ReferralCode` URL param — pre-existing affiliate surface, unrelated to the IBSL caption change.)

## 4. Defects filed this cycle

- **DEFECT-001** (LOW) — IBSL banner missing on `/calculator/` (brokerage cost calculator) page itself; present only on the `/calculators/` hub. Filed in `docs/qa/defect-ledger.md`. Not a BLOCK: a monetised page family with a banner on its hub is not a compliance gap, but the charter placement list includes "calculator pages" and the gate only checks the hub, so this is a coverage gap in the ad surface. Owner: CTO (placement is a CBO decision per charter §5 — CBO may accept the hub-only placement, in which case CQA updates the check to match).
- No DEFECTs of severity HIGH/CRITICAL. No REGRESSION vs baseline. No BLOCKs issued.

## 5. Next-week check plan (≥10/month bar — ranked candidates)

1. **Prod-vs-build drift check** — fetch N production URLs and diff key ad-surface markers (banner markup, ad-track script hash, IBSL URL/rel) against `site/`; catch the class of gap where local gate passes but production differs. (Rank 1: this cycle's /calculator/ finding was only catchable by fetching prod.)
2. **Full-family prod banner matrix** — scripted curl of one page per monetised family (home, ipo hub, upcoming, ipo detail, broker, stock, calculator, news article) asserting banner presence + sponsored tag, replacing the manual 7-page sample.
3. **SEBI disclosure string canary** — exact-string match on the IBSL disclosure note ("SEBI Reg. INZ000036136 … DP IN-DP-423-2019") on every built banner page, so any CBO wording edit that breaks the disclosure fails the gate.
4. **Beacon production probe** — live 403-on-missing-origin / 403-on-foreign-origin / 204-on-valid-origin assertions in `qa_e2e.py --url` mode.
5. **IBSL caption canary** — assert the referral-fee sentence stays absent from all banner alts/captions (locks in the `c2d45d6` fix).
6. **Sponsored-link rel sweep** — every external sponsored/affiliate anchor in built pages must carry `rel="sponsored noopener"` (currently gate checks IBSL links only; 5paisa/Zerodha/Jiraaf CTAs are unguarded).
7. **YMYL phrase scan (built site-wide)** — regex for grey-market price values and "target price ₹X" patterns across all 3,900+ pages (currently spot-checked manually).
8. **Deflection-page consistency** — assert the "share price target" / "GMP" denial FAQ copy exists and denies on all IPO-detail and stock pages (protects the 308-redirect YMYL posture).
9. **Banner count cap audit (all pages)** — extend the 3-block/2-IBSL cap check from the 6 sampled placements to a full-site scan.
10. **ad-track load-path audit** — assert `ad-track.js` is reachable from the script graph of every page that carries a banner (guards against a future template change that drops the search.js/app.js chain).
11. (Bonus) **Legal/trust page exclusion sweep** — full-site scan that no excluded family (privacy, terms, about, methodology, contact, editorial-policy, sources, sebi-registry entity, crypto, etf, 404) carries an IBSL block.

## 6. Standing duties status

| Duty | Status |
|---|---|
| Sponsored tag on ALL banners | PASS (sample) — canary check planned (#3/#6) |
| No cancel/close icons on any banner | PASS (gate + sample) |
| IBSL banners only on approved families | PASS (sample + gate exclusion list) |
| ad-track.js present → /api/ad-event | PASS (prod chain verified) |
| No grey-market prices | PASS (sample) |
| No "share price target" phrasing | PASS (sample — denial copy only) |
| Sources present | PASS (sample) |
| SEBI disclosure intact | PASS (sample) |
