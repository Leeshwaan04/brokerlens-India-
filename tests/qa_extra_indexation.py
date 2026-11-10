"""Indexation regression checks: soft 404 guard, sitemap canonical forms and first
wave, hub discovery links, SIP permutation pruning, and branch page verification.

Loaded by tests/qa_e2e.py as run(check, ROOT, load). Generation checks write into a
temporary directory, never into site/."""
import json
import os
import re
import hashlib
import shutil
import statistics
import sys
import tempfile
import xml.etree.ElementTree as ET


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

    # ---- 7. branch titles: "what is on file" wording ------------------------------
    SITE_URL = "https://www.brokerlens.in"
    hub = bbe._render_master_branches_hub(SITE_URL)
    h_title = re.search(r"<title>([^<]*)</title>", hub).group(1)
    h_meta = re.search(r'<meta name="description" content="([^"]*)"', hub).group(1)
    h_h1 = re.search(r"<h1[^>]*>([^<]*)</h1>", hub).group(1)
    promise = re.compile(r"\b(branch(es)?|address(es)?|phone|offices? (contact|locat)|find stock broker)", re.I)
    check("indexation: /branches/ master hub title, meta and H1 use the 'what is on file' wording",
          "What Is on File" in h_title and "on file" in h_h1.lower() and "on file" in h_meta.lower()
          and "No branch list is claimed" in h_meta, "%s | %s | %s" % (h_title, h_meta, h_h1))
    check("indexation: /branches/ master hub title and H1 promise no branch offices, addresses or phones",
          not promise.search(h_title) and not promise.search(h_h1), h_title + " | " + h_h1)
    check("indexation: /branches/ master hub head is self-canonical, indexable, no dashes",
          '<link rel="canonical" href="%s/branches/">' % SITE_URL in hub and "noindex" not in hub[:3000]
          and not any(d in h_title + h_meta + h_h1 for d in ("\u2014", "\u2013")))

    # A verified city with no street address (the Upstox Mumbai case): head office city on
    # file is Mumbai but the curated street address is in Delhi, so address_ok is false.
    old_site, old_cache = bbe.SITE_DIR, dict(bbe._PROFILE_CACHE)
    tmp = tempfile.mkdtemp(prefix="ix_branch2_")
    try:
        bdir = os.path.join(tmp, "data", "brokers")
        os.makedirs(bdir)
        with open(os.path.join(bdir, "upstox.json"), "w", encoding="utf-8") as fh:
            json.dump({"profile": {"hq": "Mumbai", "sebi_city": None, "sebi_entities": []}}, fh)
        with open(os.path.join(bdir, "zerodha.json"), "w", encoding="utf-8") as fh:
            json.dump({"profile": {"hq": "Bengaluru", "sebi_city": "Bangalore", "sebi_entities": []}}, fh)
        bbe.SITE_DIR = tmp
        bbe._PROFILE_CACHE.clear()

        def render(b, c):
            return bbe._render_city_branch_page(b, bbe.BROKER_BRANCH_METADATA[b], c, bbe.CITIES[c], [], SITE_URL)
        up_html, up_idx = render("upstox", "mumbai")
        zr_html, zr_idx = render("zerodha", "bengaluru")
        ut = re.search(r"<title>([^<]*)</title>", up_html).group(1)
        um = re.search(r'<meta name="description" content="([^"]*)"', up_html).group(1)
        uh = re.search(r"<h1[^>]*>([^<]*)</h1>", up_html).group(1)
        check("indexation: verified city page with no street address stays indexable", up_idx and "noindex" not in up_html)
        check("indexation: verified city page with no street address drops 'Branch', 'Address' and 'Phone' from title, meta and H1",
              not re.search(r"branch|address, phone", ut + " " + uh, re.I)
              and not re.search(r"find office contact|branch", um, re.I) and "No street address in Mumbai is on file" in um,
              ut + " | " + um)
        check("indexation: no-street-address title is the neutral registered-city wording",
              ut == "Upstox in Mumbai: Registered City, Helpline and KYC Support" and "Office contact details" not in um
              and "office contact details" not in um.lower(), ut)
        zt = re.search(r"<title>([^<]*)</title>", zr_html).group(1)
        zm = re.search(r'<meta name="description" content="([^"]*)"', zr_html).group(1)
        check("indexation: the longer Branch ... Address, Phone title is kept only when a street address is on file (address_ok)",
              zr_idx and zt.startswith("Zerodha Branch in Bengaluru, Karnataka: Address, Phone, Demat &amp; KYC Services")
              and "Find office contact details" in zm, zt)
    finally:
        bbe.SITE_DIR = old_site
        bbe._PROFILE_CACHE.clear()
        bbe._PROFILE_CACHE.update(old_cache)
        shutil.rmtree(tmp, ignore_errors=True)

    # Whatever profiles are on disk (site/data/brokers is read only here): every verified page
    # without a street address must carry the neutral title and meta. Skips when none are built.
    bbe._PROFILE_CACHE.clear()
    n_ver = n_noaddr = 0
    offenders = []
    for b_id, meta in sorted(bbe.BROKER_BRANCH_METADATA.items()):
        for c_key, c_data in sorted(bbe.CITIES.items()):
            ver = bbe._branch_verification(b_id, meta, c_key, c_data)
            if not ver["verified"]:
                continue
            n_ver += 1
            if ver["address_ok"]:
                continue
            n_noaddr += 1
            html_p, _idx = bbe._render_city_branch_page(b_id, meta, c_key, c_data, [], SITE_URL)
            tt = re.search(r"<title>([^<]*)</title>", html_p).group(1)
            mm = re.search(r'<meta name="description" content="([^"]*)"', html_p).group(1)
            if re.search(r"Branch|Address, Phone", tt) or "Find office contact details" in mm:
                offenders.append("%s/%s" % (b_id, c_key))
    bbe._PROFILE_CACHE.clear()
    bbe._PROFILE_CACHE.update(old_cache)
    if n_ver == 0:
        check("indexation: built verified city pages without an address use neutral wording (not applicable: no broker profiles built)", True)
    else:
        check("indexation: all %d verified city pages without a street address (of %d verified) use neutral title and meta" % (n_noaddr, n_ver),
              not offenders, str(offenders[:6]))

    # ---- 8. slash forms in template links, no slashless hub links ------------------
    owned = ("broker_branch_engine.py", "sip_calculator_engine.py", "fund_compare_engine.py", "price_target_section.py")
    slashless = []
    for fn in owned:
        txt = _read(os.path.join(ROOT, "pipeline", fn))
        for mm in re.finditer(r'(?:href|item|url)\s*[=:]\s*f?["\']([^"\']*?)/(ipo|calculators|news)(["\'#?])', txt):
            slashless.append("%s: %s" % (fn, mm.group(0)[:60]))
    check("indexation: template links to the /ipo/, /calculators/ and /news/ hubs use the canonical slash forms", not slashless, str(slashless[:4]))
    fc = _read(os.path.join(ROOT, "pipeline", "fund_compare_engine.py"))
    sc = _read(os.path.join(ROOT, "pipeline", "sip_calculator_engine.py"))
    check("indexation: fund compare nav links /ipo/, /calculators/, /news/ (3 templates)",
          fc.count('<a href="/ipo/">IPOs</a>') == 3 and fc.count('<a href="/calculators/">Calculators</a>') == 3
          and fc.count('<a href="/news/">News</a>') == 3)
    check("indexation: SIP pages link /calculators/ (crumbs, footer) and /ipo/, /news/ in the nav",
          sc.count('href="/calculators/"') >= 4 and '<a href="/ipo/">IPO</a>' in sc and '<a href="/news/">News</a>' in sc)
    check("indexation: sitemap repeats of a hub URL across shards are dropped (first shard wins)",
          "_seen_locs" in pub_src and "_first_time(e)" in pub_src and "submitted = len(_seen_locs)" in pub_src)

    # ---- 9. every sitemap URL maps to a built, self-canonical, indexable page -------
    site_dir = os.path.join(ROOT, "site")
    sm_dir = os.path.join(site_dir, "sitemaps")
    shards = sorted(f for f in os.listdir(sm_dir) if f.startswith("sitemap-") and f.endswith(".xml")) if os.path.isdir(sm_dir) else []
    if not shards:
        check("indexation: sitemap URLs map to self-canonical indexable built pages (not applicable: no site/sitemaps in this tree)", True)
    else:
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        base = "https://www.brokerlens.in"
        seen, dupes, missing, off_canon, noindexed, total = set(), [], [], [], [], 0
        for fn in shards:
            for loc in ET.parse(os.path.join(sm_dir, fn)).getroot().iter(ns + "loc"):
                url = (loc.text or "").strip()
                total += 1
                if url in seen:
                    dupes.append(url)
                seen.add(url)
                path = url[len(base):] if url.startswith(base) else None
                if path is None:
                    missing.append(url)
                    continue
                rel = path.strip("/")
                cands = [os.path.join(site_dir, rel, "index.html"), os.path.join(site_dir, rel + ".html")] if rel else [os.path.join(site_dir, "index.html")]
                f = next((c for c in cands if os.path.isfile(c)), None)
                if f is None:
                    missing.append(url)
                    continue
                with open(f, encoding="utf-8", errors="replace") as fh:
                    page_html = fh.read()
                cm = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', page_html) or re.search(r'<link[^>]+href="([^"]+)"[^>]+rel="canonical"', page_html)
                if not cm or cm.group(1) != url:
                    off_canon.append(url)
                if re.search(r'<meta[^>]+name="robots"[^>]+content="[^"]*noindex', page_html, re.I):
                    noindexed.append(url)
        check("indexation: no URL appears twice across the %d sitemap shards (%d URLs)" % (len(shards), total), not dupes, str(dupes[:3]))
        check("indexation: every sitemap URL maps to a built page", not missing, "%d missing, e.g. %s" % (len(missing), missing[:3]))
        check("indexation: every sitemap URL is self-canonical", not off_canon, "%d off, e.g. %s" % (len(off_canon), off_canon[:3]))
        check("indexation: no sitemap URL is noindex", not noindexed, "%d noindex, e.g. %s" % (len(noindexed), noindexed[:3]))

    # ---- 10. .table-scroll must stay horizontally scrollable on phones ---------------
    css_path = os.path.join(ROOT, "site", "assets", "css", "app.css")
    css = _read(css_path)
    rules = re.findall(r"(?<![\w-])\.table-scroll\s*\{([^}]*)\}", css)
    bad_rules = [r for r in rules if re.search(r"overflow(-x)?\s*:\s*hidden", r)]
    last_x = None
    for r in rules:
        mx = re.search(r"overflow-x\s*:\s*(\w+)", r) or re.search(r"(?<![\w-])overflow\s*:\s*(\w+)", r)
        if mx:
            last_x = mx.group(1)
    check("indexation: no .table-scroll rule sets overflow or overflow-x to hidden (it clipped wide tables on phones)",
          bool(rules) and not bad_rules, str(bad_rules[:1]))
    check("indexation: the last .table-scroll rule that sets horizontal overflow leaves it scrollable (auto)",
          last_x in ("auto", "scroll"), str(last_x))
    check("indexation: .table-scroll keeps max-width 100% so a wide table scrolls inside its box, not the page",
          any("max-width: 100%" in r for r in rules))
    check("indexation: .table-scroll scroll-hint shadows use theme tokens only (light and dark)",
          any("color-mix(in srgb, var(--text)" in r and "background-attachment: local" in r for r in rules)
          and not any(re.search(r"#[0-9a-fA-F]{3,6}\b", r) for r in rules[-1:]))
    check("indexation: app.css has no em or en dashes", "\u2014" not in css and "\u2013" not in css)

    # ---- 11. asset cache-busting stamps ---------------------------------------------
    stamp_src = "hashlib.sha256(open(path, \"rb\").read()).hexdigest()[:10]" in pub_src
    check("indexation: asset stamps are content hashes (sha256 first 10), so an edited app.js or app.css gets a new URL", stamp_src)
    app_hash = hashlib.sha256(open(os.path.join(ROOT, "site", "assets", "js", "app.js"), "rb").read()).hexdigest()[:10]
    index_html = os.path.join(ROOT, "site", "index.html")
    if os.path.isfile(index_html):
        app_mtime = os.path.getmtime(os.path.join(ROOT, "site", "assets", "js", "app.js"))
        fresh_stamps, n_fresh = set(), 0
        for sub in ("", "brokers", "compare", "ipo", "stocks", "news"):
            f = os.path.join(ROOT, "site", sub, "index.html")
            # Only pages written after the last app.js edit count: an older page is simply
            # waiting for its rebuild (the build re-stamps every /assets/ URL).
            if os.path.isfile(f) and os.path.getmtime(f) >= app_mtime:
                n_fresh += 1
                fresh_stamps.update(re.findall(r"/assets/js/app\.js\?v=([0-9a-f]{10})", _read(f)))
        check("indexation: pages written after the last app.js edit carry its current stamp %s (%d such pages sampled)"
              % (app_hash, n_fresh), fresh_stamps <= {app_hash}, str(sorted(fresh_stamps)))
    else:
        check("indexation: built pages carry the current app.js stamp (not applicable: no built site/index.html)", True)

    # ---- 12. title length distribution (reports only, always passes) ------------------
    def _titles(dirpath, only_top=True):
        out = []
        if not os.path.isdir(dirpath):
            return out
        for ent in os.scandir(dirpath):
            f = os.path.join(ent.path, "index.html")
            if ent.is_dir() and os.path.isfile(f):
                mt = re.search(r"<title>([^<]*)</title>", _read(f)[:6000])
                if mt:
                    out.append(len(mt.group(1)))
        return out
    for fam, d in (("registry", "sebi-registry"), ("ipo", "ipo"), ("stock", "stock")):
        lens = _titles(os.path.join(site_dir, d))
        if not lens:
            check("indexation: title length log, %s family (not applicable: none built)" % fam, True)
            continue
        lens.sort()
        check("indexation: title length log, %s family: n=%d min=%d median=%d p90=%d max=%d, over 60: %d, over 70: %d (report only)"
              % (fam, len(lens), lens[0], int(statistics.median(lens)), lens[int(len(lens) * 0.9) - 1], lens[-1],
                 sum(1 for n in lens if n > 60), sum(1 for n in lens if n > 70)), True)

    # ---- trade-cost pages stay out of the index ---------------------------------
    # ~30K of these broker x stock templates got indexed through internal links while
    # held out of the sitemap (98% of a 500-URL indexed sample, 23 Oct 2026), and
    # impressions fell 97% on 2 Nov. Out of the sitemap is not out of the index.
    from pipeline import trade_cost_engine as tce
    import inspect
    check("indexation: trade-cost pages and each broker's /trade/ listing carry noindex,follow; the /trade-costs/ hub does not",
          tce.TRADE_PAGE_ROBOTS == ix.NOINDEX_META
          and "{TRADE_PAGE_ROBOTS}" in inspect.getsource(tce.render_trade_cost_page)
          and "{TRADE_PAGE_ROBOTS}" in inspect.getsource(tce.render_broker_trade_index)
          and "{TRADE_PAGE_ROBOTS}" not in inspect.getsource(tce.render_trade_costs_hub))
    vj = load("vercel.json") or {}
    rule = [h for h in vj.get("headers", []) if h.get("source") == "/broker/:broker/trade/(.*)"]
    check("indexation: vercel.json also sends X-Robots-Tag noindex for /broker/:broker/trade/(.*), a second layer if a template loses the tag",
          bool(rule) and any(x.get("key") == "X-Robots-Tag" and "noindex" in x.get("value", "")
                             for x in rule[0].get("headers", [])))
    site_dir = os.path.join(ROOT, "site")
    trade_root = os.path.join(site_dir, "broker", "zerodha", "trade")
    sample = []
    if os.path.isdir(trade_root):
        for name in sorted(os.listdir(trade_root))[:20]:
            f = os.path.join(trade_root, name, "index.html")
            if os.path.isfile(f):
                sample.append(f)
        listing = os.path.join(trade_root, "index.html")
        if os.path.isfile(listing):
            sample.append(listing)
    if sample:
        missing = [p for p in sample if 'name="robots" content="noindex' not in _read(p)[:4000]]
        check("indexation: built trade-cost pages carry noindex (%d sampled)" % len(sample), not missing,
              str([m.replace(site_dir, "") for m in missing[:3]]))
    else:
        check("indexation: built trade-cost pages carry noindex (not applicable: none built)", True)
    hub = os.path.join(site_dir, "trade-costs", "index.html")
    if os.path.isfile(hub):
        check("indexation: the /trade-costs/ hub stays indexable", "noindex" not in _read(hub)[:4000])
    leaked = []
    for fn in (os.listdir(os.path.join(site_dir, "sitemaps")) if os.path.isdir(os.path.join(site_dir, "sitemaps")) else []):
        if fn.endswith(".xml"):
            leaked += re.findall(r"<loc>[^<]*/broker/[^/<]+/trade/[^<]*</loc>", _read(os.path.join(site_dir, "sitemaps", fn)))
    check("indexation: no sitemap lists a noindexed trade-cost page", not leaked, str(leaked[:3]))

    # ---- the broker x stock trade pages are retired (10 Nov 2026) ----------------
    # 75,000 near-identical pages took Google's crawl (URL Inspection, 10 Nov: last crawls
    # 17 to 25 Oct, noindex never seen) while the /ipo/ hub and broker profiles sat in
    # "Discovered - currently not indexed". They 308 to the broker's cost page now.
    from pipeline import broker_charges_engine as bce
    build_src = inspect.getsource(tce.build_trade_cost_pages)
    check("trade retirement: the build writes only the /trade-costs/ hub and deletes any old /broker/<id>/trade/ output",
          "render_trade_cost_page(" not in build_src and "render_broker_trade_index(" not in build_src
          and "remove_retired_trade_pages()" in build_src)
    gen_links = []
    for fn in sorted(os.listdir(os.path.join(ROOT, "pipeline"))):
        if fn.endswith(".py") and fn != "trade_cost_engine.py":
            gen_links += ["%s: %s" % (fn, m) for m in re.findall(r'href="/broker/[^"]*/trade/[^"]*"', _read(os.path.join(ROOT, "pipeline", fn)))]
    gen_links += ["trade_cost_engine hub: %s" % m for m in re.findall(r'href="/broker/[^"]*/trade/[^"]*"', inspect.getsource(tce.render_trade_costs_hub))]
    check("trade retirement: no page template links a /broker/<id>/trade/ URL", not gen_links, str(gen_links[:3]))

    def _vercel_redirect(path):
        """First vercel.json redirect matching `path` (path-to-regexp subset the file uses)."""
        for r in vj.get("redirects", []):
            src = r["source"]
            rx, names, i = "", [], 0
            while i < len(src):
                m = re.match(r":(\w+)(\(([^()]*(?:\([^()]*\))?[^()]*)\))?", src[i:])
                if m:
                    names.append(m.group(1))
                    rx += "(?P<%s>%s)" % (m.group(1), m.group(3) or "[^/]+")
                    i += m.end()
                elif src.startswith("(.*)", i):
                    rx += "(?:.*)"
                    i += 4
                else:
                    rx += re.escape(src[i])
                    i += 1
            hit = re.fullmatch(rx, path)
            if hit:
                dest = r["destination"]
                for n in names:
                    dest = dest.replace(":" + n, hit.group(n))
                return dest, r.get("permanent")
        return None, None

    wrong = []
    for k in sorted(tce.BROKER_RATES):
        want = bce.cost_page_path(k)
        for path in ("/broker/%s/trade" % k, "/broker/%s/trade/" % k, "/broker/%s/trade/reliance/" % k):
            got, perm = _vercel_redirect(path)
            if got != want or perm is not True:
                wrong.append((path, got, want))
    check("trade retirement: every broker's /trade/ URLs 308 to its cost page (charges page, else profile, else /trade-costs/)",
          not wrong, str(wrong[:3]))
    check("trade retirement: no other path is caught by the trade redirects",
          _vercel_redirect("/broker/zerodha/")[0] is None and _vercel_redirect("/broker/zerodha/charges/")[0] is None
          and _vercel_redirect("/stock/reliance/")[0] is None)
    if os.path.isdir(os.path.join(site_dir, "broker", "zerodha")):
        left = [b for b in os.listdir(os.path.join(site_dir, "broker")) if os.path.isdir(os.path.join(site_dir, "broker", b, "trade"))]
        check("trade retirement: the build leaves no /broker/<id>/trade/ directory behind", not left, str(left[:5]))
        dests = sorted({bce.cost_page_path(k) for k in tce.BROKER_RATES})
        dead = [d for d in dests if not os.path.isfile(os.path.join(site_dir, d.strip("/"), "index.html"))]
        check("trade retirement: every redirect destination is a page this build wrote", not dead, str(dead))
        for rel in ("stock/reliance", "broker/zerodha", "broker/zerodha/charges", "trade-costs"):
            html_ = _read(os.path.join(site_dir, rel, "index.html"))
            if html_:
                check("trade retirement: /%s/ links no retired trade page" % rel,
                      not re.search(r'href="/broker/[^"]*/trade/', html_))
        rel_html = _read(os.path.join(site_dir, "stock", "reliance", "index.html"))
        if rel_html:
            check("trade retirement: stock pages link the brokers' charges calculators instead",
                  'href="/broker/zerodha/charges/"' in rel_html and 'href="/broker/groww/charges/"' in rel_html)
        hub_html = _read(os.path.join(site_dir, "trade-costs", "index.html"))
        if hub_html:
            check("trade retirement: the hub no longer calls an unverified schedule a 'Verified Tariff'",
                  "Verified Tariff" not in hub_html)

    # ---- temporary recrawl sitemap of retired URLs --------------------------------
    retired = load("data/manual/retired_urls.json") or {}
    rpaths = retired.get("paths") or []
    not_redirected = [p for p in rpaths if _vercel_redirect(p)[1] is not True]
    check("retired sitemap: every listed URL is a permanent redirect in vercel.json (only retired URLs, never live pages)",
          rpaths and not not_redirected, str(not_redirected[:3]))
    check("retired sitemap: the list expires (an 'until' date) and states the retirement date used as lastmod",
          bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", retired.get("until") or ""))
          and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", retired.get("retired") or "")))
    smi = _read(os.path.join(site_dir, "sitemap.xml"))
    check("retired sitemap: never listed in sitemap.xml, so the index allowlist cannot read it",
          "sitemap-retired" not in smi and not (set(rpaths) & ix.sitemap_paths(site_dir)))
    rs = _read(os.path.join(site_dir, "sitemap-retired.xml"))
    robots = _read(os.path.join(site_dir, "robots.txt"))
    if rs:
        locs = re.findall(r"<loc>https://www\.brokerlens\.in([^<]+)</loc>", rs)
        built_again = [p for p in locs if os.path.isfile(os.path.join(site_dir, p.strip("/"), "index.html"))]
        check("retired sitemap: lists the retired URLs with the retirement date, none of them a built page",
              len(locs) == len(set(locs)) and set(locs) <= set(rpaths) and not built_again
              and rs.count("<lastmod>%s</lastmod>" % retired.get("retired")) == len(locs), str(built_again[:3]))
        check("retired sitemap: advertised in robots.txt next to sitemap.xml",
              "Sitemap: https://www.brokerlens.in/sitemap-retired.xml" in robots
              and "Sitemap: https://www.brokerlens.in/sitemap.xml" in robots)
    elif robots:
        check("retired sitemap: not written, so robots.txt does not advertise it", "sitemap-retired" not in robots)

    # ---- the sitemap is the index allowlist ---------------------------------------
    tmp = tempfile.mkdtemp(prefix="qa_allowlist_")
    try:
        def page(rel, head_extra=""):
            d = os.path.join(tmp, rel)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
                fh.write("<!doctype html><html><head><meta charset=\"utf-8\">%s<title>t</title></head><body>b</body></html>" % head_extra)
            return os.path.join(d, "index.html")
        os.makedirs(os.path.join(tmp, "sitemaps"))
        with open(os.path.join(tmp, "sitemap.xml"), "w") as fh:
            fh.write("<sitemapindex><sitemap><loc>https://www.brokerlens.in/sitemaps/sitemap-core.xml</loc></sitemap></sitemapindex>")
        with open(os.path.join(tmp, "sitemaps", "sitemap-core.xml"), "w") as fh:
            fh.write("<urlset><url><loc>https://www.brokerlens.in/</loc></url><url><loc>https://www.brokerlens.in/stock/irb/</loc></url>"
                     "<url><loc>https://www.brokerlens.in/brokers</loc></url></urlset>")
        root_p, listed, spa = page("."), page("stock/irb", '<meta name="robots" content="index, follow">'), page("brokers")
        unlisted_plain = page("fund/some-fund")
        unlisted_index = page("compare/stocks/a-vs-b", '<meta name="robots" content="index, follow, max-snippet:-1">')
        already = page("broker/x/trade/y", ix.NOINDEX_META)
        secondary = page("sebi-registry/acme-dp-2016", '<link rel="canonical" href="https://www.brokerlens.in/sebi-registry/acme/">')
        self_canon = page("fund/other-fund", '<link rel="canonical" href="https://www.brokerlens.in/fund/other-fund/">')
        checked, changed = ix.enforce_index_allowlist(tmp)
        r = lambda p: _read(p)
        check("indexation: allowlist leaves every sitemap page indexable (incl. no-slash SPA routes and the root)",
              "noindex" not in r(root_p) + r(listed) + r(spa) and 'content="index, follow"' in r(listed))
        check("indexation: allowlist gives noindex,follow to pages outside the sitemap, replacing an index tag rather than adding a second one",
              ix.NOINDEX_META in r(unlisted_plain) and ix.NOINDEX_META in r(unlisted_index)
              and r(unlisted_index).count('name="robots"') == 1 and ix.NOINDEX_META in r(self_canon)
              and changed == 3 and checked == 8, "checked=%d changed=%d" % (checked, changed))
        check("indexation: allowlist never adds noindex to a page whose canonical names another URL (no noindex + canonical mix)",
              "noindex" not in r(secondary))
        check("indexation: allowlist leaves an already-noindex page untouched", r(already).count('name="robots"') == 1)
        os.remove(os.path.join(tmp, "sitemap.xml"))
        check("indexation: with no sitemap written, the allowlist changes nothing (never noindexes a whole site by accident)",
              ix.enforce_index_allowlist(tmp) == (0, 0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check("indexation: build() runs the allowlist after every page and sitemap is written",
          "indexation.enforce_index_allowlist(" in pub_src
          and pub_src.find("indexation.enforce_index_allowlist(") > pub_src.find("_restamp_index_html_assets()\n    #"))
    fund_dir = os.path.join(ROOT, "site", "fund")
    built_sitemap = ix.sitemap_paths(os.path.join(ROOT, "site"))
    if os.path.isdir(fund_dir) and built_sitemap:
        # Only funds the sitemap does not list: a fund with real search demand is listed
        # (demand sitemap) and rightly stays indexable.
        funds = [os.path.join(fund_dir, n, "index.html") for n in sorted(os.listdir(fund_dir))
                 if "/fund/%s/" % n not in built_sitemap][:15]
        funds = [f for f in funds if os.path.isfile(f)]
        listed_pages = [os.path.join(ROOT, "site", p.strip("/"), "index.html") for p in sorted(built_sitemap)[:40]]
        listed_pages = [f for f in listed_pages if os.path.isfile(f)]
        check("indexation: built pages outside the sitemap (fund pages, %d sampled) carry noindex" % len(funds),
              funds and all(ix.NOINDEX_META in _read(f)[:6000] for f in funds))
        check("indexation: built sitemap pages stay indexable (%d sampled)" % len(listed_pages),
              listed_pages and not any(re.search(r'name="robots" content="noindex', _read(f)[:6000]) for f in listed_pages))
    else:
        check("indexation: built allowlist sample (not applicable: no built site)", True)

    vj2 = load("vercel.json") or {}
    check("indexation: pushes to main do not deploy straight to production; the QA-gated deploy hook does",
          ((vj2.get("git") or {}).get("deploymentEnabled") or {}).get("main") is False)
    guide_redirects = [r for r in vj2.get("redirects", [])
                       if r.get("source", "").startswith("/news/") and "price-target" in r.get("source", "")]
    targets_ok = all(os.path.isdir(os.path.join(ROOT, "site", r["destination"].strip("/"))) or not os.path.isdir(os.path.join(ROOT, "site", "stock"))
                     for r in guide_redirects)
    check("indexation: the 10 retired AI guides redirect permanently (with and without slash) to pages that exist",
          len(guide_redirects) == 20 and all(r.get("permanent") is True for r in guide_redirects) and targets_ok,
          "n=%d" % len(guide_redirects))
    news_map = os.path.join(ROOT, "site", "sitemaps", "sitemap-news.xml")
    if os.path.isfile(news_map):
        nm = _read(news_map)
        redirected = {r["source"].strip("/").split("/")[-1] for r in vj2.get("redirects", []) if r.get("source", "").startswith("/news/")}
        listed = dict(re.findall(r"<loc>[^<]*/news/([^/<]+)/</loc><lastmod>([^<]+)</lastmod>", nm))
        stale_dates = {s: d for s, d in listed.items() if re.search(r"\d{4}-\d{2}-\d{2}", s)
                       and d != re.search(r"\d{4}-\d{2}-\d{2}", s).group(0)}
        check("indexation: the news sitemap never lists a redirected (retired) article",
              not (redirected & set(listed)), str(sorted(redirected & set(listed))[:3]))
        check("indexation: archived dated news pages carry their own date as lastmod, not the build date (%d listed)" % len(listed),
              listed and not stale_dates, str(list(stale_dates.items())[:3]))

    # ---- retired-URL redirect targets always stay indexable ------------------------
    # The build noindexes anything outside the sitemap; a stock whose retired per-year URL
    # still ranks must therefore be in the sitemap, or the redirect lands on a noindexed page
    # (240 such targets on 7 Nov 2026).
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    try:
        import gsc_report as GR
    except Exception as e:  # noqa: BLE001
        GR = None
        check("indexation: scripts/gsc_report.py importable", False, repr(e))
    if GR:
        tmpd = tempfile.mkdtemp(prefix="qa_demand_")
        old_path, old_api = GR.DEMAND_PATH, GR.gsc._api
        try:
            GR.DEMAND_PATH = os.path.join(tmpd, "stock_demand.json")
            fake = {"rows": [
                {"keys": ["https://www.brokerlens.in/stock/aaa/share-price-target-2030/"], "impressions": 1},
                {"keys": ["https://www.brokerlens.in/stock/bbb/"], "impressions": 3},
                {"keys": ["https://www.brokerlens.in/stock/ccc/"], "impressions": 6}]}
            GR.gsc._api = lambda *a, **k: fake
            import datetime as _dt
            GR.update_stock_demand("t", _dt.date(2026, 10, 1), _dt.date(2026, 10, 28))
            got = set(json.load(open(GR.DEMAND_PATH))["slugs"])
            check("indexation: a stock whose retired price-target URL took even one impression joins the sitemap demand "
                  "list; a canonical page still needs the normal threshold",
                  got == {"aaa", "ccc"}, str(sorted(got)))
        finally:
            GR.DEMAND_PATH, GR.gsc._api = old_path, old_api
            shutil.rmtree(tmpd, ignore_errors=True)

    # ---- pages with real search demand stay indexable; past IPOs never vanish ----------
    tmp3 = tempfile.mkdtemp(prefix="qa_demand_sitemap_")
    old_root = pub.ROOT
    try:
        pub.ROOT = tmp3
        os.makedirs(os.path.join(tmp3, "reports", "gsc"))

        def mk(rel, robots="", canon=None):
            d = os.path.join(tmp3, "site", rel)
            os.makedirs(d, exist_ok=True)
            c = canon if canon is not None else pub.SITE_URL + "/" + rel + "/"
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
                fh.write('<html><head><link rel="canonical" href="%s">%s</head><body>x</body></html>' % (c, robots))
        mk("compare/stocks/aaa-vs-bbb")
        mk("broker/x/branches/pune", robots='<meta name="robots" content="noindex,follow">')
        mk("sebi-registry/old-slug", canon=pub.SITE_URL + "/sebi-registry/new-slug/")
        mk("broker/x/trade/aaa")
        with open(os.path.join(tmp3, "reports", "gsc", "page_demand.json"), "w") as fh:
            json.dump({"paths": ["/compare/stocks/aaa-vs-bbb/", "/broker/x/branches/pune/", "/sebi-registry/old-slug/",
                                 "/broker/x/trade/aaa/", "/stock/never-built/"]}, fh)
        got = [re.search(r"<loc>([^<]+)</loc>", e).group(1) for e in pub._demand_sitemap_entries(
            lambda loc, lm, fq="monthly": "<url><loc>%s</loc></url>" % loc, "2026-11-07")]
        check("indexation: a page with real impressions stays in the sitemap (so the allowlist keeps it indexable), "
              "but never a noindex, non-canonical, trade-cost or unbuilt page",
              got == [pub.SITE_URL + "/compare/stocks/aaa-vs-bbb/"], str(got))

        archive = os.path.join(tmp3, "ipo_archive.json")
        with open(archive, "w") as fh:
            json.dump({"past": [{"symbol": "LAURUSLABS", "listing_date": "2016-12-19", "issue_price": 428.0},
                                {"symbol": "OLDNAME", "listing_date": "2020-01-01", "issue_price": 10.0}]}, fh)
        old_arch = pub.IPO_ARCHIVE_PATH
        pub.IPO_ARCHIVE_PATH = archive
        try:
            merged = pub._with_ipo_archive({"past": [{"symbol": "OLDNAME", "listing_date": "2020-01-01", "issue_price": 11.0},
                                                     {"symbol": "NEWIPO", "listing_date": "2026-11-05", "issue_price": 50.0}]})
        finally:
            pub.IPO_ARCHIVE_PATH = old_arch
        syms = {r["symbol"]: r for r in merged["past"]}
        check("indexation: a past IPO NSE's feed no longer returns keeps its page (archive), and fresh data wins for a symbol",
              set(syms) == {"LAURUSLABS", "OLDNAME", "NEWIPO"} and syms["OLDNAME"]["issue_price"] == 11.0
              and json.load(open(archive))["past"][-1]["symbol"] == "NEWIPO", str(sorted(syms)))
    finally:
        pub.ROOT = old_root
        shutil.rmtree(tmp3, ignore_errors=True)
    stored = (load("data/manual/ipo_archive.json") or {}).get("past") or []
    check("indexation: the committed IPO archive holds the long history (UTI AMC, Laurus Labs, KFintech on file)",
          len(stored) >= 1000 and {"UTIAMC", "LAURUSLABS", "KFINTECH"} <= {r.get("symbol") for r in stored}, "n=%d" % len(stored))
    news_src = _read(os.path.join(ROOT, "pipeline", "news_engine.py"))
    muh = news_src[news_src.find("diwali-muhurat-trading-2026-timings-schedule-guide"):][:9000]
    if muh:
        check("indexation: the Muhurat 2026 article's equity timings match NSE circular 149/2026 and cite it",
              "13:50 to 14:05" in muh and "14:20 to 15:30" in muh and "NSE/CMTR/76941" in muh
              and "13:45 to 14:00" not in muh and "14:15 to 15:15" not in muh)
    # NSE renamed securityType in public-past-issues ("EQ" -> "Equity", IV -> InvIT, RR -> REIT)
    # and the IPO filter silently dropped every mainboard IPO (~490 pages 404, 5 to 7 Nov 2026).
    from pipeline.sources import nse as _nse
    check("indexation: NSE's old and new securityType spellings normalise to the codes the IPO filter keeps",
          [_nse._sec_type(x) for x in ("Equity", "EQ", "SME", "InvIT", "REIT", "DEBT", None)]
          == ["EQ", "EQ", "SME", "IV", "RR", "DEBT", None]
          and "EQ" in pub._IPO_SEC_TYPES and _nse._sec_type("Equity") in pub._IPO_SEC_TYPES)
    wf = _read(os.path.join(ROOT, ".github", "workflows", "daily-refresh.yml"))
    check("indexation: the nightly rebuild deploys only through ci.yml's QA + VAPT gate, never the bare deploy hook",
          "gh workflow run ci.yml" in wf and "DEPLOY_HOOK" not in wf)
