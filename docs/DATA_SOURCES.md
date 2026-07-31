# Data sources — what was tried, what worked, what to do next

Field notes from probing NSE, BSE, MCX and SEBI on 2026-07-30. Recorded because
the next person to touch this will otherwise repeat the same dead ends.

All tests ran from a non-India network egress and **nothing turned out to be
geo-blocked**. Every 403 encountered was Akamai Bot Manager reacting to an
incomplete browser header set, not to location. If you hit a 403, add client
hints and Sec-Fetch headers before assuming you need an Indian IP.

---

## SEBI

### Recognised-intermediary register — WORKS, with a catch

The register page is a Struts shell. Rows arrive via XHR:

```
POST https://www.sebi.gov.in/sebiweb/ajax/other/getintmfpiinfo.jsp
Content-Type: application/x-www-form-urlencoded
Referer:      https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=<n>

nextValue=1&next=s&intmId=2&contPer=&name=&regNo=&regStatus=&email=&location=
&exchange=&affiliate=&alp=&language=2&model=&esgCategory=&doDirect=-1&intmIds=
```

Load the shell page first — the session cookie matters.

**Pagination semantics** (this cost the most time):

| next | doDirect | Result |
|---|---|---|
| `s` | `-1` | page 1 (a "search") |
| `n` | `0`-based page index | that page directly |
| `n` | `-1` | the page after `nextValue` |

`nextValue` is ignored when `doDirect >= 0`. Response embeds
`<input name='totalpage'>`, `nextDel` (page size, 25) and a
`"1 to 25 of 2048 records"` string — parse the total from there.

**Category IDs** (`intmId`), discovered by enumerating and reading `<title>`:

| id | Register | Rows |
|---|---|---|
| 1 | Stock Brokers | **returns "No record(s) available" for every parameter combination** |
| 2 | Stock Brokers, commodity derivative segment | 2,048 rows → 831 entities |
| 3 | Sub-Brokers | not pulled |
| 18 | Depository Participants — CDSL | 748 → 747 entities |
| 19 | Depository Participants — NSDL | 347 → 346 entities |

`intmId=1` also renders its own exchange dropdown empty, so the gap is upstream,
not a client bug. `intmId=2` is therefore the primary identity source.

**Row shape.** Not a `<table>`. Each record is a stack of
`.card-view > .title/.value` pairs, wrapped in `.fixed-table-body.card-table`.
AJAX fragments use **single-quoted** class attributes while server-rendered pages
use double quotes — a quote-agnostic regex is required (`common.card_records`).

Fields: Name, Trade Name, Registration No., E-mail, Telephone, Address, Validity,
Exchange Name.

**One row per (entity × exchange).** 2,048 rows collapse to 831 entities. Merge on
registration number and keep the exchange list — that list *is* the "registered on
NSE, BSE and MCX" fact worth publishing.

### Defaulter / expelled brokers — WORKS

`GET https://www.sebi.gov.in/sebiweb/broker/BrokerAction.do?doBroker=yes` —
1.2 MB of HTML, same `.card-view` structure, 445 records. No pagination.

### SCORES — NOT DONE

`https://scores.sebi.gov.in` responds (120 KB). Aggregate complaint counts per
entity were not extracted. Worth investigating as a cross-check on Annexure-B.

---

## NSE

`robots.txt` allows all crawling and names the sitemap. `/api/` paths need cookies
from an HTML page load first; the homepage fetch returns 403 to a plain client but
still sets usable cookies, so warm-up failure is not fatal.

**Working:**

| Endpoint | Notes |
|---|---|
| `/api/marketStatus` | segment-wise open/closed, NIFTY 50 level |
| `/api/allIndices` | ~113 KB, all indices + per-index advances/declines |
| `/api/fiidiiTradeReact` | daily institutional flows |
| `/api/circulars` | 135 recent circulars; fields are `sub`, `circCategory`, `circCompany`, `circDepartment`, `circDisplayNo`, `circFilelink` — **not** `subject` |
| `nsearchives.nseindia.com/content/equities/EQUITY_L.csv` | equity master, ungated |
| `nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_<yyyymmdd>_F_0000.csv.zip` | daily bhavcopy; columns `TtlTrfVal`, `TtlNbOfTxsExctd` |

**Dead ends:** `/api/equity-stockIndices?index=NIFTY%2050` → 404.
`/market-data/exchange-wise-active-clients`, `/regulations/member-ucc-active-clients`
→ 404. The sitemap has no member-wise statistics page. `/all-reports` is a 583 KB
JS-driven shell whose report catalogue is not in the HTML.

### The active-clients problem

Member-wise UCC active-client counts are the single most valuable metric for this
product and the one thing not automated. Leads worth trying, in order:

1. Inspect `/all-reports` in a real browser with devtools open and capture the
   XHR that populates its report catalogue — the file is very likely listed there
   under a name containing "client" or "UCC".
2. NSE's monthly *Market Pulse* PDF contains broker-wise active clients. Free, but
   needs a PDF table parser.
3. Ask NSE Data & Analytics directly. If the site is going commercial, this
   conversation has to happen anyway for redistribution rights.

Do **not** scrape Chittorgarh, IPO Central, Dhan's blog or any other aggregator.
Their compiled tables are their work product, and the whole trust proposition here
is primary sourcing.

---

## BSE

Requests need `Referer: https://www.bseindia.com/` **and** redirect-following, or
they fail with no response at all.

**Working:**

- `api.bseindia.com/BseIndiaAPI/api/DefaultData/w` — 85 KB. This is a
  **corporate-actions** feed (`scrip_code`, `short_name`, `Ex_date`, `Purpose`,
  `RD_Date`, `payment_date`), not indices.
- `www.bseindia.com/BSEDATA/gross/<yyyy>/SCBSEALL<ddmm>.zip` — pipe-delimited
  **scrip-wise delivery** data: `DATE|SCRIP CODE|DELIVERY QTY|DELIVERY VAL|DAY'S
  VOLUME|DAY'S TURNOVER|DELV. PER.`. Aggregated into a market-wide delivery
  percentage, which is a genuinely useful free sentiment indicator.

**Corrected assumption:** `SCBSEALL` is *not* member-wise turnover. BSE does not
appear to publish member-wise activity openly, so per-broker BSE presence comes
from the SEBI register (which segments a broker is registered for) rather than
from turnover files.

**Dead ends — all return an error page:** `SensexData/w`, `IndexMovement/w`,
`MktRtrnData/w`, `GetIndexData/w`, `MarketWatchTable/w`, `Indexhighlight/w`,
`MktCapitalisation/w`.

---

---

## MCX

Requests need the **full Chrome header set**, not just a User-Agent. Akamai Bot
Manager fronts the host and scores client hints plus Sec-Fetch metadata.

**Working** (verified 2026-07-30):

```
GET https://www.mcxindia.com/market-data/market-watch/GetMarketWatch?culture=en
     User-Agent, sec-ch-ua, sec-ch-ua-mobile, sec-ch-ua-platform,
     Accept-Language, Sec-Fetch-Dest/Mode/Site,
     Content-Type: application/json, X-Requested-With: XMLHttpRequest,
     Referer: https://www.mcxindia.com/market-data/market-watch
```

Returns 2,239 contracts: ~112 `FUTCOM` futures and ~2,126 `OPTFUT` options.
Row fields: `ProductCode` (the symbol — `Symbol` itself is null), `ExpiryDate`,
`Unit`, `Open/High/Low/LTP`, `PreviousClose`, `AbsoluteChange`, `PercentChange`,
`Volume`, `OpenInterest`, `LTTValue`. `Summary.AsOn` is an ASP.NET
`/Date(millis)/` string.

**Two traps, both of which cost time:**

1. **It is a GET, not a POST, and the path is not `/backpage.aspx/`.** MCX builds
   the URL in `/assets/customjs/data.js` as
   `location.origin + location.pathname + MethodName`, so the method hangs off the
   *page* path. `POST /backpage.aspx/GetMarketWatch` returns MCX's 404 **page**
   with a 200 status — which looks like a working endpoint until you parse it.
2. **A bare request gets 403 Access Denied.** With only a User-Agent, Akamai
   refuses everything including the plain HTML page. Adding client hints gets the
   page through; the JSON endpoint additionally wants `Content-Type:
   application/json` and `X-Requested-With`, matching MCX's own jQuery `$.ajax`.

Note the HTML page still 403s from `urllib` even when the JSON endpoint answers,
so a warm-up failure is expected and must not be treated as fatal.

**Earlier incorrect conclusion, recorded so nobody repeats it:** this was first
diagnosed as an India-only geo-block, because the 403 came from `AkamaiGHost` and
the whole host appeared unreachable. It is not geographic. It is header
fingerprinting plus the wrong endpoint path. DNS resolves normally to Akamai
edge IPs from anywhere.

---

## Live quotes — what powers the rolling header ticker

| Exchange | Call | Yield |
|---|---|---|
| NSE | `GET /api/live-analysis-most-active-securities?index=volume` + `?index=gainers` on `live-analysis-variations` | 20 most-active symbols, 10 NIFTY gainers |
| BSE | `GET api/getScripHeaderData/w?scripcode=<code>` — one request per scrip, no bulk variant | 12 watchlist scrips with LTP/Chg/PcChg and company name |
| MCX | `GET /market-data/market-watch/GetMarketWatch?culture=en` | 8 traded futures products, most-traded expiry each |

Watchlists live in `config/watchlist.json`. NSE needs none — the most-active list
is inherently current.

Refreshed by `python3 -m pipeline.run ticker` (~4s, writes a 6.8KB
`site/data/ticker.json`). The browser polls that file; it never calls an exchange
directly, because all three block cross-origin requests and the site runs a
`default-src 'self'` CSP.

---

## Next, in priority order

1. **Annexure-B complaint crawler.** Per-broker, monthly, HTML or PDF. Highest
   value per unit of work: it turns the reliability score from sample to real, and
   nobody else presents it next to the marketing copy.
2. **Pin the NSE active-clients file.** See leads above.
3. **SCORES aggregate counts** as an independent cross-check on Annexure-B.
4. **Sub-broker / authorised-person register** (`intmId=3`) — expands coverage
   further into the long tail.
5. **MCX options (`OPTFUT`) and index levels** — 2,126 option rows are already in
   the payload we fetch and are currently discarded.
