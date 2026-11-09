"""IPO area regression checks (loaded by tests/qa_e2e.py via tests/qa_extra_*.py).

Hermetic: pages are rendered from fixture records with stub templates, so no built
site is needed. Real records from data/_ingest.json are used only for loops over
titles, and the check is skipped with a passing note when that file is absent.
"""
import json
import os
import re
import sys
import tempfile
import zlib
from datetime import datetime, timedelta, timezone

DASHES = ("—", "–")


def _iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")


def run(check, ROOT, load):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from pipeline import ipo_facts, ipo_engine
    from pipeline import ipo_subscription_engine as sube
    from pipeline import ipo_apply_engine as appe

    def src(name):
        with open(os.path.join(ROOT, "pipeline", name), encoding="utf-8") as fh:
            return fh.read()

    sources = {n: src(n) for n in ("ipo_engine.py", "ipo_facts.py", "ipo_subscription_engine.py", "ipo_apply_engine.py")}
    all_src = "".join(sources.values())

    # ---------------------------------------------------------- source level
    check("ipo: no derived lot-size estimator is left in the IPO engines",
          "14500" not in all_src.replace("Rs 14,500", "") and "_estimate_lot_size" not in all_src
          and "compute_lot_metrics" not in sources["ipo_engine.py"]
          and "Estimated Lot" not in all_src and "estimated lot" not in all_src.lower().replace("no derived estimated lot", ""))
    check("ipo: the word Disclosed is never printed in a value slot",
          not re.search(r'"Disclosed"|or \'Disclosed\'|"Not disclosed"', all_src), "found in source")
    check("ipo: title split uses zlib.crc32 and never hash()",
          "zlib.crc32" in sources["ipo_facts.py"] and not re.search(r"(?<![\w.])hash\(", all_src))
    check("ipo: title test is documented (docs/IPO_TITLE_TEST.md)",
          os.path.exists(os.path.join(ROOT, "docs", "IPO_TITLE_TEST.md"))
          and "crc32" in open(os.path.join(ROOT, "docs", "IPO_TITLE_TEST.md"), encoding="utf-8").read())
    check("ipo: no em or en dashes in the IPO engine sources",
          not any(d in all_src for d in DASHES))

    # ---------------------------------------------------------- A/B split
    exp = "A" if zlib.crc32(b"kfintech") % 2 == 0 else "B"
    check("ipo: title_group is the crc32 parity of the lower-cased slug",
          ipo_facts.title_group("kfintech") == exp and ipo_facts.title_group("KFINTECH") == exp
          and ipo_facts.title_group("jswcement") == ("A" if zlib.crc32(b"jswcement") % 2 == 0 else "B"))

    # ---------------------------------------------------------- fixtures
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    kfin = {"symbol": "KFINTECH", "company": "KFin Technologies Limited", "price_band": "Rs.347 to Rs.366", "issue_price": 366,
            "security_type": "EQ", "bidding_start": "2022-12-19", "bidding_end": "2022-12-21", "listing_date": "2022-12-29",
            "status": "Listed"}
    jsw = {"symbol": "JSWCEMENT", "company": "JSW Cement Limited", "price_band": "Rs.139 to Rs.147", "issue_price": 147,
           "security_type": "EQ", "bidding_start": "2025-08-07", "bidding_end": "2025-08-11", "listing_date": "2025-08-14",
           "status": "Listed"}
    uti = {"symbol": "UTIAMC", "company": "UTI Asset Management Company Limited", "price_band": "Rs.552 to Rs.554", "issue_price": 554,
           "security_type": "EQ", "bidding_start": "2020-09-29", "bidding_end": "2020-10-01", "listing_date": "2020-10-12",
           "status": "Listed"}
    open_ipo = {"symbol": "OPENCO", "company": "Open Co Limited", "price_band": "Rs.100 to Rs.105", "issue_size_shares": 8471153,
                "bidding_start": _iso(-1), "bidding_end": _iso(2), "times_subscribed": 0.44, "shares_offered": 8471153.0,
                "shares_bid": 3721912.0, "status": "Active", "security_type": None}
    soon = {"symbol": "SOONCO", "company": "Soon Co Limited", "price_band": "Rs.77 to Rs.82", "bidding_start": _iso(5),
            "bidding_end": _iso(7), "status": "Forthcoming"}
    closed = {"symbol": "CLOSEDCO", "company": "Closed Co Limited", "price_band": "Rs.50 to Rs.55", "bidding_start": _iso(-6),
              "bidding_end": _iso(-3), "status": "Closed", "security_type": "SME"}
    future_listing = dict(closed, symbol="FUTLIST", company="Future List Limited", listing_date=_iso(2), status="Listed")
    bad_ip = {"symbol": "BADIP", "company": "Bad Ip Limited", "price_band": "Rs.752 to Rs.792", "issue_price": 1381,
              "security_type": "EQ", "bidding_start": "2024-01-01", "bidding_end": "2024-01-03", "listing_date": "2024-01-08",
              "status": "Listed"}
    fixed = {"symbol": "FIXEDCO", "company": "Fixed Co Limited", "price_band": "Rs.1000", "bidding_start": "2024-02-01",
             "bidding_end": "2024-02-05", "listing_date": "2024-02-09", "issue_price": 1000, "security_type": "EQ", "status": "Listed"}
    hist = {"JSWCEMENT": [{"date": "2025-08-14", "open": 150.0, "high": 158.5, "low": 148.0, "close": 156.2},
                          {"date": "2026-10-01", "open": 112.0, "high": 114.0, "low": 110.0, "close": 112.5}],
            "KFINTECH": [{"date": "2026-04-10", "open": 904, "high": 924.4, "low": 900.55, "close": 911.45},
                         {"date": "2026-10-01", "open": 820, "high": 840, "low": 815, "close": 832}]}

    head = ('<title>%(title)s</title><meta name="description" content="%(description)s"><link rel="canonical" href="%(canonical)s">'
            '<script type="application/ld+json">%(jsonld)s</script>')

    def page(r, history=hist):
        return ipo_engine.render_full_ipo_page(
            r, history, head, "%(source_note)s", "AFFBANNER", "FIVEPAISA", lambda items: ("", {"@type": "BreadcrumbList"}),
            lambda t: t, ibsl_wide_html="IBSLBANNER", jiraaf_banner_html="JIRAAF")

    def parts(html_):
        t = re.search(r"<title>(.*?)</title>", html_, re.S).group(1)
        d = re.search(r'name="description" content="(.*?)"', html_, re.S).group(1)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html_, re.S).group(1))
        faq = next(x for x in ld["@graph"] if x["@type"] == "FAQPage")
        faq_text = " ".join(q["acceptedAnswer"]["text"] for q in faq["mainEntity"])
        return t, d, faq_text

    pk, pj, pu, po, ps, pc, pf_, pb, px = (page(x) for x in (kfin, jsw, uti, open_ipo, soon, closed, future_listing, bad_ip, fixed))
    tk, dk, fk = parts(pk)
    tj, dj, fj = parts(pj)
    to, do, fo = parts(po)

    # ---------------------------------------------------------- trust bugs
    check("ipo: a listed IPO never says it has not listed (page text and FAQPage JSON-LD)",
          all("has not listed" not in x for x in (pk, pj, pu, fk, fj, parts(pu)[2], parts(pb)[2], parts(px)[2])))
    check("ipo: an open or upcoming IPO says it has not listed, and says so only there",
          "has not listed yet" in fo and "has not listed yet" in parts(ps)[2] and "no listing is on file yet" in parts(pc)[2]
          and "has not listed" not in parts(pc)[2])
    check("ipo: a listing date still in the future does not make an IPO Listed",
          ipo_facts.ipo_status(future_listing, today) == "Closed" and "has not listed" not in parts(pf_)[2]
          and "no listing is on file yet" not in parts(pf_)[2] and "The listing date on file is" in parts(pf_)[2])
    check("ipo: status is derived from dates (Listed, Active, Forthcoming, Closed)",
          [ipo_facts.ipo_status(x, today) for x in (kfin, open_ipo, soon, closed)] == ["Listed", "Active", "Forthcoming", "Closed"])
    check("ipo: KFin main page shows the 347 to 366 band, never 366 alone as the band",
          "Rs 347 to Rs 366" in pk and "Rs 347 to 366" in dk + tk and "Rs 366 to Rs 366" not in pk
          and "Price Band Rs 366" not in tk + dk and "Rs 347 to Rs 366" in fk)
    sub_kf = sube.render_subscription_page(dict(kfin))
    boa_kf = sube.render_basis_of_allotment_page(dict(kfin))
    check("ipo: sub-pages use the same band as the main page",
          "Rs 347 to Rs 366" in sub_kf and "Rs 347 to Rs 366" in boa_kf and "₹347" not in sub_kf)
    check("ipo: no status word in a numeric slot (Disclosed) on any IPO page or sub-page",
          not any("Disclosed" in x or "Not disclosed" in x for x in (pk, pj, pu, po, ps, pc, sub_kf, boa_kf,
                                                                       sube.render_subscription_page(dict(open_ipo)),
                                                                       sube.render_subscription_hub([kfin, open_ipo, soon]),
                                                                       sube.render_allotment_hub([kfin, open_ipo, soon]))))
    check("ipo: a missing subscription multiple reads Not on file, and the FAQ says so in words",
          "Not on file" in sub_kf and "does not have an overall subscription figure" in sub_kf
          and "approximately Not on file" not in sub_kf)
    check("ipo: an issue price outside the stored band is ignored everywhere",
          "1381" not in pb and "1,381" not in pb and "Issue price" not in parts(pb)[0] + parts(pb)[1]
          and ipo_facts.price_facts(bad_ip)["issue_price_rejected"])
    check("ipo: a fixed-price IPO shows one price",
          "Issue price Rs 1,000" in parts(px)[0] + parts(px)[1] and "Rs 1,000 to Rs 1,000" not in px)

    # ---------------------------------------------------------- lot size
    check("ipo: lot size is Not on file, not estimated (JSW Cement no longer shows 99 shares)",
          "99 shares" not in pj and "estimated" not in pj.lower().replace("never an estimate", "")
          and "lot size for this issue is not on file" in pj.lower() and "Retail Lot Size" not in pj)
    with_lot = dict(jsw, lot_size=102)
    pl = page(with_lot)
    check("ipo: a sourced lot_size field is shown (102 shares, Rs 14,994 per lot at the upper price)",
          "102 shares" in pl and "Rs 14,994" in pl and ipo_facts.lot_size_on_file(with_lot) == 102
          and ipo_facts.lot_size_on_file(dict(jsw, lot_size="x")) is None and ipo_facts.lot_size_on_file(jsw) is None)
    check("ipo: apply-via page does not estimate a lot size",
          "estimated" not in appe.render_ipo_broker_apply_page(dict(open_ipo), "groww", appe.BROKERS["groww"]).lower()
          and "Not on file" in appe.render_ipo_broker_apply_page(dict(open_ipo), "groww", appe.BROKERS["groww"]))
    check("ipo: allotment-status page does not estimate a lot size",
          "estimated" not in appe.render_individual_ipo_allotment_page(dict(open_ipo)).lower())

    # ---------------------------------------------------------- title and meta
    check("ipo: group A title is facts first (price band, dates, listing) and has no return figure",
          tj.startswith("JSW Cement IPO: Price Band Rs 139 to 147, Dates 7 to 11 Aug 2025") and "Listing 14 Aug 2025" in tj
          and tj.endswith("| BrokerLens"), tj)
    check("ipo: group B title is the keyword pattern and drops lot size when not on file",
          tk == "KFin Technologies IPO Date, Price Band and Listing Date | BrokerLens"
          and parts(page(dict(kfin, lot_size=75)))[0] == "KFin Technologies IPO Date, Price Band, Lot Size and Listing Date | BrokerLens", tk)
    check("ipo: both groups appear across a sample of slugs",
          {ipo_facts.title_group(s) for s in ("kfintech", "jswcement", "utiamc", "bse", "polycab", "lauruslabs")} == {"A", "B"})
    check("ipo: the latest close and any percentage stay out of title and meta (they stay in the body with a date)",
          all(("Latest Close" not in x and "%" not in x and "832" not in x and "112.5" not in x and "Since Issue" not in x)
              for x in (tk, dk, tj, dj, to, do)) and "Latest Close (as of 01 Oct 2026)" in pj
          and "Latest Close (as of 01 Oct 2026)" in pk)
    check("ipo: meta lists dates, exchange, issue price and status only from fields on file",
          dk == "KFin Technologies IPO opened 19 Dec 2022 and closed 21 Dec 2022, listed 29 Dec 2022 on NSE. "
                "Issue price Rs 366 (price band Rs 347 to 366). Status: Listed. Latest close shown on the page with its date."
          and ipo_facts.build_description(kfin, ipo_facts.price_facts(kfin), "Listed") == dk.replace(" Latest close shown on the page with its date.", ""), dk)
    to_a = ipo_facts.build_title(open_ipo, ipo_facts.price_facts(open_ipo), "Active", group="A")
    check("ipo: a missing part is omitted, not filled (no listing date for an open IPO)",
          "Listing" not in to_a and to_a.startswith("Open Co IPO: Price Band Rs 100 to 105, Dates ") and "listed" not in do.lower())
    long_name = dict(uti, symbol="UTIAMC2")
    tl = ipo_facts.build_title(long_name, ipo_facts.price_facts(long_name), "Listed", group="A")
    check("ipo: a long name degrades gracefully, keeping the key part within the cap",
          len(tl.replace(" | BrokerLens", "")) <= ipo_facts.MAX_KEY_CHARS and "Price Band Rs 552 to 554" in tl and "Listing 12 Oct 2020" in tl, tl)
    check("ipo: no dashes in titles or meta", not any(d in x for x in (tk, dk, tj, dj, to, do) for d in DASHES))

    # ---------------------------------------------------------- facts card
    check("ipo: facts card sits before performance, sponsored banners and the FAQ",
          0 < pj.index("IPO key facts") < pj.index("Post-Listing Performance") < pj.index("IBSLBANNER") < pj.index("AFFBANNER")
          < pj.index("Frequently Asked Questions"))
    check("ipo: facts card carries a visible Data as of line", re.search(r"Data as of \d{1,2} [A-Z][a-z]{2} \d{4}", pj) is not None)
    check("ipo: facts card has price band, open, close, listing date, exchange and status",
          all(x in pj for x in ("Price band", "Bidding opens", "Bidding closes", "Listing date", "Exchange", "Status")))
    check("ipo: listing-day open/high/low/close appear only where the price history covers the listing date",
          "Open Rs 150, high Rs 158.5, low Rs 148, close Rs 156.2" in pj and "Listing day prices" not in pk
          and "Listing day prices" not in pu)
    check("ipo: listing candle needs an exact date match (no nearby candle is used)",
          ipo_facts.listing_candle("JSWCEMENT", "2025-08-15", hist) is None
          and ipo_facts.listing_candle("JSWCEMENT", "2025-08-14", hist)["open"] == 150.0)
    check("ipo: issue size and subscription appear only when on file",
          "Issue size" in po and "84,71,153" not in po and "8,471,153 shares" in po and "Issue size" not in pk
          and "0.44 times" in po and "Overall subscription" not in pk)

    check("ipo: only the performance card prints the capitalised Not on file (an IPO with its listing candle has none)",
          "Not on file" not in pj and "Listing Day Open" in pj and "Not on file" in pk)
    from html.parser import HTMLParser

    class _Bal(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth, self.bad = 0, False

        def handle_starttag(self, tag, attrs):
            if tag == "div":
                self.depth += 1

        def handle_endtag(self, tag):
            if tag == "div":
                self.depth -= 1
                self.bad = self.bad or self.depth < 0
    bal = _Bal()
    bal.feed(pj)
    check("ipo: the generated IPO body has balanced div tags", bal.depth == 0 and not bal.bad, str(bal.depth))

    # ---------------------------------------------------------- GMP
    check("ipo: GMP and listing outcome H2 is present with the unofficial statement and no number",
          "<h2 style=\"margin:0 0 8px 0;font-size:18px\">GMP and listing outcome</h2>" in pj
          and "unofficial" in pj and "does not publish it" in pj)
    check("ipo: GMP outcome (issue price, listed open) only when the listing candle is on file",
          "Issue price Rs 147, listed open Rs 150" in pj and "listed open" not in pk)
    check("ipo: GMP FAQ is present on every status and states the outcome only when on file",
          "Does BrokerLens show the GMP" in pj + pk + po and "listed open Rs 150" in fj and "listed open" not in fk)

    # ---------------------------------------------------------- apply links
    ipo_facts._APPLY_SYMBOLS["s"] = {"openco"}
    p_with, p_without = page(open_ipo), page(kfin)
    ipo_facts._APPLY_SYMBOLS.pop("s", None)
    check("ipo: apply-via links appear only for IPOs that have those pages",
          "/ipo/openco/apply-via-zerodha/" in p_with and "apply-via-" not in p_without)

    # ---------------------------------------------------------- sub-pages of listed IPOs
    robots = '<meta name="robots" content="noindex,follow">'
    # Self canonical, as the generator's docstring says: noindex plus a canonical to the main IPO
    # page is a mixed signal Google can resolve by carrying the noindex over to the main page.
    check("ipo: listed IPO sub-pages are noindex,follow with a self canonical (never noindex + canonical to the main page)",
          '<link rel="canonical" href="https://www.brokerlens.in/ipo/kfintech/subscription-status/">' in sub_kf and robots in sub_kf
          and '<link rel="canonical" href="https://www.brokerlens.in/ipo/kfintech/basis-of-allotment/">' in boa_kf and robots in boa_kf
          and '<link rel="canonical" href="https://www.brokerlens.in/ipo/kfintech/">' not in sub_kf + boa_kf)
    sub_open = sube.render_subscription_page(dict(open_ipo))
    boa_open = sube.render_basis_of_allotment_page(dict(open_ipo))
    check("ipo: open IPO sub-pages stay indexable with a self canonical",
          "noindex" not in sub_open + boa_open
          and '<link rel="canonical" href="https://www.brokerlens.in/ipo/openco/subscription-status/">' in sub_open
          and '<link rel="canonical" href="https://www.brokerlens.in/ipo/openco/basis-of-allotment/">' in boa_open)
    check("ipo: sub-pages link the allotment checker page only where it exists",
          "/ipo/kfintech/allotment-status/" not in sub_kf + boa_kf and "/ipo/openco/allotment-status/" in sub_open)
    check("ipo: hubs send listed IPOs to the main page, not to noindex sub-pages",
          "/ipo/kfintech/subscription-status/" not in sube.render_subscription_hub([kfin, open_ipo])
          and "/ipo/kfintech/basis-of-allotment/" not in sube.render_allotment_hub([kfin, open_ipo])
          and "/ipo/openco/subscription-status/" in sube.render_subscription_hub([kfin, open_ipo]))

    # the suite writes every page but returns (sitemap) only the indexable ones
    tmp = tempfile.mkdtemp(prefix="ipo_suite_")
    try:
        os.makedirs(os.path.join(tmp, "data"))
        with open(os.path.join(tmp, "data", "_ingest.json"), "w", encoding="utf-8") as fh:
            json.dump({"nse": {"ipo": {"current": [], "upcoming": [
                {"symbol": "SOONCO", "company": "Soon Co Limited", "price_band": "Rs.77 to Rs.82",
                 "bidding_start": _iso(5), "bidding_end": _iso(7), "status": "Forthcoming"}],
                "past": [dict(kfin), dict(jsw)]}}}, fh)
        old = (sube.SITE_DIR, sube.DATA_DIR)
        sube.SITE_DIR, sube.DATA_DIR = os.path.join(tmp, "site"), os.path.join(tmp, "data")
        try:
            urls = sube.build_ipo_subscription_suite()
        finally:
            sube.SITE_DIR, sube.DATA_DIR = old
        kf_file = os.path.join(tmp, "site", "ipo", "kfintech", "subscription-status", "index.html")
        check("ipo: sitemap list excludes sub-pages of listed IPOs and keeps open or upcoming ones and the hubs",
              "/ipo/soonco/subscription-status/" in urls and "/ipo/soonco/basis-of-allotment/" in urls
              and not any("/kfintech/" in u or "/jswcement/" in u for u in urls)
              and "/ipo/subscription/" in urls and "/ipo/allotment/" in urls, str(urls))
        check("ipo: listed IPO sub-pages are still written (noindex) so old links do not 404",
              os.path.exists(kf_file) and robots in open(kf_file, encoding="utf-8").read())
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------------------------------------------------- hub and archive
    check("ipo: the hub no longer prints an estimated lot size column",
          "Est. Lot Size" not in sources["ipo_engine.py"] and "Rs 14,000 to Rs 15,000" not in sources["ipo_engine.py"])

    # ---------------------------------------------------------- real records
    ing = load("data/_ingest.json")
    if not ing:
        check("ipo: real-record title loop skipped (data/_ingest.json absent)", True)
        return
    from pipeline.publish import _ipo_merge
    recs = _ipo_merge(((ing.get("nse") or {}).get("ipo")) or {})
    bad = []
    groups = {"A": 0, "B": 0}
    for r in recs:
        pf = ipo_facts.price_facts(r)
        st = ipo_facts.ipo_status(r, today)
        g = ipo_facts.title_group(r["symbol"].lower())
        groups[g] += 1
        t = ipo_facts.build_title(r, pf, st)
        d = ipo_facts.build_description(r, pf, st)
        if any(x in t + d for x in DASHES) or "None" in t + d or "nan" in (t + d).lower().split():
            bad.append(r["symbol"])
        if pf["issue_price_rejected"] and ipo_facts.fmt_price(r["issue_price"]) in re.findall(r"Rs ([\d,.]+)", t + d):
            bad.append(r["symbol"] + ":rejected-price")
        if pf["band_low"] is not None and pf["band_low"] >= pf["band_high"]:
            bad.append(r["symbol"] + ":band")
        if st == "Listed" and "has not listed" in " ".join(a for _, a in ipo_facts.build_faqs(r, pf, st, None, {}, r["symbol"], today)):
            bad.append(r["symbol"] + ":faq")
        if len(t) > 140:
            bad.append(r["symbol"] + ":long")
    check("ipo: titles, meta and FAQs for every real IPO record are clean (no dashes, None, rejected prices, band faults)",
          not bad, str(bad[:8]))
    tot = groups["A"] + groups["B"]
    check("ipo: the crc32 split over real slugs is balanced (40 to 60 percent per group)",
          tot > 0 and 0.4 <= groups["A"] / tot <= 0.6, str(groups))
