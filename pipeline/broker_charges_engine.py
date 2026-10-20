"""Per-broker "brokerage calculator and charges" pages.

One canonical page per broker at /broker/<id>/charges/, for every broker whose
fee schedule is complete in the trade-cost model (pipeline/trade_cost_engine.py,
BROKER_RATES). A broker with a missing or non-numeric field is skipped and
listed by skipped_brokers(); nothing is ever filled in with a guess.

What a page carries, all of it from data on file:
  - a calculator (equity delivery and equity intraday, the two segments the
    schedule on file covers) driven by data-attributes and
    site/assets/js/broker-charges.js (no inline script, CSP script-src 'self');
  - the fee schedule on file (brokerage rule, DP charge, annual maintenance);
  - a worked example on a Rs 1,00,000 trade computed here from the same
    schedule and the same statutory-rate constants the trade-cost engine uses;
  - an identifiers block (SEBI registration numbers, depository participant
    registrations) taken from the SEBI-register data of the build, only when on
    file;
  - FAQ (FAQPage JSON-LD text equals the visible text), BreadcrumbList, canonical,
    the IBSL sponsored banner already used on broker pages.

compute_charges() is the single formula. For equal buy and sell values it
returns exactly what trade_cost_engine.calculate_trade_fees() returns (checked in
tests/qa_extra_brokerpages.py), and broker-charges.js mirrors it step for step.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

from . import trade_cost_engine as tce
from .identity import norm as _inorm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORKED_VALUE = 100000  # the "Rs 1,00,000 trade" of the worked example

# Rate keys that are the same firm as a tracked broker profile but carry a
# different id in the trade-cost model. The page lives at the profile id so the
# broker has one charges URL, and the stock cost pages of both ids link to it.
URL_ID_ALIAS = {
    "choice-broking": "choice",
    "swastika-investmart": "swastika",
}
# Identity (SEBI numbers, legal name) comes from this profile. HDFC Sky is listed
# as an app of HDFC Securities in config/brokers_master.json (alias and apps), but
# its schedule differs from HDFC Securities', so it keeps its own page.
PROFILE_ALIAS = dict(URL_ID_ALIAS, **{"hdfc-sky": "hdfc-securities"})
# Brokers with no tracked profile: look the legal entity up in the SEBI register
# by exact normalised name. Anything that does not match shows "not on file".
REGISTER_NAMES = {
    "yes-securities": ("YES SECURITIES (INDIA) LIMITED",),
}

BROKING_CATS = ("stock_broker", "commodity_broker")

_NUM_FIELDS = ("delivery_flat", "delivery_pct", "intraday_flat", "intraday_pct", "dp_charge", "demat_amc")

# Same wording as the other calculator pages (see publish._write_calculator_pages).
DISCLAIMER = ("This is a generic cost calculation, not investment, tax or account-opening advice specific to you. "
              "BrokerLens is not a SEBI-registered investment adviser.")

SEGMENT_LABEL = {"delivery": "Equity delivery", "intraday": "Equity intraday"}

CHARGE_ROWS = (
    ("brokerage", "Brokerage (buy and sell orders)"),
    ("stt", "Securities transaction tax (STT)"),
    ("exchange_charges", "Exchange transaction charges (NSE)"),
    ("sebi_charges", "SEBI turnover fee"),
    ("stamp_duty", "Stamp duty (buy side)"),
    ("gst", "GST on brokerage, exchange and SEBI charges"),
    ("dp_charge", "Depository participant (DP) charge"),
)


def _esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


# ----------------------------------------------------------------------------
# Eligibility and URLs
# ----------------------------------------------------------------------------

def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v >= 0


def schedule_complete(rates):
    """True only when every field the calculator needs is a real, non-negative number."""
    return bool(rates and rates.get("brand")) and all(_is_num(rates.get(k)) for k in _NUM_FIELDS)


def eligible_keys():
    """Rate keys that get a page, in stable (alphabetical by brand) order."""
    keys = [k for k, r in tce.BROKER_RATES.items() if schedule_complete(r)]
    return sorted(keys, key=lambda k: (tce.BROKER_RATES[k]["brand"].lower(), k))


def skipped_brokers():
    """Rate keys whose schedule is incomplete (reported, never guessed)."""
    return [k for k, r in tce.BROKER_RATES.items() if not schedule_complete(r)]


def charges_id(rate_key):
    return URL_ID_ALIAS.get(rate_key, rate_key)


def charges_path(rate_key):
    return "/broker/%s/charges/" % charges_id(rate_key)


def has_page(rate_key):
    return rate_key in tce.BROKER_RATES and schedule_complete(tce.BROKER_RATES[rate_key])


def anchor_text(rate_key):
    return "%s brokerage calculator and charges" % tce.BROKER_RATES[rate_key]["brand"]


def charges_link_html(rate_key, style=""):
    """Visible link with the exact anchor text, or "" when the broker has no page."""
    if not has_page(rate_key):
        return ""
    return '<a href="%s"%s>%s</a>' % (
        charges_path(rate_key), (' style="%s"' % style) if style else "", _esc(anchor_text(rate_key)))


def links_for_profile(profile_id):
    """[(brand, path)] of charges pages whose identity profile is `profile_id`."""
    out = []
    for k in eligible_keys():
        if PROFILE_ALIAS.get(k, k) == profile_id:
            out.append((tce.BROKER_RATES[k]["brand"], charges_path(k)))
    return out


def profile_links_html(profile_id):
    """Small text links for a broker's main page (empty when none)."""
    links = links_for_profile(profile_id)
    if not links:
        return ""
    return "".join(
        '<p class="small" style="margin-top:14px"><a href="%s">%s brokerage calculator and charges &rarr;</a></p>'
        % (_esc(path), _esc(brand)) for brand, path in links)


def brokers_index_links_html():
    """Static-only block for the /brokers page: one small text link per page."""
    keys = eligible_keys()
    if not keys:
        return ""
    return (
        '<div class="wrap" data-static-only style="padding-top:0;padding-bottom:12px">'
        '<p class="xs faint">Brokerage calculator and charges by broker: %s</p></div>'
        % " &middot; ".join('<a href="%s">%s</a>' % (charges_path(k), _esc(tce.BROKER_RATES[k]["brand"])) for k in keys))


# ----------------------------------------------------------------------------
# The formula (mirrored by site/assets/js/broker-charges.js)
# ----------------------------------------------------------------------------

def _leg_brokerage(value, flat, pct):
    """One executed order. Same rule as trade_cost_engine.calculate_trade_fees:
    the lower of the flat fee and pct of order value; the flat fee alone when
    there is no percentage; nothing when the schedule is zero or the leg is empty."""
    if value <= 0:
        return 0.0
    if flat == 0 and pct == 0:
        return 0.0
    pct_cost = value * pct
    return min(flat, pct_cost) if pct_cost > 0 else flat


def compute_charges(rates, buy_value, sell_value, segment):
    """Charges for one buy order and one sell order on NSE.

    segment: "delivery" or "intraday". Rates are the trade-cost model's schedule
    (BROKER_RATES entry) plus its statutory constants. Every component is rounded
    to paise before summing, as the trade-cost engine does."""
    delivery = segment == "delivery"
    flat = rates["delivery_flat" if delivery else "intraday_flat"]
    pct = rates["delivery_pct" if delivery else "intraday_pct"]
    buy_value = float(buy_value)
    sell_value = float(sell_value)
    total_turnover = buy_value + sell_value

    brokerage = round(_leg_brokerage(buy_value, flat, pct) + _leg_brokerage(sell_value, flat, pct), 2)
    if delivery:
        stt = round(total_turnover * tce.STT_DELIVERY_RATE, 2)
    else:
        stt = round(sell_value * tce.STT_INTRADAY_SELL_RATE, 2)
    exchange_charges = round(total_turnover * tce.NSE_TURNOVER_RATE, 2)
    sebi_charges = round(total_turnover * tce.SEBI_TURNOVER_RATE, 2)
    if total_turnover > 0 and sebi_charges < 0.01:
        sebi_charges = 0.01
    stamp_duty = round(buy_value * (tce.STAMP_DUTY_DELIVERY_BUY if delivery else tce.STAMP_DUTY_INTRADAY_BUY), 2)
    gst = round((brokerage + exchange_charges + sebi_charges) * tce.GST_RATE, 2)
    dp_charge = rates["dp_charge"] if (delivery and sell_value > 0) else 0.0
    total = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + dp_charge, 2)
    return {
        "buy_value": buy_value, "sell_value": sell_value, "segment": segment,
        "brokerage": brokerage, "stt": stt, "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges, "stamp_duty": stamp_duty, "gst": gst,
        "dp_charge": dp_charge, "total": total,
    }


# ----------------------------------------------------------------------------
# Number and text formatting (no dashes anywhere in user-visible copy)
# ----------------------------------------------------------------------------

def inr(x, dp=2):
    """Indian digit grouping: 100000 -> 1,00,000.00"""
    s = "%.*f" % (dp, abs(x))
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if x < 0 else "") + whole + ("." + frac if dp else "")


def rs(x):
    """'Rs 20' for whole rupees, 'Rs 10.62' otherwise, Indian grouping."""
    return "Rs " + (inr(x, 0) if float(x) == int(x) else inr(x, 2))


def _pct(fraction):
    return ("%.5f" % (fraction * 100)).rstrip("0").rstrip(".")


def _rule_text(flat, pct):
    """Plain-language brokerage rule from the schedule on file."""
    if flat == 0:
        return "Rs 0 brokerage"
    if pct == 0:
        return "Flat %s per executed order" % rs(flat)
    return "Lower of %s and %s%% of order value, per executed order" % (rs(flat), _pct(pct))


def _rule_short(flat, pct):
    if flat == 0:
        return "Rs 0"
    if pct == 0:
        return "%s flat" % rs(flat)
    return "lower of %s or %s%%" % (rs(flat), _pct(pct))


def statutory_rows():
    """(label, rate text) from the trade-cost engine's own constants."""
    return [
        ("STT, equity delivery", "%s%% on the buy value and %s%% on the sell value" % (
            _pct(tce.STT_DELIVERY_RATE), _pct(tce.STT_DELIVERY_RATE))),
        ("STT, equity intraday", "%s%% on the sell value" % _pct(tce.STT_INTRADAY_SELL_RATE)),
        ("Exchange transaction charges (NSE)", "%s%% of total turnover" % _pct(tce.NSE_TURNOVER_RATE)),
        ("SEBI turnover fee", "Rs %s per crore of total turnover (%s%%)" % (
            inr(tce.SEBI_TURNOVER_RATE * 10000000, 0), _pct(tce.SEBI_TURNOVER_RATE))),
        ("Stamp duty, equity delivery", "%s%% on the buy value" % _pct(tce.STAMP_DUTY_DELIVERY_BUY)),
        ("Stamp duty, equity intraday", "%s%% on the buy value" % _pct(tce.STAMP_DUTY_INTRADAY_BUY)),
        ("GST", "%s%% on brokerage, exchange charges and SEBI fee" % _pct(tce.GST_RATE)),
    ]


def _basis(rates, res):
    """How each component of a computed example was worked out (text, per row key)."""
    delivery = res["segment"] == "delivery"
    flat = rates["delivery_flat" if delivery else "intraday_flat"]
    pct = rates["delivery_pct" if delivery else "intraday_pct"]
    buy, sell = res["buy_value"], res["sell_value"]
    total_turnover = buy + sell
    b_buy = round(_leg_brokerage(buy, flat, pct), 2)
    b_sell = round(_leg_brokerage(sell, flat, pct), 2)
    if flat == 0:
        brokerage = "Rs 0 under the schedule on file for this segment"
    else:
        brokerage = "%s: Rs %s on the buy order and Rs %s on the sell order" % (
            _rule_text(flat, pct), inr(b_buy), inr(b_sell))
    return {
        "brokerage": brokerage,
        "stt": ("%s%% of Rs %s total turnover (buy plus sell)" % (_pct(tce.STT_DELIVERY_RATE), inr(total_turnover, 0))
                if delivery else "%s%% of Rs %s sell value" % (_pct(tce.STT_INTRADAY_SELL_RATE), inr(sell, 0))),
        "exchange_charges": "%s%% of Rs %s total turnover" % (_pct(tce.NSE_TURNOVER_RATE), inr(total_turnover, 0)),
        "sebi_charges": "Rs %s per crore on Rs %s total turnover" % (
            inr(tce.SEBI_TURNOVER_RATE * 10000000, 0), inr(total_turnover, 0)),
        "stamp_duty": "%s%% of Rs %s buy value" % (
            _pct(tce.STAMP_DUTY_DELIVERY_BUY if delivery else tce.STAMP_DUTY_INTRADAY_BUY), inr(buy, 0)),
        "gst": "%s%% of Rs %s (brokerage plus exchange and SEBI charges)" % (
            _pct(tce.GST_RATE), inr(res["brokerage"] + res["exchange_charges"] + res["sebi_charges"])),
        "dp_charge": ("Charged once when the shares are sold from the demat account, as listed in the schedule on file"
                      if delivery else "Not applicable to intraday trades"),
    }


# ----------------------------------------------------------------------------
# HTML fragments
# ----------------------------------------------------------------------------

def _calc_rows_html(res):
    """Result table body, same rows and labels as broker-charges.js renders."""
    delivery = res["segment"] == "delivery"
    out = []
    for key, label in CHARGE_ROWS:
        if key == "dp_charge" and not delivery:
            continue
        out.append('<tr><th scope="row">%s</th><td class="right num">Rs %s</td></tr>' % (_esc(label), inr(res[key])))
    out.append('<tr class="total"><th scope="row">Total charges</th><td class="right num"><strong>Rs %s</strong></td></tr>'
               % inr(res["total"]))
    return "".join(out)


def _calc_table_html(res):
    return ('<div class="table-scroll"><table class="data"><thead><tr><th>Charge</th>'
            '<th class="right">Amount</th></tr></thead><tbody>%s</tbody></table></div>' % _calc_rows_html(res))


def _worked_table_html(rates, res):
    basis = _basis(rates, res)
    delivery = res["segment"] == "delivery"
    rows = []
    for key, label in CHARGE_ROWS:
        if key == "dp_charge" and not delivery:
            continue
        rows.append('<tr><th scope="row">%s</th><td class="small">%s</td><td class="right num" data-worked="%s">Rs %s</td></tr>'
                    % (_esc(label), _esc(basis[key]), key, inr(res[key])))
    rows.append('<tr><th scope="row">Total charges</th><td class="small">Sum of the rows above</td>'
                '<td class="right num" data-worked="total"><strong>Rs %s</strong></td></tr>' % inr(res["total"]))
    return ('<div class="table-scroll"><table class="data"><thead><tr><th>Charge</th><th>How it is worked out</th>'
            '<th class="right">Amount</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(rows))


def _data_attrs(rates):
    vals = {
        "delivery-flat": rates["delivery_flat"], "delivery-pct": rates["delivery_pct"],
        "intraday-flat": rates["intraday_flat"], "intraday-pct": rates["intraday_pct"],
        "dp-charge": rates["dp_charge"],
        "stt-delivery": tce.STT_DELIVERY_RATE, "stt-intraday-sell": tce.STT_INTRADAY_SELL_RATE,
        "nse": tce.NSE_TURNOVER_RATE, "sebi": tce.SEBI_TURNOVER_RATE, "gst": tce.GST_RATE,
        "stamp-delivery": tce.STAMP_DUTY_DELIVERY_BUY, "stamp-intraday": tce.STAMP_DUTY_INTRADAY_BUY,
    }
    return " ".join('data-%s="%s"' % (k, repr(float(v))) for k, v in vals.items())


def _website(rate_key, profile):
    """Broker website: the tracked profile's, else the origin of the model's own URL."""
    site = (profile or {}).get("website")
    if site:
        return site
    url = tce.BROKER_RATES[rate_key].get("cta_url") or ""
    parts = urlsplit(url)
    return ("%s://%s" % (parts.scheme, parts.netloc)) if parts.scheme and parts.netloc else ""


# ----------------------------------------------------------------------------
# Identifiers (SEBI numbers) from the build's register data
# ----------------------------------------------------------------------------

def _identifiers(rate_key, built_by_id, registry):
    """{"legal_name", "broking": [(reg_no, entity)], "dps": [(depository, reg_no, entity)], "profile"}.
    Only what the register data of this build actually holds."""
    pid = PROFILE_ALIAS.get(rate_key, rate_key)
    b = built_by_id.get(pid)
    out = {"legal_name": None, "broking": [], "dps": [], "profile": None, "profile_id": None}
    if b:
        p = b.get("profile") or {}
        out["profile"], out["profile_id"] = p, pid
        out["legal_name"] = p.get("legal_name")
        seen = set()
        for e in p.get("sebi_entities") or []:
            if e.get("reg_no") and set(e.get("categories") or []) & set(BROKING_CATS) and e["reg_no"] not in seen:
                seen.add(e["reg_no"])
                out["broking"].append((e["reg_no"], e.get("legal_name")))
        if p.get("sebi_reg_no") and p["sebi_reg_no"] not in seen:
            out["broking"].insert(0, (p["sebi_reg_no"], p.get("legal_name")))
        for d in p.get("dp_registrations") or []:
            if d.get("reg_no"):
                out["dps"].append((d.get("depository"), d["reg_no"], d.get("entity")))
        return out
    wanted = {_inorm(n) for n in REGISTER_NAMES.get(rate_key, ())}
    if wanted:
        seen_b, seen_d = set(), set()
        for rec in registry or []:
            if _inorm(rec.get("legal_name")) not in wanted or not rec.get("sebi_reg_no"):
                continue
            cats = rec.get("categories") or []
            reg = rec["sebi_reg_no"]
            if set(cats) & set(BROKING_CATS) and reg not in seen_b:
                seen_b.add(reg)
                out["broking"].append((reg, rec.get("legal_name")))
            if ("dp_cdsl" in cats or "dp_nsdl" in cats) and reg not in seen_d:
                seen_d.add(reg)
                out["dps"].append(("CDSL" if "dp_cdsl" in cats else "NSDL", reg, rec.get("legal_name")))
            out["legal_name"] = out["legal_name"] or rec.get("legal_name")
    return out


def _identifiers_html(brand, rate_key, ident):
    rows = []
    if ident["legal_name"]:
        rows.append(("Legal name", _esc(ident["legal_name"])))
    if ident["broking"]:
        rows.append(("SEBI registration number (stock broking)", "<br>".join(
            "%s%s" % (_esc(no), (" (%s)" % _esc(ent)) if ent and ident["legal_name"] and _inorm(ent) != _inorm(ident["legal_name"]) else "")
            for no, ent in ident["broking"])))
    if ident["dps"]:
        rows.append(("SEBI registration number (depository participant)", "<br>".join(
            "%s: %s" % (_esc(dep), _esc(no)) for dep, no, _ent in ident["dps"])))
    if not ident["broking"] and not ident["dps"]:
        body = ('<p class="small" style="max-width:72ch">BrokerLens does not yet hold a matched SEBI registration number or '
                'depository participant registration for %s, so none is shown. Check SEBI\'s own register before '
                'opening an account.</p>' % _esc(brand))
    else:
        body = ('<div class="table-scroll"><table class="data"><tbody>%s</tbody></table></div>'
                '<p class="xs faint" style="margin-top:6px">Source: SEBI recognised-intermediary register, as of '
                'BrokerLens\'s latest data refresh. The depository participant number above is the SEBI registration '
                'number, not the DP ID printed on your own demat account statement, which BrokerLens does not hold.</p>'
                % "".join('<tr><th scope="row">%s</th><td>%s</td></tr>' % (l, v) for l, v in rows))
    note = ""
    if rate_key in PROFILE_ALIAS and rate_key not in URL_ID_ALIAS and ident["profile"]:
        if brand in (ident["profile"].get("apps") or []):
            note = ('<p class="xs faint" style="margin-top:6px">%s is listed as an app of %s; the numbers above belong to '
                    'that entity.</p>' % (_esc(brand), _esc(ident["legal_name"] or "")))
    return '<h2 style="margin-top:28px;font-size:18px">Registration and identifiers for %s</h2>%s%s' % (_esc(brand), body, note)


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------

def _faqs(brand, rates, ex_del, ex_int, ident):
    d_rule = _rule_text(rates["delivery_flat"], rates["delivery_pct"])
    i_rule = _rule_text(rates["intraday_flat"], rates["intraday_pct"])
    amc = ("%s has no annual maintenance charge (AMC) on its demat account in the schedule on file." % brand
           if rates["demat_amc"] == 0 else
           "The schedule on file lists an annual maintenance charge (AMC) of %s per year on a %s demat account." % (
               rs(rates["demat_amc"]), brand))
    faqs = [
        ("What is the brokerage for equity delivery at %s?" % brand,
         "%s. This is the schedule on file; confirm it on the %s tariff page before you rely on it." % (d_rule, brand)),
        ("What is the intraday brokerage at %s?" % brand,
         "%s. This is the schedule on file; confirm it on the %s tariff page before you rely on it." % (i_rule, brand)),
        ("How much are total charges on a Rs 1,00,000 equity delivery trade at %s?" % brand,
         "Buying Rs 1,00,000 and selling Rs 1,00,000 of shares on NSE as delivery comes to Rs %s in total charges at %s, "
         "of which brokerage is Rs %s. This is a worked example, not a quote." % (
             inr(ex_del["total"]), brand, inr(ex_del["brokerage"]))),
        ("How much are total charges on a Rs 1,00,000 intraday trade at %s?" % brand,
         "Buying Rs 1,00,000 and selling Rs 1,00,000 of shares on NSE as intraday comes to Rs %s in total charges at %s, "
         "of which brokerage is Rs %s. This is a worked example, not a quote." % (
             inr(ex_int["total"]), brand, inr(ex_int["brokerage"]))),
        ("What is the DP charge at %s?" % brand,
         "The schedule on file lists a DP charge of %s, applied once when delivery shares are sold from the demat account." % rs(rates["dp_charge"])),
        ("Is there an annual maintenance charge on a %s demat account?" % brand, amc),
    ]
    if ident["broking"]:
        faqs.append(("What is the SEBI registration number of %s?" % brand,
                     "The SEBI register lists these stock-broking registration numbers: %s. Confirm on SEBI's register before "
                     "you act on them." % ", ".join(no for no, _e in ident["broking"])))
    if ident["dps"]:
        faqs.append(("What is the depository participant registration of %s?" % brand,
                     "The SEBI register lists: %s. These are SEBI registration numbers, not the DP ID printed on your own demat "
                     "account statement, which BrokerLens does not hold." % "; ".join(
                         "%s registration %s" % (dep, no) for dep, no, _e in ident["dps"])))
    faqs.append(("Does this calculator cover futures, options, currency and commodity at %s?" % brand,
                 "Not yet. The schedule on file for %s covers equity delivery and equity intraday only, so futures, options, "
                 "currency and commodity charges are not calculated here." % brand))
    return faqs


def render_charges_page(rate_key, built_by_id=None, registry=None, site_url="https://www.brokerlens.in",
                        generated_on=None, stocks=None):
    """Full HTML for /broker/<id>/charges/ (uses publish.py's shared page head, foot and banner)."""
    from . import publish as P  # lazy: publish imports this module's caller, not the other way round

    rates = tce.BROKER_RATES[rate_key]
    assert schedule_complete(rates), rate_key
    brand = rates["brand"]
    cid = charges_id(rate_key)
    canonical = "%s/broker/%s/charges/" % (site_url, cid)
    ident = _identifiers(rate_key, built_by_id or {}, registry)
    profile = ident["profile"]
    generated_on = generated_on or datetime.now(timezone.utc).strftime("%d %B %Y")

    ex_del = compute_charges(rates, WORKED_VALUE, WORKED_VALUE, "delivery")
    ex_int = compute_charges(rates, WORKED_VALUE, WORKED_VALUE, "intraday")
    faqs = _faqs(brand, rates, ex_del, ex_int, ident)

    h1 = "%s brokerage calculator and charges" % brand
    title = "%s Brokerage Calculator and Charges | BrokerLens" % brand
    description = (
        "%s brokerage calculator: equity delivery %s, intraday %s, DP charge %s. Works out STT, exchange fees, SEBI fee, "
        "stamp duty and GST, with a worked example on a Rs 1,00,000 trade." % (
            brand, _rule_short(rates["delivery_flat"], rates["delivery_pct"]),
            _rule_short(rates["intraday_flat"], rates["intraday_pct"]), rs(rates["dp_charge"])))[:300]

    trail = [("BrokerLens", "/"), ("Brokers", "/brokers")]
    if ident["profile_id"]:
        trail.append((profile.get("brand") or brand, "/broker/%s/" % ident["profile_id"]))
    trail.append((h1, None))
    crumb_html, crumb_jsonld = P._breadcrumb(trail)

    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebApplication", "name": h1, "url": canonical, "applicationCategory": "FinanceApplication",
         "operatingSystem": "Any (runs in browser)", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"}},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]},
        crumb_jsonld,
    ]}

    head = P._REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description), "canonical": _esc(canonical),
        "jsonld": json.dumps(jsonld, ensure_ascii=False)}
    head = head.replace("</head>", P._stamp_asset_versions(
        '<script src="/assets/js/broker-charges.js" defer></script></head>'), 1)

    website = _website(rate_key, profile)
    website_html = (' Confirm every figure on the <a href="%s" rel="noopener" target="_blank">%s website</a>.' % (
        _esc(website), _esc(brand))) if website else " Confirm every figure with the broker before you rely on it."

    sched_rows = [
        ("Equity delivery brokerage", _esc(_rule_text(rates["delivery_flat"], rates["delivery_pct"]))),
        ("Equity intraday brokerage", _esc(_rule_text(rates["intraday_flat"], rates["intraday_pct"]))),
        ("DP charge (per sale of delivery shares)", _esc(rs(rates["dp_charge"]))),
        ("Demat annual maintenance charge (AMC)", _esc(rs(rates["demat_amc"]) + " per year")),
        ("Futures, options, currency, commodity", "Not on file, so not calculated on this page"),
    ]
    sched_html = '<div class="table-scroll"><table class="data"><tbody>%s</tbody></table></div>' % "".join(
        '<tr><th scope="row">%s</th><td>%s</td></tr>' % (l, v) for l, v in sched_rows)

    stat_html = '<div class="table-scroll"><table class="data"><tbody>%s</tbody></table></div>' % "".join(
        '<tr><th scope="row">%s</th><td>%s</td></tr>' % (_esc(l), _esc(v)) for l, v in statutory_rows())

    calc_html = (
        '<div class="card" id="broker-charges" data-broker-charges %s style="margin-top:20px;padding:20px;max-width:640px">'
        '<div class="card-title">Charges calculator</div>'
        '<div class="grid g3" style="margin-top:12px">'
        '<div class="field"><label for="bc-segment">Segment</label><select id="bc-segment">'
        '<option value="delivery">Equity delivery</option><option value="intraday">Equity intraday</option></select></div>'
        '<div class="field"><label for="bc-buy">Buy value (Rs)</label>'
        '<input id="bc-buy" type="number" min="0" step="1000" value="%d" inputmode="decimal"></div>'
        '<div class="field"><label for="bc-sell">Sell value (Rs)</label>'
        '<input id="bc-sell" type="number" min="0" step="1000" value="%d" inputmode="decimal"></div></div>'
        '<button type="button" id="bc-run" class="btn btn-primary" style="margin-top:8px">Calculate charges</button>'
        '<div id="bc-out" aria-live="polite" style="margin-top:16px">%s</div>'
        '<p class="xs faint" style="margin-top:8px">Shown for a Rs %s buy and a Rs %s sell as equity delivery. Change the '
        'values and press Calculate; the sums run in your browser.</p></div>'
    ) % (_data_attrs(rates), WORKED_VALUE, WORKED_VALUE, _calc_table_html(ex_del), inr(WORKED_VALUE, 0), inr(WORKED_VALUE, 0))

    worked_html = (
        '<h2 style="margin-top:32px;font-size:18px">Worked example: charges on a Rs 1,00,000 trade at %s</h2>'
        '<p style="max-width:72ch">Buy Rs 1,00,000 of shares and sell Rs 1,00,000 of shares on NSE, the same day or later, '
        'with no profit or loss. Figures are worked out here from the schedule on file and the statutory rates below.</p>'
        '<h3 style="margin-top:16px;font-size:15px">Equity delivery</h3>%s'
        '<h3 style="margin-top:16px;font-size:15px">Equity intraday</h3>%s'
    ) % (_esc(brand), _worked_table_html(rates, ex_del), _worked_table_html(rates, ex_int))

    source_html = (
        '<h2 style="margin-top:28px;font-size:18px">Where these numbers come from</h2>'
        '<p class="small" style="max-width:72ch;line-height:1.6">Brokerage, DP charge and annual maintenance charge come from '
        'the published %s tariff as held in the BrokerLens trade-cost model, the same schedule behind every %s stock cost page on this '
        'site. The date this tariff was last checked is not on file, so check it on the broker\'s own tariff page.%s '
        'Statutory rates are the ones in the table below, as held in the same model after the 2024 SEBI and Budget '
        'revisions; a separate effective date for each rate is not on file. The figures on this page were generated on %s.</p>'
        % (_esc(brand), _esc(brand), website_html, _esc(generated_on)))

    how_html = (
        '<h2 style="margin-top:28px;font-size:18px">How the calculation works</h2>'
        '<ol class="small" style="max-width:72ch;line-height:1.6">'
        '<li>Brokerage is worked out per executed order (one buy, one sell) under the rule in the schedule above.</li>'
        '<li>STT, exchange charges, SEBI fee and stamp duty use the statutory rates in the table below.</li>'
        '<li>GST is charged on brokerage, exchange charges and the SEBI fee, not on STT or stamp duty.</li>'
        '<li>The DP charge applies once, when delivery shares are sold. It is taken as listed; no GST is added on top.</li>'
        '<li>Every line is rounded to the paisa before the total is added up.</li></ol>'
        '<h3 style="margin-top:16px;font-size:15px">Statutory rates used</h3>%s'
        '<h3 style="margin-top:16px;font-size:15px">What this does not cover</h3>'
        '<p class="small" style="max-width:72ch;line-height:1.6">NSE rates only, one buy order and one sell order, no '
        'brokerage plan variants or discounts, no call-and-trade or other add-on fees, and no futures, options, currency or '
        'commodity trades. Real contract notes can differ by a few paise.</p>' % stat_html)

    more = [
        '<a class="chip" href="/broker/%s/trade/">%s charges on a specific stock &rarr;</a>' % (_esc(rate_key), _esc(brand))]
    if ident["profile_id"]:
        more.insert(0, '<a class="chip" href="/broker/%s/">%s profile, registration and complaints &rarr;</a>' % (
            _esc(ident["profile_id"]), _esc(profile.get("brand") or brand)))
    more += ['<a class="chip" href="/calculator">Compare monthly brokerage across brokers &rarr;</a>',
             '<a class="chip" href="/trade-costs/">All stock trade cost pages &rarr;</a>']
    stock_chips = "".join(
        '<a class="chip" href="/broker/%s/trade/%s/">%s &rarr;</a>' % (_esc(rate_key), _esc(tce._stock_slug(s["symbol"])), _esc(s["symbol"]))
        for s in (stocks or []))
    others = "".join('<a class="chip" href="%s">%s</a>' % (charges_path(k), _esc(tce.BROKER_RATES[k]["brand"]))
                     for k in eligible_keys() if k != rate_key)
    more_html = (
        '<h2 style="margin-top:28px;font-size:18px">More on %s</h2><div class="row-wrap" style="gap:8px">%s</div>%s'
        '<h2 style="margin-top:28px;font-size:18px">Brokerage calculators for other brokers</h2>'
        '<div class="row-wrap" style="gap:8px">%s</div>'
    ) % (_esc(brand), "".join(more),
         ('<p class="small" style="margin-top:12px">Charges at %s on a trade in a popular stock:</p>'
          '<div class="row-wrap" style="gap:8px;margin-top:6px">%s</div>' % (_esc(brand), stock_chips)) if stock_chips else "",
         others)

    faq_html = ('<h2 style="margin-top:28px;font-size:18px">Frequently asked questions</h2><div style="max-width:68ch">%s</div>'
                % "".join('<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a)) for q, a in faqs))

    body = head + (
        crumb_html
        + '<h1 style="margin-top:0">%s</h1>' % _esc(h1)
        + '<p class="muted" style="max-width:68ch">On a Rs 1,00,000 equity delivery round trip (buy and sell), the %s schedule on '
          'file gives total charges of Rs %s, of which brokerage is Rs %s. Use the calculator for your own order values.</p>' % (
              _esc(brand), inr(ex_del["total"]), inr(ex_del["brokerage"]))
        + P.ibslBanner_html("wide", "broker")
        + calc_html
        + '<h2 style="margin-top:32px;font-size:18px">%s fee schedule on file</h2>' % _esc(brand) + sched_html
        + worked_html
        + _identifiers_html(brand, rate_key, ident)
        + source_html + how_html + faq_html + more_html
        + '<p class="xs faint" style="margin-top:20px">%s</p>' % _esc(DISCLAIMER)
    )
    body += P._REGISTRY_PAGE_FOOT % {"source_note": P._source_note(
        "This page works out charges from the broker tariff and statutory rates held in the BrokerLens trade-cost model, "
        "plus SEBI-register numbers where matched.")}
    return body


def build_broker_charges_pages(built, registry=None, site_url="https://www.brokerlens.in", site_dir=None):
    """Write every eligible page; return the list of site paths for the sitemap."""
    from . import publish as P

    site_dir = site_dir or os.path.join(ROOT, "site")
    built_by_id = {b["id"]: b for b in (built or [])}
    try:
        stocks = tce.get_trade_cost_stocks(limit_stocks=8)
    except Exception:
        stocks = []
    urls = []
    for k in eligible_keys():
        page = render_charges_page(k, built_by_id, registry, site_url=site_url, stocks=stocks)
        dest = os.path.join(site_dir, "broker", charges_id(k), "charges")
        os.makedirs(dest, exist_ok=True)
        P._write_text(os.path.join(dest, "index.html"), page)
        urls.append(charges_path(k))
    skipped = skipped_brokers()
    P.log("broker charges pages: %d written%s" % (
        len(urls), ("; skipped (incomplete schedule): %s" % ", ".join(skipped)) if skipped else ""), "ok")
    return urls
