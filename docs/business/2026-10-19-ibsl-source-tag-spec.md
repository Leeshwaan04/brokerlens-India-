# SPEC — IBSL source tag (attribution join key) for the onboarding link

**From:** CBO · **To:** CTO (implementation) + CQA (verification)
**Date:** 2026-10-19 · **Charter ref:** O3, §5 (CBO first action)
**Deadline: tag live in production by 2026-10-24 (5 days). CTO ships; CQA verifies per §6 below.**

## 1. Problem

All three IBSL banner creatives link to `https://stocks-onboarding.indiabullssecurities.com/login` with no source tag. BrokerLens clicks are countable first-party (`/api/ad-event`), but IBSL onboardings cannot be attributed to BrokerLens, so O3 (IBSL-attributed onboarding conversions) is unmeasurable.

## 2. Recommended mechanism

**Standard UTM parameters appended to the onboarding URL, carried through the existing first-party beacon as a new `src` field on click events.**

- No cloaking, no redirect service, no subdomain, no deceptive link: the href the user sees in their browser is the full IBSL onboarding URL with query params. `rel="sponsored noopener"` and `target="_blank"` are unchanged.
- A subdomain/referrer token on the IBSL side is **not** used for day 1: it requires IBSL to provision something we do not control, and it is not needed for brokerlens-side attribution (charter §5: "all attribution must be done brokerlens-side"). It is listed as an Owner-confirmation / later-enhancement item only.

## 3. Exact link format

New canonical link (single source of truth, both copies of the constant):

```
https://stocks-onboarding.indiabullssecurities.com/login?utm_source=brokerlens&utm_medium=display&utm_campaign=ibsl_sponsored
```

- `utm_source=brokerlens` — identifies our site as the origin of the traffic (IBSL-side convention: they see the host in the referrer; the param is a redundant, robust marker for their backend/BI).
- `utm_medium=display` — static sponsored banner.
- `utm_campaign=ibsl_sponsored` — the one and only sponsor campaign.
- No `utm_term`. `utm_content` is NOT put in the href — the slot (strip/wide/card) varies per page and is already captured by the beacon's existing `slot` field.

**Files to change (CTO):**

1. `pipeline/publish.py:4357` — `IBSL_LINK = "https://stocks-onboarding.indiabullssecurities.com/login?utm_source=brokerlens&utm_medium=display&utm_campaign=ibsl_sponsored"`. No other change; `ibslBanner_html()` interpolates it.
2. `site/assets/js/pages.js:36` — same value (kept byte-identical to the Python constant; both feed `href`).
3. `tests/vapt.py:477` — exact-URL assertion; update the compared string to the new URL (same `rel`/`target` checks stay).
4. `tests/qa_e2e.py:2339` — substring assertion; update the literal href string.

After a pipeline run, all ~3,962 monetised pages and the client-side SPA render carry the tagged link. The Sponsored tag, `data-ad`/`data-slot`/`data-page-type`, and `data-ad-click` are unchanged.

## 4. Exact `site/assets/js/ad-track.js` changes

Add one field, `src`, to click events only (impressions unchanged). The value is a compact constant — NOT the full URL — to keep the payload small and stable.

In `send(type, el)`, inside the click path, read the link's own href and derive the marker:

```js
let src = '';
if (type === 'click') {
  try {
    const u = new URL(link.href);
    src = u.searchParams.get('utm_campaign') ? 'ibsl-bl' : '';
  } catch (e) { src = ''; }
}
```

and add to the payload object:

```js
src: src.slice(0, 32),
```

Notes for the implementer:

- The click handler already resolves `link = e.target.closest('[data-ad-click]')` before calling `send`; pass or re-resolve it so `link.href` is available (currently `send` re-derives the wrapper from the element — pass the link itself or its `href`).
- `src` is always one of `''` or `'ibsl-bl'` — no free text, no URL, no identifier. Worst-case payload grows by ~14 bytes; the 600-byte cap in `api/ad-event.js` is unaffected.
- Impositions: do not send the destination URL, UTM strings, or anything user-specific in the beacon. Compliance posture is unchanged (no cookie, no storage, no IP, no personal identifier).

## 5. Exact `api/ad-event.js` changes

Make `src` pass the strict whitelist and be logged, so the attribution join is possible from the log line:

1. `const SRCS = new Set(['', 'ibsl-bl']);`
2. In `clean(body)`: `const src = typeof body.src === 'string' ? body.src : '';` and add `if (!SRCS.has(src)) return null;`, then include `src` in the returned object.
3. The existing `console.log(JSON.stringify({ evt: 'ad', ts: ..., ...evt }))` then logs, e.g.:

```
{"evt":"ad","ts":"2026-10-22T09:12:03.000Z","t":"click","ad":"ibsl","slot":"card","pt":"stock","path":"/stock/itc/","ref":"","dev":"d","src":"ibsl-bl"}
```

**Join semantics (what the log gives us, stated explicitly):**

- `src="ibsl-bl"` on a `click` event proves the clicked href carried the IBSL onboarding URL with the campaign param — i.e., the click went *toward* the IBSL onboarding flow from this page, slot, and page family.
- `ref` (existing field, `document.referrer` host of the *landing* page that fired the beacon) captures inbound source to our site, not outbound destination — it already exists and stays as-is.
- Cross-check with IBSL: onboardings whose referrer host is `www.brokerlens.in` (or which carry `utm_source=brokerlens`) are BrokerLens-attributable. Our `click` counts with `src="ibsl-bl"` are the brokerlens-side numerator; IBSL's count is theirs. A monthly reconciliation compares the two. **Whether IBSL's backend persists query params through the onboarding flow is unverified — see §6 step 5 and the Owner-confirmation list.**

## 6. End-to-end verification procedure (CQA runs this after deploy)

1. **Static check:** `tests/vapt.py` ad-surface check and `tests/qa_e2e.py` assertion pass with the new URL (updated literals in §3.3/§3.4); full gate (597 QA + 21 VAPT + `node tests/ad_event_test.js`) green.
2. **Add to `tests/ad_event_test.js`:** (a) a click event with `"src":"ibsl-bl"` returns 204 and the logged line contains `"src":"ibsl-bl"`; (b) a click event with `"src":"other"` returns 400; (c) an impression without `src` still returns 204 (default `''`).
3. **Production click, one per slot:** on production, open one page of each slot in use (e.g. home = strip, a news page = wide, a stock page = card), click the banner link, and confirm:
   - the browser navigates (new tab) to exactly `https://stocks-onboarding.indiabullssecurities.com/login?utm_source=brokerlens&utm_medium=display&utm_campaign=ibsl_sponsored` — no intermediate redirect, no rewritten host;
   - Network panel shows a 204 to `/api/ad-event` whose request body contains `"t":"click"`, the correct `slot`, and `"src":"ibsl-bl"`.
4. **Log check:** the Vercel log line for that click contains `"src":"ibsl-bl"` with correct `slot`/`pt`/`path`.
5. **IBSL-side spot check (requires Owner contact — out of CQA's hands):** after the first week of tagged clicks, request from IBSL a count of onboarding sessions whose referrer is `www.brokerlens.in` or whose UTM source is `brokerlens`. If their backend drops query params, brokerlens-side `src="ibsl-bl"` click counts remain the standing measure, and the subdomain/referrer-token enhancement is re-proposed to Owner.
6. **Compliance re-scan:** Sponsored tag still present top-right on all banners; no close button; `rel="sponsored noopener"` intact; ad-surface VAPT check (standing CQA duty) passes.

Sign-off: CQA posts the result in the ledger; CBO marks O3 "measurement live" in the next weekly business report.

## 7. Constraints respected

- CBO wrote only this spec; all code changes are CTO commits under the normal QA gate.
- No deal terms, rates, or rev share are implied or assumed anywhere in this spec.
- No page content, sitemaps, or pipeline logic outside the two `IBSL_LINK` constants and the two tracking files change.
- Deadline 2026-10-24. If not live by then, CBO escalates to Owner per §5 escalation triggers.
