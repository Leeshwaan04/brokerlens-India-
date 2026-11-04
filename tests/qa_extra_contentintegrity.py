"""Regression checks for content-integrity bugs fixed in commit f9dc713
(area: contentintegrity): honest GMP trend, real news losers/active count,
no FAQ dashes on broker-compare pages, no mega-cap "same sector" mislabel,
sitemap-wave gating for a newly added page family, and market share divided
by NSE's exchange-wide total rather than the sum of tracked brokers.

Exposes run(check, ROOT, load) like every tests/qa_extra_<area>.py module.

Each check calls the real pipeline function on a small synthetic fixture (no
dependency on a full site build, and no reliance on the already-built site/
output, which can be stale relative to the pipeline source -- see the
compare-page check below). Functions that write files are pointed at a fresh
tempfile.mkdtemp() by monkeypatching pipeline.publish's ROOT/SITE_DATA for the
duration of the call, then restored, so this file never touches the real
site/ tree.
"""
import datetime
import os
import re
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def run(check, ROOT, load):
    sys.path.insert(0, ROOT)

    # ------------------------------------------------------------------
    # 1. gmp_trend(): the "Rising Sentiment" badge must track the actual
    #    recorded GMP history, not a static hand-set field that can read
    #    "up" forever even after the value has been frozen for days.
    # ------------------------------------------------------------------
    try:
        from pipeline.ipo_facts import gmp_trend
    except ImportError as e:
        gmp_trend = None
        check("contentintegrity: pipeline.ipo_facts.gmp_trend importable", False, str(e))

    if gmp_trend:
        frozen = {"trend": "up", "history": [
            {"date": "2026-10-26", "gmp": 40.0}, {"date": "2026-10-27", "gmp": 40.0},
            {"date": "2026-10-28", "gmp": 40.0}, {"date": "2026-10-29", "gmp": 40.0},
            {"date": "2026-10-30", "gmp": 40.0},
        ]}
        rising = {"trend": "down", "history": [{"date": "2026-10-29", "gmp": 40.0}, {"date": "2026-10-30", "gmp": 55.0}]}
        falling = {"trend": "up", "history": [{"date": "2026-10-29", "gmp": 55.0}, {"date": "2026-10-30", "gmp": 40.0}]}
        single_point = {"trend": "down", "history": [{"date": "2026-10-30", "gmp": 40.0}]}
        no_history = {"trend": "neutral", "history": []}

        check("contentintegrity: gmp_trend() reports 'neutral' for a value frozen across the last two "
              "recorded sessions, regardless of the stale static 'trend' field",
              gmp_trend(frozen) == "neutral", "got %r" % gmp_trend(frozen))
        check("contentintegrity: gmp_trend() reports 'up'/'down' from the last two distinct history points, "
              "overriding a contradictory static 'trend' field",
              gmp_trend(rising) == "up" and gmp_trend(falling) == "down",
              "rising=%r falling=%r" % (gmp_trend(rising), gmp_trend(falling)))
        check("contentintegrity: gmp_trend() falls back to the static field only when there isn't enough "
              "history to derive a real trend (single point / no history)",
              gmp_trend(single_point) == "down" and gmp_trend(no_history) == "neutral")

        # The fix's whole point was that this helper is the single source of truth used
        # by the per-IPO page, the /ipo/gmp/ hub, and the news bulletin alike -- guard
        # against a future change re-introducing a second, independent trend computation.
        ipo_facts_src = _read(ROOT, "pipeline", "ipo_facts.py")
        news_engine_src = _read(ROOT, "pipeline", "news_engine.py")
        check("contentintegrity: render_gmp_section derives trend via the shared gmp_trend() helper, "
              "not a hand-set field",
              "trend = gmp_trend(gmp_info)" in ipo_facts_src
              and 'gmp_info.get("trend", "up")' not in ipo_facts_src)
        check("contentintegrity: the news market-wrap GMP bulletin uses the same gmp_trend() helper "
              "instead of its own str(ginfo.get('trend')...) computation",
              "ipo_facts.gmp_trend(ginfo)" in news_engine_src)

    # ------------------------------------------------------------------
    # 2. Broker-compare FAQ / JSON-LD must never interpolate literal "-"
    #    placeholders when the underlying sample dataset is withheld; it
    #    must degrade to an honest sentence instead. Exercised on the real
    #    pipeline.publish._write_compare_pages() with two brokers that have
    #    no clients/charges/complaints data, written to a throwaway temp
    #    dir (NOT the already-built site/, which predates this fix and
    #    would still show the old "- active clients" text).
    # ------------------------------------------------------------------
    try:
        import pipeline.publish as P
    except ImportError as e:
        P = None
        check("contentintegrity: pipeline.publish importable", False, str(e))

    if P:
        tmp = tempfile.mkdtemp(prefix="qa_contentintegrity_cmp_")
        old_root, old_data = P.ROOT, P.SITE_DATA
        P.ROOT = tmp
        P.SITE_DATA = os.path.join(tmp, "site", "data")
        os.makedirs(P.SITE_DATA, exist_ok=True)
        page = ""
        try:
            overview = {"brokers": [
                {"id": "qa-broker-a", "brand": "QA Broker A", "clients": 0},
                {"id": "qa-broker-b", "brand": "QA Broker B", "clients": 0},
            ]}
            built = [
                {"id": "qa-broker-a", "profile": {"brand": "QA Broker A", "type": "discount", "hq": "Mumbai",
                                                   "founded": 2020, "sebi_reg_no": "INZ000000001", "segments": ["equity"]},
                 "clients": {}, "charges": {}, "complaints": {}, "reliability": {}, "cost": {}, "regulatory_flags": {}},
                {"id": "qa-broker-b", "profile": {"brand": "QA Broker B", "type": "full_service", "hq": "Delhi",
                                                   "founded": 1990, "sebi_reg_no": "INZ000000002", "segments": ["equity"]},
                 "clients": {}, "charges": {}, "complaints": {}, "reliability": {}, "cost": {}, "regulatory_flags": {}},
            ]
            P._write_compare_pages(overview, built)
            page_path = os.path.join(tmp, "site", "compare", "qa-broker-a-vs-qa-broker-b", "index.html")
            if os.path.exists(page_path):
                with open(page_path, encoding="utf-8") as fh:
                    page = fh.read()
        except Exception as e:  # noqa: BLE001 - surface as a failed check, not a crash
            check("contentintegrity: _write_compare_pages() runs on a broker pair with no sample data", False, repr(e))
        finally:
            P.ROOT, P.SITE_DATA = old_root, old_data

        check("contentintegrity: _write_compare_pages() produced a page for the synthetic withheld pair",
              bool(page))
        if page:
            dash_artifacts = (
                " active clients (- market share)" in page or "(- market share)" in page
                or "AMC is -." in page or "delivery is -" in page or "charges is -" in page
                or "(- vs -)" in page
            )
            check("contentintegrity: broker-compare FAQ/JSON-LD never interpolates a literal '-' into prose "
                  "when the sample dataset is withheld (the exact bug fixed for 'Zerodha has - active "
                  "clients (- market share)')",
                  not dash_artifacts, "dash artifact found in generated page")
            check("contentintegrity: withheld broker-compare FAQs degrade to an honest sentence instead",
                  "not yet published from NSE's member-wise UCC disclosures" in page
                  and "not independently verified against each broker's own rate card" in page)
            check("contentintegrity: footer no longer cites an active-client disclosure source that isn't "
                  "actually used when that data is withheld",
                  "NSE monthly active client disclosures" not in page)

    # ------------------------------------------------------------------
    # 3. "Mega-Cap Cross Leaders" is a market-cap bucket, not a GICS
    #    sector: its FAQ must not claim the paired stocks "operate within
    #    the same sector" when they are actually unrelated industries.
    # ------------------------------------------------------------------
    try:
        from pipeline.stock_compare_engine import render_stock_comparison_page
    except ImportError as e:
        render_stock_comparison_page = None
        check("contentintegrity: pipeline.stock_compare_engine.render_stock_comparison_page importable", False, str(e))

    if render_stock_comparison_page:
        s1 = {"symbol": "RELI", "name": "Reliance Industries"}
        s2 = {"symbol": "TCSX", "name": "Tata Consultancy Services"}
        m1 = {"window_days": 252, "return_1y": 12.0, "volatility_30d": 18.0, "cmp": 2500.0,
              "high_52w": 2600.0, "low_52w": 2100.0, "avg_volume": 1000000}
        m2 = {"window_days": 252, "return_1y": 8.0, "volatility_30d": 15.0, "cmp": 3800.0,
              "high_52w": 4000.0, "low_52w": 3300.0, "avg_volume": 800000}

        megacap_html = render_stock_comparison_page(s1, m1, s2, m2, "Mega-Cap Cross Leaders")
        check("contentintegrity: a Mega-Cap Cross Leaders pairing never claims the two stocks "
              "'operate within the ... sector' (they are a market-cap bucket, not a GICS sector)",
              "operate within the Mega-Cap Cross Leaders sector" not in megacap_html
              and "in the Mega-Cap Cross Leaders sector" not in megacap_html)
        check("contentintegrity: a Mega-Cap Cross Leaders pairing's FAQ honestly says it's a market-cap "
              "grouping and tells the reader to check each stock's own sector",
              "grouped here by market" in megacap_html and "capitalisation, not by industry" in megacap_html)

        # Regression guard the other direction: a real curated sector pairing must still
        # claim the shared sector (the fix must not have broken the true-sector branch).
        real_sector_html = render_stock_comparison_page(s1, m1, s2, m2, "Oil & Gas")
        check("contentintegrity: a real curated sector pairing still claims the shared sector "
              "(the mega-cap fix did not regress the true-sector FAQ branch)",
              "operate within the Oil & Gas sector" in real_sector_html)

    # ------------------------------------------------------------------
    # 4. Market-wrap news articles must show real NSE losers and a real
    #    active-equities count, not the "Key Consolidators" fallback copy
    #    and a hardcoded "2,578" on every single build.
    # ------------------------------------------------------------------
    try:
        from pipeline.news_engine import generate_news_corpus
    except ImportError as e:
        generate_news_corpus = None
        check("contentintegrity: pipeline.news_engine.generate_news_corpus importable", False, str(e))

    if generate_news_corpus:
        today_iso = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        wrap_slug = "indian-stock-market-wrap-%s" % today_iso

        with_data = {"nse": {
            "pulse": {"indices": [{"last": 25000.0, "change": 10.0, "change_pct": 0.1}],
                      "breadth": {"advances": 1200, "declines": 800}},
            "live": {"gainers": [{"symbol": "ABC", "last": 100.0, "change_pct": 2.0}],
                     "losers": [{"symbol": "QAXYZCORP", "last": 50.0, "change_pct": -3.5}],
                     "most_active": []},
            "universe": ["SYM%d" % i for i in range(3142)],
            "ipo": {},
        }}
        arts = generate_news_corpus(with_data, site_url="https://www.brokerlens.in")
        wrap = next((a for a in arts if a.get("slug") == wrap_slug), None)
        check("contentintegrity: generate_news_corpus() emits the daily market-wrap article", wrap is not None)
        if wrap:
            body = wrap.get("body_html", "")
            check("contentintegrity: market-wrap 'Key Consolidators' list shows a real NSE loser when "
                  "collect() supplied one, not the generic consolidation placeholder",
                  "QAXYZCORP" in body and "Equities tracking broader market consolidation" not in body)
            check("contentintegrity: market-wrap 'Active Equities' stat reflects the real ingested "
                  "universe size, not the hardcoded 2,578",
                  "3,142" in body and "2,578" not in body)

        without_data = {"nse": {
            "pulse": {"indices": [{"last": 25000.0, "change": 10.0, "change_pct": 0.1}],
                      "breadth": {"advances": 1200, "declines": 800}},
            "live": {"gainers": [], "losers": [], "most_active": []},
            "ipo": {},
        }}
        arts2 = generate_news_corpus(without_data, site_url="https://www.brokerlens.in")
        wrap2 = next((a for a in arts2 if a.get("slug") == wrap_slug), None)
        if wrap2:
            body2 = wrap2.get("body_html", "")
            check("contentintegrity: market-wrap falls back to the honest placeholder (not a fabricated "
                  "loser) when NSE supplied none, and to 2,578 only when no universe was ingested at all",
                  "Equities tracking broader market consolidation" in body2 and "2,578" in body2)

    # ------------------------------------------------------------------
    # 5. Sitemap wave gating: a page family tagged wave 2+ in SITEMAP_WAVES
    #    must be held back from sitemap.xml while SITEMAP_WAVE=1, and
    #    included once promoted -- silently losing this would either leak
    #    thin/unready content to Google early or strand a healthy family
    #    (e.g. stock-compare, added this session) out of the index forever.
    # ------------------------------------------------------------------
    if P:
        tmp2 = tempfile.mkdtemp(prefix="qa_contentintegrity_wave_")
        old_root, old_data = P.ROOT, P.SITE_DATA
        old_wave_env = os.environ.get("SITEMAP_WAVE")
        P.ROOT = tmp2
        P.SITE_DATA = os.path.join(tmp2, "site", "data")
        os.makedirs(P.SITE_DATA, exist_ok=True)
        idx_wave1 = idx_wave2 = ""
        try:
            os.environ["SITEMAP_WAVE"] = "1"
            P._write_sitemap([], stock_compare_urls=["/compare/stocks/qa-a-vs-qa-b/"])
            sitemap_path = os.path.join(tmp2, "site", "sitemap.xml")
            if os.path.exists(sitemap_path):
                with open(sitemap_path, encoding="utf-8") as fh:
                    idx_wave1 = fh.read()

            os.environ["SITEMAP_WAVE"] = "2"
            P._write_sitemap([], stock_compare_urls=["/compare/stocks/qa-a-vs-qa-b/"])
            if os.path.exists(sitemap_path):
                with open(sitemap_path, encoding="utf-8") as fh:
                    idx_wave2 = fh.read()
        except Exception as e:  # noqa: BLE001
            check("contentintegrity: _write_sitemap() runs with SITEMAP_WAVE set", False, repr(e))
        finally:
            P.ROOT, P.SITE_DATA = old_root, old_data
            if old_wave_env is None:
                os.environ.pop("SITEMAP_WAVE", None)
            else:
                os.environ["SITEMAP_WAVE"] = old_wave_env

        if idx_wave1 or idx_wave2:
            check("contentintegrity: a wave-2 page family (stock-compare, SITEMAP_WAVES[...]=2) is held "
                  "back from sitemap.xml while SITEMAP_WAVE=1 ...",
                  "sitemap-stock-compare" not in idx_wave1)
            check("contentintegrity: ... and is submitted once SITEMAP_WAVE is promoted to 2",
                  "sitemap-stock-compare" in idx_wave2)
            check("contentintegrity: core (wave 1) URLs are always submitted regardless of the "
                  "current wave",
                  "sitemap-core" in idx_wave1 and "sitemap-core" in idx_wave2)

    # ------------------------------------------------------------------
    # 6. Market share divides by NSE's exchange-wide total from Report 1C,
    #    not by the sum of the brokers this site tracks, which overstated
    #    every share (Zerodha read 16.85% against its real 14.73%).
    # ------------------------------------------------------------------
    if P:
        from pipeline import metrics as M
        real = {"provenance": "nse_ucc", "exchange_active_clients": {"2026-09": 46120857},
                "brokers": {"zerodha": [["2026-09", 6791541]], "groww": [["2026-09", 13448194]]}}
        totals = P._market_totals(real)
        share = M.client_metrics(real["brokers"]["zerodha"], totals).get("market_share_pct")
        check("contentintegrity: market share for real (nse_ucc) data divides by NSE's exchange-wide "
              "total, not the sum of tracked brokers",
              totals == {"2026-09": 46120857} and share == round(6791541 / 46120857 * 100, 3), "share=%r" % share)
        gap = P._market_totals({"provenance": "nse_ucc", "exchange_active_clients": {"2026-09": None},
                                "brokers": real["brokers"]})
        check("contentintegrity: a real month with no exchange total gets no market share, never an "
              "overstated tracked-broker one",
              gap == {} and M.client_metrics(real["brokers"]["zerodha"], gap).get("market_share_pct") is None)
        check("contentintegrity: non-NSE data keeps the tracked-broker sum (sample data is dropped in "
              "production anyway)",
              P._market_totals({"provenance": "sample", "brokers": real["brokers"]}) == {"2026-09": 6791541 + 13448194})

    try:
        from pipeline.run import _merge_exchange_totals
    except ImportError as e:
        _merge_exchange_totals = None
        check("contentintegrity: pipeline.run._merge_exchange_totals importable", False, str(e))
    if _merge_exchange_totals:
        prior = {"provenance": "nse_ucc", "exchange_active_clients": {"2026-09": 46120857}}
        check("contentintegrity: report1c keeps earlier months' exchange totals (a later run must not "
              "erase the denominator that older shares and year-on-year change need), never seeds from "
              "the sample file, and skips a month whose total was not parsed",
              _merge_exchange_totals(prior, "2026-10", 46500000) == {"2026-09": 46120857, "2026-10": 46500000}
              and _merge_exchange_totals({"provenance": "sample", "exchange_active_clients": {"2026-08": 1}},
                                         "2026-10", 46500000) == {"2026-10": 46500000}
              and _merge_exchange_totals(prior, "2026-10", None) == {"2026-09": 46120857})

    # ------------------------------------------------------------------
    # 7. Report 1C attribution: a loose token match once gave Bajaj Broking
    #    the 20 clients of an unrelated firm, overwriting its own 66,938.
    # ------------------------------------------------------------------
    try:
        from pipeline.run import _match_report1c, _merge_complaints
        from pipeline.identity import Resolver
    except ImportError as e:
        _match_report1c = None
        check("contentintegrity: report1c matcher importable", False, str(e))
    if _match_report1c:
        master = load("config/brokers_master.json") or {}
        res = Resolver(master.get("brokers", []))

        def member(name, n, defaulter=False):
            return {"name": name, "active_clients": n, "defaulter": defaulter, "ucc_start_of_year": None}
        counts, _d, notes = _match_report1c([member("Bajaj Financial Securities Ltd.", 66938),
                                             member("Bajaj Share & Stock Brokers Pvt. Ltd", 20)], res)
        check("contentintegrity: report1c trusts only exact or suffix-only name matches, so an unrelated "
              "firm's count never lands on a tracked broker (real Sep 2026 Bajaj pair)",
              counts.get("bajaj-broking") == 66938 and any("token" in n for n in notes), str(counts))
        counts2, _d2, notes2 = _match_report1c([member("Bajaj Financial Securities Ltd.", 66938),
                                                member("Bajaj Financial Securities Limited", 5)], res)
        check("contentintegrity: a broker claimed by two trusted Report 1C rows is published for neither",
              "bajaj-broking" not in counts2 and any("published for neither" in n for n in notes2), str(counts2))

        prior = {"provenance": "sebi_annexure_b", "brokers": {
            "hdfc-securities": [{"month": "2026-09", "received": 58, "resolved": 92, "pending": 14}],
            "kotak-securities": [{"month": "2026-09", "received": 182, "resolved": 180, "pending": 34}]}}
        fresh = {"hdfc-securities": [{"month": "2026-10", "received": 40, "resolved": 41, "pending": 13}]}
        merged = _merge_complaints(prior, fresh)
        check("contentintegrity: complaint months accumulate across runs (HDFC shows one month per page) "
              "and a broker whose fetch failed this run keeps its history",
              [r["month"] for r in merged["hdfc-securities"]] == ["2026-09", "2026-10"]
              and merged["kotak-securities"][0]["received"] == 182
              and _merge_complaints({"provenance": "sample", "brokers": prior["brokers"]}, fresh)
              == {"hdfc-securities": fresh["hdfc-securities"]})

    # ------------------------------------------------------------------
    # 8. Annexure-B parsing: only the single-month source table's Grand Total
    #    may take the page's month. A trend table's cumulative Grand Total
    #    once stamped Sep 2026 with 31,319 complaints instead of 182.
    # ------------------------------------------------------------------
    try:
        from pipeline.sources import complaints as CS
    except ImportError as e:
        CS = None
        check("contentintegrity: complaints source importable", False, str(e))
    if CS:
        def tbl(rows):
            return "<table>%s</table>" % "".join(
                "<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows)
        source = tbl([["SN", "Received from", "Carried forward from previous month", "Received during the month",
                       "Total Pending", "Resolved*", "Pending at the end of the month"],
                      ["1", "Directly from Investors", "3", "14", "17", "16", "1"],
                      ["2", "SEBI (SCORES)", "40", "40", "80", "70", "10"],
                      ["", "Grand Total", "48", "58", "106", "92", "14"]])
        annual = tbl([["SN", "Year", "Carried forward from previous year", "Received during the year",
                       "Resolved during the year", "Pending at the end of the year"],
                      ["1", "2021-2022", "84", "8636", "8647", "73"],
                      ["", "Grand Total", "352", "31319", "31369", "302"]])
        page = "<html><head><title>Investor Complaints Sep 2026</title></head><body>%s%s</body></html>" % (source, annual)
        parsed, _why = CS.parse_annexure_b(page, "https://example.test/")
        check("contentintegrity: a trend table's cumulative Grand Total is never stamped as the page's month, "
              "while the source table's total still is",
              [(r["month"], r["received"], r["resolved"], r["pending"]) for r in parsed] == [("2026-09", 58, 92, 14)],
              str(parsed))

        class _Fetch:
            def __init__(self, pages):
                self.pages, self.tried, self.ttls = pages, [], set()

            def get_text(self, url, ttl=None, retries=None):
                self.tried.append(url.rsplit("-", 2)[-2])
                self.ttls.add(ttl)
                return self.pages.get(url)
        tmpl = "https://example.test/complaints-{mon}-{year}"
        fake = _Fetch({tmpl.format(mon="oct", year=2026): "<html><body>Page not found</body></html>",
                       tmpl.format(mon="sep", year=2026): page})
        url, _html = CS._resolve_monthly_url(fake, tmpl, CS.parse_annexure_b, 60,
                                             today=datetime.datetime(2026, 11, 3, tzinfo=datetime.timezone.utc))
        check("contentintegrity: monthly URL resolver starts at last month, steps past a soft-404 page, "
              "and honours the caller's cache ttl",
              url == tmpl.format(mon="sep", year=2026) and fake.tried == ["oct", "sep"] and fake.ttls == {60},
              "url=%s tried=%s ttls=%s" % (url, fake.tried, fake.ttls))

    # ------------------------------------------------------------------
    # 9. Report 1C sheet walk: a blank spacer row must not end the member
    #    list, and the exchange total is found anywhere in the header block.
    # ------------------------------------------------------------------
    try:
        from pipeline.sources import nse_report1c as R1
    except ImportError as e:
        R1 = None
        check("contentintegrity: nse_report1c importable", False, str(e))
    if R1:
        class _Sheet:
            def __init__(self, cells, nrows):
                self.cells, self.nrows = cells, nrows

            def cell_value(self, r, c):
                return self.cells.get((r, c), "")
        cells = {(6, R1.COL_NAME): "Total number of active clients", (6, R1.COL_NAME + 1): 46120857.0}
        for r, (name, n) in enumerate([("Member A Ltd.", 100.0), ("", ""), ("Member B Ltd.", 200.0),
                                       ("Total", 300.0), ("Note: figures as reported", "")], start=R1.DATA_START_ROW):
            cells[(r, R1.COL_NAME)] = name
            cells[(r, R1.COL_ACTIVE_CLIENTS)] = n
            cells[(r, R1.COL_DEFAULTER)] = "No"
        sh = _Sheet(cells, R1.DATA_START_ROW + 5)
        names = [m["name"] for m in R1._member_rows(sh)]
        check("contentintegrity: a blank row inside Report 1C's member list is skipped, not taken as its end, "
              "and the list stops at the closing Total row",
              names == ["Member A Ltd.", "Member B Ltd."], str(names))
        check("contentintegrity: Report 1C's exchange total is found anywhere in the header block",
              R1._exchange_total(sh) == 46120857)

    # ------------------------------------------------------------------
    # 10. News: evergreen articles keep their real first-published date
    #     (they were re-stamped as published today on every rebuild), the
    #     retired AI guides are gone, and no byline claims verification.
    # ------------------------------------------------------------------
    try:
        from pipeline import news_engine as NE
    except ImportError as e:
        NE = None
        check("contentintegrity: news_engine importable", False, str(e))
    if NE:
        arts = [{"slug": "asba-vs-upi-ipo-application-rules", "date": "2026-11-04", "date_str": "04 November 2026"},
                {"slug": "brand-new-guide", "date": "2026-11-04", "date_str": "04 November 2026"},
                {"slug": "indian-stock-market-wrap-2026-11-04", "date": "2026-11-04", "date_str": "04 November 2026"}]
        reg = NE.stable_article_dates(arts, "2026-11-04", {"asba-vs-upi-ipo-application-rules": "2026-10-08"})
        check("contentintegrity: an evergreen article keeps its first-published date instead of today's, a new one "
              "is recorded on first sight, and a dated market wrap keeps today's date",
              arts[0]["date"] == "2026-10-08" and arts[0]["date_str"] == "08 October 2026"
              and reg.get("brand-new-guide") == "2026-11-04" and arts[2]["date"] == "2026-11-04"
              and "indian-stock-market-wrap-2026-11-04" not in reg, str(arts[0]))
        seeded = (load("data/manual/news_first_published.json") or {}).get("first_published") or {}
        check("contentintegrity: the first-published registry is seeded (from git history) for the evergreen guides",
              seeded.get("asba-vs-upi-ipo-application-rules") == "2026-10-08" and len(seeded) >= 60, "n=%d" % len(seeded))
        news_src = _read(ROOT, "pipeline", "news_engine.py")
        check("contentintegrity: retired AI guides are no longer added to the news corpus, and no byline claims "
              "'Fact-Checked & Verified'",
              "get_autopilot_articles(today_iso)" not in news_src and "Fact-Checked" not in news_src
              and "Generated from NSE, BSE and SEBI public data. Not investment advice." in news_src)

    # ------------------------------------------------------------------
    # 11. /stock-market-holidays/ comes only from NSE's own calendar, and
    #     the TMPV vs TMCV page explains the demerger from NSE's record.
    # ------------------------------------------------------------------
    try:
        from pipeline import holidays_page as HP
        import pipeline.publish as PUB
    except ImportError as e:
        HP = None
        check("contentintegrity: holidays_page importable", False, str(e))
    if HP:
        cal = {"segments": {
            "CM": [{"date": "2026-11-08", "weekday": "Sunday", "name": "Diwali Laxmi Pujan", "muhurat": True},
                   {"date": "2026-11-10", "weekday": "Tuesday", "name": "Diwali-Balipratipada", "muhurat": False}],
            "FO": [{"date": "2026-11-08"}, {"date": "2026-11-10"}]}}
        facts = HP.page_facts(cal, datetime.date(2026, 11, 4))
        check("contentintegrity: holidays page's next holiday is the next weekday closure, not a weekend date "
              "(8 Nov 2026 is a Sunday hosting the Muhurat session)",
              facts["next"]["date"] == "2026-11-10" and facts["muhurat"]["date"] == "2026-11-08" and facts["weekend"] == 1)
        page = HP.render(cal, datetime.date(2026, 11, 4), PUB._esc, PUB._REGISTRY_PAGE_HEAD, PUB._REGISTRY_PAGE_FOOT,
                         PUB._breadcrumb, PUB.SITE_URL)
        plain = re.sub(r"<[^>]+>", " ", page)
        check("contentintegrity: the Muhurat day is named but no session time is asserted (NSE sets it by circular)",
              "Muhurat trading" in page and "set by NSE circular" in page
              and not re.search(r"\b\d{1,2}[:.]\d{2}\s*(am|pm|AM|PM)?\b", plain.split("Questions")[0].split("Diwali Muhurat")[1]))
        check("contentintegrity: holidays page renders nothing without NSE data, so it can never publish an empty list",
              HP.render({"segments": {"CM": []}}, datetime.date(2026, 11, 4), PUB._esc, PUB._REGISTRY_PAGE_HEAD,
                        PUB._REGISTRY_PAGE_FOOT, PUB._breadcrumb, PUB.SITE_URL) is None)
        stored = load("data/manual/nse_holidays.json") or {}
        check("contentintegrity: the committed holiday file is NSE's own calendar (provenance, 2026 equity list)",
              stored.get("provenance") == "nse_holiday_master" and len((stored.get("segments") or {}).get("CM") or []) >= 15)
        pub_src = _read(ROOT, "pipeline", "publish.py")
        check("contentintegrity: the sitemap lists /stock-market-holidays/ only when the page was built",
              'if os.path.isfile(os.path.join(ROOT, "site", "stock-market-holidays", "index.html")):' in pub_src)
    try:
        from pipeline.stock_compare_engine import render_stock_comparison_page as RSC
    except ImportError:
        RSC = None
    if RSC:
        mm = lambda r: {"window_days": 120, "return_1y": r, "volatility_30d": 20.0, "cmp": 400.0,
                        "high_52w": 450.0, "low_52w": 350.0, "avg_volume": 1000000}
        tm = RSC({"symbol": "TMCV", "name": "Tata Motors Limited"}, mm(5.19),
                 {"symbol": "TMPV", "name": "Tata Motors Passenger Vehicles Limited"}, mm(-17.86), "Automobiles & Electric Mobility")
        other = RSC({"symbol": "MARUTI", "name": "Maruti Suzuki"}, mm(3), {"symbol": "TMPV", "name": "Tata Motors"}, mm(1),
                    "Automobiles & Electric Mobility")
        check("contentintegrity: TMPV vs TMCV says Tata Motors and the demerger (NSE record date 14 Oct 2025), recommends "
              "neither, and other pairs keep the generic title",
              "Tata Motors Passenger vs Commercial Vehicles" in tm and "record date of 14 October 2025" in tm
              and "does not rate or recommend either" in tm and "Tata Motors after the demerger" not in other)


def _read(ROOT, *parts):
    try:
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


if __name__ == "__main__":
    # Allow `python3 tests/qa_extra_contentintegrity.py` standalone, matching
    # the convention used by the other qa_extra_<area>.py modules.
    PASS, FAIL = [], []

    def _check(name, cond, detail=""):
        (PASS if cond else FAIL).append((name, detail))
        print("  %s %-100s %s" % ("PASS" if cond else "FAIL", name, detail if not cond else ""))
        return bool(cond)

    def _load(rel):
        import json
        p = os.path.join(ROOT_DIR, rel)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    run(_check, ROOT_DIR, _load)
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    for name, detail in FAIL:
        print("  FAILED: %s %s" % (name, detail))
    sys.exit(len(FAIL))
