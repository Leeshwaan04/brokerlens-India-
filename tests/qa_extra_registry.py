"""Regression checks for the SEBI registry entity pages (area: registry).

Exposes run(check, ROOT, load) like every tests/qa_extra_<area>.py module.
Everything is verified on freshly generated sample pages (a synthetic fixture
plus, when data/_ingest.json is present, the real register) and on source
strings. Pages are written into a temporary directory only: the writer prunes
unknown folders under sebi-registry/, so it must never be pointed at a built
site.
"""
import html as _html
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import zlib

DASHES = ("\u2014", "\u2013", "&mdash;", "&ndash;")


def _row(slug, name, reg, cats, exch=None, city=None, validity=None, trade=None):
    return {"name": name, "trade_name": trade, "reg": reg, "city": city,
            "exchanges": exch or [], "categories": cats, "validity": validity, "slug": slug}


def _detail(name, reg, cats, exch=None, validities=None, address=None, email=None, phone=None, city=None):
    return {"legal_name": name, "sebi_reg_no": reg, "categories": cats, "exchanges": exch or [],
            "validities": validities or [], "validity": (validities or [None])[0],
            "address": address, "email": email, "telephone": phone, "city": city}


NSE = "NATIONAL STOCK EXCHANGE OF INDIA LIMITED"
BSE = "BOMBAY STOCK EXCHANGE LIMITED"
MCX = "Multi Commodity Exchange of India Ltd."
MCXCC = "MULTI COMMODITY EXCHANGE OF INDIA CLEARING CORPORATION (MCXCCL)"


def _fixture():
    spec = [
        # (slug, name, reg, cats, exchanges, city, validities, email)
        ("acme-broking-private-limited", "ACME BROKING PRIVATE LIMITED", "INZ000100001",
         ["commodity_broker"], [NSE, BSE, MCX, MCXCC], "Mumbai",
         ["Jan 05, 2010 - Perpetual", "Mar 01, 2024 - Perpetual"], "a@acme.example"),
        ("acme-broking-pvt-ltd", "ACME BROKING PVT. LTD.", "IN-DP-100-2016", ["dp_cdsl"], [], "Mumbai",
         ["Feb 02, 2016 - Perpetual"], None),
        ("acme-broking-pvt-ltd-002010", "Acme Broking Pvt. Ltd.", "IN-DP-NSDL-2-2010", ["dp_nsdl"], [], None,
         ["Feb 02, 2010 - Jun 11, 2022"], None),
        ("sharp-securities-limited", "SHARP SECURITIES LIMITED", "INZ000100002", ["commodity_broker"], [NSE],
         "Mumbai", ["Jan 01, 2012 - Perpetual"], None),
        ("sharp-securities-limited-122019", "SHARP SECURITIES LIMITED", "IN-DP-122-2019", ["dp_cdsl"], [],
         "Chennai", ["Jan 01, 2019 - Perpetual"], None),
        ("twin-capital-limited", "TWIN CAPITAL LIMITED", "INZ000100003", ["commodity_broker"], [NSE], None,
         ["Jan 01, 2012 - Perpetual"], None),
        ("twin-capital-limited-100004", "TWIN CAPITAL LIMITED", "INZ000100004", ["commodity_broker"], [NSE], None,
         ["Jan 01, 2013 - Perpetual"], None),
        ("mcx-only-broking-llp", "MCX ONLY BROKING LLP", "INZ000100005", ["commodity_broker"], [MCX, MCXCC],
         None, ["Jan 01, 2014 - Perpetual"], None),
        ("bare-securities-limited", "BARE SECURITIES LIMITED", "INZ000100006", ["commodity_broker"], [], None,
         [], None),
        ("old-dp-limited", "OLD DP LIMITED", "IN-DP-9-2015", ["dp_cdsl"], [], None,
         ["Jun 12, 1997 - Jun 11, 2022"], None),
        ("a-swaminathan", "A SWAMINATHAN", "INZ000100007", ["stock_broker"], [NSE], "Madurai",
         ["Jan 01, 2012 - Perpetual"], "pla.swaminathan@gmail.com"),
        ("ramesh-shah-co", "RAMESH SHAH & CO", "INZ000100008", ["stock_broker"], [BSE], "Surat",
         ["Jan 01, 2012 - Perpetual"], "rshah@example.test"),
        ("zenith-bank", "ZENITH BANK", "IN-DP-77-2016", ["dp_nsdl"], [], "Mumbai",
         ["Jan 01, 2016 - Perpetual"], "ops@zenith.example"),
        ("the-extraordinarily-long-named-securities-and-wealth-management-private-limited",
         "THE EXTRAORDINARILY LONG NAMED SECURITIES AND WEALTH MANAGEMENT PRIVATE LIMITED", "INZ000100009",
         ["stock_broker"], [NSE], "Pune", ["Jan 01, 2012 - Perpetual"], None),
        ("fresh-end-limited", "FRESH END LIMITED", "IN-DP-55-2015", ["dp_cdsl"], [], None,
         ["Jan 01, 2015 - Sep 22, 2026"], None),
    ]
    rows, details = [], []
    for slug, name, reg, cats, exch, city, vals, email in spec:
        rows.append(_row(slug, name, reg, cats, exch, city, vals[0] if vals else None))
        details.append(_detail(name, reg, cats, exch, vals, address="1 Test Road, %s" % (city or "Nowhere"),
                               email=email, phone="9101141441150", city=city))
    return rows, details


def _faq_pairs(page_html):
    return [(_html.unescape(q), _html.unescape(a))
            for q, a in re.findall(r"<h3[^>]*>(.*?)</h3><p[^>]*>(.*?)</p>", page_html)]


def run(check, ROOT, load):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    mod_path = os.path.join(ROOT, "pipeline", "registry_entity.py")
    check("registry: pipeline/registry_entity.py exists", os.path.exists(mod_path))
    if not os.path.exists(mod_path):
        return
    src = open(mod_path, encoding="utf-8").read()
    pub = open(os.path.join(ROOT, "pipeline", "publish.py"), encoding="utf-8").read()
    check("registry: entity module has no em or en dash in its source",
          not any(d in src for d in DASHES))
    check("registry: split uses zlib.crc32, never hash()", "zlib.crc32" in src and "hash(" not in src.replace("crc32(", ""))
    check("registry: publish.py hands the full register records and as-of date to the page writer",
          "_write_registry_pages(reg_rows, untracked" in pub and "registry_entity.register_asof(ingest)" in pub)
    check("registry: sitemap leaves out canonicalised secondary pages",
          'and not r.get("primary")' in pub)
    check("registry: ingest keeps every distinct validity of a repeated registration number",
          '"validities"' in open(os.path.join(ROOT, "pipeline", "sources", "sebi.py"), encoding="utf-8").read())
    check("registry: no legacy 'Commodity broker' wording left in the page template",
          "Commodity broker" not in src)
    doc = os.path.join(ROOT, "docs", "REGISTRY_TITLE_TEST.md")
    check("registry: docs/REGISTRY_TITLE_TEST.md documents the title rule",
          os.path.exists(doc) and "crc32" in open(doc, encoding="utf-8").read())

    re_ent = importlib.import_module("pipeline.registry_entity")

    # ---- names
    check("registry: ALL-CAPS name is proper-cased with Pvt/Ltd and acronyms kept sensible",
          re_ent.proper_case("R.L.P. SECURITIES PVT. LTD.") == "R.L.P. Securities Pvt. Ltd."
          and re_ent.proper_case("GRD SECURITIES LIMITED") == "GRD Securities Limited"
          and re_ent.proper_case("ABC LLP").endswith("LLP")
          and re_ent.proper_case("QE Securities LLP") == "QE Securities LLP",
          re_ent.proper_case("R.L.P. SECURITIES PVT. LTD."))
    check("registry: Pvt/Private, Ltd/Limited and dotted initials normalise to one key",
          re_ent.norm_name("R.L.P. SECURITIES PVT. LTD.") == re_ent.norm_name("R.L.P. Securities Private Limited")
          and re_ent.norm_name("B D SHAH SECURITIES LIMITED") == re_ent.norm_name("B. D. Shah Securities Ltd."))
    check("registry: LLP and Limited stay different legal forms",
          re_ent.norm_name("Foo Securities LLP") != re_ent.norm_name("Foo Securities Limited"))

    # ---- dates
    e, l, v = re_ent._dates_summary(["Mar 01, 2024 - Perpetual", "Jan 05, 2010 - Perpetual"])
    check("registry: earliest and latest registration dates are both kept", (e, l) == ("Jan 05, 2010", "Mar 01, 2024"), str((e, l)))
    check("registry: as-of date comes from the ingest log, else None",
          re_ent.register_asof({"_status": {"sebi_commodity_brokers": {"status": "ok", "last_run": "2026-10-02T17:07:10+00:00"}}})
          == "Oct 02, 2026" and re_ent.register_asof({}) is None)

    # ---- grouping on the synthetic fixture
    rows, details = _fixture()
    stats = re_ent.annotate(rows, details)
    by = {r["slug"]: r for r in rows}
    check("registry: DP pages of one legal name point at the broker (INZ) page",
          by["acme-broking-pvt-ltd"].get("primary") == "acme-broking-private-limited"
          and by["acme-broking-pvt-ltd-002010"].get("primary") == "acme-broking-private-limited"
          and "primary" not in by["acme-broking-private-limited"], str(stats))
    check("registry: same name in different cities is NOT merged",
          "primary" not in by["sharp-securities-limited"] and "primary" not in by["sharp-securities-limited-122019"])
    check("registry: two broker numbers under one name are NOT merged",
          "primary" not in by["twin-capital-limited"] and "primary" not in by["twin-capital-limited-100004"])

    models = re_ent.build_models(rows, details, "Oct 02, 2026", "https://www.brokerlens.in")
    mb = {m["slug"]: m for m in models}
    check("registry: every row gets a page model (no URL dropped)", len(models) == len(rows) and all(models))
    m = mb["acme-broking-private-limited"]
    check("registry: stock broker label is not 'Commodity broker' even when the register list is the commodity one",
          "Stock broker" in m["title"] + m["description"] and "Commodity broker" not in m["main_html"])
    check("registry: original and later effective dates are shown together",
          "Mar 01, 2024" in m["main_html"] and "Jan 05, 2010" in m["main_html"]
          and "Registration effective date per register" in m["main_html"])
    check("registry: no invented segments (equity or currency never asserted)",
          "stock broker (equity" not in m["main_html"].lower()
          and "Commodity derivatives (MCX" in m["main_html"]
          and "does not state equity, currency or commodity segments" in m["main_html"])
    check("registry: primary lists other registrations with numbers",
          "Other registrations of this entity" in m["main_html"]
          and "IN-DP-100-2016" in m["main_html"] and "IN-DP-NSDL-2-2010" in m["main_html"])
    sec = mb["acme-broking-pvt-ltd"]
    check("registry: secondary page canonicalises to the primary and links to it visibly",
          sec["canonical"].endswith("/sebi-registry/acme-broking-private-limited/")
          and 'href="/sebi-registry/acme-broking-private-limited/"' in sec["main_html"])
    check("registry: unmerged page canonicalises to itself",
          mb["sharp-securities-limited"]["canonical"].endswith("/sebi-registry/sharp-securities-limited/"))
    check("registry: unmerged page shows no Other registrations table",
          "Other registrations of this entity" not in mb["sharp-securities-limited"]["main_html"])
    check("registry: commodity-exchange-only broker is flagged from evidence, still 'Stock broker'",
          mb["mcx-only-broking-llp"]["main_html"].count("Commodity derivatives (MCX") == 1
          and "Stock broker" in mb["mcx-only-broking-llp"]["description"])
    bare = mb["bare-securities-limited"]
    check("registry: missing fields are omitted, not guessed",
          "Exchange memberships per register" not in bare["main_html"]
          and "date not on file" in bare["main_html"] and "None" not in bare["main_html"]
          and "Telephone per register" not in bare["main_html"] and "Email per register" not in bare["main_html"])
    old = mb["old-dp-limited"]
    check("registry: an end date earlier than the register date is stated neutrally, never as good standing",
          "earlier than the register date" in old["main_html"] and "Jun 11, 2022" in old["main_html"]
          and "is valid" not in old["main_html"].lower())

    # ---- end date before the as-of date: neutral wording everywhere (review Rule[2], SEO[4])
    asof_fx = "Oct 02, 2026"
    for slug in ("old-dp-limited", "fresh-end-limited"):
        mo = mb[slug]
        d, a1 = mo["description"], mo["faq"][0]
        check("registry: %s (end before as-of) has no 'Yes' in meta, FAQ1 or title and no 'Is X SEBI Registered?'" % slug,
              not d.startswith("Yes") and "Yes" not in d and not a1[1].startswith("Yes")
              and "SEBI registered?" not in a1[0] and not mo["title"].startswith("Is ")
              and "SEBI Registered?" not in mo["title"] and mo["title_pattern"] == "A",
              d + " | " + mo["title"])
        check("registry: %s meta is the neutral 'appears in the SEBI register list ... check SEBI' sentence" % slug,
              "appears in the SEBI register list; the validity end date listed is" in d and "check SEBI." in d
              and a1[0].startswith("Does ") and "appears in the SEBI register list" in a1[1]
              and "check the current position with SEBI" in a1[1], d)
    check("registry: neutral wording shows the listed end date",
          "Jun 11, 2022" in mb["old-dp-limited"]["description"] and "Sep 22, 2026" in mb["fresh-end-limited"]["description"])
    check("registry: an end date after the as-of date and a perpetual validity keep the normal wording",
          mb["acme-broking-private-limited"]["description"].startswith("Yes, ")
          and mb["acme-broking-private-limited"]["faq"][0][0].startswith("Is ")
          and not re_ent._end_before_asof({"validity": {"end": "Perpetual"}}, asof_fx)
          and not re_ent._end_before_asof({"validity": {"end": "Oct 02, 2026"}}, asof_fx)
          and re_ent._end_before_asof({"validity": {"end": "Oct 01, 2026"}}, asof_fx))
    check("registry: neutral FAQ and JSON-LD stay equal to the visible text",
          all(_faq_pairs(mb[s_]["main_html"])[0] == (mb[s_]["faq"][0][0], mb[s_]["faq"][0][1])
              and mb[s_]["faq_jsonld"]["mainEntity"][0]["acceptedAnswer"]["text"] == mb[s_]["faq"][0][1]
              for s_ in ("old-dp-limited", "fresh-end-limited")))

    # ---- BrokerLens's pull date wording (review Rule[6])
    all_faq = " ".join(a for mm in models for _q, a in mm["faq"])
    all_ld = json.dumps([mm["faq_jsonld"] for mm in models])
    check("registry: FAQ and JSON-LD say 'BrokerLens's pull of the register on <date>', never 'register dated'",
          "register dated" not in all_faq and "register dated" not in all_ld
          and "as of BrokerLens's pull of the register on Oct 02, 2026" in all_faq
          and "as of BrokerLens's pull of the register on Oct 02, 2026" in all_ld
          and "register dated" not in src)

    # ---- privacy: no email or phone anywhere, address only for corporate names (review Rule[1], Merge[4])
    contact_vals = ["pla.swaminathan@gmail.com", "9101141441150", "a@acme.example", "rshah@example.test",
                    "ops@zenith.example"]
    blob = json.dumps([{k: v for k, v in mm.items()} for mm in models], default=str)
    check("registry: no email or telephone value appears in any model, page body or structured data",
          not any(v in blob for v in contact_vals)
          and not any("@" in mm["main_html"] for mm in models)
          and not any(w in mm["main_html"] for mm in models for w in ("Email per register", "Telephone per register")))
    check("registry: the module no longer reads email or telephone from the register record",
          '"email"' not in src and '"phone"' not in src and 'get("telephone")' not in src and 'get("email")' not in src)
    check("registry: _is_corporate accepts company and institution names, rejects individuals and unclear names",
          all(re_ent._is_corporate(n) for n in (
              "ACME BROKING PVT. LTD.", "Foo Securities Private Limited", "QE Securities LLP", "HDFC BANK",
              "Zenith Bank", "Some Corporation", "Indian Business Trade INC", "X Company", "Y Financial Services Limited"))
          and not any(re_ent._is_corporate(n) for n in (
              "A SWAMINATHAN", "AMIT SAHITA", "RAMESH SHAH & CO", "HIMANSHU GOVINDLAL MEHTA", "", None)))
    check("registry: address row appears for a company and an institution",
          "Address per register" in mb["acme-broking-private-limited"]["main_html"]
          and "1 Test Road, Mumbai" in mb["acme-broking-private-limited"]["main_html"]
          and "Address per register" in mb["zenith-bank"]["main_html"])
    ind, firm = mb["a-swaminathan"], mb["ramesh-shah-co"]
    check("registry: an individual or a '& Co' firm shows no address, no city in JSON-LD, no contact data",
          "Address per register" not in ind["main_html"] and "Test Road" not in ind["main_html"]
          and "Address per register" not in firm["main_html"] and "Test Road" not in firm["main_html"]
          and "address" not in ind["org_jsonld"] and "address" not in firm["org_jsonld"]
          and "address" in mb["acme-broking-private-limited"]["org_jsonld"])
    check("registry: every page links the official SEBI register list for its category",
          "doRecognisedFpi=yes&amp;intmId=1\"" in mb["a-swaminathan"]["main_html"]
          and "doRecognisedFpi=yes&amp;intmId=2\"" in mb["acme-broking-private-limited"]["main_html"]
          and "doRecognisedFpi=yes&amp;intmId=18\"" in mb["old-dp-limited"]["main_html"]
          and "doRecognisedFpi=yes&amp;intmId=19\"" in mb["zenith-bank"]["main_html"]
          and all("Official SEBI register" in mm["main_html"] and "sebi.gov.in" in mm["main_html"] for mm in models)
          and "Email and telephone are not republished here" in ind["main_html"])
    sebi_src = open(os.path.join(ROOT, "pipeline", "sources", "sebi.py"), encoding="utf-8").read()
    check("registry: the official register URL pattern and category ids match pipeline/sources/sebi.py",
          "OtherAction.do?doRecognisedFpi=yes&intmId=%d" in sebi_src
          and re_ent.SEBI_REGISTER_URL.startswith("https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=")
          and re_ent._REGISTER_INTM_ID == {"stock_broker": 1, "commodity_broker": 2, "dp_cdsl": 18, "dp_nsdl": 19}
          and all('"%s": %d' % (k, v) in sebi_src for k, v in re_ent._REGISTER_INTM_ID.items()))

    # ---- titles and meta
    ok_split = True
    for mm in models:
        grp = re_ent.title_group(mm["slug"])
        ok_split &= (zlib.crc32(mm["slug"].encode()) % 2 == 0) == (grp == "A") and mm["title_group"] == grp
        reg = [r["reg"] for r in rows if r["slug"] == mm["slug"]][0]
        ok_split &= reg in mm["title"] and "Segments" not in mm["title"]
        if mm["title_pattern"] == "A":
            ok_split &= (not mm["title"].startswith("Is ")) and bool(re.search(r"SEBI Reg(istration|\.) No\. %s" % re.escape(reg), mm["title"]))
        else:
            ok_split &= grp == "B" and mm["title"].startswith("Is ") and "SEBI Registered? " in mm["title"]
    check("registry: titles follow the A/B rule by zlib.crc32(slug) % 2, keep the registration number, never say Segments", bool(ok_split))
    for g_slug in ("x", "y", "z", "w", "v", "u", "t", "s"):
        if re_ent.title_group(g_slug) == "A":
            tt = re_ent.make_title({"slug": g_slug, "display": "Foo Ltd", "reg": "INZ000000001", "category": "Stock broker",
                                    "validity": {"perpetual": True}}, "Oct 02, 2026")
            check("registry: short name gets the full A title without Segments (%s)" % tt,
                  tt == "Foo Ltd: SEBI Registration No. INZ000000001, Validity and Exchanges" and len(tt) <= 72, tt)
            break
    long_m = mb["the-extraordinarily-long-named-securities-and-wealth-management-private-limited"]
    check("registry: a very long legal name falls to the compact title: no legal suffix, number kept, no brand tail",
          "Private Limited" not in long_m["title"] and "INZ000100009" in long_m["title"]
          and "BrokerLens" not in long_m["title"] and len(long_m["title"]) <= 100, long_m["title"])
    check("registry: title shortening drops the Limited suffix and brand only when needed, never the number",
          re_ent._short_name("Foo Securities Private Limited") == "Foo Securities"
          and re_ent._short_name("R.L.P. Securities Pvt. Ltd.") == "R.L.P. Securities"
          and re_ent._short_name("QE Securities LLP") == "QE Securities LLP"
          and re_ent._short_name("Limited") == "Limited")
    pat_src = src.split("def make_title", 1)[1].split("def make_description", 1)[0]
    check("registry: title source has no Segments wording and fixes the length budget",
          "Segments" not in pat_src and "_TITLE_MAX = 72" in src and "_TITLE_REG_BY = 60" in src)
    check("registry: both title groups occur", {mm["title_group"] for mm in models} == {"A", "B"})
    check("registry: meta description follows the agreed pattern",
          m["description"].startswith("Yes, Acme Broking Private Limited is listed in the SEBI register. Registration INZ000100001, Stock broker, NSE, BSE, MCX, effective Mar 01, 2024.")
          and m["description"].endswith("Register as of Oct 02, 2026."), m["description"])
    check("registry: titles and meta carry no dash and no claim of safety or quality",
          not any(d in (mm["title"] + mm["description"]) for mm in models for d in DASHES)
          and not re.search(r"\b(safe|best|trusted|recommended|guarantee)", " ".join(mm["title"] + mm["description"] for mm in models), re.I))

    # ---- FAQs and JSON-LD equal the visible text
    faq_ok = True
    for mm in models:
        vis = _faq_pairs(mm["main_html"])
        ld = mm["faq_jsonld"]["mainEntity"]
        faq_ok &= len(vis) == 3 == len(ld)
        faq_ok &= all(q == e["name"] and a == e["acceptedAnswer"]["text"] for (q, a), e in zip(vis, ld))
    check("registry: three FAQs per page and FAQPage JSON-LD text equals the visible text", faq_ok)
    check("registry: FAQ answers carry the as-of date",
          all("Oct 02, 2026" in a for mm in models for _q, a in mm["faq"][:1] + mm["faq"][2:]))
    check("registry: no complaint table, enforcement or name-change claim in the body",
          not any(re.search(r"enforcement|formerly|renamed|complaints? (table|data)", mm["main_html"], re.I) for mm in models))
    check("registry: how-to-verify links only to official domains already used elsewhere",
          all(set(re.findall(r'href="(https?://[^"/]+)', mm["main_html"]))
              <= {"https://www.sebi.gov.in", "https://scores.sebi.gov.in", "https://www.nseindia.com",
                  "https://www.bseindia.com"} for mm in models))

    # ---- full pages through the real writer (tmp dir only)
    tmp = tempfile.mkdtemp(prefix="regtest_")
    try:
        pub_mod = importlib.import_module("pipeline.publish")
        saved = pub_mod.SITE_DATA
        pub_mod.SITE_DATA = os.path.join(tmp, "data")
        os.makedirs(pub_mod.SITE_DATA)
        try:
            pub_mod._write_registry_pages(rows, details, "Oct 02, 2026")
        finally:
            pub_mod.SITE_DATA = saved
        base = os.path.join(tmp, "sebi-registry")
        pages = {s: open(os.path.join(base, s, "index.html"), encoding="utf-8").read() for s in os.listdir(base)}
        check("registry: writer still emits one page per slug", set(pages) == {r["slug"] for r in rows})
        p = pages["acme-broking-pvt-ltd"]
        check("registry: written secondary page has canonical to primary and og:url to primary",
              '<link rel="canonical" href="https://www.brokerlens.in/sebi-registry/acme-broking-private-limited/">' in p
              and '<meta property="og:url" content="https://www.brokerlens.in/sebi-registry/acme-broking-private-limited/">' in p)
        check("registry: written pages are zero-JS, have one h1, FAQPage JSON-LD, and no leaked None",
              all("/assets/js/app.js" not in h and h.count("<h1") == 1 and '"FAQPage"' in h
                  and ">None<" not in h and "None</" not in h for h in pages.values()))
        check("registry: written pages contain no em or en dash",
              not any(d in h for h in pages.values() for d in DASHES))
        ld_ok = True
        for h in pages.values():
            raw = re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
            try:
                json.loads(raw.group(1))
            except Exception:
                ld_ok = False
        check("registry: JSON-LD parses on every written page", ld_ok)
    except Exception as exc:  # pragma: no cover
        check("registry: writer ran on the fixture", False, repr(exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- the real register, when the ingest file is present
    ing_path = os.path.join(ROOT, "data", "_ingest.json")
    ing = load("data/_ingest.json") if os.path.exists(ing_path) else None
    reg_by_cat = ((ing or {}).get("sebi") or {}).get("registry") or {}
    if not any(reg_by_cat.values()):
        return
    pub_mod = importlib.import_module("pipeline.publish")
    from pipeline.common import slugify
    reg = pub_mod._merge_registry(reg_by_cat)
    rrows, seen = [], {}
    for r in reg:
        row = _row(slugify(r.get("legal_name") or ""), r.get("legal_name"), r.get("sebi_reg_no"),
                   r.get("categories") or [], r.get("exchanges") or [], r.get("city"), r.get("validity"))
        base_slug = row["slug"] or "entity"
        n = seen.get(base_slug, 0)
        seen[base_slug] = n + 1
        if n:
            row["slug"] = "%s-%s" % (base_slug, re.sub(r"[^a-z0-9]", "", (row["reg"] or "").lower())[-6:] or str(n))
        rrows.append(row)
    re_ent.annotate(rrows, reg)
    rm = {r["slug"]: r for r in rrows}
    asof = re_ent.register_asof(ing)
    rmodels = re_ent.build_models(rrows, reg, asof, "https://www.brokerlens.in")
    byslug = {x["slug"]: x for x in rmodels if x}
    check("registry (real data): a model exists for every register row", len(byslug) == len(rrows))
    for slug, reg_no in (("qe-securities-llp", "INZ000041822"), ("aristro-capital-markets-limited", "INZ000219238"),
                         ("econo-broking-private-limited", "INZ000301331"),
                         ("r-l-p-securities-private-limited", "INZ000166638")):
        if slug in byslug:
            check("registry (real data): %s is a Stock broker, number intact" % reg_no,
                  "Stock broker" in byslug[slug]["description"] and reg_no in byslug[slug]["title"]
                  and "Commodity broker" not in byslug[slug]["main_html"])
    if "r-l-p-securities-pvt-ltd" in byslug:
        check("registry (real data): RLP DP pages canonicalise to the INZ page",
              byslug["r-l-p-securities-pvt-ltd"]["canonical"].endswith("/r-l-p-securities-private-limited/")
              and byslug["r-l-p-securities-pvt-ltd-442006"]["canonical"].endswith("/r-l-p-securities-private-limited/"))
    check("registry (real data): a broker (INZ) number is never demoted to a secondary page",
          all(not (rm[s].get("primary") and (rm[s]["reg"] or "").startswith("INZ")) for s in rm))
    check("registry (real data): no primary points at a row that is itself non-primary",
          all(not rm[rm[s]["primary"]].get("primary") for s in rm if rm[s].get("primary")))
    check("registry (real data): no title contains 'Commodity broker' or a dash",
          not any("Commodity broker" in x["title"] or any(d in x["title"] for d in DASHES) for x in rmodels if x))
    # review fixes on the real register (Rule[1], Rule[2], SEO[3], Rule[6])
    expired_all = [x for x in rmodels if x and "validity end date listed is" in x["description"]]
    check("registry (real data): no page with an end date before the as-of date says Yes or asks 'Is X SEBI Registered?'",
          all(not x["description"].startswith("Yes") and not x["faq"][0][1].startswith("Yes")
              and not x["title"].startswith("Is ") and "SEBI registered?" not in x["faq"][0][0]
              for x in expired_all), "%d neutral pages" % len(expired_all))
    check("registry (real data): every neutral page body also carries the end-before-register warning",
          all("earlier than the register date" in x["main_html"] for x in expired_all))
    check("registry (real data): no email, no telephone and no personal mailbox is rendered on any page",
          not any("@" in x["main_html"] or "Email per register" in x["main_html"]
                  or "Telephone per register" in x["main_html"] for x in rmodels if x))
    corp_name = {r["slug"]: re_ent._is_corporate(r["name"]) for r in rrows}
    check("registry (real data): an address row is shown only for corporate legal names",
          all(("Address per register" not in x["main_html"]) or corp_name[x["slug"]] for x in rmodels if x))
    check("registry (real data): structured data holds no phone, email or street address",
          not any(re.search(r"telephone|email|streetAddress", json.dumps([x["org_jsonld"], x["faq_jsonld"]]), re.I)
                  for x in rmodels if x))
    check("registry (real data): no title says Segments, none exceeds 120 characters, and most keep the number in the first 70",
          not any("Segments" in x["title"] for x in rmodels if x)
          and max(len(x["title"]) for x in rmodels if x) <= 120
          and sum(1 for x, r in zip(rmodels, rrows) if x and x["title"].find(r["reg"]) + len(r["reg"]) <= 70)
          >= 0.9 * len(rmodels))
    check("registry (real data): no FAQ or JSON-LD uses the phrase 'register dated'",
          not any("register dated" in a for x in rmodels if x for _q, a in x["faq"]))

