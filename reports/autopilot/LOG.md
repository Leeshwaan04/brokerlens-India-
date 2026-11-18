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

## 2026-11-17 (Claude: hub-page canonicals, broker-comparison duplicate content and dead peer links)

- Found: a sibling investigation into why all 196 broker-vs-broker /compare/ pages are
  unindexed traced it to 14 hub pages - /brokers, /compare, /leaderboards, /registry, /algo,
  /methodology, /about, /editorial-policy, /contact, /privacy-policy, /terms-of-service,
  /sources, /calculator, /cms - each writing to a directory's index.html (served with a
  trailing slash) while declaring their own canonical, og:url and JSON-LD url, and the core
  sitemap listing them, as the bare path. Cloudflare Workers Assets always 307s a bare
  directory path to its slash form (confirmed via curl -I, unconfigurable platform behavior),
  so every one of these canonicals pointed at a URL that is now only a redirect, never
  content. URL Inspection API, checked directly on 5 of them, came back "URL is unknown to
  Google" for all 5. The existing QA check that compares a core-sitemap entry's canonical
  against the page's own never caught this because it silently skips any entry that doesn't
  already end in "/" rather than flagging it as wrong.
- Change: fixed all 15 affected canonical/og:url/JSON-LD-url assignments in pipeline/publish.py
  (14 pages plus the per-market /coming-soon/<market> page) to include the trailing slash, fixed
  the 3 /editorial-policy references inside other pages' Organization JSON-LD the same way, and
  fixed the core sitemap's own url list (core_urls) to match. This is believed to be the single
  highest-leverage indexation fix found this session.
- Also found and fixed, while tracing the broker-comparison family's only entry point:
  (a) _write_compare_pages() deduped pairs by the ordered (id1, id2) tuple, but ranked_ids is
  sorted by CURRENT client count, so a rank crossover between builds (Groww overtaking Zerodha)
  regenerated an already-shipped pair in the opposite order as a second, live, duplicate-content
  URL - confirmed live in production via curl: both /compare/zerodha-vs-groww/ and
  /compare/groww-vs-zerodha/ were 200, and both of the zerodha/angel-one pair too. Fixed with a
  new shared helper, _comparison_pairs_for(), that dedups on the unordered broker set instead;
  COMPARISON_PAIRS keeps the slug order it names, the grid only picks the order for pairs it
  never names. _write_compare_pages() now also prunes any pair directory no longer in the
  current set, so a future drop stops being served instead of lingering forever. The two
  already-live duplicates got a 308 in vercel.json to their survivor, per the
  never-retire-without-a-redirect rule.
  (b) Broker profile pages' "Compare with competitors" chips linked to
  /compare/<this>-vs-<nearest-by-client-count>/ with no check that pair was ever actually
  built; 27 of 48 brokers now show 0 such links (down from up to 5, mostly broken) because
  _write_compare_pages()'s grid only pairs the top 20 brokers by client count. Fixed by
  threading _comparison_pairs_for() into _peers(), which now only returns peers with a real
  built pair and carries that pair's actual slug.
- Added 5 new regression checks to tests/qa_extra_indexation.py: every literal core-sitemap
  path ends in "/"; no hub-page canonical is still built from a bare SITE_URL + path; no two
  live /compare/ pages serve the same broker pair in opposite order; every "Compare with
  competitors" link resolves to a pair that was actually built; and a synthetic unit test that
  forces a rank-crossover by hand and proves _comparison_pairs_for() suppresses the resulting
  duplicate independent of today's live broker ranking.
- Not done here (deliberately, flagged for its own pass): the ~173 internal <a href> call sites
  across 14 files that still link to the bare form of these hub paths - a 307 to the now-correct
  canonical is not itself a ranking problem, so this is lower value and higher review cost than
  bundling it into this fix. Also not done: widening "Compare with competitors" coverage past
  the top-20-by-client-count grid for the 27 brokers that now show none - a separate, larger
  decision about how much of the full broker roster the comparison engine should cover.
- Expected effect: the 14 hub pages (several with real historical impressions already, e.g.
  /compare and /brokers at their old no-slash URLs) become indexable at their real URL for the
  first time since the Cloudflare migration; no more live duplicate-content pairs; no more dead
  internal links from broker pages. Check by 2026-11-24 that the URL Inspection API shows these
  pages as indexed (a recrawl takes time) and that GSC starts attributing impressions to the
  slash-form URLs instead of the dead bare ones.
- Verified: local build, full QA suite 1279/0 including --url live-probe checks against a local
  devserver (up from 1234/0 offline before the 5 new checks), VAPT 77/0 including --url probes.
  Rebased cleanly onto a concurrently-shipped fix (cb59eda, the Zerodha broker-charges-data fix)
  with no conflict in pipeline/publish.py; only the build-output site/brokers/index.html
  conflicted (both commits touch its single minified line), resolved by rebuilding fresh after
  the rebase rather than hand-merging HTML, then re-verified QA/VAPT green before pushing.
  CI run 44142658014: completed success.

## 2026-11-17 (Claude: audit of the suspicious shared dp_charge flagged above - no code change)

- Followed up on the entry above's flag ("four of them share the identical dp_charge of 17.70").
  Enumerated every BROKER_RATES entry directly (python3, not grep, to avoid misaligning fields):
  the real count is seven, not four - sbi-securities, anand-rathi, geojit, smc and ventura
  (withheld) plus, critically, alice-blue and tradejini, which are both ELIGIBLE right now and
  have a real, live, indexed /broker/alice-blue/charges/ and /broker/tradejini/charges/ page
  today. Every other broker in BROKER_RATES has a distinct dp_charge that matches the pattern
  "a broker-specific flat rupee figure times 1.18 GST" (e.g. Zerodha 15.34 = Rs13, Dhan 14.75 =
  Rs12.5, Upstox 21.83 = Rs18.5) with a comment naming the base figure for most of them; these
  seven have no such comment and all resolve to the same Rs15 base, spanning brokers with
  otherwise clearly distinct, specific brokerage plans (alice-blue's real "Freedom 15 Plan," Rs0
  delivery; tradejini's "CubePlus platform," Rs20 flat) and demat_amc values that are NOT
  uniform (0, 0, 354, 400, 400, 450, 500) - so the brokerage and AMC fields for these seven look
  independently researched, while dp_charge specifically does not. git blame traces all seven to
  one line each inside the same single bulk commit, 7d0ac217 (2026-10-03, "feat: add Google
  E-E-A-T compliance, IPO suites, comparison engines, and QA/VAPT hardening"), with no source
  cited in the commit message or in any code comment.
- Checked the critical question directly: whether either live page (alice-blue, tradejini)
  presents this figure as verified. It does not. render_charges_page() and _faqs() in
  pipeline/broker_charges_engine.py state, repeatedly and unconditionally for every broker
  (STATUS_SHORT, the FAQ "Are these charges verified against the broker's own tariff?", the
  worked-example disclaimer, the schedule-table disclaimer): "indicative schedule held in the
  BrokerLens model... not verified against the broker's own rate card, and the date it was
  checked is not on file." So this is a real accuracy gap (the number itself may be wrong for
  one or more of these seven brokers), but it is not a fabrication-while-claiming-true violation
  like the GMP and price-target cases reverted this session (51aa585) and flagged separately
  (the uncommitted local pipeline/publish.py and pipeline/bse_only.py reinsertion) - the page
  already discloses, honestly and specifically, that this exact field has not been verified.
  That distinction is why nothing ships here: there is no live false claim to correct, and
  replacing 17.70 with a "corrected" number without actually sourcing one per broker would just
  be a different unverified guess.
- Also checked demat_amc for a similar pattern and did not find one worth flagging the same way:
  0 repeats across prostocks, 5paisa, dhan, fyers, groww, alice-blue, ventura, espresso, upstox
  and hdfc-sky, but "zero AMC" is a real, specifically-advertised feature for several of these in
  their own stored tagline text (Dhan "zero AMC," Fyers implied free, Ventura "lifetime zero AMC
  demat account"), not an arbitrary coincidence the way dp_charge's shared non-zero figure is.
  400 repeats across geojit, smc, samco, sharekhan and motilal-oswal, which is a plausible, common
  real full-service-broker AMC figure in India; weaker signal than the dp_charge cluster and not
  independently corroborated enough here to flag as more than a lower-priority thing to check
  during the same future re-verification pass.
- Recommendation, not an action: before `eligible_keys()` is widened any further (the 15
  brokers withheld by the cap-rule threshold, per the entry above), and ideally sooner given
  alice-blue and tradejini are live today, every BROKER_RATES entry's dp_charge and demat_amc -
  not just brokerage, which has had the most attention this session - should be individually
  re-verified against that broker's own current published tariff, with a comment citing the
  source the way most other entries already do. Treat the seven brokers named here as the
  priority list for that pass, alice-blue and tradejini first since they are the two actually
  live.
- No code changed. Built in an isolated worktree off origin/main, full QA and VAPT suites
  re-run to confirm the baseline is unaffected by this documentation-only entry before pushing.

## 2026-11-18 (Claude: re-verify the seven dp_charge=17.70 brokers flagged above, starting with the two live ones)

Followed up on the priority list from the audit above: re-verify dp_charge and demat_amc for
alice-blue, tradejini, sbi-securities, anand-rathi, geojit, smc and ventura against each
broker's own current official source, alice-blue and tradejini first since they are the two
live today.

- **alice-blue (live, /broker/alice-blue/charges/): confirmed correct, no number change.**
  Fetched aliceblueonline.com/pricing directly (2026-11-18): "Rs 15 + GST per scrip applies to
  all stock sale transactions" and "No yearly maintenance charges on your demat account... Rs 0
  as long as your account stays under this plan." Rs 15 x 1.18 GST = Rs 17.70, exactly the
  stored figure. demat_amc=0 also confirmed. Added sourcing comments to both fields in
  pipeline/trade_cost_engine.py; no figure changed.
- **tradejini (live, /broker/tradejini/charges/): dp_charge was wrong, corrected.** Fetched
  tradejini.com/charges directly (2026-11-18): "DP transaction charge of Rs 12.50 + GST per
  ISIN... will be charged for all on-market debit transactions" and "AMC (Annual maintenance
  charges) Rs 300 + GST per year." Rs 12.50 x 1.18 = Rs 14.75 (not Rs 17.70, the uncited
  bulk-commit figure); corrected in pipeline/trade_cost_engine.py, confirmed rendering on the
  rebuilt page (9 occurrences of 14.75, zero of 17.70). demat_amc=354 (Rs 300 x 1.18) was
  already correct against the same source; added a sourcing comment, no change.
- **ventura (withheld, no live page yet): dp_charge was wrong, corrected anyway** since it is
  dormant BROKER_RATES data that will matter the moment the cap-rule unlock work from the
  entries above reaches it, and getting it right now is cheaper than re-checking it later.
  Fetched venturasecurities.com/pricing/ directly (2026-11-18): "For stocks sold, Ventura
  applies DP charges of Rs 20 plus GST per scrip," with the site's own GST section confirming
  18%: Rs 20 x 1.18 = Rs 23.60 (not Rs 17.70). demat_amc=0 confirmed correct against the same
  page ("AMC charges at zero"). Ventura stays withheld for the unrelated, separate cap-rule
  reason already on file; this only fixes the one field so it is not wrong whenever that
  changes.
- **sbi-securities, anand-rathi, geojit, smc: left unverified, not fixed, not guessed.** All
  four are withheld already (no live page), so there is no urgency to force a number, and none
  of the four had a source clean enough to trust over the existing unverified figure:
  - sbi-securities: no current official tariff page found stating a standard DP charge; AMC
    sources ranged from Rs 300 to Rs 750 depending on plan and year, including the broker's own
    plan PDF, which gives per-plan AMC schedules (e.g. OIOP 3K: free year 1, Rs 500 year 2)
    rather than one flat figure the model's single demat_amc field can represent.
  - anand-rathi: official site confirms free account opening and a free first-year AMC, but no
    official per-debit DP figure was found, and third-party AMC figures disagreed (Rs 450+GST
    per year vs. a Rs 999 one-time lifetime-free option vs. a separate Rs 500 figure on one FAQ
    page).
  - geojit: has an official support site with current AMC/transaction-charge pages, but the
    figures differ by account type (Basic Services Demat Account vs. Regular Services Demat
    Account) and by holding-value band, so there is no one "the DP charge" to drop into a flat
    field without checking which plan is the default being modeled here - a bigger, separate
    piece of work, not a quick fix.
  - smc: the only clean official source found, CDSL's own DP registry listing (dp_id 19100,
    Rs 300/year individual AMC, Rs 15/ISIN on-market debit, GST extra), is dated 20 May 2020 on
    its own page - nearly 6 years stale, not trustworthy as a 2026-11-18 "current" figure, so it
    was not used to change anything.
  These four stay on the priority list for the broader re-verification pass the audit above
  recommended.
- demat_amc repeats beyond tradejini (already confirmed above): not independently re-verified
  this pass beyond what the audit above already assessed; still logged there as lower priority.
- Verification: `python3 tests/qa_e2e.py` 1235/1235 offline, 1280/1280 with `--url` live-probe
  checks against a local devserver; `python3 tests/vapt.py --url ...` 77/77, 0 findings. Built
  in an isolated worktree off origin/main (data/cache, data/raw symlinked), rebuilt after
  discarding incidental daily-fetch churn (crypto prices, news, IPO index, sitemaps,
  bse_only_equities.json) so the shipped diff is exactly the three sourcing comments and two
  corrected figures in pipeline/trade_cost_engine.py, nothing else.

## 2026-11-18 (Claude: checked for the broker-charges CTR-wording pattern on stock, news, IPO
and fund-comparison pages; shipped nothing)

- Directive: the broker-charges FAQ fix (commit 73b8302) found real pages with real impressions,
  a reasonable position, and zero clicks, fixable by rewording the title/meta/FAQ to match the
  exact phrase people searched, with no new data. Checked whether the same pattern holds on four
  other page families, to act on it if real and ship nothing where it is not. Pulled real
  page+query level data from the GSC API (dimensions page, query, filtered by URL pattern, 28-day
  window) for each family rather than assuming.
- **Stock pages (`pipeline/publish.py`'s `_write_stock_pages`, `pipeline/bse_only.py`'s parallel
  writer): no fix shipped.** An initial filter (impressions >= 15, position 5-25, 0 clicks) found
  220 candidates, but 207 of them are not a wording problem at all: they are GSC performance
  still attached to the identity of `/stock/<sym>/share-price-target-<year>/` URLs that are now
  pure 308 redirects to `/stock/<sym>/` with no content of their own to reword (confirmed live:
  curl on a sample of 4 - cupid, mrf, sarveshwar, kalyankjil - all returned 308). This is the
  already-known "retired price-target URLs carry most clicks" GSC measurement artifact, not a
  live page issue. Of the 13 remaining non-"target" candidates, most are the same retired-URL
  artifact under a different query; the only genuinely live, well-positioned page in the entire
  set is `/stock/justdial/` (position ~10.7-11.2, 972 impressions/28d combined across "justdial
  stock" and "justdial stock price", 0 clicks) - a real, verifiable title/intent mismatch (the
  page's title leads with "Share Price Target 2026-2050, What-If Calculator", not plain stock/
  price framing). Checked whether this generalizes: pulled all ~3,341 generic "<name> stock" /
  "<name> share price" query rows across every stock page. 3,340 of 3,341 get 0 clicks, but
  because they sit at position 69-92 (not 5-25) - page 7-10, where 0 clicks is normal, not a
  wording problem, and not something a title rewrite fixes (BrokerLens is a broker-comparison
  site competing against Moneycontrol/NSE/Google Finance for generic "X share price," a
  structural ranking ceiling, not a wording gap). Justdial is a genuine, verified outlier, not
  evidence of a systemic pattern. Did not ship a universal title-template change on an n=1
  sample, and did not hardcode a per-symbol exception, since this project's own convention
  (the comparison-pair dedup fix, 2026-11-17) is to prefer a general rule over a named special
  case - there is no general rule to extract from one data point. Separately confirmed the
  current title (`pipeline/price_target_section.py`'s `stock_title()`) was already deliberately
  tuned against real GSC query-share data for the dominant "share price target <year>" intent
  (see its own docstring), so this is not an untouched or neglected page.
- **News pages: no fix shipped.** Only 10 distinct query rows total across the entire family in
  28 days, 1-5 impressions each, mostly position 50-98. Too small a sample to show any real
  pattern; nothing to act on.
- **IPO pages: no fix shipped.** 4 candidates, 12-47 impressions each. Checked the clearest one,
  "tango ipo listing date" on `/ipo/systango/`: the title already reads "Systango Technologies
  IPO Date, Price Band and Listing Date" - it already names "Listing Date" explicitly, so there
  is no wording gap to fix; the query's "tango" vs "Systango" mismatch is a user abbreviation,
  not something page wording can address. The other three (UTI AMC "grey market premium",
  "theikio", "edelats ipo") are each a single fuzzy/abbreviated query at 12-47 impressions,
  within normal zero-click variance at position 8-10 for that volume - and the UTI AMC case
  specifically names grey market premium, which this project's hard rule forbids asserting
  without a real cited source, so it was correctly left alone either way.
- **Fund-comparison pages: no fix shipped.** 5 candidates, 10-34 impressions each, position
  9-19. Too thin (2-3 real page instances, modest volume) to distinguish a real wording gap from
  normal variance, and one query ("jio blackrock vs sbi mutual fund which is better") carries
  the same YMYL "which is better" framing risk flagged in yesterday's broker-comparison-page
  investigation - not something to touch without stronger evidence either way.
- Net conclusion: the broker-charges pattern (systemic, verifiable, low-risk wording fix) does
  not currently exist on any of these four families at the scale or confidence that justified
  shipping it on broker charges. No code changed, no page content changed. Built in an isolated
  worktree off origin/main, full QA and VAPT suites re-run to confirm the baseline is unaffected
  before pushing.

## 2026-11-18 (Claude: internal links and client routing use the real hub-page URL, follow-up to commit 5fc7f51)

- Commit 5fc7f51 (17 Nov) fixed 14 hub pages' canonical/og:url/JSON-LD to the real trailing-slash
  URL and deliberately left ~190 internal `<a href>` call sites pointing at the old bare,
  redirect-only form as a separate cleanup. Did that cleanup, and it turned out to be more than
  mechanical:
  - Two files are hand-maintained HTML, never touched by the pipeline at all: `site/index.html`
    ("the SPA shell... hand-maintained, not generated by this module", per its own comment in
    `pipeline/publish.py`) and `site/404.html` (zero references anywhere in `pipeline/*.py`). 23
    more bare-path hrefs lived there, untouched by yesterday's fix or anything Python-side.
  - `site/assets/js/app.js`'s `TITLES`, `DESCRIPTIONS` and `ALIAS_OF` tables are keyed by path
    and looked up against the real `location.pathname` on every `render()`, first load included.
    Cloudflare always serves these hub pages at the trailing-slash form (confirmed 17 Nov,
    unconfigurable platform behavior), so the lookup was already missing on every fresh page
    load, independent of today's href cleanup: `document.title` and the meta description
    silently fell back to a generic h1-based title or the homepage's own description on
    `/brokers/`, `/compare/`, `/news/` and twelve other hub pages. Fixed the three tables to the
    trailing-slash form, also covering `/news/`, `/find-broker/` and `/match/` (same bare-key
    bug, even though their canonical was already correct, since they are real directory-backed
    pages too - confirmed by checking for a built `index.html` under each route name).
    `ROUTES` needed no change: its regexes already accept an optional trailing slash.
- Net: 190 href/path-table fixes across 12 pipeline engines and 5 hand-written JS files, 23 more
  in the two hand-maintained HTML shells, plus 3 more in `pages.js` for `/find-broker` that the
  first pass missed (caught only by writing the regression check below and running it before
  trusting it, consistent with this session's habit of verifying new check logic empirically
  rather than assuming it's right).
- Added a permanent check to `tests/qa_extra_indexation.py` scanning every `pipeline/*.py`,
  `site/assets/js/*.js`, and the two hand-maintained HTML files for the bare form of all 17 real
  hub paths, so this can't silently regress again. Fixed three `tests/qa_e2e.py` checks that
  hardcoded the old bare href as the expected value (not a reverted fix - those checks were
  simply asserting the old, wrong URL).
- Caught and fixed before shipping: the very first build after these edits stamped
  `site/brokers/index.html`, `site/cms/index.html`, `site/find-broker/index.html` and
  `site/match/index.html` with a stale `app.js?v=` cache-busting hash that didn't match app.js's
  real current content (confirmed by hashing the file directly) - not a correctness bug in the
  fix itself, but caught only by rebuilding twice more and diffing to confirm the output reached
  a stable fixed point before trusting it, the same discipline used for the stamp-sensitive-file
  issue earlier this session.
- QA: 1281/1281 (incl. `--url` live-probe checks). VAPT: 77/77. Rebased cleanly onto two
  concurrently-landing sibling commits (the CTR-wording sweep and the Tradejini/Ventura DP charge
  fix), no conflicts.
- Left deliberately undone, flagged for anyone touching this area next: `/rankings` and
  `/algo-platforms` are pure client-side aliases with no backing directory asset, so they were
  correctly left at the bare form in `ALIAS_OF`'s keys (Cloudflare has nothing to redirect there);
  only their target values (`/leaderboards/`, `/algo/`) needed fixing, and did.

## 2026-11-18 (Automated SEO Autopilot)

- Weekly 28-day snapshot comparison (2026-11-18 vs 2026-11-11):
  - Clicks: 1019 (-169 vs prior week)
  - Impressions: 98716 (-5716 vs prior week)
  - Submitted indexable URLs: 6228

- Striking distance search queries identified (positions 4 to 20, high impressions):
  - "pashupati cotspin share price target 2030": pos 4.8, 925 impressions, 27 clicks, 2.92% CTR
  - "irb infra share price target 2030": pos 8.3, 684 impressions, 3 clicks, 0.44% CTR
  - "morepen lab share price target 2030": pos 7.7, 348 impressions, 2 clicks, 0.57% CTR
  - "cupid share price target 2026": pos 6.8, 219 impressions, 0 clicks, 0% CTR
  - "pc jeweller share price target 2027": pos 5.2, 208 impressions, 6 clicks, 2.88% CTR
  - "praj industries share price target 2030": pos 8.7, 192 impressions, 4 clicks, 2.08% CTR
  - "birlasoft share price target 2030": pos 5.8, 186 impressions, 4 clicks, 2.15% CTR
  - "gujarat natural resources share price target 2030": pos 4.2, 183 impressions, 4 clicks, 2.19% CTR

- Demand sitemap verified: all current high-demand pages remain indexed in Wave 1.
- Expected effect: increase search visibility and CTR across striking-distance terms without adding thin doorway pages.
- Check impact by: 2026-12-02
