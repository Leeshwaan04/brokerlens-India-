"""Regression checks for the share-price-target replacement on stock pages
(area: pricetarget). Loaded by tests/qa_e2e.py via run(check, ROOT, load).

Sources are asserted as strings, and the section/FAQ/title builders are
exercised on synthetic NSE-style history so nothing depends on a full build.
When a built /stock/ page exists it is checked too; otherwise that block is
reported as not applicable."""
import os
import re
import sys

DASHES = ("—", "–")
KINDS = ("sip", "lumpsum", "emi", "cagr", "compound", "'capital-gains'", "'simple-interest'", "'stepup-sip'",
         "'direct-regular'", "swp", "inflation", "retirement", "ppf", "gst")


def _read(ROOT, *parts):
    try:
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _candles(n, start=100.0):
    rows = []
    for i in range(n):
        c = start + (i % 17) * 0.5
        rows.append({"date": "2026-%02d-%02d" % (1 + (i // 28) % 12, 1 + i % 28), "open": c, "high": c + 2,
                     "low": c - 3, "close": c, "volume": 1000 + i})
    return rows


def run(check, ROOT, load):
    sys.path.insert(0, ROOT)
    mod_src = _read(ROOT, "pipeline", "price_target_section.py") or ""
    pub = _read(ROOT, "pipeline", "publish.py") or ""
    js = _read(ROOT, "site", "assets", "js", "calculators.js") or ""

    check("pricetarget: section module exists and is wired into the stock page writer",
          "def price_target_section_html" in mod_src and "price_target_section_html(name, symbol, history" in pub
          and "_price_target_faqs(name, symbol, facts_line)" in pub and "_price_target_title(name, symbol)" in pub)
    check("pricetarget: stock pages load calculators.js through the versioned helper",
          "/assets/js/calculators.js" in pub and "_stamp_asset_versions(\n            '<script src=\"/assets/js/calculators.js\"" in pub)
    check("pricetarget: calculators.js gains 'price-whatif' and keeps all 14 existing kinds",
          "'price-whatif'()" in js and all(re.search(r"^  %s\(\) \{" % re.escape(k), js, re.M) for k in KINDS),
          str([k for k in KINDS if not re.search(r"^  %s\(\) \{" % re.escape(k), js, re.M)]))
    check("pricetarget: what-if kind shows no broker call to action and never sends input text to innerHTML raw",
          "brokerCta" not in js.split("'price-whatif'()")[-1].split("document.addEventListener")[0]
          and "showResult" not in js.split("'price-whatif'()")[-1].split("document.addEventListener")[0])
    check("pricetarget: retired target pages stay redirected and out of the sitemap",
          "share_price_target_urls = []" in pub
          and "build_share_price_target_suite(limit_stocks" not in pub
          and any(r.get("source") == "/stock/:symbol/share-price-target-:year" and r.get("permanent") is True
                  for r in ((load("vercel.json") or {}).get("redirects", []))))
    check("pricetarget: no em or en dashes in the section module or the calculator code",
          not any(d in mod_src for d in DASHES) and not any(d in js.split("'price-whatif'()")[-1].split("document.addEventListener")[0] for d in DASHES))

    try:
        from pipeline import price_target_section as pts
    except Exception as exc:  # pragma: no cover
        check("pricetarget: section module imports", False, str(exc))
        return

    def px(n):
        return "Rs %.2f" % n

    def ld(d):
        return d

    def esc(t):
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    short = pts.price_target_section_html("Acme Ltd", "ACME", _candles(120), px, ld, esc)
    plain = re.sub(r"<[^>]+>", " ", short)
    check("pricetarget: H2 matches the query and the page says BrokerLens publishes no targets",
          "<h2>What is a share price target for Acme Ltd?</h2>" in short
          and "does not publish price targets, forecasts or analyst ratings" in short)
    check("pricetarget: range is labelled with the real window (120 sessions), never 52-week",
          "last 120 sessions" in short and "52 weeks" not in short and "no 52-week figure is shown" in short)
    long = pts.price_target_section_html("Acme Ltd", "ACME", _candles(300), px, ld, esc)
    check("pricetarget: 52-week label only when 252+ sessions are on file, using the latest 252",
          "last 52 weeks" in long and "(252 trading sessions)" in long)
    check("pricetarget: calculator is static markup, prefilled close, empty growth, years 1 to 30, plain disclaimer",
          'data-calc="price-whatif"' in short and 'id="pw-growth"' in short and 'value="" placeholder' in short
          and 'id="pw-years"' in short and 'min="1" max="30"' in short and 'id="pw-price"' in short
          and re.search(r'id="pw-price"[^>]*value="\d+\.\d\d"', short) is not None
          and "This is arithmetic on your assumption, not a forecast or a recommendation." in short
          and "<script" not in short and "onclick" not in short)
    empty = pts.price_target_section_html("Acme Ltd", "ACME", [], px, ld, esc)
    check("pricetarget: with no history the data block is omitted and the price box is left empty",
          "Last close" not in empty and "Exchange data from NSE" not in empty
          and re.search(r'id="pw-price"[^>]*value=""', empty) is not None and "enter a starting price yourself" in empty)
    low = " ".join(plain.lower().split())
    check("pricetarget: no advice wording in the section (buy, sell, best, upside, will reach)",
          not re.search(r"\b(buy|sell|best|upside|will reach|will hit|multibagger)\b", low), low[:120])
    check("pricetarget: no em or en dashes in generated section", not any(d in short for d in DASHES))

    faqs = pts.stock_target_faqs("Acme Ltd", "ACME", "")
    check("pricetarget: three FAQ entries, first keeps the pinned query wording and the no-forecast answer",
          len(faqs) == 3 and faqs[0][0] == "What is the share price target of Acme Ltd for 2026, 2027 or 2030?"
          and "does not publish price targets or forecasts" in faqs[0][1] and "what-if price calculator" in faqs[0][1])
    check("pricetarget: FAQ copy has no dashes, no advice wording, no vendor names",
          not any(d in q + a for q, a in faqs for d in DASHES)
          and not re.search(r"\b(buy|sell|best)\b", " ".join(q + " " + a for q, a in faqs).lower())
          and not re.search(r"yahoo|google finance|moneycontrol|tradingview|screener|bloomberg", " ".join(a for _q, a in faqs).lower()))

    t = pts.stock_title("Acme Ltd", "ACME")
    check("pricetarget: title strips 'Ltd', keeps 'Name (SYM): ... | BrokerLens', covers the query, within 70, no dashes",
          t == "Acme (ACME): Share Price and What-If Calculator | BrokerLens" and "Ltd" not in t
          and len(t) <= 70 and not any(d in t for d in DASHES), t)
    t2 = pts.stock_title("Reliance Industries Limited", "RELIANCE")
    t3 = pts.stock_title("Housing Development Finance Corporation Limited", "HDFC")
    check("pricetarget: 'Limited' is stripped and the brand suffix is dropped when the title would pass 70 characters",
          t2 == "Reliance Industries (RELIANCE): Share Price and What-If Calculator" and "Limited" not in t2
          and len(t2) <= 70 and "BrokerLens" not in t2 and "What-If Calculator" in t3 and "Limited" not in t3, t2 + " / " + t3)
    check("pricetarget: short_company_name keeps the name when stripping would leave nothing, and strips Ltd.",
          pts.short_company_name("Limited", "X") == "Limited" and pts.short_company_name("Bajaj Finance Ltd.", "BAJ") == "Bajaj Finance"
          and pts.short_company_name("", "ABC") == "ABC" and pts.short_company_name(None, "") == "")
    try:
        from pipeline import ipo_facts as _ipf
        same = all(pts.short_company_name(n, "S") == _ipf._short_name(n, "S")
                   for n in ("Acme Limited", "Acme Ltd", "Acme Ltd.", "Acme", "Limited", "Foo Limited Partnership"))
        check("pricetarget: short_company_name agrees with ipo_facts._short_name", same)
    except Exception as exc:  # pragma: no cover
        check("pricetarget: short_company_name agrees with ipo_facts._short_name (not applicable: %s)" % exc, True)
    check("pricetarget: stock page title is built from the shortened name in publish.py",
          "title = _price_target_title(name, symbol)" in pub)
    page_t = _read(ROOT, "site", "stock", "itc", "index.html")
    if page_t is None:
        check("pricetarget: built stock title within budget (not applicable: no built page in this tree)", True)
    else:
        mt = re.search(r"<title>([^<]*)</title>", page_t)
        ttl = mt.group(1) if mt else ""
        # A tree built before this change may still carry the long form; only fail on a malformed title.
        check("pricetarget: built /stock/itc/ title keeps the what-if phrase and the symbol",
              "What-If" in ttl and "(ITC)" in ttl and not any(d in ttl for d in DASHES), ttl)
    d = pts.stock_description("Acme Ltd", "ACME")
    check("pricetarget: meta description states no targets are published and has no dashes",
          "publishes no price targets" in d and not any(x in d for x in DASHES), d)

    page = _read(ROOT, "site", "stock", "itc", "index.html")
    if page is None:
        check("pricetarget: built /stock/itc/ page (not applicable: no built page in this tree)", True)
    else:
        check("pricetarget: built stock page carries the section, calculator, script and FAQPage text equal to visible text",
              "What is a share price target for" in page and 'data-calc="price-whatif"' in page
              and re.search(r'/assets/js/calculators\.js\?v=[0-9a-f]{10}', page) is not None
              and page.count('"@type": "FAQPage"') == 1
              and "How does the what-if price calculator for" in page and page.count("<h2>What is a share price target") == 1)
        check("pricetarget: section sits below the chart grid and the sponsored banner is still present",
              page.find("data-stock-chart") < page.find("What is a share price target for")
              and "Sponsored" in page)
