"""Regression checks for the per-broker "brokerage calculator and charges" pages
(pipeline/broker_charges_engine.py, site/assets/js/broker-charges.js).

Exposes run(check, ROOT, load) like every tests/qa_extra_<area>.py module. Pages are
rendered in memory with render_charges_page(), so no built site is needed.
"""
import html as _html
import json
import os
import random
import re
import shutil
import subprocess
import sys


def _read(root, rel):
    p = os.path.join(root, rel)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _visible_faq(page):
    """[(question, answer)] from the visible <details> blocks, entity-decoded."""
    out = []
    for m in re.finditer(r'<details class="faq-item"><summary>(.*?)</summary><p>(.*?)</p></details>', page, re.S):
        out.append((_html.unescape(m.group(1)), _html.unescape(m.group(2))))
    return out


def _jsonld(page):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    graph = []
    for b in blocks:
        d = json.loads(b)
        graph += d.get("@graph", [d])
    return graph


def _worked(page, segment_heading):
    """{key: float} from the data-worked cells of the worked-example table under a heading."""
    i = page.index(segment_heading)
    j = page.index("</table>", i)
    return {k: float(v.replace(",", "")) for k, v in re.findall(
        r'data-worked="([a-z_]+)">(?:<strong>)?Rs ([0-9,\.]+)', page[i:j])}


def _calc_default(page):
    i = page.index('id="bc-out"')
    j = page.index("</table>", i)
    return {lab: float(v.replace(",", "")) for lab, v in re.findall(
        r'<th scope="row">([^<]*)</th><td class="right num">(?:<strong>)?Rs ([0-9,\.]+)', page[i:j])}


def _node_compute(root, cfg, cases):
    """Run broker-charges.js compute() under node for each (buy, sell, segment)."""
    js = os.path.join(root, "site", "assets", "js", "broker-charges.js")
    code = (
        "const m = require(%s); const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify(inp.cases.map(c => m.compute(inp.cfg, c[0], c[1], c[2]))));" % json.dumps(js))
    r = subprocess.run(["node", "-e", code], input=json.dumps({"cfg": cfg, "cases": cases}),
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])
    return json.loads(r.stdout)


def run(check, ROOT, load):
    sys.path.insert(0, ROOT)
    from pipeline import broker_charges_engine as E
    from pipeline import trade_cost_engine as tce
    from pipeline import publish as P

    # ---- eligibility: only complete schedules, nothing guessed -----------------
    keys = E.eligible_keys()
    skipped = E.skipped_brokers()
    check("charges pages: at least ten brokers have a complete schedule", len(keys) >= 10, "%d" % len(keys))
    check("charges pages: every eligible schedule has real numbers for every field",
          all(E.schedule_complete(tce.BROKER_RATES[k]) for k in keys))
    check("charges pages: every rate key is either built or listed as skipped",
          set(keys) | set(skipped) == set(tce.BROKER_RATES))
    check("charges pages: an incomplete schedule is refused",
          not E.schedule_complete({"brand": "X", "delivery_flat": 0, "delivery_pct": 0, "intraday_flat": 0,
                                   "intraday_pct": 0, "dp_charge": None, "demat_amc": 0}))
    ids = [E.charges_id(k) for k in keys]
    check("charges pages: one URL per page", len(ids) == len(set(ids)), "%s" % ids)
    for must in ("prostocks", "religare", "alice-blue", "samco", "fyers"):
        check("charges pages: priority broker %s has a page" % must, must in keys or E.charges_id(must) in ids)

    # ---- sources: hooks, no inline script, no dashes ---------------------------
    pub = _read(ROOT, "pipeline/publish.py")
    check("hook: build() calls build_broker_charges_pages and feeds the sitemap",
          "build_broker_charges_pages(built, registry" in pub and "broker_charges_urls=broker_charges_urls" in pub)
    check("hook: charges sitemap is in the first wave", 'SITEMAP_WAVES["broker-charges"] = 1' in pub
          and '("broker-charges", broker_charges_entries)' in pub)
    check("hook: broker main page links the charges page", "profile_links_html(bid)" in pub)
    check("hook: /brokers page links the charges pages", "brokers_index_links_html()" in pub)
    check("hook: stock cost pages link the charges page with the exact anchor",
          "_charges_link_block(broker_id)" in _read(ROOT, "pipeline/trade_cost_engine.py")
          and "brokerage calculator and charges" in _read(ROOT, "pipeline/broker_charges_engine.py"))
    js_src = _read(ROOT, "site/assets/js/broker-charges.js")
    check("broker-charges.js exists, reads data-attributes and has no eval or document.write",
          "data-' + name" in js_src and "eval(" not in js_src and "document.write" not in js_src)
    dash_chars = ("—", "–", "&mdash;", "&ndash;")
    check("broker-charges.js has no em or en dash", not any(c in js_src for c in dash_chars))
    check("charges engine source has no em or en dash",
          not any(c in _read(ROOT, "pipeline/broker_charges_engine.py") for c in dash_chars))

    # ---- build identity data like the real build does (skipped if no ingest) ----
    built, registry = [], []
    try:
        from pipeline.identity import Resolver
        master = load("config/brokers_master.json") or {}
        ing = load("data/_ingest.json") or {}
        cfg = master.get("brokers") or []
        profiles = {b["id"]: P._profile(b) for b in cfg}
        registry = P._merge_registry((ing.get("sebi") or {}).get("registry"))
        if registry:
            P._apply_sebi(profiles, Resolver(cfg), registry, [])
        built = [{"id": k, "profile": v} for k, v in profiles.items()]
    except Exception:
        built, registry = [], []
    by_id = {b["id"]: b for b in built}

    # ---- render sample pages in memory ----------------------------------------
    sample = [k for k in ("prostocks", "religare", "alice-blue", "samco", "fyers", "choice-broking", "hdfc-sky",
                          "zerodha") if k in keys]
    pages = {k: E.render_charges_page(k, by_id, registry, site_url="https://www.brokerlens.in",
                                      generated_on="19 October 2026") for k in sample}
    check("charges pages: sample pages rendered", len(pages) >= 3, "%d" % len(pages))

    vendor_words = ("trendlyne", "screener.in", "tickertape", "truedata", "kite connect", "alpha vantage", "yahoo",
                    "coingecko", "binance", "fallback")
    for k, page in pages.items():
        brand = tce.BROKER_RATES[k]["brand"]
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        check("%s: single H1 'brokerage calculator and charges'" % k,
              len(h1s) == 1 and _html.unescape(h1s[0]) == "%s brokerage calculator and charges" % brand, str(h1s))
        check("%s: canonical points at /broker/%s/charges/" % (k, E.charges_id(k)),
              '<link rel="canonical" href="https://www.brokerlens.in/broker/%s/charges/">' % E.charges_id(k) in page)
        graph = _jsonld(page)
        types = {g.get("@type") for g in graph}
        check("%s: FAQPage, BreadcrumbList and WebApplication JSON-LD" % k,
              {"FAQPage", "BreadcrumbList", "WebApplication"} <= types, str(types))
        faq_ld = [(q["name"], q["acceptedAnswer"]["text"]) for g in graph if g.get("@type") == "FAQPage"
                  for q in g["mainEntity"]]
        check("%s: FAQPage JSON-LD text equals the visible FAQ text" % k,
              bool(faq_ld) and faq_ld == _visible_faq(page))
        check("%s: IBSL sponsored banner present, marked Sponsored" % k,
              'data-ad="ibsl"' in page and 'class="ad-tag">Sponsored<' in page)
        check("%s: no crypto affiliate banner" % k, "binance" not in page.lower() and "coingecko" not in page.lower())
        check("%s: no inline script (CSP script-src 'self')" % k,
              not re.search(r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>", page))
        check("%s: loads broker-charges.js" % k, '/assets/js/broker-charges.js?v=' in page or
              '/assets/js/broker-charges.js"' in page)
        check("%s: no em dash, en dash or spaced hyphen dash in the page" % k,
              not any(c in page for c in dash_chars) and " - " not in page)
        check("%s: no vendor or fallback wording" % k, not any(w in page.lower() for w in vendor_words))
        check("%s: not-investment-advice footer pattern" % k,
              "not investment, tax or account-opening advice" in page and "not a SEBI-registered investment adviser" in page)
        check("%s: no buy/sell/best advice wording" % k,
              not re.search(r"\b(best|top pick|you should (buy|sell)|recommend(ed|ation)? to (buy|sell))\b", page, re.I))
        check("%s: states the as-of position honestly" % k,
              "19 October 2026" in page and "is not on file" in page)
        check("%s: segments not on file are said to be not on file" % k,
              "Futures, options, currency, commodity" in page and "Not on file" in page)

    # ---- identifiers only when on file -----------------------------------------
    def ident_block(page):  # the IBSL banner carries its own SEBI numbers, so look only at our block
        i = page.index("Registration and identifiers")
        return page[i:page.index("Where these numbers", i)]

    if by_id and registry:
        samco = ident_block(pages.get("samco", "Registration and identifiers Where these numbers"))
        reg = by_id["samco"]["profile"].get("sebi_reg_no")
        if reg:
            check("samco: SEBI registration number in identifiers block equals the register's", reg in samco)
        ps = ident_block(pages.get("prostocks", "Registration and identifiers Where these numbers"))
        check("prostocks: no invented registration number when none is on file",
              "does not yet hold a matched SEBI registration number" in ps and "INZ" not in ps and "IN-DP" not in ps)
        check("DP registration is labelled as a SEBI registration number, not a DP ID",
              all("not the DP ID" in ident_block(pages[k]) for k in pages if "IN-DP" in ident_block(pages[k])))
        allowed = set()
        for b in built:
            p = b["profile"]
            allowed |= {p.get("sebi_reg_no")} | {e.get("reg_no") for e in p.get("sebi_entities") or []}
            allowed |= {d.get("reg_no") for d in p.get("dp_registrations") or []}
        allowed |= {r.get("sebi_reg_no") for r in registry}
        shown = set()
        for k in pages:
            shown |= set(re.findall(r"\b(?:INZ\d+|IN-DP-[A-Z0-9-]+)\b", ident_block(pages[k])))
        check("every registration number shown is in the register data of this build", shown <= allowed,
              str(shown - allowed))

    # ---- self-consistency: worked example == calculator formula == trade-cost engine ----
    checked = 0
    cfg_for = lambda page: {  # noqa: E731  (the data-attributes the browser calculator reads)
        "deliveryFlat": float(re.search(r'data-delivery-flat="([^"]+)"', page).group(1)),
        "deliveryPct": float(re.search(r'data-delivery-pct="([^"]+)"', page).group(1)),
        "intradayFlat": float(re.search(r'data-intraday-flat="([^"]+)"', page).group(1)),
        "intradayPct": float(re.search(r'data-intraday-pct="([^"]+)"', page).group(1)),
        "dpCharge": float(re.search(r'data-dp-charge="([^"]+)"', page).group(1)),
        "sttDelivery": float(re.search(r'data-stt-delivery="([^"]+)"', page).group(1)),
        "sttIntradaySell": float(re.search(r'data-stt-intraday-sell="([^"]+)"', page).group(1)),
        "nse": float(re.search(r'data-nse="([^"]+)"', page).group(1)),
        "sebi": float(re.search(r'data-sebi="([^"]+)"', page).group(1)),
        "gst": float(re.search(r'data-gst="([^"]+)"', page).group(1)),
        "stampDelivery": float(re.search(r'data-stamp-delivery="([^"]+)"', page).group(1)),
        "stampIntraday": float(re.search(r'data-stamp-intraday="([^"]+)"', page).group(1)),
    }
    comp_keys = ("brokerage", "stt", "exchange_charges", "sebi_charges", "stamp_duty", "gst", "dp_charge")
    for k in keys:  # every eligible broker, not just three
        rates = tce.BROKER_RATES[k]
        page = pages.get(k) or E.render_charges_page(k, by_id, registry, generated_on="19 October 2026")
        ok = True
        for seg, heading in (("delivery", ">Equity delivery</h3>"), ("intraday", ">Equity intraday</h3>")):
            shown = _worked(page, heading)
            calc = E.compute_charges(rates, E.WORKED_VALUE, E.WORKED_VALUE, seg)
            engine = tce.calculate_trade_fees(1000.0, 100, k, seg)
            want = {kk: calc[kk] for kk in comp_keys if not (kk == "dp_charge" and seg == "intraday")}
            want["total"] = calc["total"]
            eng_ok = all(abs(engine[ek] - calc[ck]) < 1e-9 for ek, ck in (
                ("brokerage", "brokerage"), ("stt", "stt"), ("exchange_charges", "exchange_charges"),
                ("sebi_charges", "sebi_charges"), ("stamp_duty", "stamp_duty"), ("gst", "gst"),
                ("dp_charge", "dp_charge"), ("total_charges", "total")))
            ok = ok and shown == want and eng_ok
        default_calc = _calc_default(page)
        ok = ok and abs(default_calc.get("Total charges", -1) - E.compute_charges(rates, 1e5, 1e5, "delivery")["total"]) < 1e-9
        checked += 1
        check("%s: worked example == calculator formula == trade-cost engine (Rs 1,00,000)" % k, ok)
    check("self-consistency run over at least three brokers", checked >= 3, "%d" % checked)

    # ---- the browser formula (broker-charges.js) matches the Python one ----------
    if shutil.which("node") and js_src:
        rng = random.Random(20261019)  # fixed seed, deterministic
        cases = [[100000, 100000, "delivery"], [100000, 100000, "intraday"], [0, 50000, "delivery"],
                 [12500, 12500, "intraday"], [1, 1, "delivery"]]
        cases += [[rng.randrange(0, 5000000), rng.randrange(0, 5000000), rng.choice(["delivery", "intraday"])]
                  for _ in range(400)]
        for k in [x for x in ("prostocks", "samco", "religare", "zerodha", "hdfc-securities") if x in keys][:5]:
            page = pages.get(k) or E.render_charges_page(k, by_id, registry, generated_on="19 October 2026")
            try:
                got = _node_compute(ROOT, cfg_for(page), cases)
                bad = []
                for (b, s, seg), g in zip(cases, got):
                    want = E.compute_charges(tce.BROKER_RATES[k], b, s, seg)
                    for kk in comp_keys + ("total",):
                        if abs(g[kk] - want[kk]) > 1e-9:
                            bad.append((b, s, seg, kk, g[kk], want[kk]))
                check("%s: broker-charges.js equals Python compute_charges on %d inputs" % (k, len(cases)),
                      not bad, str(bad[:3]))
            except Exception as exc:  # node present but failed to run: a real failure
                check("%s: broker-charges.js runs under node" % k, False, str(exc))
    else:
        check("broker-charges.js parity run (node not available here, skipped)", True)

    # ---- the stock cost page links to the canonical page with the exact anchor ----
    for k in [x for x in ("prostocks", "samco", "choice-broking") if x in keys]:
        stock_page = tce.render_trade_cost_page(k, "RELIANCE", "Reliance Industries Limited", "INE002A01018", 1400.0, "EQ")
        want = '<a href="%s">%s brokerage calculator and charges</a>' % (E.charges_path(k), tce.BROKER_RATES[k]["brand"])
        check("%s: stock cost page links the charges page with exact anchor text" % k, want in stock_page)
    check("/brokers index links every charges page",
          all(E.charges_path(k) in E.brokers_index_links_html() for k in keys))
    check("broker main page links resolve to built pages",
          all(path in {E.charges_path(k) for k in keys}
              for pid in {E.PROFILE_ALIAS.get(k, k) for k in keys} for _b, path in E.links_for_profile(pid)))

    # ---- number formatting helper -------------------------------------------------
    check("Indian digit grouping", E.inr(100000, 0) == "1,00,000" and E.inr(1234567.5) == "12,34,567.50"
          and E.inr(999.5) == "999.50")
