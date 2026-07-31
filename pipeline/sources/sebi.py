"""SEBI adapters - the regulatory spine of the product.

Three datasets:

1. The recognised-intermediary registry: legal name, trade name, SEBI
   registration number, contact and validity. This is what lets the site claim
   authority, and it is what expands coverage from "the 48 brokers everyone
   writes about" to every registered entity.
2. The defaulter / expelled broker list. A hard negative signal.
3. Depository-participant registries, which tell you whether a broker holds its
   own demat licence or routes through a partner.

VERIFIED BEHAVIOUR (2026-07-30):
The registry page is a Struts shell; rows come from an XHR to
/sebiweb/ajax/other/getintmfpiinfo.jsp, reproduced exactly here.

  intmId=2  (brokers, commodity derivative segment)  -> 2048 records, 82 pages
  intmId=18 (depository participants, CDSL)          -> pulled
  intmId=19 (depository participants, NSDL)          -> pulled
  intmId=1  (stock brokers)                          -> SEBI returns
            "No record(s) available." for every parameter combination, and
            their own exchange dropdown renders empty. The fault is upstream,
            not in this client. Kept in the category list so the run log shows
            it; re-check periodically.
"""
from __future__ import annotations

import re

from ..common import Fetcher, card_records, log, sebi, snapshot

BASE = "https://www.sebi.gov.in"
AJAX = BASE + "/sebiweb/ajax/other/getintmfpiinfo.jsp"

CATEGORIES = {
    "stock_broker": 1,
    "commodity_broker": 2,
    "dp_cdsl": 18,
    "dp_nsdl": 19,
}

REG_NO = re.compile(r"\bIN[A-Z]\d{9}\b")
TOTAL_RE = re.compile(r"(\d[\d,]*)\s+to\s+(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+records", re.I)


def _shell(f: Fetcher, intm_id):
    url = "%s/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=%d" % (BASE, intm_id)
    f.get_text(url, ttl=86400)
    return url


def _page(f: Fetcher, referer, intm_id, page, name="", alp=""):
    """Page 1 is a 'search' (next='s'); later pages are 'navigate' (next='n')
    with doDirect carrying a ZERO-BASED page index - matching how SEBI's own
    pagination links call searchFormFpi('n', '<page-2>')."""
    if page <= 1:
        nav, direct = "s", "-1"
    else:
        nav, direct = "n", str(page - 1)
    fields = {
        "nextValue": str(page), "next": nav, "intmId": str(intm_id), "contPer": "",
        "name": name, "regNo": "", "regStatus": "", "email": "", "location": "",
        "exchange": "", "affiliate": "", "alp": alp, "language": "2", "model": "",
        "esgCategory": "", "doDirect": direct, "intmIds": "",
    }
    body = f.post_form(
        AJAX, fields,
        headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
        ttl=7 * 86400, retries=2,
    )
    return body.decode("utf-8", "replace") if body else ""


def _normalise(rec, category):
    name = rec.get("name") or rec.get("trade_name")
    reg = rec.get("registration_no") or rec.get("registration_number")
    if reg:
        m = REG_NO.search(reg)
        reg = m.group(0) if m else reg.strip()
    if not name:
        return None
    addr = rec.get("address") or rec.get("registered_office_address")
    return {
        "_exchange_key": reg or name.strip().lower(),
        "exchange_name": rec.get("exchange_name") or rec.get("exchange"),
        "legal_name": name.strip(),
        "trade_name": (rec.get("trade_name") or "").strip() or None,
        "sebi_reg_no": reg,
        "email": rec.get("e_mail") or rec.get("email"),
        "telephone": rec.get("telephone") or rec.get("telephone_no"),
        "address": addr,
        "city": _city(addr),
        "validity": rec.get("validity") or rec.get("valid_upto") or rec.get("registration_valid_upto"),
        "contact_person": rec.get("contact_person"),
        "category": category,
    }


_CITY_HINTS = (
    "mumbai", "delhi", "new delhi", "bengaluru", "bangalore", "kolkata", "chennai",
    "hyderabad", "ahmedabad", "pune", "surat", "jaipur", "indore", "lucknow",
    "kochi", "cochin", "rajkot", "ludhiana", "chandigarh", "noida", "gurugram",
    "gurgaon", "coimbatore", "nagpur", "vadodara", "bhopal", "patna", "kanpur",
    "thane", "salem", "mohali", "guwahati", "bhubaneswar", "visakhapatnam",
)


def _city(address):
    if not address:
        return None
    low = address.lower()
    for c in _CITY_HINTS:
        if c in low:
            return c.title()
    return None


def registry(f: Fetcher, category="commodity_broker", max_pages=None):
    intm_id = CATEGORIES[category]
    referer = _shell(f, intm_id)

    first = _page(f, referer, intm_id, 1)
    if "No record" in first:
        log("sebi %s (intmId=%d): SEBI returned no records - upstream gap, not a client fault"
            % (category, intm_id), "warn")
        return []

    m = TOTAL_RE.search(first)
    total = int(m.group(3).replace(",", "")) if m else None
    per_page = int(re.search(r"nextDel' value='(\d+)'", first).group(1)) if "nextDel" in first else 25
    pages = -(-total // per_page) if total else 1
    if max_pages:
        pages = min(pages, max_pages)
    log("sebi %s: %s records across %d pages (fetching %d)"
        % (category, total, -(-total // per_page) if total else 1, pages))

    # SEBI emits one row per (entity x exchange). Collapse to one record per
    # registration number and keep the exchange list - that IS the segment
    # coverage fact users want ("registered on NSE, BSE and MCX").
    by_key, order, rows_seen = {}, [], 0
    for p in range(1, pages + 1):
        html = first if p == 1 else _page(f, referer, intm_id, p)
        got = 0
        for rec in card_records(html):
            norm = _normalise(rec, category)
            if not norm:
                continue
            got += 1
            rows_seen += 1
            key = norm.pop("_exchange_key")
            exch = norm.pop("exchange_name", None)
            if key in by_key:
                if exch and exch not in by_key[key]["exchanges"]:
                    by_key[key]["exchanges"].append(exch)
                continue
            norm["exchanges"] = [exch] if exch else []
            by_key[key] = norm
            order.append(key)
        if not got:
            log("sebi %s: page %d yielded nothing, stopping" % (category, p), "warn")
            break

    records = [by_key[k] for k in order]
    log("sebi %s: %d entities from %d registration rows"
        % (category, len(records), rows_seen), "ok" if records else "warn")
    if records:
        snapshot("sebi_%s" % category, records)
    return records


def defaulters(f: Fetcher):
    html = f.get_text("%s/sebiweb/broker/BrokerAction.do?doBroker=yes" % BASE, ttl=7 * 86400)
    if not html:
        return []
    out = []
    for rec in card_records(html):
        name = rec.get("name") or rec.get("name_of_the_broker")
        if not name:
            continue
        out.append({
            "name": name,
            "status": rec.get("status"),
            "exchange": rec.get("exchange") or rec.get("stock_exchange"),
            "reg_no": rec.get("registration_no"),
            "raw": rec,
        })
    log("sebi defaulters: %d records" % len(out), "ok" if out else "warn")
    if out:
        snapshot("sebi_defaulters", out)
    return out


def collect(categories=("stock_broker", "commodity_broker", "dp_cdsl", "dp_nsdl"), max_pages=None):
    f = sebi()
    out = {"registry": {}, "defaulters": defaulters(f)}
    for c in categories:
        out["registry"][c] = registry(f, c, max_pages=max_pages)
    return out
