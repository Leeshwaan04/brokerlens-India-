"""NSE adapters.

NSE gates its /api/ paths behind cookies issued by an HTML page load, which the
Fetcher handles. Archive files on nsearchives.nseindia.com are ungated.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone

from ..common import (
    Fetcher,
    log,
    nse,
    nse_archives,
    snapshot,
    strip_tags,
    to_num,
)
from ..identity import _whole_word_in

API = "https://www.nseindia.com/api"
ARCH = "https://nsearchives.nseindia.com"


def market_pulse(f: Fetcher, ttl=None):
    """Live-ish market context for the site header. Cheap, safe to poll."""
    out = {"exchange": "NSE", "status": None, "indices": [], "breadth": None}

    ms = f.get_json("%s/marketStatus" % API, ttl=60 if ttl is None else ttl)
    if ms:
        segs = []
        for s in ms.get("marketState", []) or []:
            segs.append(
                {
                    "market": s.get("market"),
                    "status": s.get("marketStatus"),
                    "index": s.get("index"),
                    "last": to_num(s.get("last")),
                    "change": to_num(s.get("variation")),
                    "change_pct": to_num(s.get("percentChange")),
                    "trade_date": s.get("tradeDate"),
                }
            )
        out["status"] = segs

    ai = f.get_json("%s/allIndices" % API, ttl=120 if ttl is None else ttl)
    if ai:
        want = {
            "NIFTY 50", "NIFTY NEXT 50", "NIFTY BANK", "NIFTY FIN SERVICE",
            "NIFTY MIDCAP 100", "NIFTY SMLCAP 100", "INDIA VIX",
            "NIFTY IT", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY FMCG",
            "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY", "NIFTY PSU BANK",
            "NIFTY 100", "NIFTY 500",
        }
        adv = dec = unc = 0
        for idx in ai.get("data", []) or []:
            name = (idx.get("index") or "").upper()
            adv += to_num(idx.get("advances")) or 0
            dec += to_num(idx.get("declines")) or 0
            unc += to_num(idx.get("unchanged")) or 0
            if name in want:
                out["indices"].append(
                    {
                        "name": idx.get("index"),
                        "last": to_num(idx.get("last")),
                        "change": to_num(idx.get("variation")),
                        "change_pct": to_num(idx.get("percentChange")),
                        "open": to_num(idx.get("open")),
                        "high": to_num(idx.get("high")),
                        "low": to_num(idx.get("low")),
                        "year_high": to_num(idx.get("yearHigh")),
                        "year_low": to_num(idx.get("yearLow")),
                    }
                )
        # NIFTY 50 first, then by name, so the header order is stable
        out["indices"].sort(key=lambda i: (i["name"] != "NIFTY 50", i["name"] or ""))
        if adv or dec:
            out["breadth"] = {"advances": adv, "declines": dec, "unchanged": unc}

    snapshot("nse_market_pulse", out)
    return out


LIVE_REFERER = {"Referer": "https://www.nseindia.com/market-data/live-equity-market"}
VAR_REFERER = {"Referer": "https://www.nseindia.com/market-data/top-gainers-losers"}


def _variation(f: Fetcher, index, ttl=45, limit=15):
    """Top gainers / losers.

    NSE spells the losers parameter "loosers" - `?index=losers` returns an empty
    52-byte stub, which is easy to mistake for "no movers today".
    """
    data = f.get_json("%s/live-analysis-variations?index=%s" % (API, index),
                      ttl=ttl, headers=VAR_REFERER)
    if not isinstance(data, dict):
        return []
    grp = data.get("NIFTY") or data.get("allSec") or data.get("SecGtr20") or {}
    out = []
    for r in (grp.get("data") or [])[:limit]:
        ltp, prev = to_num(r.get("ltp")), to_num(r.get("prev_price"))
        out.append({
            "symbol": r.get("symbol"),
            "last": ltp,
            "change_pct": to_num(r.get("perChange")),
            "change": (ltp - prev) if ltp is not None and prev is not None else None,
            "volume": to_num(r.get("trade_quantity")),
        })
    return [q for q in out if q["symbol"] and q["last"] is not None]


def most_active(f: Fetcher, by="volume", ttl=45):
    data = f.get_json("%s/live-analysis-most-active-securities?index=%s" % (API, by),
                      ttl=ttl, headers=LIVE_REFERER)
    out, stamp = [], None
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        stamp = data.get("timestamp")
        for r in data["data"]:
            if not r.get("symbol"):
                continue
            out.append({
                "symbol": r.get("symbol"),
                "last": to_num(r.get("lastPrice")),
                "change": to_num(r.get("change")),
                "change_pct": to_num(r.get("pChange")),
                "volume": to_num(r.get("totalTradedVolume")),
                "high": to_num(r.get("dayHigh")),
                "low": to_num(r.get("dayLow")),
            })
    return out, stamp


def live_quotes(f: Fetcher, ttl=45, want_active=True, want_gainers=True, want_losers=False):
    """Live equity quotes for the ticker.

    /api/equity-stockIndices 404s and /api/quote-equity 403s even with full
    browser client hints, but the live-analysis endpoints answer with a warmed
    session and carry exactly what a ticker needs.

    The selector flags exist so the stream poller can hit one endpoint per tick
    at its own cadence instead of refetching everything.
    """
    out = {"exchange": "NSE", "quotes": [], "gainers": [], "losers": [],
           "timestamp": None, "note": None}

    if want_active:
        out["quotes"], out["timestamp"] = most_active(f, "volume", ttl=ttl)
    if want_gainers:
        out["gainers"] = _variation(f, "gainers", ttl=ttl)
    if want_losers:
        out["losers"] = _variation(f, "loosers", ttl=ttl)

    if want_active and not out["quotes"]:
        out["note"] = "NSE live-analysis endpoints returned nothing on this run."
    log("nse live: %d active, %d gainers, %d losers"
        % (len(out["quotes"]), len(out["gainers"]), len(out["losers"])),
        "ok" if (out["quotes"] or out["gainers"] or out["losers"]) else "warn")
    return out


def fii_dii(f: Fetcher):
    """Daily institutional flows - the macro context strip."""
    data = f.get_json("%s/fiidiiTradeReact" % API, ttl=3600)
    if not data:
        return None
    rows = []
    for r in data if isinstance(data, list) else []:
        rows.append(
            {
                "category": r.get("category"),
                "date": r.get("date"),
                "buy": to_num(r.get("buyValue")),
                "sell": to_num(r.get("sellValue")),
                "net": to_num(r.get("netValue")),
            }
        )
    snapshot("nse_fii_dii", rows)
    return rows


def _ipo_date(raw):
    """NSE spells IPO dates as '11-Sep-2026' on one endpoint and
    '08-SEP-2026' on another - never intraday, so a bare ISO date is enough."""
    if not raw or raw == "-":
        return None
    try:
        return datetime.strptime(raw.strip().title(), "%d-%b-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _ipo_sci_num(raw):
    """noOfSharesOffered/noOfsharesBid come as scientific-notation strings
    ('2.1386919E7') - to_num()'s regex strips non-digit characters including
    the 'E', which silently corrupts 21,386,919 down to 2.1386919. A plain
    float() parse handles exponent notation correctly; to_num() is shared
    across the whole pipeline and every other caller's inputs are plain
    decimal strings, so fixing this here rather than there."""
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def ipo_current(f: Fetcher, ttl=None):
    """Currently-open mainboard/SME IPOs, with real, exchange-published
    subscription data (times subscribed by category) - the factual
    alternative to grey-market-premium speculation, which BrokerLens does
    not publish (see docs/ROADMAP.md: no tips, no advice)."""
    data = f.get_json("%s/ipo-current-issue" % API, ttl=300 if ttl is None else ttl)
    rows = []
    for r in data if isinstance(data, list) else []:
        symbol = (r.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        rows.append({
            "symbol": symbol,
            "company": r.get("companyName"),
            "price_band": r.get("issuePrice"),
            "issue_size_shares": to_num(r.get("issueSize")),
            "bidding_start": _ipo_date(r.get("issueStartDate")),
            "bidding_end": _ipo_date(r.get("issueEndDate")),
            "category": r.get("category"),
            "shares_offered": _ipo_sci_num(r.get("noOfSharesOffered")),
            "shares_bid": _ipo_sci_num(r.get("noOfsharesBid")),
            "times_subscribed": to_num(r.get("noOfTime")),
        })
    return rows


def ipo_upcoming(f: Fetcher, ttl=None):
    """Active + forthcoming IPOs (NSE's own 'status' field distinguishes
    them) - forthcoming ones have a price band and dates but no bidding
    activity yet, so no subscription figures exist for them at all."""
    data = f.get_json("%s/all-upcoming-issues?category=ipo" % API, ttl=1800 if ttl is None else ttl)
    rows = []
    for r in data if isinstance(data, list) else []:
        symbol = (r.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        rows.append({
            "symbol": symbol,
            "company": r.get("companyName"),
            "price_band": r.get("issuePrice"),
            "issue_size_shares": to_num(r.get("issueSize")),
            "bidding_start": _ipo_date(r.get("issueStartDate")),
            "bidding_end": _ipo_date(r.get("issueEndDate")),
            "status": r.get("status"),
        })
    return rows


def ipo_past(f: Fetcher, ttl=None):
    """Recently closed / already-listed IPOs - final issue price and
    listing date, once NSE has them. A blank issuePrice/listingDate ('-')
    means NSE hasn't published that fact yet, not that it's zero."""
    data = f.get_json("%s/public-past-issues" % API, ttl=3600 if ttl is None else ttl)
    rows = []
    for r in data if isinstance(data, list) else []:
        symbol = (r.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        # NSE's own securityType:"SME" here covers both genuine SME equity
        # IPOs and SME-platform debt/NCD instruments, with no field that
        # tells them apart - confirmed live: exactly the digit-leading
        # symbols (a real NSE convention - no genuine equity ticker starts
        # with a digit; debt/NCD symbols encode coupon rate there, e.g.
        # "10MWL29") have an issuePrice many times the top of their own
        # priceRange, which cannot happen for genuine equity (the final
        # price must fall within the disclosed band). 5 of 767 "SME" rows
        # on the day this was checked, all matching this pattern.
        if symbol[0].isdigit():
            continue
        issue_price = to_num(r.get("issuePrice")) if r.get("issuePrice") not in (None, "-") else None
        rows.append({
            "symbol": symbol,
            "company": r.get("company") or r.get("companyName"),
            "price_band": r.get("priceRange"),
            "issue_price": issue_price,
            "security_type": r.get("securityType"),
            "bidding_start": _ipo_date(r.get("ipoStartDate")),
            "bidding_end": _ipo_date(r.get("ipoEndDate")),
            "listing_date": _ipo_date(r.get("listingDate")),
        })
    return rows


def equity_universe(fa: Fetcher):
    """The full NSE-listed equity master list, not just a count.

    EQUITY_L.csv is NSE's own published list of every listed equity symbol -
    already fetched on every run, previously discarded down to a bare count.
    Column names carry a leading space in the source file (NSE's own quirk,
    not a parsing bug here), so lookups below normalise on strip().upper().
    """
    text = fa.get_text("%s/content/equities/EQUITY_L.csv" % ARCH, ttl=86400)
    if not text:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    cols = {}
    for k in (rows[0].keys() if rows else []):
        cols[k.strip().upper()] = k

    def field(row, name):
        k = cols.get(name)
        return (row.get(k) or "").strip() if k else ""

    companies = []
    for r in rows:
        symbol = field(r, "SYMBOL")
        if not symbol:
            continue
        companies.append({
            "symbol": symbol,
            "name": field(r, "NAME OF COMPANY"),
            "series": field(r, "SERIES"),
            "listing_date": field(r, "DATE OF LISTING"),
            "isin": field(r, "ISIN NUMBER"),
            "face_value": field(r, "FACE VALUE"),
            "market_lot": field(r, "MARKET LOT"),
        })
    out = {
        "symbol_count": len(rows),
        "company_names": [c["name"] for c in companies],
        "companies": companies,
    }
    snapshot("nse_equity_universe", {"symbol_count": len(rows)})
    return out


# NSE's own published index-constituent files, confirmed live one by one
# against nsearchives.nseindia.com/content/indices/ before being added here -
# every filename in this dict was checked to return real, non-empty rows.
# Broad-market and sectoral indices only; thematic/strategy indices (momentum,
# quality, low-volatility, etc.) are deliberately left out for now since they
# rebalance more often and would need a shorter re-fetch interval to stay
# accurate rather than the same daily cache as the rest of this file.
INDEX_FILES = {
    "nifty-50": ("ind_nifty50list", "Nifty 50"),
    "nifty-next-50": ("ind_niftynext50list", "Nifty Next 50"),
    "nifty-100": ("ind_nifty100list", "Nifty 100"),
    "nifty-200": ("ind_nifty200list", "Nifty 200"),
    "nifty-500": ("ind_nifty500list", "Nifty 500"),
    "nifty-bank": ("ind_niftybanklist", "Nifty Bank"),
    "nifty-auto": ("ind_niftyautolist", "Nifty Auto"),
    "nifty-it": ("ind_niftyitlist", "Nifty IT"),
    "nifty-pharma": ("ind_niftypharmalist", "Nifty Pharma"),
    "nifty-fmcg": ("ind_niftyfmcglist", "Nifty FMCG"),
    "nifty-metal": ("ind_niftymetallist", "Nifty Metal"),
    "nifty-realty": ("ind_niftyrealtylist", "Nifty Realty"),
    "nifty-energy": ("ind_niftyenergylist", "Nifty Energy"),
    "nifty-psu-bank": ("ind_niftypsubanklist", "Nifty PSU Bank"),
    "nifty-midcap-50": ("ind_niftymidcap50list", "Nifty Midcap 50"),
    "nifty-midcap-100": ("ind_niftymidcap100list", "Nifty Midcap 100"),
    "nifty-smallcap-100": ("ind_niftysmallcap100list", "Nifty Smallcap 100"),
    "nifty-media": ("ind_niftymedialist", "Nifty Media"),
    "nifty-consumer-durables": ("ind_niftyconsumerdurableslist", "Nifty Consumer Durables"),
    "nifty-healthcare": ("ind_niftyhealthcarelist", "Nifty Healthcare"),
    "nifty-oil-gas": ("ind_niftyoilgaslist", "Nifty Oil & Gas"),
    "nifty-commodities": ("ind_niftycommoditieslist", "Nifty Commodities"),
    "nifty-cpse": ("ind_niftycpselist", "Nifty CPSE"),
    "nifty-infrastructure": ("ind_niftyinfralist", "Nifty Infrastructure"),
    "nifty-consumption": ("ind_niftyconsumptionlist", "Nifty Consumption"),
}


def index_universe(fa: Fetcher):
    """Constituent lists for NSE's own published indices.

    Same primary-source tier and same archive host as EQUITY_L.csv - these
    files are NSE's own index-methodology documents, published for exactly
    this purpose (who is currently in Nifty 50, Nifty Bank, etc).
    """
    out = {}
    for slug, (filename, label) in INDEX_FILES.items():
        text = fa.get_text("%s/content/indices/%s.csv" % (ARCH, filename), ttl=86400)
        if not text:
            continue
        rows = list(csv.DictReader(io.StringIO(text)))
        cols = {}
        for k in (rows[0].keys() if rows else []):
            cols[k.strip().upper()] = k

        def field(row, name):
            k = cols.get(name)
            return (row.get(k) or "").strip() if k else ""

        constituents = []
        for r in rows:
            symbol = field(r, "SYMBOL")
            if not symbol:
                continue
            constituents.append({
                "symbol": symbol,
                "name": field(r, "COMPANY NAME"),
                "industry": field(r, "INDUSTRY"),
                "isin": field(r, "ISIN CODE"),
            })
        if constituents:
            out[slug] = {"label": label, "constituents": constituents}

    log("nse indices: %d of %d index constituent lists fetched" % (len(out), len(INDEX_FILES)),
        "ok" if out else "warn")
    snapshot("nse_index_universe", {k: len(v["constituents"]) for k, v in out.items()})
    return out


def etf_universe(fa: Fetcher):
    """NSE's own list of listed ETFs - a separate instrument universe from
    EQUITY_L.csv (confirmed: zero symbol overlap), same archive host and
    trust tier."""
    text = fa.get_text("%s/content/equities/eq_etfseclist.csv" % ARCH, ttl=86400)
    if not text:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    cols = {}
    for k in (rows[0].keys() if rows else []):
        cols[k.strip().upper()] = k

    def field(row, name):
        k = cols.get(name)
        return (row.get(k) or "").strip() if k else ""

    etfs = []
    for r in rows:
        symbol = field(r, "SYMBOL")
        if not symbol:
            continue
        etfs.append({
            "symbol": symbol,
            "name": field(r, "SECURITYNAME"),
            "underlying_asset": field(r, "UNDERLYING ASSET"),
            "underlying_key": field(r, "UNDERLYING KEY"),
            "category": field(r, "ETF UNDERLYING"),
            "listing_date": field(r, "DATEOFLISTING"),
            "isin": field(r, "ISINNUMBER"),
            "face_value": field(r, "FACEVALUE"),
            "market_lot": field(r, "MARKETLOT"),
        })
    log("nse etfs: %d listed ETFs fetched" % len(etfs), "ok" if etfs else "warn")
    snapshot("nse_etf_universe", {"count": len(etfs)})
    return etfs


# A circular only counts against a broker if its language is actually
# disciplinary. Without this, routine product and operational notices were
# published as regulatory flags: a "Motilal Oswal BSE Midcap 150 Momentum 30
# Index Fund NFO" listing notice was the site's only regulatory flag, and it
# cost that firm 8 points of reliability score.
_ADVERSE_TERMS = (
    "penalt", "suspend", "suspens", "expel", "expuls", "disciplinary",
    "non-compliance", "noncompliance", "non compliance", "violation",
    "defaulter", "debarred", "debar", "censure", "withdrawal of", "terminat",
    "disablement", "disabled", "show cause", "adjudicat", "enquiry", "inquiry",
    "fine imposed", "action against",
)

# Notices that name a member for ordinary business reasons. Checked first, so a
# product listing is never read as an enforcement action.
_BENIGN_TERMS = (
    "nfo", "new fund offer", "mutual fund", "index fund", "etf", "listing of",
    "availability of", "empanel", "mock", "holiday", "trading holiday",
    "webinar", "certification", "launch of", "introduction of",
)


def _circular_is_adverse(blob):
    if any(t in blob for t in _BENIGN_TERMS):
        return False
    return any(t in blob for t in _ADVERSE_TERMS)


def member_circulars(f: Fetcher, broker_aliases):
    """Scan NSE's circular feed for DISCIPLINARY member-name mentions.

    Two guards, both learned from a live false positive:
      1. the alias must match on whole-word boundaries, not as a substring, so
         ordinary words like "choice" or "ventura" cannot flag a firm;
      2. the circular's language must be disciplinary, so routine product and
         operational notices are not published as regulatory flags.

    Anything that names a member benignly is recorded separately as a mention,
    never as a flag.
    """
    data = f.get_json("%s/circulars" % API, ttl=6 * 3600)
    if not data:
        return {}

    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}

    hits, skipped = {}, 0
    for c in items:
        # field names per the live payload: sub, circCategory, circCompany,
        # circDepartment, circDisplayNo, circFilelink
        blob = " ".join(
            str(c.get(k) or "")
            for k in ("sub", "circCompany", "circCategory", "circDepartment", "circDisplayNo")
        ).lower()
        if not blob.strip():
            continue
        adverse = _circular_is_adverse(blob)
        for bid, aliases in broker_aliases.items():
            matched = any(len(a) >= 6 and _whole_word_in(a, blob) for a in aliases)
            if not matched:
                continue
            if not adverse:
                skipped += 1
                break
            hits.setdefault(bid, []).append(
                {
                    "date": c.get("cirDisplayDate") or c.get("cirDate"),
                    "subject": strip_tags(c.get("sub"))[:220],
                    "category": c.get("circCategory"),
                    "department": c.get("circDepartment"),
                    "ref": c.get("circDisplayNo"),
                    "url": c.get("circFilelink"),
                }
            )
            break
    for bid in hits:
        hits[bid] = hits[bid][:10]
    snapshot("nse_member_circulars", hits)
    log("nse circulars: %d brokers with disciplinary mentions across %d circulars "
        "(%d benign name-mentions ignored)" % (len(hits), len(items), skipped))
    return hits


def cm_turnover(fa: Fetcher, days_back=7):
    """Market-wide CM turnover for the last N trading days, from bhavcopy."""
    series = []
    day = datetime.now(timezone.utc).date()
    tried = 0
    while len(series) < days_back and tried < days_back * 3:
        tried += 1
        day = day - timedelta(days=1)
        if day.weekday() >= 5:
            continue
        stamp = day.strftime("%Y%m%d")
        url = "%s/content/cm/BhavCopy_NSE_CM_0_0_0_%s_F_0000.csv.zip" % (ARCH, stamp)
        text = fa.get_zip_member(url, ttl=7 * 86400, retries=1)
        if not text:
            continue
        turnover = 0.0
        trades = 0
        rows = 0
        for r in csv.DictReader(io.StringIO(text)):
            rows += 1
            turnover += to_num(r.get("TtlTrfVal")) or 0
            trades += to_num(r.get("TtlNbOfTxsExctd")) or 0
        series.append(
            {
                "date": day.isoformat(),
                "turnover_inr": turnover,
                "trades": trades,
                "instruments": rows,
            }
        )
    series.sort(key=lambda r: r["date"])
    if series:
        snapshot("nse_cm_turnover", series)
    return series


def collect(broker_aliases):
    f = nse()
    fa = nse_archives()
    out = {
        "pulse": market_pulse(f),
        "live": live_quotes(f),
        "fii_dii": fii_dii(f),
        "universe": equity_universe(fa),
        "indices": index_universe(fa),
        "etfs": etf_universe(fa),
        "circulars": member_circulars(f, broker_aliases),
        "turnover": cm_turnover(fa),
        "ipo": {
            "current": ipo_current(f),
            "upcoming": ipo_upcoming(f),
            "past": ipo_past(f),
        },
    }
    return out
