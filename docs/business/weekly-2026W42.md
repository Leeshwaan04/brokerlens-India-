# CBO Weekly Business Report — 2026W42 (week of 2026-10-19)

**Owner-of-record:** CBO · **Objective:** O3 (IBSL revenue measurement and growth)
**Status line:** Day 1 of charter operation. Attribution spec filed today; tag live deadline 2026-10-24. No IBSL revenue number is reportable yet — see "what we cannot measure" below.

---

## 1. Tracking status — what we can and cannot measure today

### Can measure today (first-party, `/api/ad-event`, live)

| Metric | How | Caveat |
|---|---|---|
| Banner impressions by slot/page-type/page-path | `t:"imp"` beacons (50% visible, 1s dwell) | Events live only in **short-lived Vercel logs** — no durable store yet; a durable log sink is a CTO task (noted in `api/ad-event.js` header). Treat any number pulled from logs as a snapshot, not a ledger of record. |
| Banner clicks, by slot, page-type, page-path, device | `t:"click"` beacons | Same log-volatility caveat. |
| CTR by page family | click ÷ impression per `pt`/`slot` from logs | Only meaningful once we have ≥1 full week of same-window data. Baseline not yet computed — first clean baseline goes in the 2026W43 report. |
| Inbound source to our site (referrer host of the page that fired the beacon) | `ref` field | This tells us how users arrived *at BrokerLens* (e.g. google.com), not where banner clicks went. |

### Cannot measure today

- **IBSL-attributed onboardings** — the blocker. The onboarding URL has no source tag, so we cannot join our click counts to IBSL account openings. **Fixed by `docs/business/2026-10-19-ibsl-source-tag-spec.md`** (filed 2026-10-19, deadline 2026-10-24). Until the tag is live: O3 reports clicks only, and any IBSL-side conversion claim is unverifiable.
- **Click→onboarding conversion rate** — blocked on the same tag, plus confirmation from IBSL that their backend persists query params (Owner-confirmation item C3).
- **Monthly revenue** — deal terms (flat vs rev share) are not in the repo and not confirmed by Owner. No figure is stated in this report on purpose.

**Next checkpoint:** tag live 2026-10-24 → CQA verification per spec §6 → first weekly IBSL click count with `src="ibsl-bl"` in the 2026W43 report. If the tag is not live by 2026-10-24, CBO escalates to Owner per charter §5.

## 2. Placement optimisation candidates (this week)

Context: banners can depress organic CTR on the pages they sit on (charter §5: SEO specs must not assume zero-banner pages). Placement moves are **CBO-autonomous across already-monetised families**, but every move below is posted to the ledger for SEO to factor into CTR expectations before it ships. No move ships before we have a clean impression/click baseline (2026W43) except where flagged "may ship now."

Money-page input (SEO, week of 2026-10-17): top-click families are stock pages (share-price-target pages drove 280 clicks but are now 308-redirected), SEBI-registry entity pages (117c), IPO detail pages (27c / 25K imps).

| # | Family (by clicks) | Current | Candidate move | Rationale & guard |
|---|---|---|---|---|
| P1 | Stock detail pages | card (sidebar) | **Keep card; A/B strip on top-20 stock pages only** | Highest click family; card is least intrusive. Test whether strip lifts clicks without moving CTR below family baseline. May ship now, but log the move first and re-check family GSC CTR at 2 weeks. |
| P2 | IPO detail pages (27c / 25K imps) | wide (in-content) | **Keep wide; do not add strip** | 25K impressions on 27 clicks = ~0.11% — heavy-traffic, low-intent family. Two banners here risks compounding organic CTR cost. One banner, measured. |
| P3 | SEBI-registry entity pages (117c) | not currently a monetised family per the placement list | **No banner** — flag to Owner at monthly review whether to add | Registry readers are researchers, not account-openers; also these pages are close to the legal/SEBI surface where CBO must not touch copy. No action this week. |
| P4 | Home | strip | **Keep** | Largest single page-view family; strip is the least intrusive form. |
| P5 | News pages | wide | **Keep wide; review at 2026W43 baseline** | Daily-updated pages; banner fatigue possible. If news CTR is the weakest family at baseline, candidate for card. |
| P6 | Calculators hub | card | **Keep card** | High-intent (cost-sensitive) readers; card beside the tool is a natural position. |

Process rule for all moves: ship at most **one** placement change per weekly pipeline window, announce in ledger with the URL/family list, and CBO reads the GSC CTR delta for the affected family in the report two weeks later. If a family's GSC CTR drops >15% relative to its pre-move baseline and banner CTR doesn't compensate, pause the banner on that family (CBO-autonomous) and note the evidence in the ledger.

## 3. Sponsor pipeline — second sponsor

- Generic one-pager outline drafted (kept internal to CBO, no commitments made, no external distribution): (1) what BrokerLens is and why it ranks (independent broker/IPO/SEBI-registry reference, first-party data, no pay-to-rank), (2) the inventory (3 creatives × 6 page families, ~3,962 monetised pages, named slots), (3) the compliance story (sponsored tag, SEBI-registration disclosure, editorial policy, no cloaking — the same standard this spec enforces), (4) measurement (first-party, no-cookies, per-slot/per-page click and impression reporting), (5) commercial terms — **deliberately left blank; all numbers require Owner**.
- Market scan (who could pay: brokers, AMCs, DDMs) is a monthly activity per charter §5; no outreach this week.
- Dependency: **whether multi-sponsor is allowed on the same page is an Owner decision** (item C2). Until answered, the one-pager assumes one sponsor per page family.

## 4. Owner-confirmation list (blocking nothing except what's noted)

| # | Item | Why it needs Owner | Blocking? |
|---|---|---|---|
| C1 | **IBSL deal terms** — flat fee vs rev share, amount, term, renewal date. Terms are not in the repo and I will not invent them. Sponsor/deal config (rate, rev share, exclusivity) is Owner-only per §5. | Cannot report "monthly IBSL revenue" or set a revenue target for O3 without it. | Blocks revenue reporting only; not the tag (2026-10-24 proceeds regardless). |
| C2 | **Is a second sponsor allowed on the same page (or same family)?** Multi-sponsor layout, stacking, and rotation are a disclosed-commercial-model decision. | Determines sponsor-pipeline strategy and whether the "sponsor slot" abstraction becomes one slot or N per family. | Blocks pipeline commitments only. |
| C3 | **Approve the source-tag spec and the IBSL-side ask.** The spec (filed today) uses UTMs on the IBSL onboarding URL; one courtesy question to IBSL ("do your onboarding logs persist query params / can you confirm the referrer?") is requested — 2 nudges then escalate per §5. | External contact with the sponsor's commercial relationship is CBO-owned, but the deal-surface wording around the link change is CBO+Owner per §2/§5. | Not blocking CTO; tag deadline is 2026-10-24. |
| C4 | **Durable store for `/api/ad-event`.** Logs are short-lived; "zero untracked banner impressions" (a CBO KPI) is only as good as the log retention. A durable sink (e.g. KV write in the one place `api/ad-event.js` already designates) is a small CTO spec. | Infrastructure spend decision, and it affects the revenue-audit trail. | Not urgent; flag at next Owner digest. |

## 5. Ledger cross-references

- SPEC: `docs/business/2026-10-19-ibsl-source-tag-spec.md` — IBSL source tag, live by 2026-10-24.
- METRIC: day-1 baseline: 3 creatives live, ~3,962 monetised pages, first-party imp/click beacons live, 0 attributed onboardings (pre-tag).
- Next CBO output: 2026W43 weekly (Fri 2026-10-23) — includes tag status; if not live, ESCALATION is filed instead.
