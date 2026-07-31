# BrokerLens India — Indian stock broker marketplace

A statistics-first comparison site for Indian stock brokers, built the way
[mtf.trading](https://mtf.trading) is built: scheduled ingestion of free primary
data → precomputed JSON → a fast static front end. Two audiences, one dataset:

- **Investors** compare brokers on active clients, market share, SEBI complaint
  records, regulatory standing and real cost.
- **Brokers** find their own profile already live, built from regulator filings,
  and claim it to publish pricing, correct errors and receive enquiries. That is
  the revenue side: listings, sponsored placement and lead delivery.

Nothing here requires a paid data feed. No npm, no build step, stdlib-only
Python.

## Quick start

```bash
python3 -m pipeline.run seed      # clearly-labelled SAMPLE data, so the UI has something to render
python3 -m pipeline.run all       # fetch NSE + BSE + MCX + SEBI, then publish site/data/*
python3 server/devserver.py       # http://127.0.0.1:8000 (static + leads + live SSE stream)
```

`make serve-static` runs it without the stream; the front end then falls back to
polling and the site works on a plain CDN.

`pipeline.run all` exits non-zero if a source that should have returned rows
returned none, so cron can alert instead of quietly publishing a hollow site.

## Layout

```
config/
  sources.json          source registry: URL, cadence, licence note, last-verified date
  brokers_master.json   canonical broker identity map + listing tiers (the monetisation schema)
pipeline/
  common.py             stdlib HTTP with cookie jars, retry/backoff, disk cache, stale-cache fallback
  identity.py           broker-name resolution across NSE/BSE/MCX/SEBI naming
  metrics.py            derived metrics: share, growth, complaint rates, reliability, cost basket
  publish.py            emits site/data/*.json + sitemap.xml + feed.xml
  seed_sample.py        generates SAMPLE data, flagged as such end to end
  sources/{nse,bse,mcx,sebi}.py
server/
  devserver.py          static server (SPA fallback) + POST /api/leads + GET /api/stream (SSE)
  quotes.py             live-quote poller, snapshot diffing and SSE fan-out
site/                   the front end: no framework, no bundler, no external requests
data/                   raw snapshots, cache, manual inputs, captured leads
```

## What the data actually is

Verified reachable on 2026-07-30 from a non-India network egress.

| Dataset | Source | Status |
|---|---|---|
| Legal entity, SEBI registration no., exchange memberships, validity | SEBI recognised-intermediary register (`intmId=2`) | **Live** — 831 broking entities from 2,048 registration rows |
| Depository-participant licences | SEBI CDSL (`intmId=18`) + NSDL (`intmId=19`) registers | **Live** — 747 + 346 entities |
| Defaulter / expelled brokers | SEBI `BrokerAction.do` | **Live** — 445 records |
| Index levels, market breadth, market status | NSE `/api/allIndices`, `/api/marketStatus` | **Live** |
| FII/DII flows | NSE `/api/fiidiiTradeReact` | **Live** |
| Cash-market turnover | NSE bhavcopy archive | **Live** — 7 sessions |
| Delivery percentage | BSE scrip-wise gross archive | **Live** — 5 sessions |
| Corporate actions | BSE `/api/DefaultData/w` | **Live** |
| Live equity quotes | NSE `/api/live-analysis-*` | **Live** — 20 most-active + 10 gainers |
| Live BSE quotes | BSE `getScripHeaderData` | **Live** — 12 watchlist scrips |
| Live commodity futures | MCX `market-watch/GetMarketWatch` | **Live** — 8 traded products |
| Circulars naming a trading member | NSE `/api/circulars` | **Live** |
| **Per-broker active clients** | NSE member-wise UCC | **Not automated** — sample data in use |
| **Per-broker complaint counts** | Each broker's SEBI Annexure-B disclosure | **Not automated** — sample data in use |
| Brokerage / AMC charges | Broker-supplied | By design — only published once a broker claims their profile |

### The two gaps, stated plainly

The two headline *comparison* metrics — active clients per broker, and complaints
per broker — are currently **sample data**. They are real, free, published data;
they are simply not available at a machine-readable endpoint that could be
confirmed:

- **Active clients.** NSE publishes member-wise UCC active-client counts monthly,
  but not at a stable public JSON/CSV URL. Aggregator sites republish it; ingesting
  from them is off-limits (see licensing below). Options: pin the NSE file location,
  or license the data from NSE.
- **Complaints.** Every registered broker must publish monthly received/resolved/
  pending figures in SEBI's Annexure-B format, on its own website, often as a PDF.
  This needs a per-broker crawler with a PDF table parser — real work, but
  entirely doable, and the single highest-value thing to build next.

Until both land, `data/manual/*.json` carries `provenance: "sample"`, the
publisher propagates that flag, and the UI shows a persistent banner plus a
per-metric provenance dot. **No sample figure is ever presented as a fact.**
Delete `data/manual/*.json` and the fields go empty rather than fabricated.

Also worth knowing:

- SEBI's own `intmId=1` ("Stock Brokers") view returns *"No record(s) available"*
  for every parameter combination, and their exchange dropdown renders empty. The
  fault is upstream. The commodity-segment register (`intmId=2`) covers most real
  brokers, which is why it is the primary identity source.
- BSE exposes no open index-level endpoint — every documented variant 404s — so
  index levels come from NSE only.
- 36 of 48 tracked brokers have their headline legal entity matched to a SEBI
  registration; 46 of 48 are linked to at least one registration. A brand often
  spans several legal entities (Zerodha Broking Limited for equity, Zerodha
  Commodities Private Limited for commodities), and the profile shows all of them
  rather than collapsing them into one wrong name.

## Identity resolution

The hardest part. `pipeline/identity.py` resolves a raw exchange/regulator name
to a canonical broker id, cheapest strategy first: exact normalised alias →
containment → token-overlap with a **required margin over the runner-up**. An
ambiguous match is rejected rather than guessed, because silently attributing one
broker's complaints to another is far worse than a gap. Match method and score
are recorded on every profile.

## Monetisation

Built into the data model, not bolted on:

- `config/brokers_master.json` → `tiers` defines Listed (free) / Verified /
  Featured, with the price and entitlements for each.
- `listing.tier`, `listing.claimed` and `listing.sponsored_rank` on each broker
  drive promoted rows, homepage placement and the sponsor slot component.
- `/for-brokers` is the acquisition page: rate card, lead mechanics, and a claim
  form that routes by tier.
- `POST /api/leads` captures both sides — `investor_enquiry` (wants an account)
  and `broker_partner` (wants to list/advertise). Investor enquiries **require
  explicit consent** before contact details are shared with a broker; the server
  rejects them otherwise. Extra keys are dropped, not stored.

The growth loop worth noting: because profiles are generated from regulator data
and visibly flag what is unverified ("charges not verified — claim this profile"),
brokers have a standing reason to come to you. Corrections are free regardless of
whether a broker pays, and paid placement never reorders a factual ranking. That
constraint is the product — an investor who stops trusting the rankings is worth
nothing to the brokers you are selling to.

In production, replace `/api/leads` with a serverless function that writes to
your CRM; point `CONFIG.leadEndpoint` in `site/assets/js/store.js` at it.


## Live prices

The rolling header ticker shows instruments from whichever exchange is selected
in the dropdown, and it is fed in two tiers.

**Tier 1 — static file, always present.** `pipeline.run ticker` fetches quotes and
writes a ~7KB `site/data/ticker.json`. The browser paints from this immediately.
CDN-cacheable, survives an exchange outage, works with no backend at all.

**Tier 2 — pushed updates, if a stream server is running.** `server/quotes.py`
polls upstream on a background thread, diffs against an in-memory snapshot, and
pushes only instruments whose price moved to browsers over Server-Sent Events at
`/api/stream`. The client patches those prices in place (and flashes them) rather
than rebuilding the strip, so the scroll animation never jumps. If the stream is
absent or drops, `EventSource` reconnects and polling covers the gap.

The browser never talks to an exchange: all three refuse cross-origin requests,
gate on session cookies, sit behind Akamai bot walls, and the site's CSP is
`default-src 'self'`.

### Poll cadence is set by upstream payload size, not by taste

| Source | Payload | Interval | Why |
|---|---|---|---|
| NSE most-active | 7.5 KB | 3s | cheap, and it is what the market is actually trading |
| NSE gainers | 36 KB | 12s | |
| NSE pulse / indices | 113 KB | 20s | |
| BSE per-scrip | 1.1 KB | one scrip per tick, ~12s per cycle | **there is no bulk BSE quote endpoint** |
| MCX market watch | **1.27 MB** | 25s | the call returns the entire option chain (2,239 contracts) and there is no lighter endpoint |

That MCX number is the constraint worth remembering: polling it every 3s would
pull ~25 MB/min and get the IP blocked. Outside market hours every interval backs
off 20x. Watchlists live in `config/watchlist.json`.

### Deploying the stream

Tiers 1 and 2 have different hosting needs. A CDN cannot hold an open
`text/event-stream`, so:

- **Static-only** (Cloudflare Pages, Netlify, S3): deploy `site/`, run
  `pipeline.run ticker` on cron, done. Freshness 30-60s.
- **With the stream**: additionally run `server/devserver.py` on a small always-on
  host. If it sits on a different origin, widen `connect-src 'self'` in
  `site/_headers` to include it.

### The licensing reality

Publicly displaying **realtime** Indian exchange prices is licensed activity.
NSE, BSE and MCX license it through authorised-vendor agreements; free public
display is normally delayed or snapshot, which is what this does today, with the
"as of" timestamp always visible. Note also that broker APIs (Kite Connect,
Upstox, SmartAPI, Dhan) license data for *the authenticated user's own* use -
powering a public ticker with one would likely breach both the broker's terms and
the exchange data policy. Settle this before monetising, not after.

## Front end

No framework, no bundler, no external network requests — so a strict
`default-src 'self'` CSP holds. ES modules, custom routing over
`history.pushState`, and a ~7KB canvas chart module instead of a 160KB charting
library, since this site plots monthly series and categorical comparisons rather
than OHLC candles. Design tokens in `site/assets/css/tokens.css` drive both light
and dark themes, and the charts read their palette from those same tokens.

Routes: `/`, `/brokers`, `/broker/:id`, `/compare?b=a,b,c`, `/leaderboards`,
`/calculator`, `/registry`, `/for-brokers`, `/methodology`, `/sources`.

## Deploying

`site/` is a static directory — Cloudflare Pages, Netlify, S3+CloudFront all
work. Two requirements: rewrite unknown paths to `/index.html`, and give
`/data/*` a short shared cache. `site/_headers` and `site/_redirects` are
included for Cloudflare Pages and Netlify.

Suggested schedule:

```cron
* 9-16 * * 1-5    python3 -m pipeline.run ticker  # quotes only, ~4s — skip if running the SSE server
15 20 * * 1-5     python3 -m pipeline.run all     # nightly full refresh
30 2 3 * *        python3 -m pipeline.run all     # monthly, after SEBI/NSE monthly files land
```

## Licensing and compliance

Read this before charging anyone money.

- **NSE / BSE.** `robots.txt` permits crawling, but exchange data carries
  redistribution restrictions for commercial use. Get written clearance from NSE
  Data & Analytics (and BSE) before monetising derived datasets. This is the main
  legal risk in the whole plan and it is worth resolving early rather than after
  you have paying advertisers.
- **SEBI.** Regulator disclosures are public records. Attribution required, no
  redistribution licence needed.
- **Aggregators.** Never ingest from Chittorgarh, IPO Central or any comparison
  site. Their compiled tables are their work product. Primary sources only — a
  legal requirement and a trust requirement at once.
- **Not investment advice.** The site publishes facts and disclosed arithmetic.
  It names no "best broker" and gives no recommendation, which keeps it clear of
  SEBI's investment-adviser and research-analyst regimes. Keep it that way: the
  moment a page says "we recommend", the regulatory position changes.
- **Personal data.** Leads are personal data under the DPDP Act 2023. Consent is
  collected explicitly and stored with each record. Before launch you need a
  privacy notice, a retention period, and a deletion path.

## Verification status

Verified by running it:

- The pipeline completes end to end against live NSE, BSE and SEBI, exit 0.
- SEBI registry pagination, entity merging and card parsing produce 1,924
  registered entities; 445 defaulter records; correct INZ vs IN-DP registration
  separation.
- All ten routes serve 200 with SPA fallback; every asset and JSON payload loads.
- `/api/leads` accepts valid submissions and rejects missing consent, malformed
  email and unknown kinds; injected keys are dropped.
- Live quotes confirmed against all three exchanges: NSE 20 symbols, BSE 12
  scrips, MCX 8 traded futures (GOLD, SILVER, CRUDEOIL, NATURALGAS, COPPER, ZINC,
  ALUMINIUM, LEAD) with LTP, change, volume and open interest.
- `/api/stream` delivers a `retry` directive, a complete `snapshot` frame and
  15s heartbeats over a 20s capture.
- `make test-stream` asserts the push path: unchanged prices broadcast nothing, a
  moved price pushes exactly one instrument, the snapshot retains the new price,
  a new symbol counts as a change, and a subscriber that stops draining is
  dropped rather than blocking the poller.
- JS module graph cross-checked — every import resolves to a real export.

**Not yet verified:** the pages have not been rendered in a browser, so
JS runtime behaviour (chart drawing, filter and sort interactions, form wiring)
is unconfirmed. Load `http://127.0.0.1:8000` and check the console before
trusting the UI.
