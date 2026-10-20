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

Zero em dashes or en dashes anywhere in user-visible copy.
"""
from __future__ import annotations

import html
import json
import os
import re
import zlib
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BRAND = "BrokerLens"
# Titles are built from parts that are dropped from the right when the key part
# (everything before " | BrokerLens") would run past this many characters. Search
# results cut off around 60 characters on desktop, so the order of the parts puts
# the name, price band and dates first.
MAX_KEY_CHARS = 100
# Same value as build_ipo_apply_suite(limit_recent_ipos=...) in pipeline/publish.py.
APPLY_PAGES_LIMIT = 100


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


# ---------------------------------------------------------------- status

def ipo_status(r, today_iso):
    """Listed, Active, Forthcoming or Closed, from dates on file.

    A listing date that is still in the future does not make an IPO Listed (the stored
    status flag would say so). Listed is the only status that may say an IPO has listed."""
    ld = r.get("listing_date") or ""
    if ld and ld <= today_iso:
        return "Listed"
    b_start, b_end = r.get("bidding_start") or "", r.get("bidding_end") or ""
    if b_start and b_end and b_start <= today_iso <= b_end:
        return "Active"
    if b_start and b_start > today_iso:
        return "Forthcoming"
    if b_end and b_end < today_iso:
        return "Closed"
    st = r.get("status")
    if st in ("Active", "Forthcoming", "Closed"):
        return st
    if st == "Listed" and not ld:
        return "Listed"
    return "Closed"


def is_listed(r, today_iso=None):
    return ipo_status(r, today_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")) == "Listed"


def exchange_label(r):
    return "NSE Emerge" if r.get("security_type") == "SME" else "NSE"


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
        d = today_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _AS_OF_CACHE["d"] = d
    return d


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


def build_title(r, pf, status, group=None):
    """Title for the A/B test. Parts that are not on file are omitted."""
    slug = (r.get("symbol") or "").lower()
    group = group or title_group(slug)
    name = _short_name(r.get("company"), r.get("symbol"))
    if group == "B":
        lot = lot_size_on_file(r) is not None
        what = "IPO Date, Price Band, Lot Size and Listing Date" if lot else "IPO Date, Price Band and Listing Date"
        return "%s %s | %s" % (name, what, BRAND)

    b_start, b_end, ld = r.get("bidding_start") or "", r.get("bidding_end") or "", r.get("listing_date") or ""
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
    return "%s | %s" % (key(parts), BRAND)


def build_description(r, pf, status, candle=None, has_latest_close=False):
    """Meta description from fields on file. The latest-close figure is never included."""
    name = _short_name(r.get("company"), r.get("symbol"))
    b_start, b_end, ld = r.get("bidding_start") or "", r.get("bidding_end") or "", r.get("listing_date") or ""
    ex = exchange_label(r)
    s = []
    if status == "Listed":
        bits = []
        if _parse(b_start):
            bits.append("opened " + fmt_date(b_start))
        if _parse(b_end):
            bits.append("closed " + fmt_date(b_end))
        lead = "%s IPO %s" % (name, " and ".join(bits)) if bits else "%s IPO" % name
        s.append("%s, listed %s on %s." % (lead, fmt_date(ld), ex) if _parse(ld) else "%s." % lead)
    elif status == "Active":
        s.append("%s IPO is open for bidding%s." % (name, (" until " + fmt_date(b_end)) if _parse(b_end) else ""))
    elif status == "Forthcoming":
        if _parse(b_start) and _parse(b_end):
            s.append("%s IPO opens %s and closes %s." % (name, fmt_date(b_start), fmt_date(b_end)))
        elif _parse(b_start):
            s.append("%s IPO opens %s." % (name, fmt_date(b_start)))
        else:
            s.append("%s IPO dates as announced by the issuer." % name)
    else:
        bits = []
        if _parse(b_start):
            bits.append("opened " + fmt_date(b_start))
        if _parse(b_end):
            bits.append("closed " + fmt_date(b_end))
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

    add("Status", _esc("Open for bidding" if status == "Active" else ("Upcoming" if status == "Forthcoming" else status)))
    if pf["band_low"] is not None:
        add("Price band", _esc("Rs %s to Rs %s" % (fmt_price(pf["band_low"]), fmt_price(pf["band_high"]))))
        add("Issue price", _esc("Rs " + fmt_price(pf["issue_price"])) if pf["issue_price"] else "")
    else:
        one = pf["single"] if pf["single"] is not None else pf["issue_price"]
        add("Issue price (fixed)" if pf["single"] is not None else "Issue price", _esc("Rs " + fmt_price(one)) if one else "")
    add("Bidding opens", _esc(fmt_date(r.get("bidding_start"))))
    add("Bidding closes", _esc(fmt_date(r.get("bidding_end"))))
    ld = r.get("listing_date") or ""
    add("Listing date" if status == "Listed" else "Listing date (as announced)", _esc(fmt_date(ld)))
    add("Exchange", _esc(exchange_label(r)))
    add("Issue type", _esc("SME Emerge" if r.get("security_type") == "SME" else ("Mainboard equity" if r.get("security_type") == "EQ" else "")))
    lot = lot_size_on_file(r)
    add("Lot size", _esc("%d shares" % lot) if lot else "")
    add("Issue size", _esc(issue_size_text(r, pf)))
    sub = r.get("times_subscribed")
    try:
        sub_f = float(sub) if sub is not None else None
    except (TypeError, ValueError):
        sub_f = None
    if sub_f is not None and status in ("Active", "Closed"):
        add("Overall subscription", _esc("%.2f times (as of the data date below)" % sub_f))
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

def gmp_outcome_sentence(r, pf, status, candle, perf):
    """The verifiable outcome, or '' when it is not on file."""
    if status != "Listed":
        return ""
    ip = pf["issue_price"]
    if candle and ip:
        pct = (candle["open"] - ip) / ip * 100.0
        return "Issue price Rs %s, listed open Rs %s (%+.1f%% against the issue price, listing day %s)." % (
            fmt_price(ip), fmt_price(candle["open"]), pct, fmt_date(candle["date"]))
    return ""


def render_gmp_section(r, pf, status, candle, perf, company):
    outcome = gmp_outcome_sentence(r, pf, status, candle, perf)
    if outcome:
        tail = outcome
    elif status == "Listed":
        tail = ("The listing-day open for this issue is outside the exchange price history held here, "
                "so no listing outcome is shown rather than an estimate.")
    else:
        tail = "Once the issue lists, the issue price and the listing-day open from the exchange price history appear here."
    return (
        '<section class="card" style="margin-top:24px;padding:20px;background:var(--bg-raised)">'
        '<h2 style="margin:0 0 8px 0;font-size:18px">GMP and listing outcome</h2>'
        '<p class="small muted" style="margin:0 0 8px 0;max-width:72ch">Grey-market premium (GMP) is an unofficial, off-exchange '
        'figure with no regulatory oversight. BrokerLens does not publish it for %s or any other IPO.</p>'
        '<p class="small" style="margin:0;max-width:72ch">%s</p></section>' % (_esc(company), _esc(tail))
    )


# ---------------------------------------------------------------- FAQs

def build_faqs(r, pf, status, candle, perf, company, as_of_iso):
    """FAQ list that depends on status. A listed IPO never says it has not listed."""
    b_start, b_end, ld = r.get("bidding_start") or "", r.get("bidding_end") or "", r.get("listing_date") or ""
    lot = lot_size_on_file(r)
    top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
    faqs = []

    # 1. Lot size
    if lot:
        a = "The lot size on file for %s IPO is %d shares." % (company, lot)
        if top:
            a += " At the upper price of Rs %s, one lot costs Rs %s." % (fmt_price(top), fmt_price(lot * top))
        a += " Retail investors can bid up to Rs 2 lakh in the retail category."
    else:
        a = ("BrokerLens has no sourced lot size for %s IPO, so none is shown. The lot size is printed in the issue prospectus "
             "and on your broker's bid screen. Retail investors can bid up to Rs 2 lakh in the retail category under SEBI rules." % company)
    faqs.append(("What is the lot size of %s IPO?" % company, a))

    # 2. Dates
    if status == "Listed":
        bits = []
        if _parse(b_start) and _parse(b_end):
            bits.append("%s IPO bidding ran from %s to %s" % (company, fmt_date(b_start), fmt_date(b_end)))
        elif _parse(b_end):
            bits.append("%s IPO bidding closed on %s" % (company, fmt_date(b_end)))
        else:
            bits.append("%s IPO bidding dates are not on file" % company)
        a = "%s, and the shares listed on %s on %s." % (bits[0], exchange_label(r), fmt_date(ld))
    elif status == "Active":
        a = "%s IPO is open for bidding%s. The listing date is not on file yet." % (
            company, (" and closes on " + fmt_date(b_end)) if _parse(b_end) else "")
    elif status == "Forthcoming":
        a = "%s IPO opens%s%s. Dates are as announced by the issuer and can change." % (
            company, (" on " + fmt_date(b_start)) if _parse(b_start) else " on a date the issuer has yet to announce",
            (" and closes on " + fmt_date(b_end)) if _parse(b_end) else "")
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
            a = ("%s listed on the exchange at an opening price of Rs %s, a listing day gain of %+.1f%% over its issue price of Rs %s." % (
                company, fmt_price(perf["listing_open"]), perf["listing_gain_pct"], fmt_price(perf["issue_price"])))
        else:
            a = ("%s listed on %s. The listing-day open is outside the exchange price history held here, so no listing-day gain is shown." % (
                company, fmt_date(ld)))
    elif status == "Active":
        a = "%s has not listed yet. Bidding is open, and listing prices will appear here after the exchange listing." % company
    elif status == "Forthcoming":
        a = "%s has not listed yet. The issue has not opened for bidding, so there is no listing price." % company
    else:
        if _parse(ld):
            a = ("Bidding for %s IPO has closed. The listing date on file is %s, and the listing price will appear here after the exchange listing." % (company, fmt_date(ld)))
        else:
            a = "Bidding for %s IPO has closed and no listing is on file yet. The listing price will appear here after the exchange listing." % company
    faqs.append(("How did %s perform on its listing day?" % company if status == "Listed" else "Has %s IPO listed yet?" % company, a))

    # 5. GMP
    outcome = gmp_outcome_sentence(r, pf, status, candle, perf)
    a = ("No. Grey-market premium (GMP) is an unofficial, off-exchange figure with no regulatory oversight, and BrokerLens does not publish it.")
    if outcome:
        a += " The verifiable outcome is this: " + outcome
    elif status == "Listed":
        a += " The listing-day open for this issue is outside the exchange price history held here, so no outcome figure is shown."
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
