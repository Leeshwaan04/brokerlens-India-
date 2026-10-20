"""Indexation regression checks: soft 404 guard, sitemap canonical forms and first
wave, hub discovery links, SIP permutation pruning, and branch page verification.

Loaded by tests/qa_e2e.py as run(check, ROOT, load). Generation checks write into a
temporary directory, never into site/."""
import json
import os
import re
import shutil
import sys
import tempfile


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run(check, ROOT, load):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from pipeline import indexation as ix
    from pipeline import broker_branch_engine as bbe
    from pipeline import sip_calculator_engine as sip
    from pipeline import publish as pub

    pub_src = _read(os.path.join(ROOT, "pipeline", "publish.py"))
    app_js = _read(os.path.join(ROOT, "site", "assets", "js", "app.js"))
    pages_js = _read(os.path.join(ROOT, "site", "assets", "js", "pages.js"))

    # ---- 1. soft 404 on hybrid pages --------------------------------------------
    check("indexation: app.js keeps server-rendered content when the data load fails (soft 404 guard)",
          "hadServerContent" in app_js and "isNotFoundView" in app_js
          and "if (!hadServerContent)" in app_js)
    m = re.search(r"const isNotFoundView = (/.*?/)\.test", app_js)
    nf = re.search(r"export function notFound\(msg\) \{\s*return `([^`]*)`", pages_js, re.S)
    ok = False
    if m and nf:
        # The guard's pattern must match the markup notFound() really emits.
        pat = re.compile(m.group(1)[1:-1].replace("\\/", "/"))
        sample = nf.group(1).replace("${msg || 'That page does not exist.'}", "No broker profile")
        ok = bool(pat.search(sample)) and not pat.search('<h1 style="margin-top:16px">Zerodha</h1>')
    check("indexation: the not-found guard pattern matches pages.notFound() markup and not a real page", ok)
    check("indexation: robots.txt still blocks raw JSON (the guard, not a robots change, fixes the soft 404)",
          '"Disallow: /data/"' in pub_src)

    # ---- 2. sitemap: canonical forms, first wave ---------------------------------
    block = pub_src[pub_src.index("core_urls = ["):pub_src.index("for slug in (report_slugs or [])")]
    core = re.findall(r'"(/[^"]*)"', block)
    for bare in ("/ipo", "/news", "/calculators", "/stocks", "/funds-by", "/etfs", "/crypto", "/ipo/archive"):
        check("indexation: core sitemap lists the canonical %s/ (not %s)" % (bare, bare),
              (bare + "/") in core and bare not in core)
    for must in ("/ipo/", "/ipo/upcoming/", "/news/", "/trade-costs/", "/branches/"):
        check("indexation: first-wave core sitemap has %s" % must, must in core)
    # Every static hub in the built site: sitemap form equals its own canonical.
    site = os.path.join(ROOT, "site")
    checked, bad = 0, []
    for u in core:
        f = os.path.join(site, u.strip("/"), "index.html") if u != "/" else os.path.join(site, "index.html")
        if os.path.exists(f) and u.endswith("/"):
            head = _read(f)[:20000]
            mm = re.search(r'<link rel="canonical" href="([^"]+)"', head)
            checked += 1
            if not mm or not mm.group(1).endswith(u):
                bad.append(u)
    check("indexation: built static hub pages carry the same canonical the sitemap lists (%d checked)" % checked,
          not bad, str(bad))
    check("indexation: top ETFs join the first sitemap wave inside stocks-top",
          "top_etf_slugs" in pub_src and "(stock_top_entries if slug in top_etfs else fund_entries)" in pub_src)
    sl = lambda s: s.lower()
    picked = ix.top_etf_slugs(
        [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}],
        {"AAA": [{"volume": 10}], "BBB": [{"volume": 99}], "CCC": []}, sl, limit=5)
    check("indexation: top_etf_slugs ranks by volume and skips ETFs with no volume history", picked == ["bbb", "aaa"], str(picked))

    # ---- 3. discovery links ------------------------------------------------------
    hubs = ("/ipo/upcoming/", "/ipo/subscription/", "/trade-costs/", "/index/nifty-50/", "/etf/niftybees/")
    shell_foot = pub.__dict__["_APP_SHELL_FOOT"]
    reg_foot = pub.__dict__["_REGISTRY_PAGE_FOOT"]
    for h in hubs:
        check("indexation: shared page footers carry a plain <a href> to %s" % h,
              ('<a href="%s"' % h) in shell_foot and ('<a href="%s"' % h) in reg_foot)
    sample_home = ('<main id="app"></main><footer class="site"><ul>'
                   '<li><a href="/ipo/">IPO tracker</a></li></ul><ul>'
                   '<li><a href="/stocks/">Browse stocks A-Z</a></li>'
                   '<li><a href="/etfs/">Browse ETFs</a></li></ul></footer>')
    once = ix.add_home_footer_links(sample_home)
    check("indexation: home footer gets every discovery link, once, idempotently",
          all(once.count('href="%s"' % h) == 1 for h in hubs) and ix.add_home_footer_links(once) == once)
    check("indexation: home prerender applies the footer links", "add_home_footer_links" in pub_src)
    chips = pub._index_chips_html({"nifty-50": {"label": "Nifty 50"}, "nifty-bank": {"label": "Nifty Bank"}})
    check("indexation: /stocks/ hub lists index pages as crawlable links",
          'href="/index/nifty-50/"' in chips and 'href="/index/nifty-bank/"' in chips and "_index_chips_html(indices)" in pub_src)
    check("indexation: /calculators/ hub links /trade-costs/", 'href="/trade-costs/"' in pub_src[pub_src.index("def _write_calculator_hub"):])

    # ---- 4. SIP permutations -----------------------------------------------------
    n_ok = sum(1 for a in sip.AMOUNTS for y in sip.DURATIONS if ix.sip_indexable(a, y))
    check("indexation: exactly 10 amounts x 8 years of SIP permutations stay indexable",
          n_ok == 80 and set(ix.SIP_INDEX_AMOUNTS) <= set(sip.AMOUNTS) and set(ix.SIP_INDEX_YEARS) <= set(sip.DURATIONS), str(n_ok))
    old_site = sip.SITE_DIR
    tmp = tempfile.mkdtemp(prefix="ix_sip_")
    try:
        sip.SITE_DIR = tmp
        urls = sip.build_sip_calculator_suite(site_url="https://www.brokerlens.in")
        check("indexation: SIP suite returns only the hub plus 80 searched permutations for the sitemap",
              len(urls) == 81 and "/calculators/sip/" in urls, str(len(urls)))
        keep = open(os.path.join(tmp, "calculators", "sip", "5000-per-month-for-10-years", "index.html"), encoding="utf-8").read()
        drop = open(os.path.join(tmp, "calculators", "sip", "5000-per-month-for-7-years", "index.html"), encoding="utf-8").read()
        odd = open(os.path.join(tmp, "calculators", "sip", "7500-per-month-for-10-years", "index.html"), encoding="utf-8").read()
        check("indexation: a searched SIP page has no robots noindex", "noindex" not in keep)
        check("indexation: unsearched SIP pages are noindex,follow and still written (live)",
              'content="noindex,follow"' in drop and 'content="noindex,follow"' in odd)
        pages = sum(1 for _ in os.scandir(os.path.join(tmp, "calculators", "sip")))
        check("indexation: all SIP permutation pages stay on disk", pages == len(sip.AMOUNTS) * len(sip.DURATIONS) + 1, str(pages))
    finally:
        sip.SITE_DIR = old_site
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 5. branch pages: indexable only where the data places the broker --------
    keys = set(bbe.CITIES)
    check("indexation: register spellings map to branch city keys",
          ix.city_key("Bangalore", keys) == "bengaluru" and ix.city_key("NEW DELHI", keys) == "delhi"
          and ix.city_key("Navi Mumbai", keys) == "navi-mumbai" and ix.city_key("Nowhereville", keys) is None)
    check("indexation: Navi Mumbai or Thane never verifies Mumbai",
          not ix.address_mentions_city("Plot 1, Ghansoli, Navi Mumbai 400710", "mumbai", "Mumbai")
          and ix.address_mentions_city("Andheri East, Mumbai 400093", "mumbai", "Mumbai"))
    old_site, old_cache = bbe.SITE_DIR, dict(bbe._PROFILE_CACHE)
    tmp = tempfile.mkdtemp(prefix="ix_branch_")
    try:
        bdir = os.path.join(tmp, "data", "brokers")
        os.makedirs(bdir)
        with open(os.path.join(bdir, "zerodha.json"), "w", encoding="utf-8") as fh:
            json.dump({"profile": {"hq": "Bengaluru", "sebi_city": "Bangalore",
                                   "sebi_entities": [{"city": "Bangalore"}, {"city": None}]}}, fh)
        with open(os.path.join(bdir, "dhan.json"), "w", encoding="utf-8") as fh:
            json.dump({"profile": {"hq": None, "sebi_city": None, "sebi_entities": []}}, fh)
        bbe.SITE_DIR = tmp
        urls = bbe.generate_all(site_url="https://www.brokerlens.in")
        stats = dict(bbe.LAST_RUN_STATS)

        def page(b, c):
            return open(os.path.join(tmp, "broker", b, "branches", c, "index.html"), encoding="utf-8").read()
        z_ok, z_no, d_no = page("zerodha", "bengaluru"), page("zerodha", "rajkot"), page("dhan", "rajkot")
        check("indexation: a broker's registered city page stays indexable with its original title",
              "noindex" not in z_ok and "<title>Zerodha Branch in Bengaluru, Karnataka: Address, Phone, Demat" in z_ok)
        check("indexation: an unverified city page is noindex,follow", 'content="noindex,follow"' in z_no and 'content="noindex,follow"' in d_no)
        check("indexation: an unverified city page claims no branch (title, h1, FAQ, schema)",
              "Branch in" not in z_no and "No Rajkot office or authorised-person location" in z_no
              and "Authorized Branch" not in z_no and "streetAddress" not in z_no and "walk-in" not in z_no.lower(),
              re.search(r"<title>[^<]*", z_no).group(0))
        check("indexation: noindex city pages are left out of the returned sitemap URLs",
              "/broker/zerodha/branches/bengaluru/" in urls and "/broker/zerodha/branches/rajkot/" not in urls
              and "/broker/dhan/branches/rajkot/" not in urls)
        check("indexation: branch run stats count the flipped pages",
              stats["city_pages"] == len(bbe.BROKER_BRANCH_METADATA) * len(bbe.CITIES)
              and stats["city_pages_noindex"] == stats["city_pages"] - stats["city_pages_indexable"]
              and stats["city_pages_indexable"] >= 1, str(stats))
        check("indexation: a broker with no city on file has a noindex hub and no city in the sitemap",
              not any(u.startswith("/broker/dhan/branches/") for u in urls) and stats["broker_hubs_noindex"] >= 1)
        dashes = [f for f in ("zerodha/branches/bengaluru", "zerodha/branches/rajkot")
                  if "—" in page(*f.split("/branches/")) or "–" in page(*f.split("/branches/"))]
        check("indexation: branch pages carry no em or en dashes", not dashes, str(dashes))
    finally:
        bbe.SITE_DIR = old_site
        bbe._PROFILE_CACHE.clear()
        bbe._PROFILE_CACHE.update(old_cache)
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 6. copy hygiene in this module's own output ------------------------------
    src = _read(os.path.join(ROOT, "pipeline", "indexation.py"))
    check("indexation: module copy has no em or en dashes", "—" not in src and "–" not in src)
