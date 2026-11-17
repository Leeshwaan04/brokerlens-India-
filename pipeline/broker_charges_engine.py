"""Per-broker "brokerage calculator and charges" pages.

One canonical page per broker at /broker/<id>/charges/, for every broker whose
fee schedule is complete in the trade-cost model (pipeline/trade_cost_engine.py,
BROKER_RATES) AND whose encoded brokerage rule is unambiguous (see
withheld_reasons()). A broker with a missing or non-numeric field is skipped and
listed by skipped_brokers(); a broker whose rule the model cannot state safely
(a percentage plan with a rupee cap the model does not support, a restricted or
conditional plan) is withheld and listed by withheld_brokers(). Nothing is ever
filled in with a guess. eligible_keys() is the single function every hook uses
(page writer, sitemap list, stock cost page link, broker profile link, /brokers
list, hub chips), so the withheld set is honoured everywhere.

The figures are an indicative schedule held in the BrokerLens model. They are NOT
verified against the broker's own rate card and no check date is on file, and the
copy says so (the rest of the site shows no pricing it cannot verify).

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

# ----------------------------------------------------------------------------
# Withholding rule (an unambiguous encoded rule, or no page)
# ----------------------------------------------------------------------------
# The model encodes a brokerage rule as (flat, pct). flat=0 and pct=0 is "zero";
# pct=0 is a flat per-order fee; both set means "lower of flat and pct of order
# value". That last form is the discount-broker cap ("Rs 20 or 0.1%, whichever is
# lower") and is only safe to render when the percentage is a discount-broker
# level. A percentage above CAP_RULE_MAX_PCT defaults to withheld, because for
# most brokers at that level the real plan is an uncapped ad-valorem commission
# with no flat alternative at all (ICICI Direct 0.55%, HDFC Securities 0.50%,
# Sharekhan 0.30%, Motilal Oswal 0.20% and so on), and rendering "lower of Rs 20
# and X%" for those would publish a wrong rupee total. 2026-11-17 verification
# (see reports/autopilot/LOG.md) found this threshold is not a perfect test,
# though: Choice Broking's own current pricing page states a genuine "Rs 20 or
# 0.20%, whichever is lower" cap, above the threshold but real. A broker whose
# cap above the threshold has been read off its own current pricing page gets a
# "cap_verified_asof" date on its BROKER_RATES entry, which lets it through this
# check without loosening the default for every other broker at that level.
CAP_RULE_MAX_PCT = tce.CAP_RULE_MAX_PCT  # single source of truth: trade_cost_engine.py

# Wording in the model's own tagline that marks a restricted or conditional plan
# (the schedule would only hold for some customers, or only for a period).
CONDITIONAL_PLAN_MARKERS = {
    "young investors": "zero brokerage applies to a restricted plan (young investors)",
    "loss making": "zero brokerage applies only to loss-making trades, which the schedule does not model",
    "pay only when": "brokerage is conditional on profit, which the schedule does not model",
    "first year": "a fee waiver that holds for the first year only, which the schedule does not model",
}


def rule_kind(flat, pct):
    """'zero', 'flat' (fixed fee per order) or 'lower_of' (flat cap with a percentage)."""
    if flat == 0 and pct == 0:
        return "zero"
    if pct == 0:
        return "flat"
    return "lower_of"


def withheld_reasons(rate_key):
    """Reasons the page for this rate key must not be published ([] when it may be).

    Pure function of the BROKER_RATES entry, so it is testable on fixtures."""
    return _withheld_reasons_for(tce.BROKER_RATES.get(rate_key) or {})


def _withheld_reasons_for(rates):
    reasons = []
    kinds = {}
    cap_verified = bool(rates.get("cap_verified_asof"))
    for seg in ("delivery", "intraday"):
        flat, pct = rates.get(seg + "_flat"), rates.get(seg + "_pct")
        if not (_is_num(flat) and _is_num(pct)):
            continue  # incomplete schedules are skipped_brokers()'s business
        kinds[seg] = rule_kind(flat, pct)
        if kinds[seg] == "lower_of" and pct > CAP_RULE_MAX_PCT and not cap_verified:
            if flat == 0:
                reasons.append(
                    "%s rule is a %s%% uncapped percentage plan that the model does not support" % (
                        seg, _pct(pct)))
            else:
                reasons.append(
                    "%s rule is a %s%% percentage plan with a Rs %s cap that the model does not support "
                    "without checking the broker's own current pricing page" % (
                        seg, _pct(pct), ("%g" % flat)))
    if kinds and all(k == "zero" for k in kinds.values()) and len(kinds) == 2:
        reasons.append("zero brokerage on every segment is a restricted-plan signal, not a standard schedule")
    tag = (rates.get("tagline") or "").lower()
    for marker, why in CONDITIONAL_PLAN_MARKERS.items():
        if marker in tag:
            reasons.append(why)
    return reasons


def is_withheld(rate_key):
    return bool(withheld_reasons(rate_key))


def withheld_brokers():
    """{rate_key: [reasons]} for complete schedules whose page is withheld, in model order."""
    out = {}
    for k, r in tce.BROKER_RATES.items():
        if schedule_complete(r):
            why = _withheld_reasons_for(r)
            if why:
                out[k] = why
    return out


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
    ("dp_charge", "DP charge (includes GST)"),
)

# What every page says about the status of its figures. Kept in one place so the
# source copy, meta description, FAQ and JSON-LD cannot drift apart.
STATUS_SHORT = "indicative schedule in the BrokerLens model, not verified against the broker's own rate card"
CHECKED_NOT_ON_FILE = "The date it was checked is not on file"
DP_GST_NOTE = "The DP charge already includes 18% GST, so no further GST is added to it"


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
    """Rate keys that get a page, in stable (alphabetical by brand) order.

    The ONE list every hook reads: complete schedule and not withheld."""
    keys = [k for k, r in tce.BROKER_RATES.items() if schedule_complete(r) and not _withheld_reasons_for(r)]
    return sorted(keys, key=lambda k: (tce.BROKER_RATES[k]["brand"].lower(), k))


def skipped_brokers():
    """Rate keys whose schedule is incomplete (reported, never guessed)."""
    return [k for k, r in tce.BROKER_RATES.items() if not schedule_complete(r)]


def charges_id(rate_key):
    return URL_ID_ALIAS.get(rate_key, rate_key)


def charges_path(rate_key):
    return "/broker/%s/charges/" % charges_id(rate_key)


def has_page(rate_key):
    return rate_key in tce.BROKER_RATES and schedule_complete(tce.BROKER_RATES[rate_key]) and not is_withheld(rate_key)


_PROFILE_IDS = None


def _profile_ids():
    """Broker ids that have a /broker/<id>/ profile (config/brokers_master.json)."""
    global _PROFILE_IDS
    if _PROFILE_IDS is None:
        try:
            with open(os.path.join(ROOT, "config", "brokers_master.json"), encoding="utf-8") as fh:
                _PROFILE_IDS = {b.get("id") for b in (json.load(fh).get("brokers") or []) if b.get("id")}
        except (OSError, ValueError):
            _PROFILE_IDS = set()
    return _PROFILE_IDS


def cost_page_path(rate_key):
    """The one page that answers cost questions about this broker.

    The charges page when the broker has one, else its profile, else the /trade-costs/
    hub. The retired /broker/<key>/trade/... pages 308 here (vercel.json), and every link
    that used to point at them now points here instead."""
    if has_page(rate_key):
        return charges_path(rate_key)
    pid = PROFILE_ALIAS.get(rate_key, rate_key)
    if pid in _profile_ids():
        return "/broker/%s/" % pid
    return "/trade-costs/"


def _schedule_signature(rates):
    return tuple(rates.get(k) for k in _NUM_FIELDS)


def same_schedule_peers(rate_key):
    """Brands of other eligible brokers whose schedule on file is identical field for field.

    Their worked-example tables match apart from the brand name, and the page says so."""
    me = tce.BROKER_RATES.get(rate_key)
    if not me:
        return []
    sig = _schedule_signature(me)
    return [tce.BROKER_RATES[k]["brand"] for k in eligible_keys()
            if k != rate_key and _schedule_signature(tce.BROKER_RATES[k]) == sig]


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
        ("GST", "%s%% on brokerage, exchange charges and SEBI fee (the DP charge already includes its own GST)" % _pct(tce.GST_RATE)),
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
        "gst": "%s%% of Rs %s (brokerage plus exchange and SEBI charges; the DP charge carries its own GST)" % (
            _pct(tce.GST_RATE), inr(res["brokerage"] + res["exchange_charges"] + res["sebi_charges"])),
        "dp_charge": ("Charged once when the shares are sold from the demat account, as listed in the indicative schedule. "
                      "The figure already includes 18% GST, so none is added to it"
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


def _reg_link(no, reg_to_registry_slug):
    slug = (reg_to_registry_slug or {}).get(str(no).strip().upper())
    return '<a href="/sebi-registry/%s/">%s</a>' % (slug, _esc(no)) if slug else _esc(no)


def _identifiers_html(brand, rate_key, ident, reg_to_registry_slug=None):
    rows = []
    if ident["legal_name"]:
        rows.append(("Legal name", _esc(ident["legal_name"])))
    if ident["broking"]:
        rows.append(("SEBI registration number (stock broking)", "<br>".join(
            "%s%s" % (_reg_link(no, reg_to_registry_slug), (" (%s)" % _esc(ent)) if ent and ident["legal_name"] and _inorm(ent) != _inorm(ident["legal_name"]) else "")
            for no, ent in ident["broking"])))
    if ident["dps"]:
        rows.append(("SEBI registration number (depository participant)", "<br>".join(
            "%s: %s" % (_esc(dep), _reg_link(no, reg_to_registry_slug)) for dep, no, _ent in ident["dps"])))
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

def _faqs(brand, rates, ex_del, ex_int, ident, peers=()):
    d_rule = _rule_text(rates["delivery_flat"], rates["delivery_pct"])
    i_rule = _rule_text(rates["intraday_flat"], rates["intraday_pct"])
    confirm = ("This is the indicative schedule held in the BrokerLens model. It has not been verified against %s's own rate card "
               "and the date it was checked is not on file, so confirm it on the %s tariff page before you rely on it." % (brand, brand))
    amc = ("The indicative schedule lists no annual maintenance charge (AMC) on a %s demat account." % brand
           if rates["demat_amc"] == 0 else
           "The indicative schedule lists an annual maintenance charge (AMC) of %s per year on a %s demat account. "
           "It has not been verified against the broker's own rate card." % (rs(rates["demat_amc"]), brand))
    faqs = [
        ("Are these %s charges verified against the broker's own tariff?" % brand,
         "No. The figures are an indicative schedule held in the BrokerLens model. They have not been verified against %s's "
         "own rate card, and the date they were checked is not on file. Confirm them on the broker's own tariff page." % brand),
        ("What is the brokerage for equity delivery at %s?" % brand, "%s. %s" % (d_rule, confirm)),
        ("What is the intraday brokerage at %s?" % brand, "%s. %s" % (i_rule, confirm)),
        ("How much are total charges on a Rs 1,00,000 equity delivery trade at %s?" % brand,
         "On the indicative schedule, buying Rs 1,00,000 and selling Rs 1,00,000 of shares on NSE as delivery comes to Rs %s in "
         "total charges at %s, of which brokerage is Rs %s. This is a worked example, not a quote, and the schedule is not "
         "verified against the broker's own rate card." % (inr(ex_del["total"]), brand, inr(ex_del["brokerage"]))),
        ("How much are total charges on a Rs 1,00,000 intraday trade at %s?" % brand,
         "On the indicative schedule, buying Rs 1,00,000 and selling Rs 1,00,000 of shares on NSE as intraday comes to Rs %s in "
         "total charges at %s, of which brokerage is Rs %s. This is a worked example, not a quote, and the schedule is not "
         "verified against the broker's own rate card." % (inr(ex_int["total"]), brand, inr(ex_int["brokerage"]))),
        ("What is the DP charge at %s?" % brand,
         "The indicative schedule lists a DP charge (includes GST) of %s, applied once when delivery shares are sold from the "
         "demat account. Some brokers' own pages call this the CDSL or NSDL charge instead of the DP charge; it is the same fee. "
         "The figure already includes 18%% GST, so no further GST is added to it. Confirm the current DP charge on the broker's "
         "own tariff page." % rs(rates["dp_charge"])),
        ("Is there an annual maintenance charge on a %s demat account?" % brand, amc),
        # The questions below answer the exact short phrasings real searches use for this
        # page (confirmed from Search Console query data: "<broker> charges", "intraday
        # charges for <broker>", "stt charges in <broker>", "<broker> f&o charges"), none
        # with any new figure: each reuses d_rule/i_rule/the statutory table already built
        # from data on file. 17 Nov 2026.
        ("What are the brokerage charges at %s?" % brand,
         "For equity delivery: %s. For equity intraday: %s. %s" % (d_rule, i_rule, confirm)),
        ("What are the intraday charges at %s?" % brand,
         "The intraday brokerage is %s. An intraday trade also carries STT on the sell value, exchange transaction charges, "
         "the SEBI turnover fee, stamp duty on the buy value and GST, at the same statutory rates listed on this page for every "
         "broker; %s does not set those. %s" % (i_rule, brand, confirm)),
        ("What are the delivery charges at %s?" % brand,
         "The delivery brokerage is %s. A delivery trade also carries STT on the buy and sell value, exchange transaction "
         "charges, the SEBI turnover fee, stamp duty on the buy value, GST, and the DP charge when shares are sold, at the same "
         "statutory rates listed on this page for every broker; %s does not set those. %s" % (d_rule, brand, confirm)),
        ("Does %s set its own STT, stamp duty or other statutory charges?" % brand,
         "No. STT, exchange transaction charges, the SEBI turnover fee, stamp duty and GST are set by the government, the "
         "stock exchange and SEBI, the same for every broker trading the same segment on NSE. %s does not set or vary them; "
         "see the statutory rates table on this page for the exact figures." % brand),
    ]
    if peers:
        faqs.append(("Why do the %s figures match another broker's page?" % brand,
                     "The indicative schedule held in the BrokerLens model for %s is the same, field for field, as the one held for %s, "
                     "so the worked examples match apart from the name. That is a property of the model, not a finding that the "
                     "two brokers charge alike." % (brand, ", ".join(peers))))
    if ident["broking"]:
        faqs.append(("What is the SEBI registration number of %s?" % brand,
                     "The SEBI register lists these stock-broking registration numbers: %s. Confirm on SEBI's register before "
                     "you act on them." % ", ".join(no for no, _e in ident["broking"])))
    if ident["dps"]:
        faqs.append(("What is the depository participant registration of %s?" % brand,
                     "The SEBI register lists: %s. These are SEBI registration numbers, not the DP ID printed on your own demat "
                     "account statement, which BrokerLens does not hold." % "; ".join(
                         "%s registration %s" % (dep, no) for dep, no, _e in ident["dps"])))
    faqs.append(("What are the F&O (futures and options) charges at %s?" % brand,
                 "Not calculated on this page. The indicative schedule for %s covers equity delivery and equity intraday only; "
                 "futures, options, currency and commodity charges are not on file, so this page does not show them." % brand))
    return faqs


def render_charges_page(rate_key, built_by_id=None, registry=None, site_url="https://www.brokerlens.in",
                        generated_on=None, stocks=None, reg_to_registry_slug=None):
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
    peers = same_schedule_peers(rate_key)
    faqs = _faqs(brand, rates, ex_del, ex_int, ident, peers)

    h1 = "%s brokerage calculator: indicative charges" % brand
    title = "%s Brokerage Calculator: Indicative Charges | BrokerLens" % brand
    description = (
        "%s brokerage calculator on an indicative schedule held in the BrokerLens model: delivery %s, intraday %s, DP charge "
        "%s incl. GST. Not verified against the broker's rate card; check date not on file." % (
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
    website_html = (' Confirm every figure on the <a href="%s" rel="noopener" target="_blank">%s website</a> or its tariff page.' % (
        _esc(website), _esc(brand))) if website else " Confirm every figure on the broker's own tariff page before you rely on it."

    sched_rows = [
        ("Equity delivery brokerage", _esc(_rule_text(rates["delivery_flat"], rates["delivery_pct"]))),
        ("Equity intraday brokerage", _esc(_rule_text(rates["intraday_flat"], rates["intraday_pct"]))),
        ("DP charge (includes GST), per sale of delivery shares", _esc(rs(rates["dp_charge"]) + ", already including 18% GST")),
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
        'values and press Calculate; the sums run in your browser. The figures use the indicative schedule below, not verified '
        'against the broker\'s own rate card, and the DP charge already includes 18%% GST.</p></div>'
    ) % (_data_attrs(rates), WORKED_VALUE, WORKED_VALUE, _calc_table_html(ex_del), inr(WORKED_VALUE, 0), inr(WORKED_VALUE, 0))

    peer_note = (" The indicative schedule for %s is identical to the one held for %s, so the tables there match apart from the name." % (
        brand, ", ".join(peers))) if peers else ""
    worked_html = (
        '<h2 style="margin-top:32px;font-size:18px">Worked example: charges on a Rs 1,00,000 trade at %s</h2>'
        '<p style="max-width:72ch">Buy Rs 1,00,000 of shares and sell Rs 1,00,000 of shares on NSE, the same day or later, '
        'with no profit or loss. Figures are worked out here from the indicative schedule in the BrokerLens model and the statutory rates below, and are not verified against the broker\'s own rate card.%s</p>'
        '<h3 style="margin-top:16px;font-size:15px">Equity delivery</h3>%s'
        '<h3 style="margin-top:16px;font-size:15px">Equity intraday</h3>%s'
    ) % (_esc(brand), _esc(peer_note), _worked_table_html(rates, ex_del), _worked_table_html(rates, ex_int))

    source_html = (
        '<h2 style="margin-top:28px;font-size:18px">Where these numbers come from</h2>'
        '<p class="small" style="max-width:72ch;line-height:1.6">Brokerage, DP charge and annual maintenance charge are an '
        'indicative schedule held in the BrokerLens trade-cost model, the same schedule behind every %s stock cost page on this '
        'site. It has not been verified against %s\'s own rate card, and the date it was checked is not on file.%s '
        'Statutory rates are the ones in the table below, as held in the same model after the 2024 SEBI and Budget '
        'revisions; a separate effective date for each rate is not on file. The figures on this page were generated on %s.</p>'
        % (_esc(brand), _esc(brand), website_html, _esc(generated_on)))

    how_html = (
        '<h2 style="margin-top:28px;font-size:18px">How the calculation works</h2>'
        '<ol class="small" style="max-width:72ch;line-height:1.6">'
        '<li>Brokerage is worked out per executed order (one buy, one sell) under the rule in the schedule above.</li>'
        '<li>STT, exchange charges, SEBI fee and stamp duty use the statutory rates in the table below.</li>'
        '<li>GST is charged on brokerage, exchange charges and the SEBI fee, not on STT, stamp duty or the DP charge.</li>'
        '<li>The DP charge applies once, when delivery shares are sold. The figure in the schedule already includes 18%% GST, '
        'so it is taken as listed and no GST is added on top.</li>'
        '<li>Every line is rounded to the paisa before the total is added up.</li></ol>'
        '<h3 style="margin-top:16px;font-size:15px">Statutory rates used</h3>%s'
        '<h3 style="margin-top:16px;font-size:15px">What this does not cover</h3>'
        '<p class="small" style="max-width:72ch;line-height:1.6">NSE rates only, one buy order and one sell order, no '
        'brokerage plan variants or discounts, no call-and-trade or other add-on fees, and no futures, options, currency or '
        'commodity trades. Real contract notes can differ by a few paise.</p>' % stat_html)

    # The per-stock /broker/<id>/trade/<symbol>/ pages are retired (308 here, vercel.json):
    # this calculator takes any order value, so it answers what each of those pages did.
    more = []
    if ident["profile_id"]:
        more.append('<a class="chip" href="/broker/%s/">%s profile, registration and complaints &rarr;</a>' % (
            _esc(ident["profile_id"]), _esc(profile.get("brand") or brand)))
    more += ['<a class="chip" href="/calculator">Compare monthly brokerage across brokers &rarr;</a>',
             '<a class="chip" href="/trade-costs/">Trading cost hub &rarr;</a>']
    others = "".join('<a class="chip" href="%s">%s</a>' % (charges_path(k), _esc(tce.BROKER_RATES[k]["brand"]))
                     for k in eligible_keys() if k != rate_key)
    more_html = (
        '<h2 style="margin-top:28px;font-size:18px">More on %s</h2><div class="row-wrap" style="gap:8px">%s</div>'
        '<h2 style="margin-top:28px;font-size:18px">Brokerage calculators for other brokers</h2>'
        '<div class="row-wrap" style="gap:8px">%s</div>'
    ) % (_esc(brand), "".join(more), others)

    faq_html = ('<h2 style="margin-top:28px;font-size:18px">Frequently asked questions</h2><div style="max-width:68ch">%s</div>'
                % "".join('<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a)) for q, a in faqs))

    body = head + (
        crumb_html
        + '<h1 style="margin-top:0">%s</h1>' % _esc(h1)
        + '<p class="muted" style="max-width:68ch">On a Rs 1,00,000 equity delivery round trip (buy and sell), the indicative %s '
          'schedule in the BrokerLens model gives total charges of Rs %s, of which brokerage is Rs %s. That schedule has not been '
          'verified against the broker\'s own rate card and the date it was checked is not on file, so confirm it on the '
          'broker\'s own tariff page. Use the calculator for your own order values.</p>' % (
              _esc(brand), inr(ex_del["total"]), inr(ex_del["brokerage"]))
        + P.ibslBanner_html("wide", "broker")
        + calc_html
        + '<h2 style="margin-top:32px;font-size:18px">%s indicative fee schedule (BrokerLens model, not verified)</h2>' % _esc(brand) + sched_html
        + worked_html
        + _identifiers_html(brand, rate_key, ident, reg_to_registry_slug)
        + source_html + how_html + faq_html + more_html
        + '<p class="xs faint" style="margin-top:20px">%s</p>' % _esc(DISCLAIMER)
    )
    body += P._REGISTRY_PAGE_FOOT % {"source_note": P._source_note(
        "This page works out charges from an indicative broker schedule and statutory rates held in the BrokerLens trade-cost "
        "model, not verified against the broker's own rate card, plus SEBI-register numbers where matched.")}
    return body


def remove_withheld_pages(site_dir):
    """Delete a previously generated charges page of a broker that is now withheld, so a stale
    page cannot stay reachable after the rule changed. Only removes <site>/broker/<id>/charges/
    when it holds nothing but the generated index.html. Returns the ids removed."""
    removed = []
    keep = {charges_id(k) for k in eligible_keys()}
    for k in tce.BROKER_RATES:
        cid = charges_id(k)
        if cid in keep:
            continue
        d = os.path.join(site_dir, "broker", cid, "charges")
        try:
            if os.path.isdir(d) and os.listdir(d) == ["index.html"]:
                os.remove(os.path.join(d, "index.html"))
                os.rmdir(d)
                removed.append(cid)
        except OSError:
            pass
    return removed


def build_broker_charges_pages(built, registry=None, site_url="https://www.brokerlens.in", site_dir=None,
                                reg_to_registry_slug=None):
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
        page = render_charges_page(k, built_by_id, registry, site_url=site_url, stocks=stocks,
                                    reg_to_registry_slug=reg_to_registry_slug)
        dest = os.path.join(site_dir, "broker", charges_id(k), "charges")
        os.makedirs(dest, exist_ok=True)
        P._write_text(os.path.join(dest, "index.html"), page)
        urls.append(charges_path(k))
    removed = remove_withheld_pages(site_dir)
    skipped = skipped_brokers()
    if removed:
        P.log("broker charges pages: removed %d stale page(s) of withheld brokers: %s" % (len(removed), ", ".join(removed)), "ok")
    P.log("broker charges pages: %d written%s" % (
        len(urls), ("; skipped (incomplete schedule): %s" % ", ".join(skipped)) if skipped else ""), "ok")
    return urls
