"""SEBI registry entity pages: grouping, labelling, titles, and page body.

Why this module exists
----------------------
The register lists one row per (registration number x exchange). Several rows
can share one registration number, and one legal entity can hold several
registration numbers (a stock broker INZ number plus one or two depository
participant numbers). Before this module each registry URL was an isolated
single-row page: stock brokers carried the label of the register list they
were pulled from (the commodity list), which reads as "not a share broker", and one company could
own three competing URLs.

Honesty rules baked in here
---------------------------
* Only fields that are on file are shown. The register list BrokerLens holds
  has NO per-row segment field and NO separate "original registration date":
  it has exchange names and a validity string ("<start date> - <end or
  Perpetual>"). So segments are never invented. The category is derived from
  the registration number series (INZ = stock broker, IN-DP = depository
  participant, the same reading the rest of the codebase already uses), and
  the only segment evidence shown is exchange membership as listed.
* No current good standing is stated. Every validity statement is "per the
  register as of <date>".
* Grouping is conservative: an ambiguous name (different cities or pincodes,
  or two broker numbers under one name) is never merged.

Public API (used from pipeline/publish.py)
------------------------------------------
register_asof(ingest)                       -> "Oct 02, 2026" or None
annotate(reg_rows, details)                 -> sets row["primary"] on non-primary rows
build_models(reg_rows, details, asof, site) -> list of page models
"""
from __future__ import annotations

import html as _html
import re
import zlib
from datetime import datetime

SEBI_HOME = "https://www.sebi.gov.in/"
SCORES_URL = "https://scores.sebi.gov.in/"
NSE_HOME = "https://www.nseindia.com/"
BSE_HOME = "https://www.bseindia.com/"

# ------------------------------------------------------------------ names

_ACRONYMS = {
    "LLP", "LLC", "IFSC", "HDFC", "ICICI", "IDBI", "IDFC", "IIFL", "SBI", "UTI", "LIC",
    "PNB", "NSE", "BSE", "MCX", "NCDEX", "NBFC", "AMC", "IL", "FS", "SMC", "JM", "KJMC",
    "RBL", "DCB", "UCO", "BNP", "HSBC", "IFCI", "TCI", "JSW", "ESAF", "CSB", "KGI", "GRD",
    "CDSL", "NSDL",
}
_SMALL_WORDS = {"AND", "OF", "THE", "FOR", "IN"}
_VOWELS = set("AEIOU")


def proper_case(name):
    """Title-case an ALL-CAPS legal name for display; leave mixed-case names alone.

    Rules: names that already contain lower-case letters are returned as is
    (the register's own casing, e.g. "QE Securities LLP"). Otherwise each
    alphabetic chunk is title-cased, except single letters (R.L.P.), listed
    acronyms (LLP, HDFC, ...) and vowel-less chunks of up to five letters
    (GRD, SMC), which stay upper-case. Small joining words (and, of, the, for,
    in) go lower-case after the first word. Unknown acronyms that contain a
    vowel (for example "ABC") are title-cased: a documented limitation.
    """
    if not name:
        return name
    s = " ".join(str(name).split())
    if any(ch.islower() for ch in s):
        return s
    state = {"first": True}

    def fix(m):
        w = m.group(0)
        start = m.start()
        prev = s[start - 1] if start else ""
        first = state["first"]
        state["first"] = False
        if prev in ("'", "’"):
            return w.lower()
        if len(w) == 1:
            return w
        if w in ("PVT", "LTD"):
            return w.capitalize()
        if set(w) <= set("IVX"):                   # roman numerals: II, III, IV
            return w
        if w in _ACRONYMS:
            return w
        if len(w) <= 5 and not (set(w) & _VOWELS):
            return w
        if w in _SMALL_WORDS and not first:
            return w.lower()
        return w.capitalize()

    return re.sub(r"[A-Za-z]+", fix, s)


def norm_name(name):
    """Grouping key: punctuation, case and Pvt/Private, Ltd/Limited spelling removed."""
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"\b([a-z])\.", r"\1", s)          # R.L.P. -> rlp
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = s.replace("limited liability partnership", "llp")
    toks = [{"pvt": "private", "ltd": "limited"}.get(t, t) for t in s.split()]
    out, run = [], []
    for t in toks + [""]:
        if len(t) == 1 and t.isalpha():
            run.append(t)                          # "b d shah" and "b.d. shah" agree
            continue
        if run:
            out.append("".join(run))
            run = []
        if t:
            out.append(t)
    return " ".join(out)


# ------------------------------------------------------------------ dates

_DATE_FMT = "%b %d, %Y"


def _parse_date(text):
    try:
        return datetime.strptime((text or "").strip(), _DATE_FMT)
    except ValueError:
        return None


def parse_validity(text):
    """"Apr 07, 2026 - Perpetual" -> {start, end, perpetual}. Missing parts are None."""
    t = (text or "").strip()
    if not t:
        return {"start": None, "end": None, "perpetual": False, "text": None}
    parts = [p.strip() for p in re.split(r"\s+-\s+", t, maxsplit=1)]
    start = parts[0] if parts and _parse_date(parts[0]) else None
    end = parts[1] if len(parts) > 1 and parts[1] else None
    perpetual = bool(end and end.lower() == "perpetual")
    return {"start": start, "end": end, "perpetual": perpetual, "text": t}


def _dates_summary(validity_texts):
    """Collapse every validity string on file for one registration number.

    Returns (earliest_start, latest_start, validity_dict_of_latest_row).
    earliest != latest only when the register itself lists differing start
    dates for the same number (for example a later re-issue)."""
    parsed = [parse_validity(v) for v in validity_texts if v]
    dated = [p for p in parsed if p["start"]]
    if not dated:
        return None, None, (parsed[0] if parsed else parse_validity(None))
    dated.sort(key=lambda p: _parse_date(p["start"]))
    return dated[0]["start"], dated[-1]["start"], dated[-1]


def register_asof(ingest):
    """Date BrokerLens last pulled the SEBI register list, from the ingest log.

    The register carries no list date of its own, so the pull date is the
    honest as-of date. Returns e.g. "Oct 02, 2026", or None when not on file."""
    ingest = ingest or {}
    stamps = []
    for key, val in ((ingest.get("_status") or {}).items()):
        if key in ("sebi_stock_brokers", "sebi_commodity_brokers") and isinstance(val, dict):
            if val.get("status") == "ok" and val.get("last_run"):
                stamps.append(str(val["last_run"]))
    if not stamps and ingest.get("fetched_at"):
        stamps.append(str(ingest["fetched_at"]))
    for st in sorted(stamps, reverse=True):
        try:
            return datetime.strptime(st[:10], "%Y-%m-%d").strftime(_DATE_FMT)
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------ exchanges

# (substring, label, role, commodity). Clearing corporations come first so the
# longer, more specific names win.
_EXCH = (
    ("nse clearing", "NSE Clearing", "clearing", False),
    ("multi commodity exchange of india clearing", "MCX Clearing", "clearing", True),
    ("national commodity & derivatives exchange clearing", "NCDEX Clearing", "clearing", True),
    ("national commodity and derivatives exchange clearing", "NCDEX Clearing", "clearing", True),
    ("indian commodity exchange clearing", "ICEX Clearing", "clearing", True),
    ("indian clearing corporation", "ICCL", "clearing", False),
    ("national stock exchange", "NSE", "exchange", False),
    ("bombay stock exchange", "BSE", "exchange", False),
    ("bse limited", "BSE", "exchange", False),
    ("multi commodity exchange", "MCX", "exchange", True),
    ("national commodity & derivatives exchange", "NCDEX", "exchange", True),
    ("national commodity and derivatives exchange", "NCDEX", "exchange", True),
    ("indian commodity exchange", "ICEX", "exchange", True),
    ("metropolitan stock exchange", "MSE", "exchange", False),
)


def classify_exchange(raw):
    low = (raw or "").lower()
    for needle, label, role, commodity in _EXCH:
        if needle in low:
            return {"label": label, "role": role, "commodity": commodity}
    return {"label": proper_case(raw), "role": "other", "commodity": False}


def exchange_summary(raw_list):
    """Ordered, de-duplicated {trading, clearing, other, commodity_labels}."""
    seen, trading, clearing, other, commodity = set(), [], [], [], []
    for raw in raw_list or []:
        c = classify_exchange(raw)
        if c["label"] in seen:
            continue
        seen.add(c["label"])
        {"exchange": trading, "clearing": clearing}.get(c["role"], other).append(c["label"])
        if c["commodity"]:
            commodity.append(c["label"])
    return {"trading": trading, "clearing": clearing, "other": other, "commodity": commodity}


# ------------------------------------------------------------------ registrations

_KIND_PRIORITY = {"stock_broker": 0, "dp_cdsl": 1, "dp_nsdl": 2, "other": 3}


def reg_kind(reg, categories):
    """(kind, label, phrase) from the registration number series and categories."""
    r = (reg or "").upper()
    cats = categories or []
    if r.startswith("INZ"):
        return "stock_broker", "Stock broker", "a stock broker"
    if r.startswith("IN-DP") or any(c in ("dp_cdsl", "dp_nsdl") for c in cats):
        if "dp_cdsl" in cats and "dp_nsdl" not in cats:
            return "dp_cdsl", "Depository participant (CDSL)", "a depository participant (CDSL)"
        if "dp_nsdl" in cats and "dp_cdsl" not in cats:
            return "dp_nsdl", "Depository participant (NSDL)", "a depository participant (NSDL)"
        if "dp_cdsl" in cats and "dp_nsdl" in cats:
            return "other", "Depository participant (CDSL and NSDL)", "a depository participant (CDSL and NSDL)"
        return "other", "Depository participant", "a depository participant"
    return "other", "SEBI registered intermediary", "a SEBI registered intermediary"


def _member(row, detail):
    detail = detail or {}
    reg = row.get("reg")
    cats = row.get("categories") or detail.get("categories") or []
    kind, label, phrase = reg_kind(reg, cats)
    vtexts = []
    for v in (detail.get("validities") or []):
        if v and v not in vtexts:
            vtexts.append(v)
    for v in (row.get("validity"), detail.get("validity")):
        if v and v not in vtexts:
            vtexts.append(v)
    earliest, latest, vrow = _dates_summary(vtexts)
    exch = row.get("exchanges") or detail.get("exchanges") or []
    return {
        "slug": row.get("slug"),
        "name": row.get("name") or "Unnamed entity",
        "display": proper_case(row.get("name") or "Unnamed entity"),
        "trade_name": row.get("trade_name") or detail.get("trade_name"),
        "reg": reg,
        "kind": kind, "category": label, "phrase": phrase,
        "exchanges": exch,
        "xs": exchange_summary(exch),
        "earliest": earliest, "effective": latest, "validity": vrow,
        "email": detail.get("email"), "phone": detail.get("telephone"),
        "address": detail.get("address"), "city": row.get("city") or detail.get("city"),
        "norm": norm_name(row.get("name") or ""),
    }


# ------------------------------------------------------------------ grouping

def _ambiguous(members):
    """Same normalised name but evidence of different entities: different cities
    on file, or more than one stock broker number under one name."""
    cities = {m["city"] for m in members if m["city"]}
    if len(cities) > 1:
        return True
    if len({m["reg"] for m in members if m["kind"] == "stock_broker"}) > 1:
        return True
    return False


def _sort_key(m):
    return (_KIND_PRIORITY.get(m["kind"], 9), m["reg"] or "", m["slug"] or "")


def _pair_details(reg_rows, details):
    """Pair each reg_row with its detail record: by position when aligned, else by reg."""
    details = details or []
    if len(details) == len(reg_rows) and all(
            (d.get("sebi_reg_no") or None) == (r.get("reg") or None)
            for d, r in zip(details, reg_rows)):
        return list(details)
    by_reg = {d.get("sebi_reg_no"): d for d in details if d.get("sebi_reg_no")}
    return [by_reg.get(r.get("reg")) or {} for r in reg_rows]


def group_members(members):
    """-> (list of groups, set of slugs in ambiguous groups). Each group is a list
    of members sorted with the primary first."""
    buckets, order = {}, []
    for m in members:
        key = m["norm"]
        if not key or not m["slug"]:
            order.append([m])
            continue
        if key not in buckets:
            buckets[key] = []
            order.append(buckets[key])
        buckets[key].append(m)
    groups, ambiguous = [], set()
    for g in order:
        if len(g) > 1 and _ambiguous(g):
            ambiguous.update(m["slug"] for m in g)
            groups.extend([m] for m in g)
        else:
            groups.append(sorted(g, key=_sort_key))
    return groups, ambiguous


def annotate(reg_rows, details):
    """Mark non-primary rows with row["primary"] = primary slug. Returns counts."""
    pairs = _pair_details(reg_rows, details)
    members = [_member(r, d) for r, d in zip(reg_rows, pairs)]
    groups, ambiguous = group_members(members)
    by_slug = {r.get("slug"): r for r in reg_rows}
    merged_groups = non_primary = 0
    for g in groups:
        if len(g) < 2:
            continue
        merged_groups += 1
        for m in g[1:]:
            by_slug[m["slug"]]["primary"] = g[0]["slug"]
            non_primary += 1
    return {"groups": merged_groups, "non_primary": non_primary,
            "ambiguous_slugs": len(ambiguous)}


# ------------------------------------------------------------------ titles and copy

def title_group(slug):
    """Deterministic A/B split: zlib.crc32(slug) % 2 (0 = A, 1 = B)."""
    return "AB"[zlib.crc32((slug or "").encode("utf-8")) % 2]


def make_title(m):
    if title_group(m["slug"]) == "A":
        return "%s: SEBI Registration No. %s, Status and Segments | BrokerLens" % (m["display"], m["reg"])
    cat = re.sub(r"\s*\(([^()]*)\)$", r", \1", m["category"])      # avoid nested brackets in the title
    return "Is %s SEBI Registered? Registration No. %s (%s)" % (m["display"], m["reg"], cat)


def make_description(m, asof):
    bits = ["Registration %s" % m["reg"], m["category"]]
    ex = m["xs"]["trading"] or (m["xs"]["trading"] + m["xs"]["clearing"] + m["xs"]["other"])
    if ex:
        bits.append(", ".join(ex))
    if m["effective"]:
        bits.append("effective %s" % m["effective"])
    text = "Yes, %s is listed in the SEBI register. %s." % (m["display"], ", ".join(bits))
    if asof:
        text += " Register as of %s." % asof
    return text


def _validity_phrase(m):
    v = m["validity"] or {}
    if v.get("perpetual"):
        return "Perpetual"
    if v.get("start") and v.get("end"):
        return "%s to %s" % (v["start"], v["end"])
    if v.get("text"):
        return v["text"]
    return None


def _end_before_asof(m, asof):
    v = m["validity"] or {}
    end, a = _parse_date(v.get("end")), _parse_date(asof)
    return bool(end and a and end < a)


def _asof_clause(asof):
    return ("as of the register dated %s" % asof) if asof else \
        "per the register file BrokerLens holds (its date is not on file)"


def make_faq(m, group, asof):
    name, reg = m["display"], m["reg"]
    others = [o for o in group if o is not m]
    clause = _asof_clause(asof)
    a1 = ("Yes. %s is listed in the SEBI register of recognised intermediaries as %s, "
          "registration number %s, %s. BrokerLens does not rate or recommend any intermediary."
          % (name, m["phrase"], reg, clause))
    a2 = "The SEBI registration number of %s in the register is %s (%s)." % (name, reg, m["category"])
    if others:
        a2 += " Other registrations listed under the same legal name: %s." % "; ".join(
            "%s (%s)" % (o["reg"], o["category"]) for o in others)
    vp = _validity_phrase(m)
    eff = (", with the registration effective %s" % m["effective"]) if m["effective"] else ""
    if vp == "Perpetual":
        a3 = "The register lists the validity of %s as perpetual%s, %s." % (reg, eff, clause)
    elif vp:
        a3 = "The register lists the validity of %s as %s%s, %s." % (reg, vp, eff, clause)
        if _end_before_asof(m, asof):
            a3 += " The end date listed is earlier than the register date, so confirm the current position with SEBI."
    else:
        a3 = "The register file BrokerLens holds does not list a validity for %s, %s." % (reg, clause)
    a3 += (" This reflects the register list only and is not a live status check, "
           "so confirm the current position on the SEBI website before relying on it.")
    return [
        ("Is %s SEBI registered?" % name, a1),
        ("What is %s's registration number?" % name, a2),
        ("Is the registration valid?", a3),
    ]


# ------------------------------------------------------------------ html

def esc(s):
    return _html.escape(str(s), quote=False)


def _attr(s):
    return _html.escape(str(s), quote=True)


def _row(label, value_html):
    return ('<div class="mega-seg"><div class="mega-seg-label">%s</div>'
            '<div style="margin-top:2px">%s</div></div>' % (esc(label), value_html))


def _exchange_html(m):
    xs = m["xs"]
    parts = []
    if xs["trading"]:
        parts.append("Exchanges: %s" % esc(", ".join(xs["trading"])))
    if xs["clearing"]:
        parts.append("Clearing corporations: %s" % esc(", ".join(xs["clearing"])))
    if xs["other"]:
        parts.append("Also listed: %s" % esc(", ".join(xs["other"])))
    return "<br>".join(parts)


def _dates_html(m):
    if not m["effective"]:
        return "Not on file"
    s = esc(m["effective"])
    if m["earliest"] and m["earliest"] != m["effective"]:
        s += " (earliest registration date listed: %s)" % esc(m["earliest"])
    return s


def _verify_html(m):
    items = [
        '<li>Open the SEBI website (<a href="%s" rel="noopener" target="_blank">sebi.gov.in</a>) and search the '
        'recognised intermediaries list for registration number %s. The name, number and category should match this page.</li>'
        % (SEBI_HOME, esc(m["reg"]))
    ]
    xs = m["xs"]["trading"] + m["xs"]["clearing"]
    links = []
    if "NSE" in xs:
        links.append('<a href="%s" rel="noopener" target="_blank">nseindia.com</a>' % NSE_HOME)
    if "BSE" in xs:
        links.append('<a href="%s" rel="noopener" target="_blank">bseindia.com</a>' % BSE_HOME)
    if links:
        items.append("<li>The register lists exchange membership for this number. Compare it with the member "
                     "information published by the exchange itself (%s).</li>" % " or ".join(links))
    elif m["kind"] == "stock_broker":
        items.append("<li>Compare the exchange membership shown here with the member information published by "
                     "each exchange itself.</li>")
    items.append('<li>If something does not match, or you have a complaint, SEBI runs '
                 '<a href="%s" rel="noopener" target="_blank">SEBI SCORES</a>.</li>' % SCORES_URL)
    return ('<div class="section-title"><h2>How to verify</h2></div>'
            '<ol class="small" style="max-width:72ch;line-height:1.6">%s</ol>' % "".join(items))


def _others_html(m, group, site_url):
    others = [o for o in group if o is not m]
    if not others:
        return ""
    rows = []
    for o in others:
        rows.append(
            '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td><a href="/sebi-registry/%s/">View page</a></td></tr>'
            % (esc(o["category"]), esc(o["reg"]), esc(o["effective"] or "Not on file"),
               esc(_validity_phrase(o) or "Not on file"), esc(o["slug"])))
    return ('<div class="section-title"><h2>Other registrations of this entity</h2></div>'
            '<p class="xs faint" style="max-width:72ch">Matched by identical legal name on the register '
            '(punctuation and Pvt/Private, Ltd/Limited spelling ignored).</p>'
            '<div class="table-scroll"><table class="data"><thead><tr><th>Registration type</th>'
            '<th>Registration number</th><th>Effective date per register</th><th>Validity per register</th>'
            '<th></th></tr></thead><tbody>%s</tbody></table></div>' % "".join(rows))


def render_main(m, group, asof, faq, site_url):
    """Everything inside <main> after the breadcrumb."""
    primary = group[0]
    is_primary = primary is m
    vp = _validity_phrase(m)
    answer = "Listed in the SEBI register as %s: registration no. %s, effective %s per register, validity %s. %s" % (
        esc(m["phrase"]), esc(m["reg"]),
        esc(m["effective"]) if m["effective"] else "date not on file",
        esc(vp) if vp else "not on file",
        ("Register as of %s." % esc(asof)) if asof else "Register date not on file.")

    html = ['<h1 style="margin-top:0">%s: SEBI registration details</h1>' % esc(m["display"])]
    if m["trade_name"] and norm_name(m["trade_name"]) != m["norm"]:
        html.append('<p class="muted">Trading as %s</p>' % esc(proper_case(m["trade_name"])))
    html.append('<p style="max-width:72ch;font-size:1.05em"><strong>%s</strong></p>' % answer)
    if not is_primary:
        html.append(
            '<p class="small" style="max-width:72ch">This is a secondary registration of the same legal name. '
            'The main page for this entity is <a href="/sebi-registry/%s/">%s: %s (%s)</a>.</p>'
            % (esc(primary["slug"]), esc(primary["display"]), esc(primary["reg"]), esc(primary["category"])))

    rows = [
        _row("Legal name", esc(m["display"])),
        _row("Category", esc(m["category"])),
        _row("SEBI registration number", esc(m["reg"])),
    ]
    if m["xs"]["trading"] or m["xs"]["clearing"] or m["xs"]["other"]:
        rows.append(_row("Exchange memberships per register", _exchange_html(m)))
        if m["kind"] == "stock_broker":
            if m["xs"]["commodity"]:
                rows.append(_row("Segments evidenced by exchange membership",
                                 "Commodity derivatives (%s)" % esc(", ".join(m["xs"]["commodity"]))))
            rows.append(_row("Segment detail",
                             "The register list BrokerLens holds does not state equity, currency or "
                             "commodity segments per number, so none are inferred here."))
    rows.append(_row("Registration effective date per register", _dates_html(m)))
    rows.append(_row("Validity per register", esc(vp) if vp else "Not on file"))
    if vp and vp != "Perpetual" and _end_before_asof(m, asof):
        rows.append(_row("Note", "The validity end date listed is earlier than the register date. Confirm the "
                                 "current position with SEBI."))
    if m["address"]:
        rows.append(_row("Address per register", esc(m["address"])))
    if m["email"]:
        rows.append(_row("Email per register", esc(m["email"])))
    if m["phone"]:
        rows.append(_row("Telephone per register", esc(m["phone"])))
    html.append('<div class="section-title"><h2>Registration snapshot</h2></div>')
    html.append('<div class="card" style="margin-top:8px;padding:16px">%s</div>' % "".join(rows))
    html.append('<p class="xs faint" style="margin-top:8px">%s Source: SEBI recognised-intermediary register. '
                'This page states what the register lists; it does not confirm current standing.</p>'
                % (("Register as of %s (the date BrokerLens last pulled the SEBI list)." % esc(asof))
                   if asof else "Register date not on file."))

    html.append(_others_html(m, group, site_url))
    html.append(_verify_html(m))

    html.append('<div class="section-title"><h2>Frequently asked questions</h2></div>')
    for q, a in faq:
        html.append('<h3 style="margin:12px 0 4px;font-size:1em">%s</h3><p class="small" '
                    'style="max-width:72ch;margin:0">%s</p>' % (esc(q), esc(a)))
    return "".join(h for h in html if h)


def build_models(reg_rows, details, asof, site_url):
    """One model per reg_row, in the same order.

    model keys: slug, display, title, description, canonical, main_html, org_jsonld,
    faq_jsonld, title_group, primary_slug, faq."""
    pairs = _pair_details(reg_rows, details)
    members = [_member(r, d) for r, d in zip(reg_rows, pairs)]
    groups, _amb = group_members(members)
    group_of = {}
    for g in groups:
        for m in g:
            group_of[id(m)] = g
    models = []
    for m in members:
        if not m["slug"]:
            models.append(None)
            continue
        g = group_of[id(m)]
        primary = g[0]
        canonical = "%s/sebi-registry/%s/" % (site_url, primary["slug"])
        faq = make_faq(m, g, asof)
        org = {"@type": "Organization", "name": m["display"], "url": canonical, "identifier": m["reg"]}
        if m["trade_name"] and norm_name(m["trade_name"]) != m["norm"]:
            org["alternateName"] = proper_case(m["trade_name"])
        if m["city"]:
            org["address"] = {"@type": "PostalAddress", "addressLocality": m["city"], "addressCountry": "IN"}
        faq_ld = {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        models.append({
            "slug": m["slug"], "display": m["display"],
            "title": make_title(m), "description": make_description(m, asof),
            "canonical": canonical, "title_group": title_group(m["slug"]),
            "primary_slug": primary["slug"], "faq": faq,
            "org_jsonld": org, "faq_jsonld": faq_ld,
            "main_html": render_main(m, g, asof, faq, site_url),
        })
    return models
