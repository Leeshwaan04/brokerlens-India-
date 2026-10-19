# CTO Indexation Audit — 2026-10-19

**Question:** GSC sitemaps panel shows **114,996 submitted / 0 indexed** while URL Inspection shows 11 URLs PASS. Is the sitemap pipeline broken?

## Verdict

**The sitemap pipeline is not broken. No indexation blocker was found.** The "0 indexed" is GSC panel lag on a freshly resubmitted sitemap index; the "114,996" is a stale count from the previous (pre-tiering) sitemap generation. Evidence below.

## What was checked

### 1. Pipeline → sitemap generation (`pipeline/publish.py`)

- Sitemap builder: `pipeline/publish.py:7239` (`_write_sitemap`). Wave logic at `publish.py:7232` (`SITEMAP_WAVES`), tiering at `publish.py:7490-7532`.
- `SITE_URL` defaults to `https://www.brokerlens.in` (`publish.py:43`) — correct host, HTTPS.
- Wave 1 = `core, brokers, ipos, registry, news, crypto, stocks-top`. Build log (last 9 runs): `3,943 URLs submitted (wave 1); 88,672 URLs held back` (branches, funds, trade-costs, comparisons, sip-calc, …). Held-back URLs are **not noindexed** — only excluded from the index (publish.py:7477-7481).
- Sharding cap `CHUNK_LIMIT = 45,000` (`publish.py:7475`) — under Google's 75,000/50 MB limit; no wave-1 sitemap comes close (largest is `sitemap-ipos.xml`, 1,254 URLs).
- **All 3,949 wave-1 sitemap URLs verified**: every one resolves to a built page in `site/`, every page carries exactly one `<link rel="canonical">` matching the sitemap URL, and **zero pages carry a `noindex` meta tag**. `grep noindex pipeline/publish.py` only matches comments.
- Sitemap index entries use `SITE_URL` + `/sitemaps/<file>` — well-formed, single host, single protocol.
- Stale-shard deletion exists (`publish.py:7512-7519`), so wave-2/3 files are not left advertising held-back URLs.

### 2. robots.txt (repo `site/robots.txt` + live `https://www.brokerlens.in/robots.txt`)

```
User-agent: *
Allow: /
Disallow: /api/
Disallow: /data/

Sitemap: https://www.brokerlens.in/sitemap.xml
```

- No rule blocks any wave-1 path (`/broker/`, `/ipo/`, `/stock/`, `/sebi-registry/`, `/crypto/`, `/news/`, …).
- Sitemap line matches the GSC-submitted URL exactly.

### 3. Live production checks (curl, 2026-10-19)

- `https://brokerlens.in` → 307 → `https://www.brokerlens.in`; `http://` → 308 → `https://`. Consistent single canonical host.
- `https://www.brokerlens.in/sitemap.xml` → **200**, valid `<sitemapindex>` with the 7 wave-1 sub-sitemaps.
- All 7 wave-1 sub-sitemaps → **200**, correct XML. Wave-2/3 files → 404 (intended, not referenced anywhere).
- Sample wave-1 pages fetched live: `/`, `/broker/zerodha/`, `/ipo/kfintech/`, `/stock/tcs/`, `/sebi-registry/qe-securities-llp/`, `/crypto/btc/` — all **HTTP 200**, canonical = `https://www.brokerlens.in<same-path>`, **no noindex** in `<head>`.

### 4. Cross-check vs GSC export (`gsc_audit.json`)

- `sitemaps` key: index `https://www.brokerlens.in/sitemap.xml`, **last downloaded by GSC 2026-10-17T11:00:25Z, warnings 0, errors 0**.
- `inspection` key: 11 of 24 URLs **PASS = "Submitted and indexed"** (`/`, `/brokers`, `/ipo/kfintech/`, `/stock/tcs/`, `/fund/hdfc-…`, `/funds-by/hdfc-mutual-fund/`, `/registry`, `/sebi-registry/qe-securities-llp/`, `/calculators/sip-calculator/`, `/crypto/btc/`, `/methodology`). Several NEUTRALS show "Crawled – currently not indexed" (`/stock/itc/`, crawled 2026-10-19) and "Discovered – currently not indexed" — i.e. **Google is actively crawling the wave-1 surface right now**.

## Ranked hypotheses (against the 114,996 / 0 numbers)

1. **Stale panel + lag — CONFIRMED as the cause of "0 indexed".** The tiered wave-1 sitemaps shipped in commit `8d89ab7` (2026-10-17, "feat: tiered sitemaps…"), one day before the 2026-10-17T11:00Z GSC download. Before that commit the pipeline emitted all 16 sub-sitemaps (~92.6K URLs, see build logs "written 16 sub-sitemaps (92,614 total URLs)"); the 114,996 figure is the panel's retained count from that era (plus incremental IPO/news URLs). The panel's "submitted" does not refresh atomically with a resubmission, and "indexed" for sitemaps is a slow, lagging metric on a domain that was only just re-organized. GSC indexing for a new/young domain legitimately takes days-to-weeks per URL; the 11 PASS "Submitted and indexed" verdicts and 2026-10-19 crawl timestamps prove the index path works.
2. Wrong host / HTTP vs HTTPS / malformed URLs — **ruled out** (all `https://www.brokerlens.in`, well-formed, single host, HTTPS-only after 308).
3. Sitemap not referenced / robots block — **ruled out** (robots.txt `Sitemap:` line correct, `Allow: /`, only `/api/` and `/data/` disallowed).
4. noindex on submitted wave-1 URLs — **ruled out** (0 of 3,949 carry noindex; canonicals all self-referential).
5. Sitemap over limits — **ruled out** (largest shard 1,254 URLs; 45,000 cap < 75,000 limit).
6. Site not crawlable (soft-404/JS-only) — **ruled out** (static HTML, 200s, real content).

## Non-blocking observations (not the cause, parked for later)

- `/ipo` (no trailing slash) is in `sitemap-core.xml` while its canonical is `https://www.brokerlens.in/ipo/`. Self-canonicalizing URLs in sitemaps are harmless (Google follows the canonical) and this is 1 of 3,949 URLs; it already appears "unknown to Google" for the same lag reason. Cosmetic generator cleanup for a future cycle: align `core_urls` entries with canonical forms (`/ipo`, `/brokers` vs `/brokers/`, etc.).
- Non-www host returns 307 instead of 308 (www 308s, non-www 307s). Non-www is not in any sitemap/canonical, so no SEO impact; 308 would be marginally cleaner.
- `/broker/zerodha/` shows "Soft 404" in one old inspection while the page is fully built and in the sitemap — likely a stale verdict from before the page was regenerated; no page-content defect (22 KB, complete head/body). Worth a re-inspect next week, not a fix.

## Fix / action plan

**No code fix required today.** Nothing in `pipeline/`, `site/robots.txt`, or the built HTML needs changing to unblock indexation.

Actions:
1. In GSC, resubmit the sitemap index `https://www.brokerlens.in/sitemap.xml` (Sitemaps → detail → resubmit) to force the panel's "submitted" to converge from the stale 114,996 to the true wave-1 count (~3,943). This is a GSC-console action (Owner/any human with access); it needs no credentials from me.
2. **What "fixed" looks like:** Sitemaps panel → index entry shows `submitted ≈ 3,943`, `errors 0`, `warnings 0`; the "indexed" column starts climbing from 0 over the following days–weeks (sitemaps-panel index counts lag; URL Inspection / Page Indexing "Submitted and indexed" verdicts rise in parallel). I do not promise specific GSC numbers or dates; the mechanism is proven working (11 already indexed, crawl activity today).
3. Next CTO cycle: verify the panel converged; if "indexed" is still 0 after ~14 days post-resubmission with 0 crawl activity, reopen with a new audit (at that point the suspect set shrinks to domain-authority/crawl-budget, not pipeline defects).
4. Optional follow-ups (queued, low priority): align `core_urls` trailing-slash forms with canonicals; switch non-www 307→308; re-inspect `/broker/zerodha/`.

## Next-cycle queue recommendation (CTO)

1. Verify GSC sitemaps panel convergence after resubmission (metric, no code).
2. Begin wave-2 promotion prep: per charter, wave 2 (funds, comparisons, long-tail stocks) promotes once wave 1 indexes well — define the trigger (e.g. wave-1 indexed ≥ 50%) and the `SITEMAP_WAVE=2` run.
3. Ship the first CTO-originated traction pages (charter KPI: ≥10/week from 2026-10-20) from GSC query demand — e.g. the NEUTRAL head-term pages (`/ipo/`, `/etf/niftybees/`) need quality upgrades to convert NEUTRALpassing.
4. Pull specs from `docs/seo/spec-*` + `docs/product/spec-*` (authored concurrently this week; not started today per scope).

*Audit performed read-only against repo at `c2d45d6` and live `https://www.brokerlens.in`; no rebuilds, no deploys, no config changes.*
