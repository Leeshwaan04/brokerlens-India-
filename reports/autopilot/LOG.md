# SEO autopilot log

One entry per run, newest last. Each change states its evidence, the effect it should have and a date to check it by; later runs record what actually happened.

## Baseline (before the autopilot)

- 28 days to 5 Nov 2026: 1,146 clicks, 99,588 impressions, average position 25.8 (GSC snapshot).
- Weekdays 4 to 6 Nov 2026: 34 to 41 clicks and 3,100 to 4,100 impressions a day. Best recent day: 28 Oct, 77 clicks, 7,951 impressions.
- Query-level data (28 days to 8 Nov): 60,162 impressions, 409 clicks, CTR 0.68%. Share-price-target queries carry most clicks; IPO queries carry about 15,000 impressions a month with almost no clicks.

## 2026-11-08 to 2026-11-09 (manual, before the autopilot)

- 09a33af: 296 BSE-only stock pages (/stocks/bse/, sitemap-stocks-bse.xml). Expect first impressions within 1 to 3 weeks. Check by 2026-11-29: URL-inspect 20 of them; count impressions on /stock/<slug>/ for slugs in data/manual/bse_only_equities.json.
- 68f1757, fa22d68: retired 87 dated template news pages carrying invented or wrong figures (308 to /news/). Expect no traffic loss (they drew about 12 impressions in 60 days).
- 8f1b502: no page carries noindex together with a canonical to another URL (481 secondary SEBI registrations, 2,548 IPO sub-pages). Expect the main registry pages to gain the roughly 4,300 monthly impressions the secondary pages drew. Check by 2026-11-30.
- ad6e53c: removed invented GMP quotes and price bands for IPOs never filed; hand-written IPO titles replaced by fact-based ones (e.g. "Laurus Labs IPO Date, Price Band and Listing Date"). Expect IPO CTR to rise from about 0.04% (15,136 impressions, 6 clicks in 60 days). Check by 2026-11-30.
- edd06cf: IPO pages no longer show a return since issue across splits and bonuses.

## 2026-11-09 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-09 vs 2026-11-02):
  - Clicks: 1168 (+155 vs prior week)
  - Impressions: 101225 (+5393 vs prior week)
  - Submitted indexable URLs: 7196

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.5, 704 impressions, 25 clicks, 3.55% CTR
  - "irb infra share price target 2030": pos 7.8, 543 impressions, 3 clicks, 0.55% CTR
  - "cupid share price target 2026": pos 6.8, 489 impressions, 2 clicks, 0.41% CTR
  - "econo broking": pos 10.2, 352 impressions, 0 clicks, 0% CTR
  - "fourdegreewater services private limited": pos 10.0, 336 impressions, 0 clicks, 0% CTR
  - "morepen lab share price target 2030": pos 7.5, 301 impressions, 3 clicks, 1.0% CTR
  - "praj industries share price target 2030": pos 8.8, 250 impressions, 4 clicks, 1.6% CTR
  - "comfort intech share price target 2030": pos 5.9, 236 impressions, 0 clicks, 0% CTR

- Synchronized 1 pages with verified search demand into sitemap-demand.xml:
  - /brokers/
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-11-23

## 2026-11-09 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-09 vs 2026-11-02):
  - Clicks: 1168 (+155 vs prior week)
  - Impressions: 101225 (+5393 vs prior week)
  - Submitted indexable URLs: 7196

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.5, 704 impressions, 25 clicks, 3.55% CTR
  - "irb infra share price target 2030": pos 7.8, 543 impressions, 3 clicks, 0.55% CTR
  - "cupid share price target 2026": pos 6.8, 489 impressions, 2 clicks, 0.41% CTR
  - "econo broking": pos 10.2, 352 impressions, 0 clicks, 0% CTR
  - "fourdegreewater services private limited": pos 10.0, 336 impressions, 0 clicks, 0% CTR
  - "morepen lab share price target 2030": pos 7.5, 301 impressions, 3 clicks, 1.0% CTR
  - "praj industries share price target 2030": pos 8.8, 250 impressions, 4 clicks, 1.6% CTR
  - "comfort intech share price target 2030": pos 5.9, 236 impressions, 0 clicks, 0% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-11-23

## 2026-11-10 (Claude: retire the broker x stock trade pages)

- Last 6 weekdays (4 to 9 Nov): 25 to 41 clicks and 2.5K to 4.1K impressions a day, against 46 to 83 clicks and 3.8K to 8.0K on 26 to 31 Oct. 55 of 57 clicks in the week to 10 Nov came from "share price target" queries (average position 8); every other query family sits at position 45 to 90.
- Evidence: URL Inspection on 10 Nov. Trade pages were last crawled 17 to 25 Oct (still "Submitted and indexed", so Google never saw the 4 Nov noindex); retired price-target URLs last crawled 7 to 16 Oct; /ipo/ hub and the Groww, Alice Blue, Samco and HDFC Securities profiles "Discovered - currently not indexed"; Zerodha profile "Soft 404". The build wrote 73,786 trade pages (30 brokers x 2,500 stocks) and every stock page linked four of them.
- Change: the build no longer writes /broker/<id>/trade/ pages; every such URL 308s to the broker's charges page (11 brokers), else its profile, else /trade-costs/ (vercel.json, one rule set generated from broker_charges_engine.cost_page_path). Stock, profile, charges, branch and stock-compare pages now link the charges calculators. The /trade-costs/ hub no longer labels an unverified schedule "Verified Tariff".
- Expected effect: Google's crawl moves to pages that can rank (IPO hub, broker profiles, charges pages, BSE-only stocks) and the 33.5K thin pages leave the index as they are recrawled; charges pages gain the "<broker> brokerage charges / calculator" queries the trade pages drew at position 80 or worse. Check by 2026-12-01: count of /broker/*/trade/ URLs with impressions (1,312 in 4 to 9 Nov), impressions on /broker/*/charges/ (37 in 90 days), and index status of /ipo/ and the broker profiles.
- Follow-up: temporary /sitemap-retired.xml (robots.txt only, never in sitemap.xml) lists the 3,932 trade URLs Search Console showed in results (10 Aug to 10 Nov), lastmod 2026-11-10, so Google recrawls them and sees the 308s sooner. It stops being written after 2026-12-31 (data/manual/retired_urls.json).

## 2026-11-10 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-10 vs 2026-11-03):
  - Clicks: 1176 (+122 vs prior week)
  - Impressions: 102452 (+4040 vs prior week)
  - Submitted indexable URLs: 7197

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.6, 715 impressions, 25 clicks, 3.5% CTR
  - "irb infra share price target 2030": pos 7.8, 550 impressions, 3 clicks, 0.55% CTR
  - "cupid share price target 2026": pos 6.8, 439 impressions, 2 clicks, 0.46% CTR
  - "econo broking": pos 10.1, 340 impressions, 0 clicks, 0% CTR
  - "fourdegreewater services private limited": pos 10.0, 328 impressions, 0 clicks, 0% CTR
  - "morepen lab share price target 2030": pos 7.5, 310 impressions, 3 clicks, 0.97% CTR
  - "praj industries share price target 2030": pos 8.8, 247 impressions, 4 clicks, 1.62% CTR
  - "comfort intech share price target 2030": pos 6.0, 241 impressions, 0 clicks, 0% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-11-24

## 2026-11-12 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-12 vs 2026-11-05):
  - Clicks: 1206 (+124 vs prior week)
  - Impressions: 106279 (+8335 vs prior week)
  - Submitted indexable URLs: 7197

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.6, 766 impressions, 26 clicks, 3.39% CTR
  - "irb infra share price target 2030": pos 8.1, 619 impressions, 3 clicks, 0.48% CTR
  - "cupid share price target 2026": pos 6.8, 375 impressions, 2 clicks, 0.53% CTR
  - "morepen lab share price target 2030": pos 7.7, 353 impressions, 3 clicks, 0.85% CTR
  - "econo broking": pos 10.1, 326 impressions, 0 clicks, 0% CTR
  - "fourdegreewater services private limited": pos 10.0, 311 impressions, 0 clicks, 0% CTR
  - "comfort intech share price target 2030": pos 6.0, 246 impressions, 0 clicks, 0% CTR
  - "praj industries share price target 2030": pos 8.7, 238 impressions, 4 clicks, 1.68% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-11-26

## 2026-11-13 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-13 vs 2026-11-06):
  - Clicks: 1203 (+122 vs prior week)
  - Impressions: 107599 (+12269 vs prior week)
  - Submitted indexable URLs: 7197

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.7, 797 impressions, 26 clicks, 3.26% CTR
  - "irb infra share price target 2030": pos 8.2, 661 impressions, 3 clicks, 0.45% CTR
  - "morepen lab share price target 2030": pos 7.7, 365 impressions, 3 clicks, 0.82% CTR
  - "cupid share price target 2026": pos 6.7, 339 impressions, 1 clicks, 0.29% CTR
  - "econo broking": pos 10.1, 310 impressions, 0 clicks, 0% CTR
  - "fourdegreewater services private limited": pos 10.0, 301 impressions, 0 clicks, 0% CTR
  - "comfort intech share price target 2030": pos 6.0, 253 impressions, 0 clicks, 0% CTR
  - "praj industries share price target 2030": pos 8.8, 229 impressions, 4 clicks, 1.75% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-11-27

## 2026-11-14 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-14 vs 2026-11-07):
  - Clicks: 1152 (+40 vs prior week)
  - Impressions: 105019 (+7747 vs prior week)
  - Submitted indexable URLs: 7197

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.8, 838 impressions, 26 clicks, 3.1% CTR
  - "irb infra share price target 2030": pos 8.2, 679 impressions, 3 clicks, 0.44% CTR
  - "morepen lab share price target 2030": pos 7.7, 373 impressions, 3 clicks, 0.8% CTR
  - "cupid share price target 2026": pos 6.7, 305 impressions, 0 clicks, 0% CTR
  - "fourdegreewater services private limited": pos 10.0, 286 impressions, 0 clicks, 0% CTR
  - "econo broking": pos 10.1, 274 impressions, 0 clicks, 0% CTR
  - "comfort intech share price target 2030": pos 6.0, 257 impressions, 0 clicks, 0% CTR
  - "praj industries share price target 2030": pos 8.7, 219 impressions, 4 clicks, 1.83% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-11-28

## 2026-11-15 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-15 vs 2026-11-08):
  - Clicks: 1146 (+0 vs prior week)
  - Impressions: 103977 (+4389 vs prior week)
  - Submitted indexable URLs: 7197

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.8, 886 impressions, 26 clicks, 2.93% CTR
  - "irb infra share price target 2030": pos 8.2, 679 impressions, 3 clicks, 0.44% CTR
  - "morepen lab share price target 2030": pos 7.7, 371 impressions, 3 clicks, 0.81% CTR
  - "cupid share price target 2026": pos 6.7, 279 impressions, 0 clicks, 0% CTR
  - "fourdegreewater services private limited": pos 9.9, 270 impressions, 0 clicks, 0% CTR
  - "comfort intech share price target 2030": pos 6.0, 254 impressions, 0 clicks, 0% CTR
  - "econo broking": pos 10.1, 241 impressions, 0 clicks, 0% CTR
  - "praj industries share price target 2030": pos 8.7, 208 impressions, 4 clicks, 1.92% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-11-29

## 2026-11-16 (Claude: revert two reintroduced fabrication violations)

- Found live on production: (1) pipeline/price_target_section.py (commit 0eb340e) added a
  server-rendered table labelling rows "<year> Target" with computed Rs figures at 10/15/20%
  CAGR per milestone year, directly contradicting this same page's own copy and the hard rule
  that a price-target page never asserts a number. (2) data/manual/ipo_gmp.json (commit 087ff2f,
  "activate live IPO GMP board") was hand-populated in a feature commit, not the automated
  scraper, with GMP/Kostak figures for 9 real IPOs under a generic "source" string
  ("Market survey (InvestorGain / Chittorgarh public quotes)") and a synthetic 3-day history.
  Nothing in the codebase fetches a GMP quote from any network source; this satisfied the letter
  of the existing "has a source field" check while remaining invented, reintroducing the pattern
  commit ad6e53c fixed once already (9 Nov).
- Change: removed the price-target table (kept the safe year-pick buttons and the facts/calculator
  above it); reverted ipo_gmp.json to {}; deleted the 10 GMP news articles the fabricated board had
  generated (9 per-IPO + the generic hub bulletin), each already or newly redirected to /ipo/gmp/ in
  vercel.json; regenerated site/_redirects from vercel.json (scripts/generate_cloudflare_config.py,
  which is only called from scripts/vercel-build.sh, not from `pipeline.run build` directly, so this
  needs to be run by hand after any vercel.json edit until that gap is fixed). Added regression
  checks: no <table> is ever server-rendered in the price-target section and no more than the 3
  factual data tiles' worth of "Rs n.nn" figures appear in it; the GMP file must be empty unless
  real fetch code exists, and no stored quote may cite a generic/unverifiable source phrase.
- Also found and flagged, not fixed here (needs the user's decision): the site migrated from Vercel
  to Cloudflare Workers this week (DNS already cut over) but CLOUDFLARE_API_TOKEN is not set as a
  GitHub secret, so ci.yml's deploy step has been silently skipping on every run; production has
  nonetheless been updated 10+ times via a local `wrangler deploy`, bypassing the QA/VAPT gate
  entirely, which is how both violations above reached production without the gate catching them.
- Evidence: direct inspection of the live site (both issues confirmed rendering with real company
  names and computed figures), git history of the affected files, and a local QA + VAPT run (see
  below). Expected effect: removes two live compliance violations; no traffic effect intended since
  these pages are not expected to currently drive meaningful clicks. Check by 2026-11-23 that no GMP
  or price-target figure has reappeared and that the Cloudflare deploy gate question has been
  resolved one way or the other.
- Verified: local build, full QA suite 1237/0 (up from 1236/1 before this fix), VAPT 77/0.

## 2026-11-16 (Claude: redirect orphaned comparison pages, part 2 of the in-depth review)

- Found by the in-depth review: commit 1c035c0 ("keep static asset count under 20k for
  Cloudflare Pages") cut fund_compare_engine's curated pairs per category from 20 to 4 and
  capped stock_compare_engine's sector peer groups at 5 members, then added an unconditional
  `rm -rf site/compare/stocks site/compare/mutual-funds` before every rebuild. ~1,640 of these
  pages had real Search Console impressions (reports/gsc/page_demand.json) and, once deleted
  with no redirect, 404 live. Confirmed with a direct curl.
- Change: added 1,200 redirects (vercel.json), each orphaned comparison page to its first
  symbol's own real page (/stock/<sym>/ or /fund/<slug>/, falling back to the family hub when
  neither symbol has one). All 1,154 orphaned stock pairs fit; only 46 of 486 orphaned fund
  pairs fit inside Cloudflare's 2,000-static-redirect cap (confirmed via developers.cloudflare.com:
  static assets always follow a matching redirect even over a real file at that path, so a
  careless rule can silently take down a page that still exists, and the limit is a hard 2,000
  static / 100 dynamic per _redirects file). 440 fund pairs remain 404 for now; every included
  redirect was checked against the current build to confirm it does not also point away from a
  page that still exists.
- Added two permanent QA guards (tests/qa_extra_indexation.py): the total static/dynamic count
  in site/_redirects must stay under Cloudflare's caps with headroom, and no redirect source may
  also be a currently-built page (the exact failure mode above). A third check fails if the
  unredirected orphan count ever grows past today's known 440-pair shortfall, so a future cut
  of this kind cannot repeat silently.
- Not done here (flagged, needs a decision): a durable, self-healing fix so future builds never
  orphan a real-demand comparison page again (right now this is a one-time backfill against
  today's page_demand.json snapshot); and whether the account is actually on Cloudflare's paid
  tier (100,000-file limit) rather than the free 20,000, which would remove the original
  pressure to cut these pages at all.
- Verified: local build, full QA suite 1201/0, VAPT 77/0.

## 2026-11-17 (Claude: fix a QA check that had blocked every deploy for 24 hours)

- Found: tests/qa_extra_indexation.py's new 16 Nov check ("unredirected orphaned comparison
  pages do not exceed... 440") used an exact day-of count as a hard ceiling. page_demand.json
  refreshes daily from live Search Console data and drifted to 442 by today, failing
  qa_e2e.py on every run since (ci.yml: 5 straight failures, 16 Nov 10:55 to 17 Nov 03:46;
  autopilot-content.yml likewise). Because ci.yml's Cloudflare deploy step sits inside the
  same job as the QA run, this blocked every deploy, not just a red check on GitHub: the
  live site has been serving whatever was deployed before 16 Nov while fresh data kept
  landing in git (daily-pipeline.yml and daily-ipo-gmp.yml both succeeded repeatedly, since
  neither runs qa_e2e.py). Confirmed live: the homepage's "today" market wrap article was
  still dated 16 Nov during 17 Nov trading hours.
- Change: replaced the exact 440 with a 700-page ceiling (headroom for ordinary day-to-day
  demand drift; still fails on a real regression of hundreds of pages). Also fixed, found in
  the same review pass: MapmyIndia's listed ticker was the wrong symbol (CEINFO, should be
  MAPMYINDIA) in two duplicated homepage/stocks-directory lists; the homepage's "Fastest
  growing" and "Most clients added" leaderboard cards rendered an empty, headerless table
  when no broker yet has 12 months of history, now an honest message, fixed in both the
  Python and JS renderers; ci.yml's header comment was corrected to describe the current
  Cloudflare deploy step and the missing-secret bypass instead of a removed Vercel job.
- Expected effect: deploys (and this site's own freshness signals to Google) resume once
  pushed. Not expected to move clicks or impressions on its own; it restores the pipeline
  that other changes need to reach users at all. Check by 2026-11-18 that ci.yml is green
  and that the live market wrap carries the correct day's date.
- Skipped, by design: linking SEBI registry pages for a broker's group entities (e.g.
  Zerodha Commodities) back to that broker's own profile. No reliable signal distinguishes
  a real group company from an unrelated firm that happens to share a brand word (e.g. an
  "Axis"-named entity having nothing to do with a broker called Axis), and asserting a
  corporate relationship without one is the same class of mistake as the fabricated GMP
  data fixed on 16 Nov. Left undone rather than guessed.
- Verified: local build, full QA suite 1201/0, VAPT 77/0.

## 2026-11-17 (Claude: redirect status codes, draft Worker cleanup, wrangler pin)

- scripts/generate_cloudflare_config.py emitted 301/302 for every redirect, the older HTTP
  semantics, when Cloudflare's _redirects supports 308/307 just as well
  (developers.cloudflare.com/workers/static-assets/redirects/) - the exact codes this
  project's own hard rule calls for ("add a 308") and the ones Vercel used for the same
  `permanent` flag before the migration. Fixed; all 1,989 lines in site/_redirects now use
  308 or 307. Added a permanent check so this can't silently regress.
- Checked the other open redirect-status item (a bare /registry or /compare 307s to its own
  trailing-slash form): confirmed via Cloudflare's docs this is a fixed platform behavior of
  `assets.html_handling` (every mode, including the default, uses 307 for this specific
  redirect) - nothing to fix, not a bug.
- cloudflare-worker/ (the undeployed draft edge router found in the earlier review) now
  carries a top-of-file warning and a README stating it has never been deployed, what to
  verify before it ever is, and fixed its wildcard CORS header to the same allowlist pattern
  api/ad-event.js already uses.
- Pinned `npx wrangler deploy` to wrangler@4.114.0 in ci.yml (was unpinned: a production
  deploy token handed to whatever npm resolves at run time, with no lockfile in the repo).
- Checked api/ad-event.js (a Vercel serverless function with no execution path on Cloudflare
  Workers Assets, found in the earlier review): confirmed no user-visible effect, since it's
  called via navigator.sendBeacon (fire-and-forget, browser never surfaces the failure) and
  only ever logged to short-lived function logs, never a durable store. Fixing it for real
  means adding an actual Worker script, a bigger step than this pass; left open.
- Verified: local build, full QA suite 1202/0, VAPT 77/0.

## 2026-11-17 (Claude: patch one newly-orphaned comparison page)

- Investigating a user question about striking-distance queries found
  /compare/stocks/tmcv-vs-tmpv/ (and several TMCV/TMPV sector-peer pairs) 404ing live despite
  ranking position 4 to 9 for "tmcv vs tmpv" style queries with 231 impressions/28d across
  the 4 phrasing variants and zero clicks - almost certainly the page intermittently 404ing
  is itself suppressing clicks. Root cause: TMCV and TMPV sit at positions 1 and 2 in their
  fixed SECTOR_PEER_GROUPS list (well inside CURATED_SECTOR_TOP_N=5), so they drop out only
  when their OWN equity-history data is briefly incomplete - a fresh build just now has them
  valid again, so production's current 404 is a day-to-day data snapshot issue, not a
  redirect gap; nothing to patch there, and it should self-correct once today's data deploys.
- Re-ran the full orphan computation against today's fresh page_demand.json and found exactly
  one real new gap: /compare/stocks/centralbk-vs-zeemedia/. Added a redirect to
  /stock/centralbk/. Fund-side gaps unchanged at 441 (still budget-limited; see 16 Nov entry).
- Verified: local build, full QA suite 1202/0, VAPT 77/0.

## 2026-11-17 (Claude: broker charges pages answer the exact phrases people search)

- Pulled full 28-day query data for every eligible broker's charges page (not a sample):
  Angel One, Groww, Upstox, Dhan and Fyers carry real volume (71 to 216 impressions/28d
  each) at position 37 to 91 with zero clicks across every one of them. The queries are
  mostly already answerable from data already on the page (brokerage, DP charge, AMC, STT
  and the other statutory rates); the page's existing FAQ wording just never used the short
  phrases people actually type ("<broker> charges", "intraday charges for <broker>", "stt
  charges in <broker>"), or the question people were really asking ("<broker> f&o charges"
  was answered as "does this calculator cover futures/options", never using "f&o charges").
- Added 5 new FAQ entries (pipeline/broker_charges_engine.py's _faqs()) matching that real
  phrasing exactly, and reworded the existing F&O entry's question. Every new answer reuses
  numbers already computed for the page (the brokerage rule, the statutory rate table) or
  states plainly that F&O/currency/commodity are not on file; no new figure of any kind. The
  DP-charge FAQ now also names the "CDSL or NSDL charge" phrasing some brokers' own pages
  use for the same fee. Applies to all 11 eligible brokers via the one shared template, not
  just the 5 with real query volume.
- Added regression checks (tests/qa_extra_brokerpages.py) that the new questions are present
  for every broker, that the STT/statutory answer states these charges are broker-independent,
  that the F&O answer never asserts a figure, and that the not-verified disclosure count
  didn't drop.
- Not done: brokerage charges pages don't exist at all for Kotak, HDFC Securities, Religare or
  Axis Direct (all show up in the same query data at position 60 to 90) because their fee
  schedule doesn't fit the calculator model unambiguously. That needs someone tracing each
  broker's current rate card by hand, not a template edit; left open.
- Verified: local build, full QA suite 1230/0 (plus 1275/0 with the live-probe checks earlier
  in this session), VAPT 77/0.

## 2026-11-17 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-17 vs 2026-11-10):
  - Clicks: 1031 (-145 vs prior week)
  - Impressions: 98064 (-4388 vs prior week)
  - Submitted indexable URLs: 6228

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.8, 925 impressions, 27 clicks, 2.92% CTR
  - "irb infra share price target 2030": pos 8.3, 682 impressions, 3 clicks, 0.44% CTR
  - "morepen lab share price target 2030": pos 7.7, 353 impressions, 2 clicks, 0.57% CTR
  - "cupid share price target 2026": pos 6.7, 234 impressions, 0 clicks, 0% CTR
  - "pc jeweller share price target 2027": pos 5.1, 204 impressions, 6 clicks, 2.94% CTR
  - "praj industries share price target 2030": pos 8.6, 197 impressions, 4 clicks, 2.03% CTR
  - "comfort intech share price target 2030": pos 5.9, 191 impressions, 0 clicks, 0% CTR
  - "birlasoft share price target 2030": pos 5.8, 186 impressions, 4 clicks, 2.15% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-12-01

## 2026-11-17 (Claude: research 4 missing broker charges pages, Kotak Securities, HDFC Securities, Religare, Axis Direct)

- Task: build a real /broker/<id>/charges/ page for these 4 brokers, currently excluded by
  broker_charges_engine.py's eligible_keys(), only if their current official rate card actually
  fits the calculator model (compute_charges(): a single flat fee, a single percentage of order
  value, or the lower of the two). Every figure had to trace to a source fetched from the
  broker's own official site, dated today, never an aggregator, never a guess. Result: none of
  the 4 shipped. All 4 stay excluded, each for a real, confirmed reason below, no code changed.
- Kotak Securities: the BROKER_RATES entry on file (delivery and intraday both Rs 0, tagline
  "zero brokerage for young investors") is the Trade Free Youth plan, which the engine already
  excludes on purpose (a restricted-plan signal). But that entry still renders live today on
  /trade-costs/, a real indexed hub page, as if it were Kotak's general schedule, which it is
  not. Kotak's actual current general plan ("Trade Free", account opening Rs 0, subscription Rs
  0) is confirmed via Kotak's own mandatory account-opening Tariff Sheet PDF
  (kotakneo.com/uploads/trad_free_charges_b8c1383fa9.pdf, fetched today): equity delivery 0.20%
  of order value with no rupee cap, equity intraday the lower of Rs 10 or 0.05% per executed
  order. The 0.20% no-cap delivery rule cannot be expressed in the model's current (flat, pct)
  encoding without a small general extension (a pure ad-valorem rule with no flat alternative,
  the same shape as 13 other already-withheld brokers, for example ICICI Direct 0.55% and HDFC
  Securities 0.50%). Did not add that extension or touch this entry this run: Kotak's DP charge
  has no single rupee figure in any official Kotak document reachable today (its own DP-charge
  FAQ PDF confirms the fee is flat per scrip but never states the amount), and its demat AMC is
  genuinely tiered (Rs 0 for BSDA holdings up to Rs 4 lakh, Rs 100 for BSDA Rs 4 to 10 lakh, Rs
  50 a month, about Rs 600 a year, for a non-BSDA account above Rs 1,000 month-end value, per
  kotakneo.com's own demat-AMC support page), so completing the entry would mean picking a
  number I cannot source. Fixing the brokerage fields alone would have also silently flipped
  Kotak into eligible_keys() (its two current withheld reasons both disappear once the real
  numbers replace the Youth-plan ones), which is a bigger, more consequential change than this
  task's verified sourcing could responsibly support in one pass. Flagging as a ready-to-resume
  follow-up with the exact sourced numbers above, not shipped here.
- HDFC Securities: no single current schedule exists to encode. hdfcsec.com/brokerage-plans
  lists six named plans (Optima, Maxima, Premia, Platina, Supreme, Elite) tied to HDFC Bank
  account segments, with no stated default for a new customer. The only rate figures found (via
  hdfc.bank.in's own Value Plan pages) quote delivery brokerage as paise per share, not a
  percentage of order value, a billing unit the model has no parameter for since it only takes
  rupee order values, never share quantity, plus a separate percentage-based minimum brokerage
  floor per plan (the opposite of the cap the model supports). Two of HDFC Bank's own pages for
  the same Premia plan disagree with each other on its intraday rate (0.02% on one page, 0.015%
  on another). No single, unambiguous, officially confirmed schedule exists to ship.
- Axis Direct: could not reach a general-public official tariff sheet. simplehai.axisdirect.in's
  own policies document (Policies And Procedures.pdf) confirms brokerage follows "the Tariff
  sheet" but does not embed it, and its pricing pages returned session-expired errors to an
  automated fetch (likely JavaScript-rendered). The one official rate document found
  (Axis Bank's "Freedom Plan for priority customers" PDF) is restricted to Axis Bank
  priority-banking customers, not a general schedule, and its link is now dead (301 to the
  site's sitemap). Third-party sources disagree with each other by more than 2x on both delivery
  (0.50% down to 0.20%) and intraday (0.05% down to 0.02%), consistent with Axis Direct also
  running multiple named plans like HDFC Securities, not one schedule. Nothing fetched today from
  axisdirect.in's own site confirms a current figure.
- Religare Broking: confirmed, from Religare's own plan document (religareonline.com, Elite -
  Equity, Currency & Commodity addendum) and its own Schedule of Charges for Depository Services
  (w.e.f. 20-09-2023), that brokerage is billed on a monthly turnover slab (7 slabs, A through G,
  0.50% delivery / 0.05% intraday in slab A for under Rs 5 lakh of that segment's turnover in the
  calendar month, down to 0.10% / 0.01% in slab G for over Rs 20 crore), resolved only after a
  full month of the customer's own trading, which the model has no way to represent since it
  prices one trade at a time with no concept of monthly cumulative volume; a new customer is
  billed at slab A for their first month. The same document shows AMC split across three demat
  schemes (Normal Rs 400 a year, Bandhan nil AMC against a refundable Rs 3,000 deposit, BIMA nil
  AMC against a one-time Rs 1,999 fee) plus a separate BSDA tier, and debit charges split by
  whether the client has given a POA or DDPI (Rs 12 versus Rs 25 per debit on the Normal scheme).
  No single number represents any of brokerage, AMC or the debit charge. The existing
  BROKER_RATES entry on file (delivery Rs 20 or 0.25%, intraday Rs 20 or 0.025%) does not match
  slab A, the new-customer default, or any other single slab in this official document cleanly,
  which suggests it was never sourced from Religare directly; left unchanged since there is no
  single correct number to replace it with, flagged for a future fix.
- Separately found, not fixed here (same root cause as the withheld-reasons the engine already
  tracks for icici-direct, motilal-oswal, sharekhan, sbi-securities, anand-rathi, geojit, smc,
  ventura, nirmal-bang, choice-broking, swastika-investmart, samco, yes-securities): all 13 of
  these are withheld for the identical reason as Kotak's delivery rule above, a pure percentage
  plan the model's (flat, pct) encoding cannot state without a wrong implied cap. A single,
  general rule-shape extension (ad valorem with no flat alternative) would be the fix for all of
  them, the same one Kotak needs; out of scope for this task, which was limited to the 4 named
  brokers, so not implemented. Flagging as the natural next step once a decision is made.
- No code changed, no page built, no commit made: every path that could have shipped a page
  required either inventing a number (Kotak's DP charge and AMC) or picking one figure out of a
  genuinely multi-valued official schedule (HDFC Securities' 6 plans, Axis Direct's conflicting
  sources, Religare's monthly slabs), both of which this task's sourcing bar rules out. QA and
  VAPT were not re-run since nothing in the repository changed.

## 2026-11-17 (follow-up on the Kotak and 13-broker findings above, commit 748d3e8)

- Part 1, shipped: Kotak Securities' entry in `BROKER_RATES` (pipeline/trade_cost_engine.py) held
  the restricted Trade Free Youth plan (Rs 0 delivery, Rs 0 intraday) as if it were Kotak's
  general schedule, live and indexed today on `/trade-costs/`. Verified Kotak's real general
  Trade Free Plan directly against kotakneo.com's own pricing and support pages today
  (kotaksecurities.com now redirects there): 0.20% of trade value, uncapped, for delivery; the
  lower of Rs 10 per order or 0.05% of the order for intraday (both pages also describe a Rs 0
  promo for the first 30 days from account opening; used the standing post-promo rate, the
  convention every other broker's entry here uses). Corrected both fields and the tagline (no
  longer says "for young investors"). dp_charge and demat_amc were deliberately left untouched
  and unverified: Kotak's real DP debit fee is 0.04% of value plus NSDL pass-through (around Rs
  20 minimum, not a flat figure) and its AMC is tiered by holding value and monthly debit count,
  neither representable as the single number the charges-page model requires. That is the real,
  separate reason `broker_charges_engine.py` must keep withholding a dedicated
  `/broker/kotak-securities/charges/` page even after this correction; it now shows exactly one
  accurate reason (delivery is a 0.2% uncapped percentage plan) instead of the two inaccurate
  ones it showed before (zero-on-both-segments, and the young-investors tagline marker).

- Part 2, a narrower and different finding than the "13 brokers share one fixable gap" framing
  above: that framing conflated two different problems. Re-verified Choice Broking (one of the
  13) against its own current pricing page, choiceindia.com/brokerage-charges, today: delivery is
  "Rs 20 or 0.20% of trade value, whichever is lower" and intraday is "Rs 20 or 0.02%, whichever
  is lower" - a genuine discount-broker cap, not an uncapped ad-valorem commission, even though
  0.20% sits above `CAP_RULE_MAX_PCT` (0.1%), the threshold the model uses to guess which shape a
  broker's percentage figure is. Choice's stored (flat, pct) was already correct; it was being
  wrongly withheld by a threshold that is a good heuristic, not a perfect one. Its dp_charge
  (21.24) did not match the real figure on that same page (Rs 10 + 18% GST = 11.80) and has been
  corrected; its demat_amc (236 = Rs 200 + 18% GST from year 2, year 1 free) was already right.
  Added an explicit `cap_verified_asof` field a BROKER_RATES entry can carry once its cap above
  the threshold has been read off the broker's own current page; `_withheld_reasons_for` (and the
  matching logic in trade_cost_engine.py's own fee calculator, `_rule_short` and `_rule_text`,
  which had the identical unconditional threshold check and would otherwise have disagreed with
  broker_charges_engine.py the moment Choice became eligible, caught immediately by the project's
  own compute_charges()-equals-calculate_trade_fees() regression test) now skip the cap-mismatch
  withholding only when that date is present. Choice Broking is now eligible: 12 brokers have a
  real charges page, up from 11. The other 12 brokers withheld for the same threshold reason
  (icici-direct, hdfc-securities, motilal-oswal, sharekhan, sbi-securities, axis-direct,
  anand-rathi, geojit, smc, ventura, nirmal-bang, swastika-investmart, samco, religare,
  yes-securities - 15, not 13; the 13 figure above undercounted) are untouched: none were checked
  against a real current source today, and their stored dp_charge/demat_amc show suspicious
  uniformity across unrelated brokers (four of them share the identical dp_charge of 17.70)
  consistent with templated placeholder data, not independently sourced figures - a reason to
  verify each one fully (brokerage AND dp_charge AND demat_amc) before trusting any of them, not
  just to re-run the cap check. Flagging this data-integrity pattern for whoever does that work
  next; three of these fifteen (hdfc-securities, axis-direct, religare) are already known from
  the entry above to be genuinely too complex for this model regardless of the cap question.

- Also fixed: the retired `/broker/choice-broking/trade/*` redirect in vercel.json, written once
  during the 10 Nov trade-page retirement and never regenerated, pointed at Choice's profile page
  (`/broker/choice/`) because that was its `cost_page_path()` result at the time. Now points at
  `/broker/choice/charges/`, matching the function's live output. This class of staleness (a
  one-time-written redirect going wrong the moment a broker's eligibility changes later) is not
  otherwise guarded against; the regression test here only checks the current-eligible-set-vs-
  redirects invariant, not that the redirects stay in sync if eligibility changes again.

- Did not implement a general-purpose "uncapped percentage" extension for broker_charges_engine.py
  beyond the cap_verified_asof mechanism: trade_cost_engine.py's own fee math already treats any
  pct > CAP_RULE_MAX_PCT as uncapped (fixed there on 2 Nov for the comparison-tool display), so
  the capability already exists for whichever of the 15 remaining brokers turns out to genuinely
  need it once verified; no broker shipped this pass needed it, so it was not ported into
  broker_charges_engine.py's withholding logic as a separate code path, to keep this change's
  surface area to what was actually verified today.

- Verification: QA 1230/1230 offline, 1275/1275 with live-probe checks (`--url`); VAPT 21/21
  offline, 77/77 with live-probe checks. Commit 748d3e8, rebased once onto a concurrent sitewide
  canonical fix (5fc7f51) with no conflicts after a full rebuild. Pushed to origin/main; CI run
  44143579912 triggered, watch in progress at the time of this entry.

- Check by 2026-11-24: `/broker/choice/charges/` should show real impressions; URL-inspect it if
  not. Also check that the corrected Kotak delivery/intraday figures on `/trade-costs/` match
  kotakneo.com's then-current page (broker fee schedules change without notice).
