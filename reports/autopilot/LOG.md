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
