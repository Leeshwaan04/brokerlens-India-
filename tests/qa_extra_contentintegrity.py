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
