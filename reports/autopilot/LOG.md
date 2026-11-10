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
