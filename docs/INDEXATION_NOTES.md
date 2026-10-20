# Crawl and index notes (area: indexation)

Written 2026-10-19 from the Search Console inspection samples in `gsc_audit.json` and
`discover_inspect.json`. Everything below is either read from code and files or marked as
unverified. No Googlebot rendering was run; nothing was probed on the live site beyond 3
sequential HEAD or GET requests.

## 1. What the evidence says

| Sample | Result |
|---|---|
| 24 URLs in `gsc_audit.json` | 7 unknown to Google (`/ipo/`, `/ipo/upcoming/`, `/news/`, `/trade-costs/`, `/index/nifty-50/`, `/etf/niftybees/`, `/broker/groww/`), 1 soft 404 (`/broker/zerodha/`) |
| 25 of the 262 URLs in the brokers sitemap shard | 0 indexed: 16 discovered not indexed, 6 unknown, 2 soft 404 (`/broker/ventura/`, `/broker/stoxkart/`), 1 crawled not indexed |
| IPO and top-stock shards | 28 of 30 and 22 of 30 indexed |

The brokers shard is 262 URLs: 48 `/broker/<id>/` profiles, 191 `/compare/<a>-vs-<b>/` pairs and 23
`/brokers-by/` hubs. So "broker pages" are mostly compare pairs, and both profiles and pairs are
hybrid pages (static HTML that the single-page app then re-renders).

## 2. Root cause of the `/broker/zerodha/` soft 404

The static HTML is not thin. One GET of the live page returned HTTP 200, 22,638 bytes: H1, SEBI
registration table, how-to-verify steps, complaint route, trade-cost links, a 7-question FAQ and
FAQPage JSON-LD. The built file in `site/` is the same page.

The soft 404 is created after load, by `site/assets/js/app.js`:

1. `robots.txt` says `Disallow: /data/`.
2. The page loads `app.js`, whose router matches `/broker/<id>/` and calls `pages.broker(id)`.
3. `pages.broker()` fetches `/data/brokers/<id>.json`. A crawler that obeys robots.txt cannot fetch
   it, so the call fails and the `catch` returns `notFound("No broker profile for ...")`.
4. `render()` then did `app.innerHTML = html` on the first render, which replaced the real
   server-rendered `<main id="app">` content with `<h1>Not found</h1> ... That page does not exist.`,
   and rewrote `document.title` to "Not found: BrokerLens" and the meta description from that H1.
   Only the `data-static-only` block after `</main>` survived.

So Google's rendered snapshot says "Not found" on a URL that returns 200, which is the textbook
soft 404. A visitor whose browser can read `/data/` never sees it, which is why it went unnoticed.
The same path affects every hybrid route that loads JSON (`/broker/<id>/`, `/compare/<a>-vs-<b>/`,
`/brokers`, `/leaderboards`, `/registry`, `/news`, and so on): when the data fetch fails, the
renderer used to replace good static content with an error view.

Status of this explanation: strongly supported by the code path, robots.txt and the symptom, but
it was not reproduced in a Googlebot render. After deploy, confirm with URL Inspection, "Test live
URL", "View tested page", and check the rendered HTML shows the profile and not "Not found".

### Fix (site/assets/js/app.js)

On the first render of a page that arrived with its own H1 inside `#app`, a failed data load (an
exception, or the not-found view) now leaves the server-rendered content in place instead of
overwriting it. In-app navigation and unknown ids on pages with no server content behave as before.
`robots.txt` is unchanged: raw JSON stays out of the index, and the guard removes the need for
crawlers to read it. Alternative that was not taken: allow `/data/` and add an
`X-Robots-Tag: noindex` header on it. That also works but invites Googlebot to crawl about 50
broker JSON files and the large registry and search files.

## 3. Sitemap and discovery changes

| Change | Why |
|---|---|
| Core sitemap now lists `/calculators/`, `/stocks/`, `/funds-by/`, `/etfs/`, `/crypto/`, `/ipo/`, `/ipo/archive/`, `/news/` | The built pages declare these slash forms as canonical but the sitemap listed `/ipo`, `/news` and others without the slash. Both forms return 200 with the same body, so Google was handed a URL that is not the canonical. This explains why the inspected `/ipo/` and `/news/` were "unknown": the sitemap named `/ipo` and `/news`. |
| Top 40 ETFs by average daily volume added to the first-wave `stocks-top` shard | `/etf/` pages lived only in the `funds` shard (wave 2, not submitted), so `/etf/niftybees/` was never offered to Google. `/index/` pages were already in wave 1. |
| Footer links (plain `<a href>`): Upcoming IPOs, IPO subscription status, Trade cost calculator, Nifty 50 constituents, Nifty 50 ETF: NIFTYBEES | Added to the shared shell footer, the compact footer used by stock, ETF, fund, registry and hub pages, and the home footer (patched by the home prerender step because `site/index.html` is hand-maintained). |
| `/stocks/` gained a "Browse by index" chip list for all index pages | Nothing but a stock page's membership line linked to `/index/<slug>/`. |
| `/calculators/` gained a card linking `/trade-costs/` | `/trade-costs/` was linked only from the footer, `/brokers` and `/leaderboards`. |

Link coverage after the change (where each previously unknown URL is linked from):

| URL | Header or footer | Hub or list page |
|---|---|---|
| `/ipo/` | header nav on every page, footers | is the IPO hub |
| `/ipo/upcoming/` | footers (new) | `/ipo/` (existing) |
| `/news/` | header nav, footers | is the news hub |
| `/trade-costs/` | footers incl. home (new) | `/brokers`, `/leaderboards`, `/calculators/` (new) |
| `/index/nifty-50/` | footers incl. home (new) | `/stocks/` index chips (new), stock pages (existing) |
| `/etf/niftybees/` | footers incl. home (new) | `/etfs/` (existing) |
| `/broker/groww/` | home page body (4 links, existing) | `/brokers` (48 profile links), `/leaderboards`; no change needed |

`/broker/groww/` is already in the first-wave brokers shard and already linked from the home page
and `/brokers`. It is "unknown" because Google has not yet worked through the queue (sitemap
submitted 17 Oct), not because it is unlinked.

## 4. Branch pages

`broker_branch_engine.py` wrote 30 brokers x 58 cities = 1,740 city pages, each saying the broker
has a branch, desks or "authorised partner service desks" in that city. A city page is now
indexable only if the data on file places the broker there: a SEBI register entity matched to the
broker lists that city, the profile's register city is that city, or the curated head-office city
is that city. City text is mapped by exact name only (Bangalore to Bengaluru, New Delhi to Delhi);
Navi Mumbai and Thane never count as Mumbai.

Computed against the live build's `site/data/brokers/*.json` (read only):

| Page type | Total | Stay indexable | Flip to `noindex,follow` and leave the sitemap |
|---|---|---|---|
| Broker x city pages | 1,740 | 30 | 1,710 |
| Per-broker `/broker/<id>/branches/` hubs | 30 | 25 | 5 (hdfc-sky, prostocks, choice-broking, swastika-investmart, yes-securities: no city on file) |
| `/branches/city/<city>/` hubs | 58 | 5 | 53 (no tracked broker lists that city) |
| `/registry/city/<city>/` hubs | 58 | 27 | 31 (no register entity in that city) |

The 30 indexable city pages: 5paisa (Mumbai, Thane), Alice Blue (Bengaluru), Anand Rathi (Mumbai),
Angel One (Mumbai), Axis Direct (Mumbai), Dhan (Mumbai), Espresso (Mumbai), Fyers (Bengaluru,
Mumbai), Geojit (Kochi, Mumbai), Groww (Bengaluru), HDFC Securities (Mumbai), ICICI Direct
(Mumbai), Kotak Securities (Mumbai), Motilal Oswal (Mumbai), Nirmal Bang (Mumbai), Paytm Money
(Bengaluru, Delhi), Religare (Delhi), Samco (Mumbai), SBI Securities (Mumbai), Sharekhan (Mumbai),
SMC (Delhi), Tradejini (Bengaluru), Upstox (Mumbai), Ventura (Mumbai, Thane), Zerodha
(Bengaluru).

Known side effect: the pages that were ranking in positions 4 to 10 and are not verifiable now flip
to noindex: `/broker/paytm-money/branches/varanasi/` and `/vadodara/`,
`/broker/kotak-securities/branches/indore/`, `/broker/dhan/branches/rajkot/`. This is the intended
trade of the plan (doorway risk on a YMYL topic), but it will cost a handful of impressions.

Wording on pages that stay or go noindex:

- Verified pages keep their original title and H1. They say "Head office address on file" only when
  the curated street address names that city, otherwise "City listed on the SEBI register" or
  "Head office city on file" with "a street address in this city is not on file". Walk-in service is
  never claimed.
- Unverified pages get an honest title ("Dhan in Rajkot: Office Status, KYC and Demat Support"), no
  postal-address schema, "No Rajkot office or authorised-person location is on file", and the
  Operating Model, key-zones and over-the-counter demat wording removed.
- Invented figures on these pages were removed (turnaround "5 to 10 minutes", "15 to 21 working
  days", "within 7 days", "24-page booklet", `priceRange` in schema, "900+ branches" operating-model
  text). The `/branches/city/<city>/` hubs lost the "Best Stock Brokers in" title and the claim that
  named brokers operate branches in every city.
- Register city names were previously matched by raw text, so `/registry/city/bengaluru/` and
  `/registry/city/delhi/` missed entities filed as "Bangalore" and "New Delhi". They now match.

## 5. SIP permutation pages

37 amounts x 25 horizons = 925 scenario pages plus the hub. Indexable and in the sitemap: amounts
500, 1000, 2000, 3000, 5000, 10000, 15000, 20000, 25000, 50000 with 1, 3, 5, 10, 15, 20, 25, 30
years, so 80 pages. The other 845 stay live with `noindex,follow` and are not returned for the
sitemap. (The `sip-calc` shard is wave 2 and is not submitted yet, so today this changes
index eligibility, not the submitted count.)

## 6. Checklist for Search Console (you do this, after the deploy is live)

Daily "Request indexing" quota is small (roughly 10 to 12 URLs per property per day), so spread it
over a few days. Use the exact canonical URLs below. In the property `sc-domain:brokerlens.in`:

Day 1 (do these first)

1. Sitemaps: resubmit `https://www.brokerlens.in/sitemap.xml` (the shard contents changed).
2. URL Inspection, "Test live URL", "View tested page" for `https://www.brokerlens.in/broker/zerodha/`.
   Expect the profile in the rendered HTML, not "Not found". If it still shows "Not found", stop and
   report back; the explanation in section 2 would be wrong.
3. Request indexing: `https://www.brokerlens.in/broker/zerodha/`
4. Request indexing: `https://www.brokerlens.in/broker/groww/`
5. Request indexing: `https://www.brokerlens.in/ipo/`
6. Request indexing: `https://www.brokerlens.in/ipo/upcoming/`
7. Request indexing: `https://www.brokerlens.in/news/`
8. Request indexing: `https://www.brokerlens.in/trade-costs/`
9. Request indexing: `https://www.brokerlens.in/index/nifty-50/`
10. Request indexing: `https://www.brokerlens.in/etf/niftybees/`

Day 2

11. Page indexing report, "Soft 404", click "Validate fix" (the guard should clear
    `/broker/zerodha/`, `/broker/ventura/`, `/broker/stoxkart/`).
12. Request indexing: `https://www.brokerlens.in/broker/ventura/`
13. Request indexing: `https://www.brokerlens.in/broker/stoxkart/`
14. Request indexing: `https://www.brokerlens.in/broker/fyers/`
15. Request indexing: `https://www.brokerlens.in/broker/goodwill/`
16. Request indexing: `https://www.brokerlens.in/broker/angel-one/`
17. Request indexing: `https://www.brokerlens.in/broker/upstox/`
18. Request indexing: `https://www.brokerlens.in/ipo/subscription/`
19. Request indexing: `https://www.brokerlens.in/stocks/`
20. Request indexing: `https://www.brokerlens.in/etfs/`

Day 3 to 5 (re-check, no new requests)

21. Re-inspect the Day 1 URLs. "Discovered - currently not indexed" on a new domain is a queue state;
    it usually moves after the first crawl. Re-inspect, do not re-request.
22. Do not inspect or request the slash-less forms `/ipo` or `/news`: they are not the canonical.
23. Check the sample of branch pages that flipped to noindex (`/broker/dhan/branches/rajkot/`):
    inspection should report "Excluded by 'noindex' tag". That is the intended state.
24. Ignore the sitemap "indexed" counter (it has read 0 while pages are indexed); use per-URL
    inspection and the Pages report.

## 7. Not verified, and risks

- The soft-404 root cause is inferred from code, robots.txt and symptoms. No Googlebot render was
  run (the rules forbid active probing of the live site).
- The `app.js` guard was syntax-checked and its regex was tested against the real `notFound()`
  markup, but it was not run in a browser against a blocked `/data/` fetch.
- Branch indexability reads `site/data/brokers/<id>.json` at build time. If those files are missing
  (a partial build), every city page fails closed to noindex. Normal builds write them first.
- The curated `BROKER_BRANCH_METADATA` (helplines, demat IDs, street addresses) is hand-entered and
  was not audited here; the new verification uses SEBI register and master-file cities, not those
  addresses, and prints a street address only on the page of the city it names. Upstox shows a Delhi
  street address in the curated file but Mumbai as its head-office city in the master file; its
  Mumbai page therefore shows no street address.
- 191 of the 262 brokers-shard URLs are `/compare/<a>-vs-<b>/` pairs. They share the hydration
  hazard, so the guard should help them too, but whether Google chooses to index 191 near-identical
  pair pages is a separate question this change does not answer.
- Sitemap wave 1 grows by about 40 ETF URLs. The existing offline QA still passes its shard-name
  check because the ETFs ride in `stocks-top`.
