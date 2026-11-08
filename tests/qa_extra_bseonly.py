"""BSE-only stock pages (pipeline/bse_only.py, sources/bse.py's bse_only_history).

Loaded by tests/qa_e2e.py as run(check, ROOT, load). The archive logic is exercised
against a temporary file, never the committed one."""
import json
import os
import re
import shutil
import sys
import tempfile


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def run(check, ROOT, load):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from pipeline import bse_only
    from pipeline import publish as pub
    from pipeline.sources import bse as bsrc

    # ---- 1. identity rules ------------------------------------------------------
    check("bse-only: a split re-issues the ISIN serial but the issuer key stays the same (Bansal Wire)",
          bsrc.isin_issuer_key("INE0B9K01025") == bsrc.isin_issuer_key("INE0B9K01033") == "INE0B9K01")
    check("bse-only: only equity-share ISINs count (fund units, debt and rights are not companies to page)",
          bsrc.is_equity_isin("INE301O01023") and not bsrc.is_equity_isin("INF109K01Z48")
          and not bsrc.is_equity_isin("INE301O08010") and bsrc.isin_issuer_key("INF109K01Z48") is None)
    check("bse-only: names keep their real casing; capitals are title-cased only as a last resort",
          bsrc._display_name("BMW INDUSTRIES LIMITED", "BMW Industries Ltd") == "BMW Industries Ltd"
          and bsrc._display_name("Chandrima Mercantiles limited", "") == "Chandrima Mercantiles Limited"
          and bsrc._display_name("", "NHC FOODS LTD") == "Nhc Foods Ltd")
    check("bse-only: with no NSE list to compare against, nothing is called BSE-only",
          bsrc.bse_only_history(None, set()) is None and bsrc.bse_only_history(None, {"INE000001"}) is None)
    check("bse-only: SME and non-equity groups stay out; Z stays in (its page names the group)",
          set(bsrc.MAINBOARD_GROUPS) == {"A", "B", "T", "X", "XT", "Z"})

    # ---- 2. the committed list only grows ---------------------------------------
    tmp = tempfile.mkdtemp(prefix="qa-bseonly-")
    old_path = bse_only.ARCHIVE_PATH
    try:
        bse_only.ARCHIVE_PATH = os.path.join(tmp, "bse_only_equities.json")
        nse = [{"symbol": "NSE%04d" % i, "isin": "INE%04d01011" % i} for i in range(1600)]
        nse.append({"symbol": "TAKEN", "isin": "INE999Z01011"})
        def scrip(code, sym, isin, liquid=True):
            return {"code": code, "symbol": sym, "name": sym.title() + " Ltd", "isin": isin, "group": "X",
                    "liquid": liquid, "master": True, "candles": [{"date": "2026-11-06", "close": 10.0}], "mktcap_cr": 100.0}
        day1 = {"scrips": {"1": scrip("1", "ALPHA", "INEAAAA01011"), "2": scrip("2", "BETA", "INEBBBB01011", False),
                           "3": scrip("3", "TAKEN", "INECCCC01011")}}
        s1, _f = bse_only.load_universe(day1, nse, pub._stock_slug, today="2026-11-08")
        check("bse-only: a liquid BSE-only company joins; an illiquid one and one whose URL an NSE stock owns do not",
              [s["slug"] for s in s1] == ["alpha"], str([s["slug"] for s in s1]))
        s2, _f = bse_only.load_universe(None, nse, pub._stock_slug, today="2026-11-09")
        check("bse-only: a day with no BSE data keeps every page (no 404s from an outage)",
              [s["slug"] for s in s2] == ["alpha"] and s2[0]["added"] == "2026-11-08")
        trunc = {"scrips": {"1": dict(scrip("1", "ALPHA", "INEAAAA01011"), name="Alpha Industries And Infrastruc", master=False),
                            "9": scrip("9", "GAMMA", "INEGGGG01011") | {"master": False}}}
        s2b, _f = bse_only.load_universe(trunc, nse, pub._stock_slug, today="2026-11-09")
        check("bse-only: without BSE's scrip list, a bhavcopy-only record neither renames a page nor adds one",
              [(s["slug"], s["name"]) for s in s2b] == [("alpha", "Alpha Ltd")], str([(s["slug"], s["name"]) for s in s2b]))
        s3, _f = bse_only.load_universe(None, nse[:100], pub._stock_slug, today="2026-11-09")
        check("bse-only: a partial NSE list never retires a page", [s["slug"] for s in s3] == ["alpha"])
        s4, _f = bse_only.load_universe(None, nse + [{"symbol": "ALPHANEW", "isin": "INEAAAA01029"}],
                                        pub._stock_slug, today="2026-11-10")
        check("bse-only: a company that lists on NSE (same issuer, any serial) leaves the BSE-only list",
              s4 == [] and json.load(open(bse_only.ARCHIVE_PATH))["scrips"] == {})
    finally:
        bse_only.ARCHIVE_PATH = old_path
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 3. wiring ----------------------------------------------------------------
    run_src = _read(os.path.join(ROOT, "pipeline", "run.py"))
    check("bse-only: the fetch hands BSE the NSE issuer keys and the codes that already have pages",
          "bse_src.collect(wl.get(\"bse\"), _nse_issuer_keys(out.get(\"nse\")), _bse_only_codes())" in run_src)
    check("bse-only: the sitemap family is submitted in wave 1", pub.SITEMAP_WAVES.get("stocks-bse") == 1)

    # ---- 4. the built pages ---------------------------------------------------------
    archive = (load("data/manual/bse_only_equities.json") or {}).get("scrips") or {}
    check("bse-only: the committed list holds the BSE-only companies (NSDL among them)",
          len(archive) >= 200 and any(s.get("slug") == "nsdl" for s in archive.values()), "n=%d" % len(archive))
    site = os.path.join(ROOT, "site")
    if not os.path.isdir(os.path.join(site, "stock")):
        return
    nse_slugs = {pub._stock_slug(c.get("symbol")) for c in
                 (((load("data/_ingest.json") or {}).get("nse") or {}).get("universe") or {}).get("companies") or []}
    expected = sorted(s["slug"] for s in archive.values() if s["slug"] not in nse_slugs)
    missing = [s for s in expected if not os.path.exists(os.path.join(site, "stock", s, "index.html"))]
    check("bse-only: every company on the list has its /stock/ page", not missing, str(missing[:5]))
    smap = _read(os.path.join(site, "sitemaps", "sitemap-stocks-bse.xml"))
    listed = set(re.findall(r"/stock/([a-z0-9-]+)/</loc>", smap))
    check("bse-only: every page is in the stocks-bse sitemap (outside it the build would noindex it)",
          set(expected) <= listed and "/stocks/bse/</loc>" in smap, "missing %s" % sorted(set(expected) - listed)[:5])
    check("bse-only: the sitemap index lists the stocks-bse shard",
          "sitemap-stocks-bse.xml" in _read(os.path.join(site, "sitemap.xml")))
    nsdl = _read(os.path.join(site, "stock", "nsdl", "index.html"))
    if nsdl:
        desc = (re.search(r'<meta name="description" content="([^"]*)"', nsdl) or [None, ""])[1]
        check("bse-only: the NSDL page says BSE, names its scrip code and never claims NSE data",
              "BSE: NSDL &middot; Scrip code 544467" in nsdl and "(BSE: NSDL)" in desc and "(NSE:" not in desc
              and "NSE's bhavcopy" not in nsdl and "NSE daily" not in nsdl and "NSE's listed-securities" not in nsdl)
        check("bse-only: the NSDL page is indexable, self-canonical, with Corporation and FAQPage JSON-LD",
              "noindex" not in nsdl and 'rel="canonical" href="https://www.brokerlens.in/stock/nsdl/"' in nsdl
              and '"Corporation"' in nsdl and '"FAQPage"' in nsdl)
        check("bse-only: the page states the listing fact and the BSE group in words",
              "Listed only on BSE" in nsdl and "Is National Securities Depository Limited listed on NSE?" in nsdl
              and "group A" in nsdl)
        check("bse-only: the page links back to the hub and to other BSE-only stocks",
              nsdl.count('href="/stocks/bse/"') >= 2 and "Other BSE-only stocks of a similar size" in nsdl)
    hub = _read(os.path.join(site, "stocks", "bse", "index.html"))
    check("bse-only: the hub links every BSE-only page",
          hub and all('href="/stock/%s/"' % s in hub for s in expected))
    check("bse-only: the A-Z stock index links the hub",
          'href="/stocks/bse/"' in _read(os.path.join(site, "stocks", "index.html")))
    rel = _read(os.path.join(site, "stock", "reliance", "index.html"))
    if rel:
        check("bse-only: NSE stock pages keep their NSE wording (exchange label defaults to NSE)",
              "NSE's bhavcopy" in rel and "(NSE: RELIANCE)" in rel and "NSE and BSE websites" in rel)
    rows = load("site/data/search.json") or []
    check("bse-only: site search finds BSE-only stocks", any(r[1] == "/stock/nsdl/" for r in rows))
