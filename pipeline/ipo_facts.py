"""Shared IPO fact helpers: one source of truth for price, status, titles and facts card.

Everything here works from fields that are on file for an IPO record. Nothing is
estimated. When a field is missing the helper returns None and the caller omits the
part or shows "Not on file".

Title and meta A/B split (documented in docs/IPO_TITLE_TEST.md):
    group = "A" if zlib.crc32(slug.lower().encode("utf-8")) % 2 == 0 else "B"
zlib.crc32 is deterministic across runs and Python versions (the built-in hash function is randomised per
process, so it must never be used for a split). Group A uses a facts-first pattern
(price band, dates, listing date), group B uses the keyword pattern
("IPO Date, Price Band, Lot Size and Listing Date"). The latest-close figure never
appears in the title or meta description; it stays in the page body with its date.

Status model (ipo_status): Listed, Active, Forthcoming, Closed (bidding over, still inside the
SEBI T+3 listing window) and "No listing on file" (STATUS_NO_LISTING): no listing date is on file
and the issue either carries a withdrawn, postponed or withdrawal label in its name, closed more than
NO_LISTING_AFTER_DAYS days ago, or is already past its expected T+3 listing date. That status never says
a listing is awaited, never shows the T+3 timeline and is treated like Listed for sub-page noindex and
sitemap exclusion.

Zero em dashes or en dashes anywhere in user-visible copy.
"""
from __future__ import annotations

import html
import json
import os
import re
import zlib
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BRAND = "BrokerLens"
# Titles are built from parts that are dropped from the right when the key part
# (everything before " | BrokerLens") would run past this many characters. Search
# results cut off around 60 characters on desktop, so the order of the parts puts
# the name, price band and dates first.
MAX_KEY_CHARS = 100
# Same value as build_ipo_apply_suite(limit_recent_ipos=...) in pipeline/publish.py.
APPLY_PAGES_LIMIT = 10

STATUS_NO_LISTING = "No listing on file"
NO_LISTING_NOTE = "No listing is on file for this issue."
LISTING_INCONSISTENT = "Listing date on file looks inconsistent; see the exchange"
# A Closed issue with no listing date turns into STATUS_NO_LISTING after this many calendar days.
NO_LISTING_AFTER_DAYS = 15
# A listing date earlier than the bidding end, or later than this many days after it, is treated as a
# data fault (SEBI's T+3 rule puts a real listing within about a week, holidays included).
MAX_LISTING_GAP_DAYS = 20
OPEN_STATUSES = ("Active", "Forthcoming")

# The one place the SEBI bid limits live. They are rules, not per-issue data, so every page that shows
# them takes the values and the note from here.
SEBI_BID_LIMITS = {
    "retail": "Rs 2 lakh",
    "snii": "Rs 10 lakh",
    "upi": "Rs 5 lakh",
    "note": "as per SEBI ICDR, confirm in the offer document",
}


def _esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


# ---------------------------------------------------------------- A/B split

def title_group(slug):
    """'A' or 'B' from a stable CRC32 of the lower-cased slug. Never use the built-in hash function."""
    return "A" if zlib.crc32(str(slug or "").lower().encode("utf-8")) % 2 == 0 else "B"


# ---------------------------------------------------------------- dates

def _parse(iso):
    try:
        return datetime.strptime(str(iso or "").strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None


def fmt_date(iso):
    """'2022-12-29' -> '29 Dec 2022' (no leading zero). '' when not a date."""
    dt = _parse(iso)
    if not dt:
        return ""
    return "%d %s" % (dt.day, dt.strftime("%b %Y"))


def date_range_text(a_iso, b_iso):
    """'19 to 21 Dec 2022', '28 Nov to 2 Dec 2022', or two full dates. Uses the word to."""
    da, db = _parse(a_iso), _parse(b_iso)
    if not da or not db:
        return ""
    if da == db:
        return fmt_date(a_iso)
    if da.year == db.year and da.month == db.month:
        return "%d to %d %s" % (da.day, db.day, db.strftime("%b %Y"))
    if da.year == db.year:
        return "%d %s to %d %s" % (da.day, da.strftime("%b"), db.day, db.strftime("%b %Y"))
    return "%s to %s" % (fmt_date(a_iso), fmt_date(b_iso))


# ---------------------------------------------------------------- prices

def fmt_price(x):
    """Rs amounts without noise: 366 -> '366', 1229.5 -> '1,229.5', 85.09 -> '85.09'."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return ""
    s = "{:,.2f}".format(v)
    if s.endswith(".00"):
        return s[:-3]
    if s.endswith("0"):
        return s[:-1]
    return s


def _nums(text):
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(text or "").replace(",", ""))]


def price_facts(r):
    """The one place that reads price_band and issue_price.

    Returns a dict:
      band_low, band_high  floats when the stored band holds two different prices, else None
      single               the one price when the stored band holds a single figure (fixed price)
      issue_price          the final issue price when it is on file AND consistent with the band
      issue_price_rejected True when a stored issue price lies outside the stored band (data
                           fault, 49 such rows exist); it is then ignored everywhere
    Low and high always come from the stored price band, so the title, meta, facts card,
    sub-pages and hubs can never disagree (the old code replaced both by the issue price).
    """
    nums = _nums(r.get("price_band"))
    low = high = single = None
    if len(nums) >= 2 and nums[0] > 0 and nums[1] > 0:
        if nums[0] < nums[1]:
            low, high = nums[0], nums[1]
        elif nums[0] == nums[1]:
            single = nums[0]
        # nums[0] > nums[1] is a malformed band: ignored
    elif len(nums) == 1 and nums[0] > 0:
        single = nums[0]

    ip = None
    rejected = False
    try:
        raw = float(r.get("issue_price")) if r.get("issue_price") not in (None, "", "-") else 0.0
    except (TypeError, ValueError):
        raw = 0.0
    if raw > 0:
        if low is not None and high is not None:
            ok = low - 0.005 <= raw <= high + 0.005
        elif single is not None:
            ok = abs(raw - single) < 0.005
        else:
            ok = True
        if ok:
            ip = raw
        else:
            rejected = True
    return {"band_low": low, "band_high": high, "single": single,
            "issue_price": ip, "issue_price_rejected": rejected}


def band_text(r, rs="Rs ", sep=" to "):
    """'Rs 347 to Rs 366', 'Rs 366' (single price), or '' when no price is on file."""
    pf = price_facts(r)
    if pf["band_low"] is not None:
        return "%s%s%s%s%s" % (rs, fmt_price(pf["band_low"]), sep, rs, fmt_price(pf["band_high"]))
    one = pf["single"] if pf["single"] is not None else pf["issue_price"]
    return "%s%s" % (rs, fmt_price(one)) if one else ""


def band_short(pf):
    """Title form: 'Rs 347 to 366'."""
    return "Rs %s to %s" % (fmt_price(pf["band_low"]), fmt_price(pf["band_high"]))


def lot_size_on_file(r):
    """Sourced IPO lot size or None.

    NSE's public-issue feeds that BrokerLens reads carry no lot size, and EQUITY_L's
    MARKET LOT is the trading lot (1 share), not the IPO bid lot. So today this is None
    for every record. The page code only prints a lot size when a record carries an
    explicit positive integer lot_size field from a real source. The old estimate
    (about Rs 14,500 divided by price) printed 99 shares for JSW Cement against the 102
    in the prospectus, so it is gone."""
    v = r.get("lot_size")
    try:
        n = int(float(v))
        whole = float(v) == n
    except (TypeError, ValueError):
        return None
    return n if n > 0 and whole else None


def issue_size_text(r, pf):
    """Shares on file, plus the rupee value at the upper band when a band is on file."""
    try:
        shares = int(float(r.get("issue_size_shares")))
    except (TypeError, ValueError):
        return ""
    if shares <= 0:
        return ""
    txt = "{:,} shares".format(shares)
    top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
    if top:
        txt += " (about Rs {:,.1f} Cr at the upper price)".format(shares * top / 1e7)
    return txt


# ---------------------------------------------------------------- names

_FLAG_ANY_RE = re.compile(r"\b(withdrawn|postponed|withdrawal)\b", re.I)
_FLAG_TAIL_RE = re.compile(r"\s*[-:]\s*(?:issue\s+)?(?:withdrawn|postponed|withdrawal(?:\s+window)?)\s*$", re.I)


def name_flag(r):
    """'withdrawn', 'postponed', 'withdrawal window' or '' from the company name in the exchange feed.

    The feed appends the state to the company name ('...Limited-Issue Withdrawn'). It is the only
    place that state is recorded, so it is read from there and nowhere else."""
    m = _FLAG_ANY_RE.search(str((r or {}).get("company") or ""))
    if not m:
        return ""
    w = m.group(1).lower()
    return "withdrawal window" if w == "withdrawal" else w


def display_name(r):
    """Company name without the exchange's trailing state label (Issue Withdrawn, Issue postponed)."""
    raw = str((r or {}).get("company") or "").strip()
    clean = _FLAG_TAIL_RE.sub("", raw).strip() if raw else ""
    return clean or raw or str((r or {}).get("symbol") or "").strip()


# ---------------------------------------------------------------- listing date plausibility

def listing_date_state(r):
    """'none' (no listing date), 'ok' or 'inconsistent'.

    A listing date that precedes the bidding end, or comes more than MAX_LISTING_GAP_DAYS after it,
    contradicts the SEBI T+3 timeline (CAMS 'listed' 7 May 2021 for a Sep 2020 issue, Ruchi Soya 2 Jan 2003
    for a Mar 2022 issue). About 140 records in the feed are like that, so such a date is never published
    as a fact and never used to compute a listing-day result."""
    ld = _parse((r or {}).get("listing_date"))
    if not ld:
        return "none"
    ref = _parse((r or {}).get("bidding_end")) or _parse((r or {}).get("bidding_start"))
    if ref is None:
        return "ok"
    gap = (ld - ref).days
    return "ok" if 0 <= gap <= MAX_LISTING_GAP_DAYS else "inconsistent"


def reliable_listing_date(r):
    """The stored listing date (ISO) when it passes the plausibility rule, else ''."""
    return str((r or {}).get("listing_date") or "")[:10] if listing_date_state(r) == "ok" else ""


def listing_date_display(r, none_text="Not on file"):
    """Text for a 'Listing date' slot: the date, the inconsistency note, or none_text."""
    st = listing_date_state(r)
    if st == "ok":
        return fmt_date(r.get("listing_date"))
    if st == "inconsistent":
        return LISTING_INCONSISTENT
    return none_text


# ---------------------------------------------------------------- status

def add_working_days(iso, n):
    """Date n weekdays after iso (Mon to Fri only; exchange holidays are not known here)."""
    d = _parse(iso)
    if not d:
        return None
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.strftime("%Y-%m-%d")


def ipo_status(r, today_iso):
    """Listed, Active, Forthcoming, Closed or STATUS_NO_LISTING, from dates on file.

    A listing date that is still in the future does not make an IPO Listed (the stored
    status flag would say so). Listed is the only status that may say an IPO has listed.
    Closed means bidding is over and the issue is still inside its SEBI T+3 listing window. After that
    window, or 15 days after bidding closed, or when the name says withdrawn or postponed, an issue with
    no listing date is STATUS_NO_LISTING, never 'awaiting listing'."""
    ld = r.get("listing_date") or ""
    if ld and ld <= today_iso:
        return "Listed"
    # A future listing date counts only when it passes the plausibility rule.
    ld_future_ok = bool(ld) and listing_date_state(r) == "ok"
    if name_flag(r) and not ld_future_ok:
        return STATUS_NO_LISTING
    b_start, b_end = r.get("bidding_start") or "", r.get("bidding_end") or ""
    if b_start and b_end and b_start <= today_iso <= b_end:
        return "Active"
    if b_start and b_start > today_iso:
        return "Forthcoming"
    if b_end and b_end < today_iso:
        if ld_future_ok:
            return "Closed"
        t = _parse(today_iso)
        be = _parse(b_end)
        if t and be and (t - be).days > NO_LISTING_AFTER_DAYS:
            return STATUS_NO_LISTING
        exp = add_working_days(b_end, 3)
        if exp and exp < today_iso:
            return STATUS_NO_LISTING
        return "Closed"
    st = r.get("status")
    if st in ("Active", "Forthcoming", "Closed"):
        return st
    if st == "Listed" and not ld:
        return "Listed"
    return "Closed"


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_listed(r, today_iso=None):
    return ipo_status(r, today_iso or _today()) == "Listed"


def is_settled(r, today_iso=None):
    """Listed or STATUS_NO_LISTING: no bidding or allotment window is open, so the per-IPO
    subscription, basis-of-allotment, allotment-status and apply-via pages are noindex,follow
    and kept out of the sitemap."""
    return ipo_status(r, today_iso or _today()) in ("Listed", STATUS_NO_LISTING)


def is_open_for_bids(r, today_iso=None):
    return ipo_status(r, today_iso or _today()) in OPEN_STATUSES


def status_label(status):
    """The status word shown to visitors."""
    return {"Active": "Open for bidding", "Forthcoming": "Upcoming"}.get(status, status)


def exchange_label(r):
    return "NSE Emerge" if r.get("security_type") == "SME" else "NSE"


# ---------------------------------------------------------------- non-equity issues

_FAM_RE = re.compile(r"^([A-Z]{3,}?)(\d{1,2})$")
_FAMILY_CACHE = {}
_SIBLINGS = {}
_EQUITY_TYPES = ("EQ", "SME")


def _symbol_families():
    """{(symbol prefix, lower-case company): set of security types} for the past issues in the feed."""
    if "f" in _FAMILY_CACHE:
        return _FAMILY_CACHE["f"]
    fam = {}
    _SIBLINGS.clear()
    try:
        with open(os.path.join(ROOT, "data", "_ingest.json"), encoding="utf-8") as fh:
            past = (((json.load(fh) or {}).get("nse") or {}).get("ipo") or {}).get("past") or []
        for x in past:
            m = _FAM_RE.match(str(x.get("symbol") or "").upper())
            if m:
                fam.setdefault((m.group(1), str(x.get("company") or "").strip().lower()), set()).add(x.get("security_type"))
                _SIBLINGS.setdefault((m.group(1), str(x.get("company") or "").strip().lower()), []).append(
                    (str(x.get("symbol") or "").upper(), x.get("security_type")))
    except (OSError, ValueError):
        fam = {}
    _FAMILY_CACHE["f"] = fam
    return fam


def is_non_equity_issue(r):
    """True when the record is very likely a debt or other non-equity public issue.

    Evidence used, nothing else: (1) the record itself carries a security type other than EQ or SME; or
    (2) it has no security type (current and upcoming feeds carry none), and every earlier series of the same
    symbol family and company in the past-issues feed (SMCG01 to SMCG03 for SMCG04) is classified as
    something other than EQ or SME (DEBT). SMC Global's SMCG04 (fixed Rs 1,000, 750,000 securities) is the
    case this catches. It is an inference from the feed, so the page says so."""
    st = r.get("security_type")
    if st and st not in _EQUITY_TYPES:
        return True
    if st:
        return False
    m = _FAM_RE.match(str(r.get("symbol") or "").upper())
    if not m:
        return False
    sibs = _symbol_families().get((m.group(1), str(r.get("company") or "").strip().lower()))
    return bool(sibs) and all(t not in _EQUITY_TYPES for t in sibs)


def non_equity_note(r):
    """One honest sentence for a page about a non-equity issue, or '' for an equity IPO."""
    if not is_non_equity_issue(r):
        return ""
    st = r.get("security_type")
    m = _FAM_RE.match(str(r.get("symbol") or "").upper())
    sibs = sorted(sym for sym, t in _SIBLINGS.get((m.group(1), str(r.get("company") or "").strip().lower()), [])) if m else []
    if st and st not in _EQUITY_TYPES:
        why = "the exchange feed classifies this issue as security type %s, not as equity" % st
    elif sibs:
        why = "the exchange feed classifies the earlier series of this symbol (%s) as debt" % ", ".join(sibs)
        sp = price_facts(r)["single"]
        if sp:
            why += ", and this series has a fixed price of Rs %s" % fmt_price(sp)
    else:
        why = "the exchange feed does not classify it as equity"
    return ("This record is not presented as an equity IPO: %s. BrokerLens treats it as a likely debt issue "
            "(for example debentures). This is an inference from the feed, so check the issue document on the exchange website." % why)


def ipo_records_only(records):
    """records without the non-equity issues (kept out of the hub, archive, feeds and sub-pages)."""
    return [r for r in records if not is_non_equity_issue(r)]


# ---------------------------------------------------------------- data freshness

_AS_OF_CACHE = {}


def data_as_of(today_iso=None):
    """Date the IPO feed was fetched (fetched_at in data/_ingest.json), else today."""
    if "d" in _AS_OF_CACHE:
        return _AS_OF_CACHE["d"]
    d = ""
    try:
        with open(os.path.join(ROOT, "data", "_ingest.json"), encoding="utf-8") as fh:
            d = str((json.load(fh) or {}).get("fetched_at") or "")[:10]
    except (OSError, ValueError):
        d = ""
    if not _parse(d):
        d = today_iso or _today()
    _AS_OF_CACHE["d"] = d
    return d


def data_age_days(as_of_iso, today_iso=None):
    a, t = _parse(as_of_iso), _parse(today_iso or _today())
    return (t - a).days if a and t else 0


def earliest_year(records):
    """Earliest year of any bidding date on file (the listing date is not used: it is the faultier field)."""
    ys = []
    for r in records:
        for k in ("bidding_start", "bidding_end"):
            d = _parse(r.get(k))
            if d:
                ys.append(d.year)
    return min(ys) if ys else None


# ---------------------------------------------------------------- subscription snapshot

def subscription_info(r, status, as_of_iso):
    """The overall subscription multiple on file and what it can honestly be called.

    The multiple comes from the current-issue feed, a snapshot taken on the feed date. It is the final result
    only when the feed date is after the bidding end. Otherwise it is a snapshot taken while bidding was open
    and must never be presented as the result of a closed issue.
    Returns None when no multiple is on file, else {value, as_of, final, open_now}."""
    try:
        v = r.get("times_subscribed")
        val = float(v) if v is not None else None
    except (TypeError, ValueError):
        val = None
    if val is None:
        return None
    be = r.get("bidding_end") or ""
    final = bool(be and as_of_iso and as_of_iso > be and status != "Active")
    return {"value": val, "as_of": as_of_iso, "final": final, "open_now": status == "Active"}


def subscription_phrase(info):
    """'0.44 times as of 2 Oct 2026, while bidding was open' style text for a snapshot, or the plain
    multiple for a final figure."""
    if not info:
        return ""
    t = "%.2f times" % info["value"]
    if info["final"]:
        return t
    if info["open_now"]:
        return "%s as of %s" % (t, fmt_date(info["as_of"]))
    return "%s as of %s, while bidding was open (final figure not on file)" % (t, fmt_date(info["as_of"]))


# ---------------------------------------------------------------- uniqueness of short names

_NAME_COUNT_CACHE = {}


def _short_name_counts():
    if "n" in _NAME_COUNT_CACHE:
        return _NAME_COUNT_CACHE["n"]
    counts = {}
    try:
        with open(os.path.join(ROOT, "data", "_ingest.json"), encoding="utf-8") as fh:
            ipo = ((json.load(fh) or {}).get("nse") or {}).get("ipo") or {}
        seen = set()
        for k in ("upcoming", "current", "past"):
            for x in ipo.get(k) or []:
                sym = str(x.get("symbol") or "").upper()
                if not sym or sym in seen:
                    continue
                if k == "past" and x.get("security_type") not in _EQUITY_TYPES:
                    continue
                seen.add(sym)
                key = _short_name(display_name(x), sym).lower()
                counts[key] = counts.get(key, 0) + 1
    except (OSError, ValueError):
        counts = {}
    _NAME_COUNT_CACHE["n"] = counts
    return counts


def name_is_shared(r):
    """True when another IPO record on file has the same short name (Penta Gold: PENTAGLTD and PENTAGOLD)."""
    key = _short_name(display_name(r), r.get("symbol")).lower()
    return _short_name_counts().get(key, 0) > 1


# ---------------------------------------------------------------- listing day candle

def listing_candle(symbol, listing_date, equity_history):
    """Listing-day open/high/low/close, only when the exchange history on file has a
    candle for exactly the listing date. None otherwise (never a nearby candle)."""
    ld = (listing_date or "")[:10]
    if not ld or not symbol or not equity_history:
        return None
    candles = equity_history.get(str(symbol).upper().strip())
    if not isinstance(candles, list):
        return None
    c = next((x for x in candles if x.get("date") == ld), None)
    if not c:
        return None
    try:
        o, h, l, cl = (float(c.get(k) or 0.0) for k in ("open", "high", "low", "close"))
    except (TypeError, ValueError):
        return None
    if min(o, h, l, cl) <= 0:
        return None
    return {"date": ld, "open": o, "high": h, "low": l, "close": cl}


# ---------------------------------------------------------------- title and meta

def _short_name(company, symbol):
    name = (company or symbol or "").strip()
    short = re.sub(r"\s+(limited|ltd\.?)\s*$", "", name, flags=re.I).strip()
    return short or name


def _title_name(r):
    """Short display name; the symbol is added when another IPO on file has the same short name."""
    name = _short_name(display_name(r), r.get("symbol"))
    if name_is_shared(r):
        name = "%s (%s)" % (name, str(r.get("symbol") or "").upper())
    return name


# Hand-written title and description overrides used to live here. All were retired on
# 9 Nov 2026: four promised a "Listing Price" and "post-listing gain" for IPOs whose
# listing day predates the price history on file (the page said so), and the rest
# described Jio, Tata Sons and boAt IPOs with invented price bands, or called long
# listed issues (NSDL, Swiggy, HDB Financial, Ather) "expected". Titles come only from
# facts on file (build_title below).
_RESCUE_TITLES = {}
_RESCUE_DESCRIPTIONS = {}


def build_title(r, pf, status, group=None):
    """Title for the A/B test. Parts that are not on file are omitted: 'Listing Date' only when a plausible
    listing date is on file, 'Price Band' only when a band is on file."""
    slug = (r.get("symbol") or "").lower()
    if slug in _RESCUE_TITLES:
        return _RESCUE_TITLES[slug]
    group = group or title_group(slug)
    name = _title_name(r)
    b_start, b_end = r.get("bidding_start") or "", r.get("bidding_end") or ""
    ld = reliable_listing_date(r)
    # "<company> ipo gmp" is the single highest-intent IPO query while an issue is open or
    # about to open (confirmed by real GSC data: the IPO section is the worst-performing
    # page family on the site despite real search volume), and the body already renders a
    # GMP section whenever data is on file via render_gmp_section() - the title just never
    # mentioned it. Once listed, GMP is moot, so this only applies pre-listing.
    gmp_on_file = status in OPEN_STATUSES and bool(get_ipo_gmp(r.get("symbol")))
    if group == "B":
        bits = []
        if gmp_on_file:
            bits.append("GMP")
        if _parse(b_start) or _parse(b_end):
            bits.append("Date")
        if pf["band_low"] is not None:
            bits.append("Price Band")
        elif pf["single"] is not None or pf["issue_price"]:
            bits.append("Issue Price")
        if lot_size_on_file(r) is not None:
            bits.append("Lot Size")
        if _parse(ld):
            bits.append("Listing Date")
        if not bits:
            return "%s IPO Key Facts | %s" % (name, BRAND)
        what = bits[0] if len(bits) == 1 else "%s and %s" % (", ".join(bits[:-1]), bits[-1])
        return "%s IPO %s | %s" % (name, what, BRAND)

    band = ""
    if pf["band_low"] is not None:
        band = "Price Band " + band_short(pf)
    else:
        one = pf["single"] if pf["single"] is not None else pf["issue_price"]
        if one:
            band = "Issue price Rs " + fmt_price(one)
    dates = ""
    if _parse(b_start) and _parse(b_end):
        dates = "Dates " + date_range_text(b_start, b_end)
    elif _parse(b_end):
        dates = "Closes " + fmt_date(b_end)
    elif _parse(b_start):
        dates = "Opens " + fmt_date(b_start)
    listing = ("Listing " + fmt_date(ld)) if _parse(ld) else ""
    parts = [p for p in (band, dates, listing) if p]

    def key(ps):
        return "%s IPO: %s" % (name, ", ".join(ps)) if ps else "%s IPO Key Facts" % name

    # Degrade gracefully when the key part runs long. For a listed IPO the listing date is
    # what people search for, so the bidding dates go first; otherwise the listing date goes.
    order = (dates, listing) if status == "Listed" else (listing, dates)
    while len(parts) > 1 and len(key(parts)) > MAX_KEY_CHARS:
        drop = next((x for x in order if x in parts), parts[-1])
        parts.remove(drop)
    if gmp_on_file:
        # Added after the degrade loop, never a candidate for removal: GMP is the keyword
        # driving real search demand, so it is kept even if the rest already used the full
        # budget, same principle as the stock price-target title (file/pipeline/
        # price_target_section.py's stock_title()).
        parts = ["GMP"] + parts
    return "%s | %s" % (key(parts), BRAND)


def _flag_sentence(r):
    f = name_flag(r)
    if not f:
        return ""
    return "The exchange feed labels this issue as %s." % ("a withdrawal window" if f == "withdrawal window" else f)


def build_description(r, pf, status, candle=None, has_latest_close=False):
    """Meta description from fields on file. The latest-close figure and any subscription multiple are never included."""
    slug = (r.get("symbol") or "").lower()
    if slug in _RESCUE_DESCRIPTIONS:
        return _RESCUE_DESCRIPTIONS[slug]
    name = _short_name(display_name(r), r.get("symbol"))
    b_start, b_end = r.get("bidding_start") or "", r.get("bidding_end") or ""
    ld = reliable_listing_date(r)
    ld_state = listing_date_state(r)
    ex = exchange_label(r)
    s = []
    bits = []
    if _parse(b_start):
        bits.append("opened " + fmt_date(b_start))
    if _parse(b_end):
        bits.append("closed " + fmt_date(b_end))
    if status == "Listed":
        lead = "%s IPO %s" % (name, " and ".join(bits)) if bits else "%s IPO" % name
        if _parse(ld):
            s.append("%s, listed %s on %s." % (lead, fmt_date(ld), ex))
        elif ld_state == "inconsistent":
            s.append("%s. %s." % (lead, LISTING_INCONSISTENT))
        else:
            s.append("%s." % lead)
    elif status == "Active":
        s.append("%s IPO is open for bidding%s." % (name, (" until " + fmt_date(b_end)) if _parse(b_end) else ""))
    elif status == "Forthcoming":
        if _parse(b_start) and _parse(b_end):
            s.append("%s IPO opens %s and closes %s." % (name, fmt_date(b_start), fmt_date(b_end)))
        elif _parse(b_start):
            s.append("%s IPO opens %s." % (name, fmt_date(b_start)))
        else:
            s.append("%s IPO dates as announced by the issuer." % name)
    elif status == STATUS_NO_LISTING:
        s.append("%s IPO %s." % (name, " and ".join(bits)) if bits else "%s IPO." % name)
        fs = _flag_sentence(r)
        if fs:
            s.append(fs)
        s.append(NO_LISTING_NOTE)
    else:
        s.append("%s IPO %s." % (name, " and ".join(bits)) if bits else "%s IPO has closed." % name)
        s.append("Listing date %s." % (("set for " + fmt_date(ld)) if _parse(ld) else "not on file yet"))

    if pf["issue_price"]:
        s.append("Issue price Rs %s%s." % (fmt_price(pf["issue_price"]),
                 (" (price band %s)" % band_short(pf)) if pf["band_low"] is not None else ""))
    elif pf["band_low"] is not None:
        s.append("Price band %s." % band_short(pf))
    elif pf["single"] is not None:
        s.append("Issue price Rs %s." % fmt_price(pf["single"]))
    if candle:
        s.append("Listing day open Rs %s." % fmt_price(candle["open"]))
    lot = lot_size_on_file(r)
    if lot:
        s.append("Lot size %d shares." % lot)
    s.append("Status: %s." % ("Open" if status == "Active" else status))
    if has_latest_close:
        s.append("Latest close shown on the page with its date.")
    return " ".join(s)[:295]


# ---------------------------------------------------------------- facts card

def render_facts_card(r, pf, status, candle, as_of_iso, company, perf_sub=None):
    """Compact key-facts table that sits above performance blocks and banners."""
    rows = []

    def add(label, value):
        if value:
            rows.append((label, value))

    add("Status", _esc(status_label(status)))
    if pf["band_low"] is not None:
        add("Price band", _esc("Rs %s to Rs %s" % (fmt_price(pf["band_low"]), fmt_price(pf["band_high"]))))
        add("Issue price", _esc("Rs " + fmt_price(pf["issue_price"])) if pf["issue_price"] else "")
    else:
        one = pf["single"] if pf["single"] is not None else pf["issue_price"]
        add("Issue price (fixed)" if pf["single"] is not None else "Issue price", _esc("Rs " + fmt_price(one)) if one else "")
    add("Bidding opens", _esc(fmt_date(r.get("bidding_start"))))
    add("Bidding closes", _esc(fmt_date(r.get("bidding_end"))))
    ld_state = listing_date_state(r)
    if ld_state == "ok":
        add("Listing date" if status == "Listed" else "Listing date (as announced)", _esc(fmt_date(r.get("listing_date"))))
    elif ld_state == "inconsistent":
        add("Listing date", _esc(LISTING_INCONSISTENT))
    elif status == STATUS_NO_LISTING:
        add("Listing", _esc(NO_LISTING_NOTE))
    add("Exchange", _esc(exchange_label(r)))
    if is_non_equity_issue(r):
        itype = "Not classified as an equity IPO (see the note on this page)"
    elif r.get("security_type") == "SME":
        itype = "SME Emerge"
    elif r.get("security_type") == "EQ":
        itype = "Mainboard equity"
    else:
        itype = ""
    if re.search(r"\bFPO\b", str(r.get("company") or "")):
        itype = "Follow-on public offer (FPO), as named in the exchange feed"
    add("Issue type", _esc(itype))
    lot = lot_size_on_file(r)
    add("Lot size", _esc("%d shares" % lot) if lot else "")
    add("Issue size", _esc(issue_size_text(r, pf)))
    info = subscription_info(r, status, as_of_iso)
    if info and status in ("Active", "Closed", STATUS_NO_LISTING):
        add("Overall subscription", _esc(subscription_phrase(info)))
    if candle:
        add("Listing day prices", _esc("Open Rs %s, high Rs %s, low Rs %s, close Rs %s" % (
            fmt_price(candle["open"]), fmt_price(candle["high"]), fmt_price(candle["low"]), fmt_price(candle["close"]))))

    body = "".join('<tr><th scope="row" style="text-align:left;width:42%%">%s</th><td>%s</td></tr>' % (_esc(l), v) for l, v in rows)
    return (
        '<section class="card ipo-facts" aria-labelledby="ipo-facts-h" style="margin-top:16px;padding:18px;background:var(--bg-raised)">'
        '<h2 id="ipo-facts-h" style="margin:0 0 10px 0;font-size:18px">%s IPO key facts</h2>'
        '<div class="table-scroll"><table class="data"><tbody>%s</tbody></table></div>'
        '<p class="xs faint" style="margin:10px 0 0 0">Data as of %s. Source: NSE public-issue disclosures and NSE price history.</p>'
        '</section>' % (_esc(company), body, _esc(fmt_date(as_of_iso)))
    )


# ---------------------------------------------------------------- GMP and outcome

def open_vs_issue_phrase(open_price, issue_price):
    """'2.0% above the issue price', '10.0% below the issue price' or 'in line with the issue price'.
    It is the listing-day open compared with the issue price, never called a gain or a loss."""
    pct = (open_price - issue_price) / issue_price * 100.0
    if abs(pct) < 0.05:
        return "in line with the issue price"
    return "%.1f%% %s the issue price" % (abs(pct), "above" if pct > 0 else "below")


_GMP_CACHE = None


def get_ipo_gmp(symbol):
    """Retrieve timestamped GMP observation for an IPO symbol if on file."""
    global _GMP_CACHE
    if _GMP_CACHE is None:
        p = os.path.join(ROOT, "data", "manual", "ipo_gmp.json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    _GMP_CACHE = json.load(fh) or {}
            except Exception:
                _GMP_CACHE = {}
        else:
            _GMP_CACHE = {}
    return _GMP_CACHE.get((symbol or "").upper())


def gmp_trend(gmp_info):
    """'up'/'down'/'neutral' derived from the actual recorded history, not
    the static hand-set field, so a value frozen for days stops reading as
    'Rising' everywhere it is shown (GMP section, /ipo/gmp/ hub, bulletins)."""
    hist = (gmp_info or {}).get("history") or []
    dated = [h for h in hist if h.get("gmp") is not None]
    if len(dated) >= 2:
        last_gmp, prev_gmp = float(dated[-1]["gmp"]), float(dated[-2]["gmp"])
        return "up" if last_gmp > prev_gmp else "down" if last_gmp < prev_gmp else "neutral"
    return (gmp_info or {}).get("trend", "neutral")


def gmp_outcome_sentence(r, pf, status, candle, perf):
    """The verifiable outcome, or '' when it is not on file."""
    if status != "Listed":
        return ""
    ip = pf["issue_price"]
    if candle and ip:
        return "Issue price Rs %s, listed open Rs %s (listing-day open %s, listing day %s)." % (
            fmt_price(ip), fmt_price(candle["open"]), open_vs_issue_phrase(candle["open"], ip), fmt_date(candle["date"]))
    return ""


def render_gmp_section(r, pf, status, candle, perf, company):
    sym = r.get("symbol") or ""
    gmp_info = get_ipo_gmp(sym)
    outcome = gmp_outcome_sentence(r, pf, status, candle, perf)

    if gmp_info:
        gmp_val = float(gmp_info.get("gmp", 0.0))
        kostak = gmp_info.get("kostak")
        updated = gmp_info.get("last_updated", "")
        source = gmp_info.get("source", "Market Quotes")
        top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])

        est_listing = ""
        gain_str = ""
        if top and top > 0:
            est_p = top + gmp_val
            pct = (gmp_val / top) * 100
            est_listing = f"Rs {fmt_price(est_p)}"
            gain_str = f"+{pct:.1f}% estimated gain"

        hist = gmp_info.get("history") or []
        trend = gmp_trend(gmp_info)

        trend_badge = ""
        if trend == "up":
            trend_badge = '<span class="badge badge-up">▲ Rising Sentiment</span>'
        elif trend == "down":
            trend_badge = '<span class="badge badge-down">▼ Softening</span>'
        else:
            trend_badge = '<span class="badge">━ Steady</span>'

        history_html = ""
        if len(hist) > 1:
            h_rows = "".join(
                f'<tr><td>{_esc(h.get("date"))}</td><td class="right font-semibold" style="color:var(--up)">+Rs {float(h.get("gmp", 0)):.1f}</td></tr>'
                for h in hist[-5:]
            )
            history_html = f"""
            <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px">
              <span class="xs muted font-semibold">Recent GMP Trend History:</span>
              <table class="data" style="margin-top:6px;max-width:320px;font-size:12px">
                <thead><tr><th>Date</th><th class="right">GMP</th></tr></thead>
                <tbody>{h_rows}</tbody>
              </table>
            </div>
            """

        outcome_block = ""
        if outcome:
            outcome_block = f'<div style="margin-top:12px;padding:10px 12px;background:rgba(0,82,254,0.06);border-radius:6px" class="small"><strong>Exchange Listing Day Result:</strong> {_esc(outcome)}</div>'

        kostak_block = f"<div class='card' style='padding:12px;background:var(--bg);border:1px solid var(--border)'><div class='xs muted'>Kostak Rate</div><div style='font-size:20px;font-weight:700;margin-top:4px'>Rs {kostak}</div><div class='xs faint'>Per application</div></div>" if kostak else ""

        return f"""
        <section class="card" style="margin-top:24px;padding:22px;background:var(--bg-raised)">
          <div class="row-between" style="align-items:center;margin-bottom:12px">
            <h2 style="margin:0;font-size:18px">Grey Market Premium (GMP) &amp; Sentiment</h2>
            <div style="display:flex;gap:6px;align-items:center">
              {trend_badge}
              <span class="badge" style="background:var(--bg);font-size:11px">Updated: {_esc(updated)}</span>
            </div>
          </div>
          
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px">
            <div class="card" style="padding:12px;background:var(--bg);border:1px solid var(--border)">
              <div class="xs muted">Current GMP Estimate</div>
              <div style="font-size:20px;font-weight:700;color:var(--up);margin-top:4px">+Rs {gmp_val:,.1f}</div>
              <div class="xs faint">Per equity share</div>
            </div>
            <div class="card" style="padding:12px;background:var(--bg);border:1px solid var(--border)">
              <div class="xs muted">Estimated Listing Price</div>
              <div style="font-size:20px;font-weight:700;color:var(--text);margin-top:4px">{est_listing or 'Awaited'}</div>
              <div class="xs" style="color:var(--up)">{gain_str or 'Based on upper band'}</div>
            </div>
            {kostak_block}
          </div>
          
          {history_html}
          {outcome_block}
          
          <div style="margin-top:16px;padding:12px;background:rgba(239,68,68,0.05);border-left:3px solid var(--accent);border-radius:4px" class="xs muted">
            <strong>Mandatory Safeguard Disclaimer:</strong> Grey Market Premium (GMP) is an unofficial, off-exchange indicative market observation with zero regulatory oversight. It is not an exchange-verified price, guaranteed listing return, or investment recommendation. BrokerLens does not publish unverified speculative tips. Always base bidding decisions on official SEBI offer documents, company financials, and verified exchange subscription numbers. Source: {_esc(source)}.
          </div>
        </section>
        """

    # Baseline fallback when no GMP observation is on file
    if outcome:
        tail = outcome
    elif status == "Listed":
        tail = ("The listing-day open for this issue is outside the exchange price history held here, "
                "so no listing outcome is shown rather than an estimate.")
    elif status == STATUS_NO_LISTING:
        tail = "No listing is on file for this issue, so there is no listing outcome to show."
    else:
        tail = "Once the issue lists, the issue price and the listing-day open from the exchange price history appear here."
    return (
        '<section class="card" style="margin-top:24px;padding:20px;background:var(--bg-raised)">'
        '<h2 style="margin:0 0 8px 0;font-size:18px">GMP and listing outcome</h2>'
        '<p class="small muted" style="margin:0 0 8px 0;max-width:72ch">Grey-market premium (GMP) is an unofficial, off-exchange '
        'figure with no regulatory oversight. BrokerLens does not publish it for %s or any other IPO without verified quote evidence.</p>'
        '<p class="small" style="margin:0;max-width:72ch">%s</p></section>' % (_esc(company), _esc(tail))
    )


# ---------------------------------------------------------------- FAQs

def build_faqs(r, pf, status, candle, perf, company, as_of_iso):
    """FAQ list that depends on status. A listed IPO never says it has not listed, and an issue with no
    listing on file never says a listing is awaited."""
    b_start, b_end = r.get("bidding_start") or "", r.get("bidding_end") or ""
    ld = reliable_listing_date(r)
    ld_state = listing_date_state(r)
    lot = lot_size_on_file(r)
    top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
    note = SEBI_BID_LIMITS["note"]
    faqs = []

    # 1. Lot size
    if lot:
        a = "The lot size on file for %s IPO is %d shares." % (company, lot)
        if top:
            a += " At the upper price of Rs %s, one lot costs Rs %s." % (fmt_price(top), fmt_price(lot * top))
        a += " Retail investors can bid up to %s in the retail category (%s)." % (SEBI_BID_LIMITS["retail"], note)
    else:
        a = ("BrokerLens has no sourced lot size for %s IPO, so none is shown. The lot size is printed in the issue prospectus "
             "and on your broker's bid screen. Retail investors can bid up to %s in the retail category (%s)." % (
                 company, SEBI_BID_LIMITS["retail"], note))
    faqs.append(("What is the lot size of %s IPO?" % company, a))

    # 2. Dates
    if status == "Listed":
        if _parse(b_start) and _parse(b_end):
            head = "%s IPO bidding ran from %s to %s" % (company, fmt_date(b_start), fmt_date(b_end))
        elif _parse(b_end):
            head = "%s IPO bidding closed on %s" % (company, fmt_date(b_end))
        else:
            head = "%s IPO bidding dates are not on file" % company
        if _parse(ld):
            a = "%s, and the shares listed on %s on %s." % (head, exchange_label(r), fmt_date(ld))
        else:
            a = ("%s, and the exchange feed records a listing on %s, but the listing date on file looks inconsistent with the "
                 "bidding dates, so none is shown. See the exchange for the listing date." % (head, exchange_label(r)))
    elif status == "Active":
        a = "%s IPO is open for bidding%s. The listing date is not on file yet." % (
            company, (" and closes on " + fmt_date(b_end)) if _parse(b_end) else "")
    elif status == "Forthcoming":
        a = "%s IPO opens%s%s. Dates are as announced by the issuer and can change." % (
            company, (" on " + fmt_date(b_start)) if _parse(b_start) else " on a date the issuer has yet to announce",
            (" and closes on " + fmt_date(b_end)) if _parse(b_end) else "")
    elif status == STATUS_NO_LISTING:
        a = "%s IPO bidding closed%s. %s" % (company, (" on " + fmt_date(b_end)) if _parse(b_end) else "", NO_LISTING_NOTE)
        fs = _flag_sentence(r)
        if fs:
            a += " " + fs
        if ld_state == "inconsistent":
            a += " The listing date on file looks inconsistent with the bidding dates, so none is shown."
    else:
        a = "%s IPO bidding closed%s." % (company, (" on " + fmt_date(b_end)) if _parse(b_end) else "")
        a += (" The listing date on file is %s." % fmt_date(ld)) if _parse(ld) else " The listing date is not on file yet."
    faqs.append(("What are the open, close and listing dates of %s IPO?" % company, a))

    # 3. Price
    if pf["band_low"] is not None:
        a = "The price band for %s IPO is Rs %s to Rs %s per share." % (company, fmt_price(pf["band_low"]), fmt_price(pf["band_high"]))
        if pf["issue_price"]:
            a += " The final issue price on file is Rs %s." % fmt_price(pf["issue_price"])
    elif pf["single"] is not None or pf["issue_price"]:
        a = "%s IPO is priced at Rs %s per share." % (company, fmt_price(pf["single"] if pf["single"] is not None else pf["issue_price"]))
    else:
        a = "No price band or issue price is on file for %s IPO." % company
    faqs.append(("What is the price band of %s IPO?" % company, a))

    # 4. Performance / status
    if status == "Listed":
        if perf.get("has_listing_data"):
            a = ("%s listed on the exchange with a listing-day open of Rs %s, which is %s of Rs %s. "
                 "This compares the open with the issue price; it is not a full-day or later return." % (
                     company, fmt_price(perf["listing_open"]),
                     open_vs_issue_phrase(perf["listing_open"], perf["issue_price"]), fmt_price(perf["issue_price"])))
        elif _parse(ld):
            a = ("%s listed on %s. The listing-day open is outside the exchange price history held here, so no listing-day gain is shown." % (
                company, fmt_date(ld)))
        else:
            a = ("%s is recorded as listed in the exchange feed, but the listing date on file looks inconsistent, so no listing-day "
                 "figure is shown." % company)
    elif status == "Active":
        a = "%s has not listed yet. Bidding is open, and listing prices will appear here after the exchange listing." % company
    elif status == "Forthcoming":
        a = "%s has not listed yet. The issue has not opened for bidding, so there is no listing price." % company
    elif status == STATUS_NO_LISTING:
        a = "BrokerLens has no listing on file for %s IPO, so no listing price is shown. " % company
        fs = _flag_sentence(r)
        if fs:
            a += fs + " "
        a += "Check the exchange for the current position of the issue."
    else:
        if _parse(ld):
            a = ("Bidding for %s IPO has closed. The listing date on file is %s, and the listing price will appear here after the exchange listing." % (company, fmt_date(ld)))
        else:
            a = "Bidding for %s IPO has closed and no listing is on file yet. The listing price will appear here after the exchange listing." % company
    faqs.append(("How did %s perform on its listing day?" % company if status == "Listed" else "Has %s IPO listed yet?" % company, a))

    # 5. GMP
    outcome = gmp_outcome_sentence(r, pf, status, candle, perf)
    gmp_info = get_ipo_gmp(r.get("symbol"))
    if gmp_info:
        top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
        gmp_val = float(gmp_info.get("gmp", 0.0))
        est_gain = f" (estimated listing gain of around {((gmp_val / top) * 100):.1f}% over the upper band)" if top else ""
        a = (f"The latest indicative Grey Market Premium (GMP) on file for {company} IPO is +Rs {gmp_val:,.1f} per share{est_gain}, "
             f"recorded on {gmp_info.get('last_updated')}. GMP is an unofficial, off-exchange observation and does not guarantee listing performance.")
        if outcome:
            a += " The verifiable outcome is this: " + outcome
    else:
        a = ("Grey-market premium (GMP) is an unofficial, off-exchange figure with no regulatory oversight, and BrokerLens does not publish it without verified quote evidence.")
        if outcome:
            a += " The verifiable outcome is this: " + outcome
        elif status == "Listed":
            a += " The listing-day open for this issue is outside the exchange price history held here, so no outcome figure is shown."
        elif status == STATUS_NO_LISTING:
            a += " No listing is on file for this issue, so there is no outcome figure to show."
        else:
            a += " After listing, the issue price and listing-day open from the exchange price history are shown on this page."
    faqs.append(("Does BrokerLens show the GMP of %s IPO?" % company, a))

    # 6. Advice
    faqs.append((
        "Is investing in %s IPO recommended by BrokerLens?" % company,
        "No. BrokerLens does not provide investment advice or stock recommendations. It publishes public-issue disclosures "
        "(price band, dates, subscription figures and listing facts) so investors can do their own research."))
    return faqs


# ---------------------------------------------------------------- apply-via pages

_APPLY_SYMBOLS = {}


def apply_page_symbols():
    """Lower-case symbols that get /ipo/<slug>/apply-via-<broker>/ pages (same selection as
    build_ipo_apply_suite). The main IPO page links to those pages only for these symbols;
    before, it linked all 1,265 IPOs but only 104 have the pages (about 1,160 dead links)."""
    if "s" in _APPLY_SYMBOLS:
        return _APPLY_SYMBOLS["s"]
    out = set()
    try:
        from pipeline.ipo_apply_engine import select_target_ipos
        with open(os.path.join(ROOT, "data", "_ingest.json"), encoding="utf-8") as fh:
            ipo_data = ((json.load(fh) or {}).get("nse") or {}).get("ipo") or {}
        out = {(x.get("symbol") or "").lower() for x in select_target_ipos(ipo_data, APPLY_PAGES_LIMIT)}
    except Exception:
        out = set()
    _APPLY_SYMBOLS["s"] = out
    return out


def has_apply_pages(slug):
    return str(slug).lower() in apply_page_symbols()
