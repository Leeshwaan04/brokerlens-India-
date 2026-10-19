# BrokerLens India — Defect Ledger (standing tracker)

**Owner:** CQA (charter §4) · **Created:** 2026-10-19
**Rules:** Append-only. Each defect gets an ID, severity, exact reproduction, owner role, and status. CQA never fixes application code — it files; the owning role fixes; CQA verifies on the next gate. `DEFECT` = current bug; `REGRESSION` = previously-working behaviour broken by a change (include the breaking commit). `BLOCK` = page type quarantined from the pipeline until its checks pass (the only "lock" in the system).

**Severity scale:**
- **CRITICAL** — wrong/misleading financial data, broken compliance (missing SEBI disclosure / missing sponsored tag on a live banner), data leak. Escalates same-day.
- **HIGH** — page family broken, gate bypass possible, tracking silently dead on a monetised family.
- **MEDIUM** — placement/copy gap on a monetised surface, coverage hole that could mask a regression.
- **LOW** — cosmetic or coverage nit; no user or revenue impact today.

**Status values:** OPEN → IN-FIX (owner ack'd) → FIXED (gate-verified by CQA) → CLOSED. Aging >3 days on OPEN/IN-FIX is reported in the weekly QA report; a BLOCK >7 days escalates to Owner.

---

## Open defects

### DEFECT-001 — IBSL banner missing on the `/calculator/` calculator page (LOW) — OPEN
- **Found:** 2026-10-19, production spot check (first CQA cycle).
- **Reproduction:** `curl -sL https://brokerlens.in/calculator/` → 307 → `https://www.brokerlens.in/calculators/` (hub, has the wide IBSL banner, `data-page-type="calculator"`). The brokerage-cost-calculator page itself (`site/calculator/index.html`, served at `/calculator/` locally, 307-redirected away in production) contains **no** IBSL block: `grep -c 'data-ad="ibsl"' site/calculator/index.html` → 0.
- **Why it matters:** Charter placement list includes "calculator pages"; the gate (`tests/qa_e2e.py` placement map, line ~2383) only checks the `/calculators/` hub, so a calculator page without a banner passes the gate silently. Production 307 makes the user land on the hub anyway, so user-visible revenue impact is nil today — this is a coverage/placement gap, not a live hole.
- **Owner:** CTO (placement policy is CBO's per charter §5 — CBO may ratify hub-only placement, in which case CQA files the check update).
- **Resolution path:** Either (a) place the banner on the calculator page, or (b) CBO acks hub-only placement and CQA adds a check that documents/asserts the chosen placement for all calculator pages.
- **Fix-or-escalate SLA:** 72h from filing (per CQA→CTO interface).

---

## Regressions

None on file.

## BLOCKs (page-type quarantines)

None active.

## Closed / resolved

(None yet — ledger opened 2026-10-19.)

---

## Baseline snapshot at ledger opening (2026-10-19, HEAD `c2d45d6`)

| Gate | Result |
|---|---|
| `python3 tests/qa_e2e.py` | 597 pass / 0 fail / 1 skip |
| `python3 tests/vapt.py` | 21 checks passed, 0 findings |
| `node tests/ad_event_test.js` | 15 passed, 0 failed |

Summary: gate green, 1 LOW defect open, 0 regressions, 0 blocks.
