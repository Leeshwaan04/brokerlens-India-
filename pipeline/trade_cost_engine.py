"""Stock x Broker Transaction Cost & Breakeven Calculator Engine.

Generates high-intent, EEAT-compliant static comparison pages:
  /broker/[broker-id]/trade/[stock-symbol]/

Calculates exact, statutory rupee-by-rupee trading costs:
  - Brokerage (Delivery vs Intraday vs F&O)
  - STT / CTT (Securities Transaction Tax: 0.1% delivery, 0.025% sell intraday)
  - Exchange Turnover Charges (NSE true-to-label 0.00297%)
  - SEBI Turnover Charges (Rs 10 per crore = 0.0001%)
  - Stamp Duty (0.015% delivery buy, 0.003% intraday buy)
  - GST (18% on Brokerage + Exchange Charges + SEBI Fees)
  - DP Charges (CDSL/NSDL per debit transaction)
  - Exact Breakeven points needed to make a profit.
  - Side-by-side cost savings matrix against peer brokers.

Structured Data:
  - Schema.org FinancialProduct + Table + BreadcrumbList JSON-LD.
  - Zero external npm dependencies; stdlib Python.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

try:
    from . import indexation as _ix
except ImportError:  # run as a script
    import indexation as _ix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")

# Every broker x stock page, and each broker's /trade/ listing, is noindex,follow.
# Wave 3 kept them out of the sitemap, but with no robots tag they were indexable and
# every stock page links to them, so Google indexed them anyway: 491 of a 500-URL
# sample of the 33.5K indexed pages (Search Console, 23 Oct 2026) were these
# near-identical templates, on a two-month-old finance domain, and impressions fell
# 97% overnight on 2 Nov. They stay crawlable (follow) so Google sees the noindex and
# drops them; the single /trade-costs/ hub stays indexable. Releasing this family is
# a deliberate decision (remove this tag), never a side effect of a missing one.
TRADE_PAGE_ROBOTS = _ix.NOINDEX_META
DATA_DIR = os.path.join(ROOT, "data")
CONFIG_DIR = os.path.join(ROOT, "config")


def _stock_slug(sym: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (sym or "").lower()).strip("-")

# Standard statutory rates in India (post-2024 SEBI & Budget revisions)
NSE_TURNOVER_RATE = 0.0000297  # 0.00297%
SEBI_TURNOVER_RATE = 0.000001   # Rs 10 per crore (0.0001%)
GST_RATE = 0.18                 # 18% on financial charges
STT_DELIVERY_RATE = 0.001       # 0.1% on buy and sell
STT_INTRADAY_SELL_RATE = 0.00025 # 0.025% on sell side
STAMP_DUTY_DELIVERY_BUY = 0.00015 # 0.015% on buy
STAMP_DUTY_INTRADAY_BUY = 0.00003 # 0.003% on buy

# A brokerage plan encoded as (flat, pct) is only a genuine "lower of Rs flat
# or pct% of turnover, whichever is lower" discount-broker cap when pct is at
# a discount-broker level. Above CAP_RULE_MAX_PCT it is a full-service or
# regional percentage-of-turnover plan with no such cap (ICICI Direct 0.55%,
# HDFC Securities 0.50%, Sharekhan 0.30%, Motilal Oswal 0.20% and so on) -
# taking min(flat, pct_cost) for those would silently substitute the tiny
# flat fee for the real, much larger ad-valorem commission. broker_charges_
# engine.py imports this same constant so the two engines can never disagree
# on which brokers get the capped formula.
CAP_RULE_MAX_PCT = 0.001  # 0.1% of order value, either segment

# Standard broker fee structures (verified published pricing)
BROKER_RATES = {
    "zerodha": {
        "brand": "Zerodha",
        "delivery_flat": 0.0,
        "delivery_pct": 0.0,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003, # min(Rs 20, 0.03%)
        "dp_charge": 15.34, # Rs 13 + 18% GST
        "demat_amc": 300,
        "account_open": 200,
        "tagline": "Brokerage-free equity delivery, flat Rs 20 intraday",
        "cta_url": "https://zerodha.com/open-account?c=ZE5729",
        "partner_badge": "BrokerLens Partner"
    },
    "groww": {
        "brand": "Groww",
        "delivery_flat": 20.0,
        "delivery_pct": 0.001, # min(Rs 20, 0.1%)
        "intraday_flat": 20.0,
        "intraday_pct": 0.001,
        "dp_charge": 15.93, # Rs 13.5 + 18% GST
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Rs 20 or 0.1% flat, zero AMC Demat",
        "cta_url": "https://groww.in",
        "partner_badge": None
    },
    "angel-one": {
        "brand": "Angel One",
        "delivery_flat": 20.0,
        "delivery_pct": 0.001, # min(Rs 20, 0.1%)
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 23.60, # Rs 20 + 18% GST
        "demat_amc": 240,
        "account_open": 0,
        "tagline": "Rs 20 flat trading, free account opening",
        "cta_url": "https://www.angelone.in/open-demat-account?referral=BROKERLENS",
        "partner_badge": "BrokerLens Partner"
    },
    "dhan": {
        "brand": "Dhan",
        "delivery_flat": 0.0,
        "delivery_pct": 0.0,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 14.75, # Rs 12.5 + 18% GST
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Free delivery, Rs 20 intraday, zero AMC",
        "cta_url": "https://dhan.co/?ref=BROKERLENS",
        "partner_badge": "BrokerLens Partner"
    },
    "upstox": {
        "brand": "Upstox",
        "delivery_flat": 20.0,
        "delivery_pct": 0.001,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0005,
        "dp_charge": 21.83, # Rs 18.5 + 18% GST
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Flat Rs 20 equity trading, modern charting",
        "cta_url": "https://upstox.com/open-account/?f=BROKERLENS",
        "partner_badge": "BrokerLens Partner"
    },
    "5paisa": {
        "brand": "5paisa",
        "delivery_flat": 20.0,
        "delivery_pct": 0.0,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0,
        "dp_charge": 14.75,
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Flat Rs 20 across all segments, NSE/BSE listed",
        "cta_url": "https://www.5paisa.com/demat-account?ReferralCode=53293333&ReturnUrl=invest-open-account",
        "partner_badge": "BrokerLens Partner"
    },
    "icici-direct": {
        "brand": "ICICI Direct",
        "delivery_flat": 20.0,
        "delivery_pct": 0.0055, # Standard delivery 0.55% (or Neo Rs 20)
        "intraday_flat": 20.0,
        "intraday_pct": 0.0005,
        "dp_charge": 23.60,
        "demat_amc": 700,
        "account_open": 0,
        "tagline": "3-in-1 ICICI Bank Demat, research and Neo brokerage",
        "cta_url": "https://www.icicidirect.com",
        "partner_badge": None
    },
    "kotak-securities": {
        "brand": "Kotak Securities",
        # Corrected 2026-11-17: this entry held the restricted Trade Free
        # Youth plan (Rs 0 / Rs 0) as if it were Kotak's general schedule.
        # Real general Trade Free Plan, verified against kotakneo.com's own
        # pricing and support pages (kotaksecurities.com now redirects there):
        # delivery 0.20% of trade value, no flat alternative or cap; intraday
        # the lower of Rs 10 per order or 0.05% of the order, whichever is
        # lower. Both pages describe a Rs 0 promo for the first 30 days from
        # account opening; this uses the standing post-promo rate, the same
        # convention every other broker's entry here uses.
        "delivery_flat": 0.0,
        "delivery_pct": 0.002,  # 0.20%, uncapped (CAP_RULE_MAX_PCT)
        "intraday_flat": 10.0,
        "intraday_pct": 0.0005,  # lower of Rs 10 or 0.05%
        # dp_charge and demat_amc below are NOT re-verified by this correction
        # and should not be trusted: Kotak's real DP debit fee is 0.04% of
        # value plus NSDL pass-through (minimum ~Rs 20, not a flat figure),
        # and its AMC is tiered by holding value and monthly debit count, not
        # one number. Both are unrepresentable as a single real figure, which
        # is the separate, genuine reason broker_charges_engine.py must keep
        # withholding a dedicated /broker/kotak-securities/charges/ page even
        # after this correction (see withheld_brokers() and LOG.md 2026-11-17).
        "dp_charge": 15.34,
        "demat_amc": 300,
        "account_open": 0,
        "tagline": "0.20% equity delivery, Rs 10 or 0.05% intraday, whichever is lower",
        "cta_url": "https://www.kotaksecurities.com",
        "partner_badge": None
    },
    "hdfc-securities": {
        "brand": "HDFC Securities",
        "delivery_flat": 20.0,
        "delivery_pct": 0.005, # HDFC Sky flat Rs 20 / classical 0.50%
        "intraday_flat": 20.0,
        "intraday_pct": 0.0005,
        "dp_charge": 23.60,
        "demat_amc": 500,
        "account_open": 0,
        "tagline": "HDFC Bank backed 3-in-1 security and HDFC Sky flat fee",
        "cta_url": "https://www.hdfcsec.com",
        "partner_badge": None
    },
    "motilal-oswal": {
        "brand": "Motilal Oswal",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0002,
        "dp_charge": 25.0,
        "demat_amc": 400,
        "account_open": 0,
        "tagline": "Full-service advisory, equity research and MO Trader",
        "cta_url": "https://www.motilaloswal.com",
        "partner_badge": None
    },
    "sharekhan": {
        "brand": "Sharekhan",
        "delivery_flat": 20.0,
        "delivery_pct": 0.003, # Classical 0.30% or flat Rs 20 under discount scheme
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 19.47,
        "demat_amc": 400,
        "account_open": 0,
        "tagline": "Full-service branch network, TradeTiger terminal & research",
        "cta_url": "https://www.sharekhan.com",
        "partner_badge": None
    },
    "fyers": {
        "brand": "Fyers",
        "delivery_flat": 0.0,
        "delivery_pct": 0.0,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 14.75,
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Free equity delivery, flat Rs 20 F&O, TradingView charts",
        "cta_url": "https://fyers.in",
        "partner_badge": None
    },
    "paytm-money": {
        "brand": "Paytm Money",
        "delivery_flat": 20.0,
        "delivery_pct": 0.001,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0005,
        "dp_charge": 15.34,
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Flat Rs 20 equity brokerage, instant mobile onboarding",
        "cta_url": "https://www.paytmmoney.com",
        "partner_badge": None
    },
    "sbi-securities": {
        "brand": "SBI Securities",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002, # 0.20% delivery
        "intraday_flat": 20.0,
        "intraday_pct": 0.0002,
        "dp_charge": 17.70,
        "demat_amc": 500,
        "account_open": 0,
        "tagline": "Backed by SBI, 3-in-1 integration and national branch trust",
        "cta_url": "https://www.sbisecurities.in",
        "partner_badge": None
    },
    "axis-direct": {
        "brand": "Axis Direct",
        "delivery_flat": 20.0,
        "delivery_pct": 0.0025,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 20.88,
        "demat_amc": 650,
        "account_open": 0,
        "tagline": "Axis Bank 3-in-1 account, Ring app, and expert research calls",
        "cta_url": "https://simplehai.axisdirect.in",
        "partner_badge": None
    },
    "anand-rathi": {
        "brand": "Anand Rathi",
        "delivery_flat": 20.0,
        "delivery_pct": 0.0025,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 17.70,
        "demat_amc": 450,
        "account_open": 0,
        "tagline": "Nationwide wealth advisory, Trade X app & research desk",
        "cta_url": "https://www.rathi.com",
        "partner_badge": None
    },
    "geojit": {
        "brand": "Geojit",
        "delivery_flat": 20.0,
        "delivery_pct": 0.0025,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 17.70,
        "demat_amc": 400,
        "account_open": 0,
        "tagline": "South India branch footprint, Selfie trading app & NRI desks",
        "cta_url": "https://www.geojit.com",
        "partner_badge": None
    },
    "smc": {
        "brand": "SMC Global",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0002,
        "dp_charge": 17.70,
        "demat_amc": 400,
        "account_open": 0,
        "tagline": "Extensive sub-broker network, SMC ACE app & derivative algorithms",
        "cta_url": "https://www.smcindiaonline.com",
        "partner_badge": None
    },
    "ventura": {
        "brand": "Ventura Securities",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        # dp_charge corrected 2026-11-18 from 17.70 (uncited) to Rs 20 + 18%
        # GST per scrip on sell, verified against venturasecurities.com/pricing/
        "dp_charge": 23.60,
        "demat_amc": 0, # Rs 0, verified against venturasecurities.com/pricing/
        "account_open": 0,
        "tagline": "POINTER desktop software, lifetime zero AMC demat account",
        "cta_url": "https://www.ventura1.com",
        "partner_badge": None
    },
    "nirmal-bang": {
        "brand": "Nirmal Bang",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0002,
        "dp_charge": 18.88,
        "demat_amc": 450,
        "account_open": 0,
        "tagline": "Institutional heritage, Beyond mobile app & research reports",
        "cta_url": "https://www.nirmalbang.com",
        "partner_badge": None
    },
    "hdfc-sky": {
        "brand": "HDFC Sky",
        "delivery_flat": 20.0,
        "delivery_pct": 0.001,
        "intraday_flat": 20.0,
        "intraday_pct": 0.00025,
        "dp_charge": 23.60,
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Flat Rs 20 equity delivery & intraday, zero AMC first year",
        "cta_url": "https://www.hdfcsky.com",
        "partner_badge": None
    },
    "alice-blue": {
        "brand": "Alice Blue",
        "delivery_flat": 0.0,
        "delivery_pct": 0.0,
        "intraday_flat": 15.0,
        "intraday_pct": 0.0003,
        "dp_charge": 17.70, # Rs 15 + 18% GST, verified against aliceblueonline.com/pricing 2026-11-18
        "demat_amc": 0, # Rs 0 lifetime, verified against aliceblueonline.com/pricing 2026-11-18
        "account_open": 0,
        "tagline": "Freedom 15 Plan: Rs 0 delivery, Rs 15 intraday & F&O",
        "cta_url": "https://aliceblueonline.com",
        "partner_badge": None
    },
    "prostocks": {
        "brand": "ProStocks",
        "delivery_flat": 0.0,
        "delivery_pct": 0.0,
        "intraday_flat": 7.0,
        "intraday_pct": 0.0002,
        "dp_charge": 10.62,
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Ultra low cost: Flat Rs 7 per order, zero delivery brokerage",
        "cta_url": "https://www.prostocks.com",
        "partner_badge": None
    },
    "tradejini": {
        "brand": "Tradejini",
        "delivery_flat": 0.0,
        "delivery_pct": 0.0,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        # dp_charge corrected 2026-11-18 from 17.70 (uncited) to Rs 12.50 +
        # 18% GST per ISIN on-market debit, verified against tradejini.com/charges
        "dp_charge": 14.75,
        "demat_amc": 354, # Rs 300 + 18% GST, verified against tradejini.com/charges 2026-11-18
        "account_open": 0,
        "tagline": "CubePlus platform: Flat Rs 20 trading, free equity delivery",
        "cta_url": "https://www.tradejini.com",
        "partner_badge": None
    },
    "choice-broking": {
        "brand": "Choice Broking",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002,  # lower of Rs 20 or 0.20%, confirmed below
        "intraday_flat": 20.0,
        "intraday_pct": 0.0002,  # lower of Rs 20 or 0.02%, confirmed below
        # dp_charge corrected 2026-11-17 from 21.24 (stale/wrong) to Rs 10 +
        # 18% GST = 11.80, per choiceindia.com/brokerage-charges' "Debit to
        # market (sell): Rs 10 per instruction + GST". demat_amc (236 = Rs
        # 200 + 18% GST, the standing rate from year 2; year 1 is free) was
        # already correct and verified against the same page on the same date.
        "dp_charge": 11.80,
        "demat_amc": 236,
        # Verified against choiceindia.com/brokerage-charges on 2026-11-17: the
        # page states delivery is "0.20% of trade value or Rs 20 per executed
        # order, whichever is lower" and intraday is "0.02% ... or Rs 20 ...,
        # whichever is lower" - a genuine discount-broker cap, not an uncapped
        # ad-valorem commission, even though 0.20% exceeds CAP_RULE_MAX_PCT.
        # This date lets broker_charges_engine.py's withholding rule treat this
        # one broker's already-correct (flat, pct) rule as the real cap it is,
        # without loosening the rule for any other broker above the threshold.
        "cap_verified_asof": "2026-11-17",
        "account_open": 0,
        "tagline": "Choice Jiffy platform, advisory research calls & margin funding",
        "cta_url": "https://choiceindia.com",
        "partner_badge": None
    },
    "swastika-investmart": {
        "brand": "Swastika Investmart",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0002,
        "dp_charge": 20.65,
        "demat_amc": 350,
        "account_open": 0,
        "tagline": "JustTrade flat brokerage, regional branch network across Central India",
        "cta_url": "https://www.swastika.co.in",
        "partner_badge": None
    },
    "espresso": {
        "brand": "Espresso",
        "delivery_flat": 20.0,
        "delivery_pct": 0.001,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0003,
        "dp_charge": 18.88,
        "demat_amc": 0,
        "account_open": 0,
        "tagline": "Pay only when you profit: Rs 0 brokerage on loss making trades",
        "cta_url": "https://www.myespresso.com",
        "partner_badge": None
    },
    "samco": {
        "brand": "SAMCO",
        "delivery_flat": 20.0,
        "delivery_pct": 0.002,
        "intraday_flat": 20.0,
        "intraday_pct": 0.0002,
        "dp_charge": 19.47,
        "demat_amc": 400,
        "account_open": 0,
        "tagline": "KyaTrade & StockNote platforms with flat Rs 20 executed orders",
        "cta_url": "https://www.samco.in",
        "partner_badge": None
    },
    "religare": {
        "brand": "Religare Broking",
        "delivery_flat": 20.0,
        "delivery_pct": 0.0025,
        "intraday_flat": 20.0,
        "intraday_pct": 0.00025,
        "dp_charge": 23.60,
        "demat_amc": 354,
        "account_open": 0,
        "tagline": "Full service retail broking, dedicated relationship managers",
        "cta_url": "https://www.religareonline.com",
        "partner_badge": None
    },
    "yes-securities": {
        "brand": "YES Securities",
        "delivery_flat": 20.0,
        "delivery_pct": 0.0025,
        "intraday_flat": 20.0,
        "intraday_pct": 0.00025,
        "dp_charge": 21.24,
        "demat_amc": 413,
        "account_open": 0,
        "tagline": "YES 3-in-1 banking and investment suite, institutional research",
        "cta_url": "https://yesinvest.in",
        "partner_badge": None
    }
}


def _load_affiliate_overrides():
    aff_path = os.path.join(ROOT, "config", "affiliates.json")
    if os.path.exists(aff_path):
        try:
            with open(aff_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            partners = data.get("partners") or {}
            for bid, url in partners.items():
                if bid in BROKER_RATES and url:
                    BROKER_RATES[bid]["cta_url"] = url
                    if not BROKER_RATES[bid].get("partner_badge"):
                        BROKER_RATES[bid]["partner_badge"] = "BrokerLens Partner"
        except Exception:
            pass

_load_affiliate_overrides()


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _rule_short(flat, pct, cap_verified=False):
    """Compact 'X flat' / 'lower of X or Y%' / 'Z% of trade value' label for a
    stat tile - same convention as broker_charges_engine.py's _rule_short(),
    extended for the uncapped percentage plans that module never has to
    render (its own pages are withheld for exactly those brokers). pct above
    CAP_RULE_MAX_PCT defaults to "uncapped" unless cap_verified is set (the
    broker's own current pricing page confirms a real whichever-is-lower cap
    even at that level - see CAP_RULE_MAX_PCT above and withheld_reasons())."""
    flat, pct = flat or 0.0, pct or 0.0
    if not flat and not pct:
        return "Rs 0 (Zero)"
    if pct > CAP_RULE_MAX_PCT and not cap_verified:
        return "%g%% of trade value" % (pct * 100)
    if not pct:
        return "Rs %g flat" % flat
    return "Rs %g or %g%%" % (flat, pct * 100)


def _rule_text(flat, pct, cap_verified=False):
    """Honest one-line description of a (flat, pct) brokerage rule - used in
    the page's FAQ prose and JSON-LD. Two separate hardcoded sentences here
    used to describe every broker's delivery brokerage as its flat fee alone
    (and every intraday rule as "flat X or Y%, whichever is lower"), which is
    wrong for the 16 brokers whose real plan is an uncapped percentage of
    turnover - see CAP_RULE_MAX_PCT above and calculate_trade_fees(). A
    broker whose cap above that threshold is confirmed real on its own
    current pricing page passes cap_verified=True instead."""
    flat, pct = flat or 0.0, pct or 0.0
    if not flat and not pct:
        return "Rs 0 (Zero Brokerage)"
    if pct > CAP_RULE_MAX_PCT and not cap_verified:
        return "%g%% of trade value" % (pct * 100)
    if not pct:
        return "Rs %g flat per order" % flat
    return "Rs %g or %g%% per order, whichever is lower" % (flat, pct * 100)


def _charges_link_block(broker_id):
    """Visible link to /broker/<id>/charges/ with the exact anchor text, or "" when the broker has no page."""
    try:
        from .broker_charges_engine import charges_link_html
        link = charges_link_html(broker_id)
    except Exception:
        link = ""
    return ('<p class="small" style="margin-top:14px">%s: delivery and intraday charges, DP charge and a worked example on Rs 1,00,000.</p>' % link
            ) if link else ""


def calculate_trade_fees(price: float, qty: int, broker_key: str, trade_type: str = "delivery"):
    """Computes exact rupee breakdown for buy and sell round-trip transaction."""
    b = BROKER_RATES.get(broker_key, BROKER_RATES["zerodha"])
    buy_turnover = round(price * qty, 2)
    sell_turnover = buy_turnover # assume roundtrip at parity for baseline cost audit
    total_turnover = buy_turnover + sell_turnover

    cap_verified = bool(b.get("cap_verified_asof"))

    # 1. Brokerage
    def _brokerage(pct, flat):
        pct = pct or 0.0
        pct_cost = buy_turnover * pct
        if not flat and not pct:
            return 0.0
        # A real percentage-of-turnover plan (not a discount-broker cap) has
        # no flat-fee floor to fall back to - see CAP_RULE_MAX_PCT above.
        # A broker whose own current pricing page confirms a real
        # whichever-is-lower cap even above that threshold (cap_verified_asof
        # on its BROKER_RATES entry) keeps the real cap instead.
        if pct > CAP_RULE_MAX_PCT and not cap_verified:
            return pct_cost
        if not flat:
            return pct_cost
        return min(flat, pct_cost) if pct_cost > 0 else flat

    if trade_type == "delivery":
        if b["delivery_flat"] == 0 and b["delivery_pct"] == 0:
            buy_brokerage = 0.0
        else:
            buy_brokerage = _brokerage(b.get("delivery_pct", 0.0), b.get("delivery_flat", 20.0))
        sell_brokerage = buy_brokerage
    else: # intraday
        buy_brokerage = _brokerage(b.get("intraday_pct", 0.0003), b.get("intraday_flat", 20.0))
        sell_brokerage = buy_brokerage

    total_brokerage = round(buy_brokerage + sell_brokerage, 2)

    # 2. STT (Securities Transaction Tax)
    if trade_type == "delivery":
        stt = round(total_turnover * STT_DELIVERY_RATE, 2)
    else:
        stt = round(sell_turnover * STT_INTRADAY_SELL_RATE, 2)

    # 3. Exchange Turnover Charges (NSE: 0.00297%)
    exchange_charges = round(total_turnover * NSE_TURNOVER_RATE, 2)

    # 4. SEBI Turnover Charges (Rs 10 / crore)
    sebi_charges = round(total_turnover * SEBI_TURNOVER_RATE, 2)
    if sebi_charges < 0.01:
        sebi_charges = 0.01

    # 5. Stamp Duty (on buy side only)
    if trade_type == "delivery":
        stamp_duty = round(buy_turnover * STAMP_DUTY_DELIVERY_BUY, 2)
    else:
        stamp_duty = round(buy_turnover * STAMP_DUTY_INTRADAY_BUY, 2)

    # 6. GST (18% on Brokerage + Exchange Charges + SEBI Charges)
    taxable_services = total_brokerage + exchange_charges + sebi_charges
    gst = round(taxable_services * GST_RATE, 2)

    # 7. DP Charges (Applies on sell side for delivery only)
    dp_charge = b.get("dp_charge", 15.34) if trade_type == "delivery" else 0.0

    total_charges = round(total_brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + dp_charge, 2)
    breakeven_pts = round(total_charges / qty, 2)
    breakeven_pct = round((breakeven_pts / price) * 100, 2) if price > 0 else 0.0

    return {
        "trade_value": buy_turnover,
        "qty": qty,
        "brokerage": total_brokerage,
        "stt": stt,
        "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "dp_charge": dp_charge,
        "total_charges": total_charges,
        "breakeven_pts": breakeven_pts,
        "breakeven_pct": breakeven_pct
    }


def render_trade_cost_page(broker_id: str, stock_sym: str, stock_name: str, isin: str,
                           price: float, sector: str, site_url: str = "https://www.brokerlens.in") -> str:
    """Generates a complete, beautiful, SEO-optimized static HTML page."""
    b = BROKER_RATES.get(broker_id, BROKER_RATES["zerodha"])
    brand = b["brand"]
    stock_slug = _stock_slug(stock_sym)
    canonical_url = f"{site_url}/broker/{broker_id}/trade/{stock_slug}/"
    page_title = f"{brand} Charges to Trade {stock_name} ({stock_sym}) | Brokerage & Tax Calculator"
    meta_desc = (f"Exact brokerage, STT, exchange fees, GST, stamp duty and breakeven calculator for "
                 f"buying {stock_name} ({stock_sym}) shares on {brand}. Compare delivery vs intraday.")[:290]

    # Link to the broker's canonical calculator page (one-line hook, see broker_charges_engine)
    charges_link_html = _charges_link_block(broker_id)

    # Pre-calculated standard trade tiers
    quantities = [1, 10, 50, 100, 500]
    delivery_tiers = [calculate_trade_fees(price, q, broker_id, "delivery") for q in quantities]
    intraday_tiers = [calculate_trade_fees(price, q, broker_id, "intraday") for q in quantities]

    # Comparison against alternative brokers for 100 shares
    cmp_brokers = [k for k in ["zerodha", "groww", "angel-one", "dhan", "icici-direct"] if k != broker_id][:4]
    cmp_results = []
    for cb_id in cmp_brokers:
        cb_info = BROKER_RATES[cb_id]
        res = calculate_trade_fees(price, 100, cb_id, "delivery")
        diff = round(res["total_charges"] - delivery_tiers[3]["total_charges"], 2)
        cmp_results.append({
            "id": cb_id,
            "brand": cb_info["brand"],
            "total_charges": res["total_charges"],
            "diff": diff,
            "brokerage": res["brokerage"]
        })

    # Schema JSON-LD
    schema_graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "Brokers", "item": f"{site_url}/brokers"},
                    {"@type": "ListItem", "position": 3, "name": brand, "item": f"{site_url}/broker/{broker_id}/"},
                    {"@type": "ListItem", "position": 4, "name": f"Trade {stock_sym}", "item": canonical_url}
                ]
            },
            {
                "@type": "FinancialProduct",
                "name": f"{brand} Trading Charges for {stock_name}",
                "provider": {
                    "@type": "FinancialService",
                    "name": brand,
                    "url": f"{site_url}/broker/{broker_id}/"
                },
                "description": meta_desc,
                "feesAndCommissionsSpecification": f"Delivery: {_rule_text(b['delivery_flat'], b['delivery_pct'], b.get('cap_verified_asof'))}. Intraday: {_rule_text(b['intraday_flat'], b['intraday_pct'], b.get('cap_verified_asof'))}."
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f"What is the brokerage for buying {stock_name} shares on {brand}?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f"On {brand}, equity delivery brokerage for {stock_name} is {_rule_text(b['delivery_flat'], b['delivery_pct'], b.get('cap_verified_asof'))}. Intraday brokerage is {_rule_text(b['intraday_flat'], b['intraday_pct'], b.get('cap_verified_asof'))}."
                        }
                    },
                    {
                        "@type": "Question",
                        "name": f"How much STT and government tax is charged when buying {stock_name} on {brand}?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f"Statutory taxes include 0.1% Securities Transaction Tax (STT) on buy and sell for delivery, 0.00297% NSE exchange turnover charges, 0.0001% SEBI charges, 0.015% stamp duty on buy, and 18% GST on brokerage and exchange fees."
                        }
                    },
                    {
                        "@type": "Question",
                        "name": f"What is the breakeven price movement required for {stock_sym} on {brand}?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f"For an order of 100 shares of {stock_sym} at Rs {price:,.2f}, the roundtrip transaction cost is Rs {delivery_tiers[3]['total_charges']:.2f}, meaning the stock needs to rise by Rs {delivery_tiers[3]['breakeven_pts']:.2f} ({delivery_tiers[3]['breakeven_pct']}%) to break even."
                        }
                    }
                ]
            }
        ]
    }

    tier_rows_html = "".join(f"""
    <tr>
      <td><strong>{t['qty']}</strong> share{'s' if t['qty'] > 1 else ''}</td>
      <td class="right num">&#8377;{t['trade_value']:,.2f}</td>
      <td class="right num">&#8377;{t['brokerage']:.2f}</td>
      <td class="right num">&#8377;{t['stt']:.2f}</td>
      <td class="right num">&#8377;{t['exchange_charges'] + t['sebi_charges']:.2f}</td>
      <td class="right num">&#8377;{t['stamp_duty']:.2f}</td>
      <td class="right num">&#8377;{t['gst']:.2f}</td>
      <td class="right num">&#8377;{t['dp_charge']:.2f}</td>
      <td class="right num" style="font-weight:700">&#8377;{t['total_charges']:.2f}</td>
      <td class="right num up">+{t['breakeven_pts']:.2f} ({t['breakeven_pct']}%)</td>
    </tr>
    """ for t in delivery_tiers)

    intraday_rows_html = "".join(f"""
    <tr>
      <td><strong>{t['qty']}</strong> share{'s' if t['qty'] > 1 else ''}</td>
      <td class="right num">&#8377;{t['trade_value']:,.2f}</td>
      <td class="right num">&#8377;{t['brokerage']:.2f}</td>
      <td class="right num">&#8377;{t['stt']:.2f}</td>
      <td class="right num">&#8377;{t['exchange_charges'] + t['sebi_charges']:.2f}</td>
      <td class="right num">&#8377;{t['stamp_duty']:.2f}</td>
      <td class="right num">&#8377;{t['gst']:.2f}</td>
      <td class="right num" style="font-weight:700">&#8377;{t['total_charges']:.2f}</td>
      <td class="right num up">+{t['breakeven_pts']:.2f} ({t['breakeven_pct']}%)</td>
    </tr>
    """ for t in intraday_tiers)

    cmp_rows_html = "".join(f"""
    <tr>
      <td><a href="/broker/{c['id']}/">{c['brand']}</a></td>
      <td class="right num">&#8377;{c['brokerage']:.2f}</td>
      <td class="right num">&#8377;{c['total_charges']:.2f}</td>
      <td class="right num {'up' if c['diff'] > 0 else ('down' if c['diff'] < 0 else '')}">
        {'+' if c['diff'] > 0 else ''}{c['diff']:.2f}
      </td>
    </tr>
    """ for c in cmp_results)

    html_page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="/assets/js/theme-init.js"></script>
<title>{_esc(page_title)}</title>
<meta name="description" content="{_esc(meta_desc)}">
{TRADE_PAGE_ROBOTS}
<link rel="canonical" href="{canonical_url}">
<meta name="theme-color" content="#2f4a8f">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/assets/css/app.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BrokerLens">
<meta property="og:locale" content="en_IN">
<meta property="og:url" content="{canonical_url}">
<meta property="og:title" content="{_esc(page_title)}">
<meta property="og:description" content="{_esc(meta_desc)}">
<script type="application/ld+json">
{json.dumps(schema_graph, ensure_ascii=False)}
</script>
</head>
<body>
<header class="site"><div class="wrap nav">
  <a class="brand" href="/">
    <svg class="brand-logo" viewBox="0 0 512 512" width="26" height="26" role="img" aria-label="BrokerLens">
      <defs><clipPath id="bl-lens-trade"><circle cx="256" cy="256" r="143"/></clipPath></defs>
      <circle cx="256" cy="256" r="166" fill="none" stroke="var(--accent)" stroke-width="46"/>
      <path d="M-24 392 L146 340 L212 288 L272 336 L360 190 L528 128" fill="none" stroke="var(--up)"
            stroke-width="46" stroke-linecap="round" stroke-linejoin="round" clip-path="url(#bl-lens-trade)"/>
    </svg>
    <span>BrokerLens</span>
  </a>
  <button class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="navlinks" aria-label="Menu"><span aria-hidden="true">&#9776;</span></button>
  <nav class="nav-links" id="navlinks">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/leaderboards">Movers</a>
    <a href="/calculators/">Calculators</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News &amp; Blogs</a>
  </nav>
  <button class="icon-btn" id="search-toggle" title="Search (Ctrl+K)" aria-label="Search"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
  <button class="icon-btn" id="theme-toggle" title="Switch theme" aria-label="Switch theme">&#9680;</button>
</div></header>

<main class="wrap" style="padding-top:24px;padding-bottom:36px">
<nav class="breadcrumb" aria-label="Breadcrumb">
  <a href="/">BrokerLens</a><span class="sep"> &rsaquo; </span>
  <a href="/brokers">Brokers</a><span class="sep"> &rsaquo; </span>
  <a href="/broker/{broker_id}/">{brand}</a><span class="sep"> &rsaquo; </span>
  <span aria-current="page">Trade {stock_sym}</span>
</nav>

<div class="row-between" style="align-items:flex-start;flex-wrap:wrap;gap:16px;margin-top:10px">
  <div>
    <div class="pill-tag accent" style="margin-bottom:8px"><span>✦</span> Primary-Disclosed Fee Matrix</div>
    <h1 style="margin:0 0 4px 0">{brand} Charges for {stock_name}</h1>
    <p class="muted" style="margin:0">NSE: <strong>{stock_sym}</strong> &middot; Last Close: <strong>&#8377;{price:,.2f}</strong> &middot; Sector: {sector or 'Diversified'}</p>
  </div>
  <div class="row-wrap" style="gap:10px">
    <a class="btn btn-primary" href="{b['cta_url']}" target="_blank" rel="noopener sponsored">Open {brand} Account &rarr;</a>
    <a class="btn" href="/stock/{stock_slug}/">View Stock Facts</a>
  </div>
</div>

{charges_link_html}
<div class="grid g4" style="margin-top:24px">
  <div class="card stat">
    <div class="stat-label">Delivery Brokerage</div>
    <div class="stat-value">{_esc(_rule_short(b['delivery_flat'], b['delivery_pct'], b.get('cap_verified_asof')))}</div>
    <div class="stat-sub">{b['tagline']}</div>
  </div>
  <div class="card stat">
    <div class="stat-label">Intraday Brokerage</div>
    <div class="stat-value">{_esc(_rule_short(b['intraday_flat'], b['intraday_pct'], b.get('cap_verified_asof')))}</div>
    <div class="stat-sub">per executed order</div>
  </div>
  <div class="card stat">
    <div class="stat-label">Roundtrip 100 Shares</div>
    <div class="stat-value">&#8377;{delivery_tiers[3]['total_charges']:.2f}</div>
    <div class="stat-sub">Includes STT, Exchange Fees, GST &amp; DP</div>
  </div>
  <div class="card stat">
    <div class="stat-label">Breakeven Target</div>
    <div class="stat-value up">+{delivery_tiers[3]['breakeven_pts']:.2f} pts</div>
    <div class="stat-sub">+{delivery_tiers[3]['breakeven_pct']:.2f}% share price move</div>
  </div>
</div>

<div class="section-title" style="margin-top:36px">
  <div>
    <div class="section-eyebrow">EQUITY DELIVERY FEE BREAKDOWN</div>
    <h2>Exact Delivery Cost by Order Quantity (Roundtrip)</h2>
  </div>
</div>
<div class="table-scroll">
  <table class="data">
    <thead>
      <tr>
        <th>Quantity</th>
        <th class="right">Trade Value</th>
        <th class="right">Brokerage</th>
        <th class="right">STT (0.1%)</th>
        <th class="right">Exch+SEBI</th>
        <th class="right">Stamp Duty</th>
        <th class="right">GST (18%)</th>
        <th class="right">DP Fee</th>
        <th class="right">Total Cost</th>
        <th class="right">Breakeven</th>
      </tr>
    </thead>
    <tbody>
      {tier_rows_html}
    </tbody>
  </table>
</div>
<p class="xs faint" style="margin-top:8px">Exchange turnover fee calculated at NSE's revised true-to-label tariff (0.00297%). DP charge of &#8377;{b['dp_charge']:.2f} is levied on the sell-leg from Demat.</p>

<div class="section-title" style="margin-top:40px">
  <div>
    <div class="section-eyebrow">INTRADAY SCENARIO</div>
    <h2>Intraday Buy &amp; Sell Charges (Square-Off Same Day)</h2>
  </div>
</div>
<div class="table-scroll">
  <table class="data">
    <thead>
      <tr>
        <th>Quantity</th>
        <th class="right">Trade Value</th>
        <th class="right">Brokerage</th>
        <th class="right">STT (0.025%)</th>
        <th class="right">Exch+SEBI</th>
        <th class="right">Stamp Duty</th>
        <th class="right">GST (18%)</th>
        <th class="right">Total Cost</th>
        <th class="right">Breakeven</th>
      </tr>
    </thead>
    <tbody>
      {intraday_rows_html}
    </tbody>
  </table>
</div>

<div class="section-title" style="margin-top:40px">
  <div>
    <div class="section-eyebrow">PEER BENCHMARK</div>
    <h2>How {brand} Compares to Alternatives (100 Shares of {stock_sym})</h2>
  </div>
</div>
<div class="table-scroll">
  <table class="data">
    <thead>
      <tr>
        <th>Broker</th>
        <th class="right">Brokerage Fee</th>
        <th class="right">Total Transaction Charges</th>
        <th class="right">Difference vs {brand}</th>
      </tr>
    </thead>
    <tbody>
      <tr style="background:var(--accent-soft)">
        <td><strong>{brand} (Selected)</strong></td>
        <td class="right num">&#8377;{delivery_tiers[3]['brokerage']:.2f}</td>
        <td class="right num">&#8377;{delivery_tiers[3]['total_charges']:.2f}</td>
        <td class="right num">&mdash;</td>
      </tr>
      {cmp_rows_html}
    </tbody>
  </table>
</div>

<div class="card" style="margin-top:36px;padding:24px;background:var(--bg-raised)">
  <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:16px">
    <div>
      <h3 style="margin:0 0 6px 0">Ready to trade {stock_name}?</h3>
      <p class="xs muted" style="margin:0">Open an account with {brand} in 5 minutes with paperless e-KYC.</p>
    </div>
    <a class="btn btn-primary" href="{b['cta_url']}" target="_blank" rel="noopener sponsored">Start Account Opening &rarr;</a>
  </div>
</div>

<div class="mobile-sticky-cta">
  <div>
    <div class="xs muted">Trade {stock_sym} on {brand}</div>
    <div style="font-weight:700">&#8377;{delivery_tiers[3]['total_charges']:.2f} <span class="xs muted">/ 100 shares</span></div>
  </div>
  <a class="btn btn-primary btn-sm" href="{b['cta_url']}" target="_blank" rel="noopener sponsored">Open Account &rarr;</a>
</div>

<h2 style="margin-top:36px;font-size:17px">Frequently Asked Questions</h2>
<div style="max-width:72ch">
  <details class="faq-item" open>
    <summary>What is the brokerage for buying {stock_name} shares on {brand}?</summary>
    <p>On {brand}, equity delivery brokerage for {stock_name} is {_rule_text(b['delivery_flat'], b['delivery_pct'], b.get('cap_verified_asof'))}. Intraday trades incur {_rule_text(b['intraday_flat'], b['intraday_pct'], b.get('cap_verified_asof'))}.</p>
  </details>
  <details class="faq-item">
    <summary>How much STT and government tax is charged when buying {stock_name}?</summary>
    <p>Statutory taxes include 0.1% Securities Transaction Tax (STT) on buy and sell for delivery, 0.00297% NSE exchange turnover charges, 0.0001% SEBI turnover fees, 0.015% stamp duty on buy, and 18% GST on non-tax services.</p>
  </details>
  <details class="faq-item">
    <summary>What is the breakeven price movement required for {stock_sym} on {brand}?</summary>
    <p>For an order of 100 shares of {stock_sym} at &#8377;{price:,.2f}, the roundtrip transaction cost is &#8377;{delivery_tiers[3]['total_charges']:.2f}, meaning the stock needs to rise by &#8377;{delivery_tiers[3]['breakeven_pts']:.2f} ({delivery_tiers[3]['breakeven_pct']}%) to break even.</p>
  </details>
</div>

</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">BrokerLens is an independent financial research service, not a SEBI-registered investment adviser. Calculations reflect official NSE, BSE, SEBI, and broker published rate schedules as of BrokerLens's latest data refresh. Nothing here constitutes a recommendation to buy, sell, or trade any security. <a href="/methodology">Methodology</a> &middot; <a href="/sources">Sources &amp; lineage</a> &middot; <a href="/editorial-policy">Editorial Policy</a></p>
  <p class="small"><a href="/brokers">All Brokers</a> &middot; <a href="/compare">Compare Brokers</a> &middot; <a href="/calculator">Fee Calculator</a> &middot; <a href="/stocks/">Stocks Directory</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>
"""
    return html_page


def render_trade_costs_hub(brokers, popular_stocks, site_url="https://www.brokerlens.in"):
    """Renders the master /trade-costs/ directory and fee comparator hub."""
    canonical = f"{site_url}/trade-costs/"
    title = "Stock Trading Cost & Brokerage Calculator Hub | BrokerLens"
    desc = "Compare rupee-by-rupee trading costs, STT, NSE turnover charges, stamp duty, GST, and DP charges across top Indian stock brokers."
    try:
        from .broker_charges_engine import cost_page_path
    except Exception:  # run as a script
        cost_page_path = lambda k: "/trade-costs/"  # noqa: E731

    broker_cards = []
    for b_id, b in brokers.items():
        cost_href = cost_page_path(b_id)
        deliv = _rule_short(b["delivery_flat"], b["delivery_pct"], b.get('cap_verified_asof'))
        intra = _rule_short(b["intraday_flat"], b["intraday_pct"], b.get('cap_verified_asof'))
        broker_cards.append(f"""
        <div class="card" style="padding:20px;display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="row-between" style="align-items:center;margin-bottom:10px">
              <h3 style="margin:0;font-size:18px"><a href="{cost_href}" style="color:inherit;text-decoration:none">{_esc(b['brand'])}</a></h3>
              <span class="badge">Indicative schedule</span>
            </div>
            <p class="xs muted" style="margin:0 0 14px 0">{_esc(b['tagline'])}</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:13px;margin-bottom:16px">
              <div style="background:var(--bg-raised);padding:8px 10px;border-radius:4px">
                <div class="xs muted">Delivery Brokerage</div>
                <div style="font-weight:600;color:var(--accent)">{deliv}</div>
              </div>
              <div style="background:var(--bg-raised);padding:8px 10px;border-radius:4px">
                <div class="xs muted">Intraday Brokerage</div>
                <div style="font-weight:600">{intra}</div>
              </div>
              <div style="background:var(--bg-raised);padding:8px 10px;border-radius:4px">
                <div class="xs muted">DP Charges / Debit</div>
                <div style="font-weight:600">₹{b['dp_charge']:.2f}</div>
              </div>
              <div style="background:var(--bg-raised);padding:8px 10px;border-radius:4px">
                <div class="xs muted">Demat AMC</div>
                <div style="font-weight:600">{'₹0 (Free)' if b['demat_amc'] == 0 else f'₹{b["demat_amc"]}/yr'}</div>
              </div>
            </div>
          </div>
          {_charges_link_block(b_id)}
        </div>
        """)

    stock_pills = []
    for s in popular_stocks[:48]:
        slug = _stock_slug(s["symbol"])
        stock_pills.append(f"""<a href="/stock/{slug}/" class="badge" style="padding:8px 12px;font-size:13px;text-decoration:none;background:var(--bg-raised);border:1px solid var(--border)"><strong>{_esc(s['symbol'])}</strong> <span class="muted" style="margin-left:4px">₹{s['price']:,.1f}</span></a>""")

    crumb_html = '<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li class="muted">Trade Costs</li></ol></nav>'
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "name": title,
                "url": canonical,
                "description": desc
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": site_url},
                    {"@type": "ListItem", "position": 2, "name": "Trade Costs", "item": canonical}
                ]
            }
        ]
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/" style="color:var(--accent);font-weight:600">Trade Costs</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:28px">Stock Trading Cost & Brokerage Calculator Hub</h1>
<p class="muted" style="max-width:75ch;margin:0 0 28px 0;line-height:1.6">
  Calculate exact roundtrip statutory charges, STT, exchange turnover fees, GST, SEBI charges, stamp duty, and Demat debit fees for buying and selling shares across India's leading stock brokers.
</p>

<h2 style="font-size:20px;margin-bottom:12px">Active Trader Scenario Presets</h2>
<p class="xs muted" style="margin-bottom:16px">Statutory breakdown for popular retail trading sizes at the STT rates in force from April 1, 2026 (Union Budget 2026). Net figures include exchange, SEBI, stamp duty and 18% GST.</p>
<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(260px, 1fr));gap:14px;margin-bottom:36px">
  <div class="card" style="padding:16px;background:var(--bg-raised);border-top:3px solid var(--accent)">
    <div style="font-weight:700;font-size:15px">Nifty Index Option (1 Lot)</div>
    <div class="xs muted" style="margin:4px 0 10px 0">65 Qty &middot; Buy @ Rs 120, Sell @ Rs 140</div>
    <div class="small" style="line-height:1.6">
      <div>Turnover: <strong>Rs 16,900</strong></div>
      <div>Brokerage (Rs 20 flat): <strong>Rs 40.00</strong></div>
      <div>Brokerage (Rs 11 flat): <strong>Rs 22.00</strong></div>
      <div>STT (0.15% on Sell Premium): <strong>Rs 13.65</strong></div>
      <div>Exchange + SEBI + Stamp: <strong>Rs 6.17</strong></div>
      <div style="margin-top:6px;color:var(--up);font-weight:600">Net Profit: +Rs 1,232 (Rs 20 broker), +Rs 1,253 (Rs 11 broker)</div>
    </div>
  </div>
  <div class="card" style="padding:16px;background:var(--bg-raised);border-top:3px solid var(--accent)">
    <div style="font-weight:700;font-size:15px">Equity Delivery (Rs 1 Lakh)</div>
    <div class="xs muted" style="margin:4px 0 10px 0">50 Shares @ Rs 2,000 &middot; Roundtrip</div>
    <div class="small" style="line-height:1.6">
      <div>Turnover: <strong>Rs 2,00,000</strong></div>
      <div>Brokerage (Zero): <strong>Rs 0.00</strong></div>
      <div>STT (0.1% Buy + Sell): <strong>Rs 200.00</strong></div>
      <div>Exchange + SEBI: <strong>Rs 6.14</strong></div>
      <div>Stamp Duty (0.015% on Buy) + GST: <strong>Rs 16.11</strong></div>
      <div style="margin-top:6px;color:var(--accent);font-weight:600">Total Statutory Taxes: Rs 222</div>
    </div>
  </div>
  <div class="card" style="padding:16px;background:var(--bg-raised);border-top:3px solid var(--accent)">
    <div style="font-weight:700;font-size:15px">Stock Intraday Momentum</div>
    <div class="xs muted" style="margin:4px 0 10px 0">500 Shares @ Rs 500 &middot; Rs 5L Turnover</div>
    <div class="small" style="line-height:1.6">
      <div>Turnover: <strong>Rs 5,00,000</strong></div>
      <div>Brokerage (max Rs 20): <strong>Rs 40.00</strong></div>
      <div>STT (0.025% on Sell): <strong>Rs 62.50</strong></div>
      <div>Exchange Charges: <strong>Rs 14.85</strong></div>
      <div>Stamp + SEBI + GST: <strong>Rs 17.96</strong></div>
      <div style="margin-top:6px;color:var(--up);font-weight:600">Breakeven Point: +Rs 0.27/share</div>
    </div>
  </div>
  <div class="card" style="padding:16px;background:var(--bg-raised);border-top:3px solid var(--accent)">
    <div style="font-weight:700;font-size:15px">BankNifty Expiry Scalp</div>
    <div class="xs muted" style="margin:4px 0 10px 0">30 Qty &middot; Buy @ Rs 220, Sell @ Rs 280</div>
    <div class="small" style="line-height:1.6">
      <div>Turnover: <strong>Rs 15,000</strong></div>
      <div>Brokerage (Rs 11 flat): <strong>Rs 22.00</strong></div>
      <div>STT (0.15% on Sell Premium): <strong>Rs 12.60</strong></div>
      <div>Exchange + SEBI + Stamp: <strong>Rs 5.46</strong></div>
      <div>GST: <strong>Rs 4.91</strong></div>
      <div style="margin-top:6px;color:var(--up);font-weight:600">Net Profit: +Rs 1,755</div>
    </div>
  </div>
</div>

<h2 style="font-size:20px;margin-bottom:16px">Compare by Stock Broker</h2>
<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(320px, 1fr));gap:16px;margin-bottom:40px">
  {''.join(broker_cards)}
</div>

<h2 style="font-size:20px;margin-bottom:12px">Most traded NSE stocks</h2>
<p class="xs muted" style="margin-bottom:16px">Last close from NSE's daily bhavcopy. Open a stock for its price history and trading range.</p>
<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:40px">
  {''.join(stock_pills)}
</div>

<div class="card" style="padding:24px;background:var(--bg-raised)">
  <h2 style="font-size:19px;margin-top:0">Statutory Transaction Cost Schedule in India (from April 1, 2026)</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Charge Name</th><th>Levied By</th><th>Equity Delivery Rate</th><th>Equity Intraday Rate</th><th>Derivatives (F&amp;O) Rate</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>STT (Securities Transaction Tax)</strong></td><td>Govt of India / MoF</td><td>0.1% on Buy &amp; Sell</td><td>0.025% on Sell only</td><td>0.05% on Futures (Sell), 0.15% on Options (Sell Premium), 0.15% on Exercised Options (Intrinsic Value)</td></tr>
        <tr><td><strong>Exchange Turnover Charge</strong></td><td>NSE / BSE</td><td>0.00297% (NSE true-to-label)</td><td>0.00297%</td><td>0.00173% (Futures), 0.03503% (Options Premium)</td></tr>
        <tr><td><strong>SEBI Turnover Charge</strong></td><td>SEBI Regulatory</td><td>₹10 per Crore (0.0001%)</td><td>₹10 per Crore (0.0001%)</td><td>₹10 per Crore (0.0001%)</td></tr>
        <tr><td><strong>Stamp Duty</strong></td><td>State Revenue (Indian Stamp Act)</td><td>0.015% on Buy</td><td>0.003% on Buy</td><td>0.002% on Futures Buy, 0.003% on Options Buy</td></tr>
        <tr><td><strong>GST (Goods &amp; Services Tax)</strong></td><td>Govt of India</td><td>18% on (Brokerage + Exchange + SEBI)</td><td>18% on (Brokerage + Exchange + SEBI)</td><td>18% on (Brokerage + Exchange + SEBI)</td></tr>
        <tr><td><strong>DP (Depository) Charges</strong></td><td>CDSL / NSDL + Depository Participant</td><td>₹13.50 to ₹20 + GST per debit transaction</td><td>₹0 (No Demat movement)</td><td>₹0 (Cash-settled derivatives)</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="card" style="margin-top:28px;padding:24px;background:var(--bg-raised);border-left:4px solid var(--accent);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm)">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
    <h2 style="font-size:19px;margin:0;color:var(--text)">F&amp;O Cost Audit: Save Over Rs 47,000 Annually in Brokerage</h2>
    <span class="badge badge-verified" style="font-size:11px">Flat Rs 11 F&amp;O</span>
  </div>
  <p class="small muted" style="margin:8px 0 16px 0;line-height:1.6">
    Under the revised 2026 STT rates, keeping brokerage low is essential for derivatives traders. Here is how annual costs compare for an active trader executing 10 trades daily (220 trades monthly = 2,640 trades annually):
  </p>
  <div class="table-scroll">
    <table class="data" style="margin-bottom:16px">
      <thead>
        <tr><th>Broker Model</th><th>Brokerage per Order</th><th>Roundtrip Cost (Buy + Sell)</th><th>Annual Brokerage (2,640 trades)</th><th>Annual Savings vs Percentage</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>Traditional Percentage Broker</strong></td><td>0.05% (~Rs 50 to Rs 100)</td><td>~Rs 100 to Rs 200</td><td>~Rs 264,000</td><td>Baseline</td></tr>
        <tr><td><strong>Standard Discount Broker</strong></td><td>Flat Rs 20</td><td>Rs 40</td><td>Rs 105,600</td><td>Rs 158,400 Saved</td></tr>
        <tr style="background:rgba(16,185,129,0.06)"><td><strong>Indiabulls Securities</strong></td><td><strong>Flat Rs 11</strong></td><td><strong>Rs 22</strong></td><td><strong>Rs 58,080</strong></td><td><strong style="color:var(--up)">Rs 205,920 Saved (Rs 47,520 vs Rs 20 brokers)</strong></td></tr>
      </tbody>
    </table>
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
    <a class="btn btn-primary" href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" style="font-weight:600">Open Demat Account (Flat Rs 11 F&amp;O Orders) &rarr;</a>
    <span class="xs faint">SEBI Reg. INZ000036136 &middot; 20+ Years Trusted &middot; Sponsored</span>
  </div>
</div>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">BrokerLens is an independent financial research service, not a SEBI-registered investment adviser. Calculations reflect official NSE, BSE, SEBI, and broker published rate schedules as of BrokerLens's latest data refresh. Nothing here constitutes a recommendation to buy, sell, or trade any security. <a href="/methodology">Methodology</a> &middot; <a href="/sources">Sources &amp; lineage</a> &middot; <a href="/editorial-policy">Editorial Policy</a></p>
  <p class="small"><a href="/brokers">All Brokers</a> &middot; <a href="/compare">Compare Brokers</a> &middot; <a href="/calculator">Fee Calculator</a> &middot; <a href="/stocks/">Stocks Directory</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_broker_trade_index(broker_id, broker_info, stocks, site_url="https://www.brokerlens.in"):
    """Renders /broker/[broker_id]/trade/ directory of all calculated stocks."""
    brand = broker_info["brand"]
    canonical = f"{site_url}/broker/{broker_id}/trade/"
    title = f"{brand} Stock Trade Cost & Brokerage Calculator Directory | BrokerLens"
    desc = f"Audit {brand} equity delivery and intraday trading charges across {len(stocks)} NSE stocks. Calculate exact brokerage, STT, DP charges, and breakeven points."

    stock_items = []
    for s in stocks:
        slug = _stock_slug(s["symbol"])
        stock_items.append(f"""
        <div style="background:var(--bg-raised);padding:14px;border-radius:6px;border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
          <div>
            <a href="/broker/{broker_id}/trade/{slug}/" style="font-weight:600;font-size:15px;color:var(--fg);text-decoration:none">{_esc(s['symbol'])}</a>
            <div class="xs muted" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px">{_esc(s['name'])}</div>
          </div>
          <div style="text-align:right">
            <div style="font-weight:600;font-size:14px">₹{s['price']:,.2f}</div>
            <a href="/broker/{broker_id}/trade/{slug}/" class="xs" style="color:var(--accent);text-decoration:none">Calculate &rarr;</a>
          </div>
        </div>
        """)

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/brokers">Brokers</a></li><li class="muted">/</li><li><a href="/broker/{broker_id}/">{brand}</a></li><li class="muted">/</li><li class="muted">Trade Costs</li></ol></nav>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
{TRADE_PAGE_ROBOTS}
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<div class="row-between" style="align-items:center;flex-wrap:wrap;gap:16px;margin:20px 0 16px 0">
  <div>
    <h1 style="margin:0 0 6px 0;font-size:26px">{brand} Stock Trading Cost Directory</h1>
    <p class="muted" style="margin:0;max-width:70ch">Select any stock below to view exact rupee-by-rupee statutory brokerage, STT, GST, and breakeven calculations on {brand}.</p>
  </div>
  <a href="{broker_info['cta_url']}" target="_blank" rel="noopener sponsored" class="btn btn-primary">Open {brand} Account &rarr;</a>
</div>
{_charges_link_block(broker_id)}

<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));gap:12px;margin-top:24px">
  {''.join(stock_items)}
</div>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All trade calculations are based on published broker tariffs and official SEBI/NSE statutory schedules. Not investment advice.</p>
  <p class="small"><a href="/trade-costs/">All Brokers Trade Costs</a> &middot; <a href="/broker/{broker_id}/">{brand} Review</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


PRIORITY_SYMBOLS = {
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC",
    "KOTAKBANK", "LT", "AXISBANK", "TATAMOTORS", "MARUTI", "SUNPHARMA", "TITAN",
    "BAJFINANCE", "WIPRO", "HCLTECH", "ZOMATO", "SWIGGY", "BSE", "CDSL", "ANGELONE",
    "NTPC", "ONGC", "POWERGRID", "COALINDIA", "TATASTEEL", "JSWSTEEL", "ADANIENT",
    "ADANIPORTS", "ASIANPAINT", "NESTLEIND", "ULTRACEMCO", "GRASIM", "M&M", "BAJAJ-AUTO"
}


def get_trade_cost_stocks(limit_stocks: int = 1000):
    """Returns sorted, liquid NSE equities prioritized by turnover and relevance."""
    ingest_path = os.path.join(DATA_DIR, "_ingest.json")
    if not os.path.exists(ingest_path):
        return []

    with open(ingest_path, "r", encoding="utf-8") as f:
        ingest = json.load(f)

    nse = ingest.get("nse", {})
    companies = nse.get("universe", {}).get("companies", [])
    eq_hist = nse.get("equity_history", {})

    valid_stocks = []
    for c in companies:
        sym = (c.get("symbol") or "").upper().strip()
        hist = eq_hist.get(sym) or []
        if hist and hist[-1].get("close"):
            last_price = float(hist[-1]["close"])
            if last_price > 5.0: # filter out penny stocks / suspended
                vols = [float(x.get("volume") or 0) for x in hist[-30:]]
                avg_vol = sum(vols) / len(vols) if vols else 0
                turnover = avg_vol * last_price
                pri = 10 if sym in PRIORITY_SYMBOLS else 0
                valid_stocks.append({
                    "symbol": sym,
                    "name": c.get("name") or sym,
                    "isin": c.get("isin") or "",
                    "price": last_price,
                    "sector": c.get("series") or "EQ",
                    "turnover": turnover,
                    "priority": pri
                })

    valid_stocks.sort(key=lambda s: (-s["priority"], -s["turnover"]))
    return valid_stocks[:limit_stocks]


def build_trade_cost_pages(limit_stocks: int = 1000, site_url: str = "https://www.brokerlens.in"):
    """Writes the /trade-costs/ hub. The broker x stock pages are retired (see below)."""
    removed = remove_retired_trade_pages()
    if removed:
        print(f"[trade_cost_engine] Removed {removed} retired /broker/<id>/trade/ directories")
    valid_stocks = get_trade_cost_stocks(limit_stocks=limit_stocks)
    if not valid_stocks:
        print("[trade_cost_engine] Error: no valid stocks found")
        return []

    generated_urls = []

    # 1. Master Trade Costs Hub (/trade-costs/)
    hub_dir = os.path.join(SITE_DIR, "trade-costs")
    os.makedirs(hub_dir, exist_ok=True)
    hub_html = render_trade_costs_hub(BROKER_RATES, valid_stocks, site_url=site_url)
    with open(os.path.join(hub_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(hub_html)
    generated_urls.append("/trade-costs/")

    # 2. The broker x stock pages are retired (10 Nov 2026). 30 brokers x 2,500 stocks made
    # 75,000 near-identical pages: Google indexed 33.5K of them, impressions fell 97% on
    # 2 Nov, and on 10 Nov URL Inspection showed Google still spending its crawl on them
    # (last crawls 17 to 25 Oct, so it had not even seen their noindex) while the /ipo/ hub
    # and most broker profiles sat in "Discovered - currently not indexed". Each one now
    # 308s to its broker's cost page (broker_charges_engine.cost_page_path, vercel.json),
    # whose calculator takes any order value. Never regenerate them.
    print("[trade_cost_engine] Wrote the /trade-costs/ hub")
    return generated_urls


def remove_retired_trade_pages(site_dir=None):
    """Delete /broker/<id>/trade/ output left by an older build; returns how many dirs went."""
    import shutil
    broker_dir = os.path.join(site_dir or SITE_DIR, "broker")
    n = 0
    if os.path.isdir(broker_dir):
        for b_id in os.listdir(broker_dir):
            t_dir = os.path.join(broker_dir, b_id, "trade")
            if os.path.isdir(t_dir):
                shutil.rmtree(t_dir, ignore_errors=True)
                n += 1
    return n


if __name__ == "__main__":
    urls = build_trade_cost_pages(limit_stocks=500)
    print(f"Generated {len(urls)} pages.")

