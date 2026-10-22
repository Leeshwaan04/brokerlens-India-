"""IPO Lot Size, Listing Performance & Subscription Analytics Engine.

Provides NSE-sourced IPO analysis:
  - SEBI application categories; a lot size is shown only when it is sourced (never estimated).
  - Post-listing returns: Issue Price vs Listing Day Open vs Current Market Price (CMP), where the
    exchange price history on file covers them.
  - Listing-day open versus issue price (% and Rs) + total return since the issue.
  - Overall subscription multiple as a dated snapshot (no category split is on file, none is estimated).
  - Registrar details with direct online allotment checking links.
  - Zero external npm/pip dependencies; stdlib Python.
  - Zero em dashes or en dashes anywhere.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
from datetime import datetime, timezone, timedelta

try:
    from . import ipo_facts
except ImportError:  # run as a script
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from pipeline import ipo_facts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _slugify(text):
    text = (text or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _long_date(d_str):
    if not d_str or not isinstance(d_str, str):
        return ""
    try:
        parts = d_str.strip().split("-")
        if len(parts) == 3:
            dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            return dt.strftime("%d %b %Y")
    except Exception:
        pass
    return str(d_str)


def _add_working_days(iso, n):
    """Date n weekdays after iso (Mon-Fri only). Exchange holidays are not known
    here, so callers label the result indicative ("expected on or around")."""
    return ipo_facts.add_working_days(iso, n)


def _stage_banner(status, r, today_iso, as_of_iso=None):
    """A one-glance status line with the dates that matter at this stage. The
    T+3 listing date is SEBI's rule (listing within three working days of the
    issue closing), shown as expected on or around that date, never as a fact, and only
    while the issue is still inside that window. An issue with no listing on file never
    shows the timeline or says a listing is awaited."""
    b_start, b_end = r.get("bidding_start") or "", r.get("bidding_end") or ""
    listing = ipo_facts.reliable_listing_date(r)
    ld_state = ipo_facts.listing_date_state(r)
    steps = ""
    if status == "Listed":
        if listing:
            head, tone = "Listed on %s" % _long_date(listing), "var(--green)"
            detail = "Listing-day and current figures below are from NSE's own candles, shown only where the price history on file covers them."
        else:
            head, tone = "Listed, per the exchange feed", "var(--green)"
            detail = ipo_facts.LISTING_INCONSISTENT + "."
    elif status == "Active":
        head, tone = "Bidding is open" + ((", closes %s" % _long_date(b_end)) if b_end else ""), "var(--accent)"
        detail = "Basis of allotment, refunds and listing follow after the issue closes."
    elif status == "Forthcoming":
        head, tone = "Opens %s" % _long_date(b_start) if b_start else "Announced, dates to follow", "var(--text)"
        detail = "Dates and price band are as announced by the issuer and can change."
    elif status == ipo_facts.STATUS_NO_LISTING:
        flag = ipo_facts.name_flag(r)
        if flag:
            head = "Marked %s in the exchange feed" % ("as a withdrawal window" if flag == "withdrawal window" else flag)
        else:
            head = "Bidding closed" + ((" on %s" % _long_date(b_end)) if b_end else "")
        tone = "var(--text)"
        detail = ipo_facts.NO_LISTING_NOTE
        if ld_state == "inconsistent":
            detail += " " + ipo_facts.LISTING_INCONSISTENT + "."
    else:
        head, tone = "Bidding closed" + ((" on %s" % _long_date(b_end)) if b_end else ""), "var(--text)"
        detail = "Awaiting basis of allotment and listing."
    if b_end and status in ("Active", "Forthcoming", "Closed"):
        t1, t2, t3 = (_add_working_days(b_end, k) for k in (1, 2, 3))
        if t1 and t2 and t3:
            steps = (
                '<div class="xs faint" style="margin-top:6px">SEBI listing timeline (issue close + 3 working days), expected on or '
                'around: basis of allotment %s, refunds and demat credit %s, listing %s. The exchange notice is the final word.</div>'
                % (_long_date(t1), _long_date(t2), _long_date(t3)))
    return (
        '<div class="card" style="padding:14px;margin:0 0 16px 0;border-left:3px solid %s">'
        '<div style="font-weight:700">%s</div><div class="small muted" style="margin-top:2px">%s</div>%s'
        '<div class="xs faint" style="margin-top:6px">Page data as of %s.</div></div>'
        % (tone, _esc(head), _esc(detail), steps, ipo_facts.fmt_date(as_of_iso or today_iso))
    )


def parse_price_band(band_str, issue_price=None):
    """(low, high, cut_off) from the stored band; kept for callers outside this module.

    Reads through ipo_facts.price_facts, so a stored issue price no longer replaces both
    ends of the band (that made /ipo/kfintech/ say 366 where the band is 347 to 366).
    0.0 stands for not on file."""
    pf = ipo_facts.price_facts({"price_band": band_str, "issue_price": issue_price})
    if pf["band_low"] is not None:
        return pf["band_low"], pf["band_high"], pf["band_high"]
    one = pf["single"] if pf["single"] is not None else pf["issue_price"]
    return (one, one, one) if one else (0.0, 0.0, 0.0)


def compute_listing_performance(symbol, effective_issue_price, equity_history, listing_date=None):
    """Returns since issue (latest close vs issue price) and, only when the real
    listing-day candle is on file, the listing-day gain.

    BrokerLens holds a short price history (about 120 sessions), so for most
    listed IPOs the listing day lies before the first candle. The old code treated
    candles[0] as the listing day and, with no issue price, defaulted the issue
    price to that same candle's open, which printed a made-up "listing gain" on
    most listed IPO pages. Now: the listing-day candle must match the record's
    listing_date exactly, and the issue price is never guessed from a candle."""
    out = {"has_listing_data": False, "has_current_data": False}
    if not equity_history or not symbol:
        return out
    candles = equity_history.get(str(symbol).upper().strip())
    if not candles or not isinstance(candles, list):
        return out

    latest = candles[-1]
    cmp = float(latest.get("close") or 0.0)
    cmp_date = latest.get("date") or ""
    ip = float(effective_issue_price or 0.0)
    all_highs = [float(c.get("high") or 0.0) for c in candles if c.get("high")]
    all_lows = [float(c.get("low") or 0.0) for c in candles if c.get("low")]
    out.update({
        "n_sessions": len(candles),
        "cmp": cmp, "cmp_date": cmp_date,
        "high_52w": max(all_highs[-252:]) if all_highs else cmp,
        "low_52w": min(all_lows[-252:]) if all_lows else cmp,
    })
    if ip > 0 and cmp > 0:
        out.update({
            "has_current_data": True, "issue_price": ip,
            "current_gain_inr": cmp - ip, "current_gain_pct": (cmp - ip) / ip * 100.0,
            "gain_multiple": cmp / ip,
        })

    ld = (listing_date or "")[:10]
    lc = next((c for c in candles if c.get("date") == ld), None) if ld else None
    if lc and ip > 0:
        lo = float(lc.get("open") or 0.0) or float(lc.get("close") or 0.0)
        if lo > 0:
            out.update({
                "has_listing_data": True, "listing_date": ld, "listing_open": lo,
                "listing_close": float(lc.get("close") or 0.0),
                "listing_gain_inr": lo - ip, "listing_gain_pct": (lo - ip) / ip * 100.0,
            })
    return out


def _signed_move(pct, inr):
    """'+2.0% (+Rs 3.00)' or '-10.0% (-Rs 11.00)': the sign sits in front of both numbers."""
    sg = "+" if pct >= 0 else "-"
    return "%s%.1f%% (%sRs %s)" % (sg, abs(pct), sg, "{:,.2f}".format(abs(inr)))


def render_performance_card(perf, sym_slug):
    """Renders the post-listing returns card (issue price, listing-day open, latest close)."""
    if not perf or not perf.get("has_current_data"):
        return ""
    has_ld = bool(perf.get("has_listing_data"))

    lg_pct = perf["listing_gain_pct"] if has_ld else 0.0
    lg_cls = "var(--green)" if lg_pct >= 0 else "var(--red)"

    cg_pct = perf["current_gain_pct"]
    cg_cls = "var(--green)" if cg_pct >= 0 else "var(--red)"

    if has_ld:
        badge_label = "Listing Open Above Issue" if lg_pct >= 0 else "Listing Open Below Issue"
        badge_cls = "badge-up" if lg_pct >= 0 else "badge-warn"
        sub_note = "Verified exchange performance tracked from official NSE listing day open to current market close."
        listing_cell = (f'<div class="xs muted">Listing Day Open</div>'
                        f'<div style="font-size:18px;font-weight:700;margin-top:4px">Rs {perf["listing_open"]:,.2f}</div>'
                        f'<div class="xs" style="color:{lg_cls};font-weight:600">{_signed_move(lg_pct, perf["listing_gain_inr"])} vs issue price</div>')
    else:
        badge_label, badge_cls = "Since Issue", ""
        sub_note = ("Latest close versus the issue price. The listing-day candle is before the price history BrokerLens holds, "
                    "so no listing-day gain is shown rather than a guessed one.")
        listing_cell = ('<div class="xs muted">Listing Day Open</div>'
                        '<div style="font-size:14px;font-weight:600;margin-top:6px">Not on file</div>'
                        '<div class="xs faint">before our price history</div>')
    n_s = perf.get("n_sessions") or 0
    range_label = "52-Week Range" if n_s >= 252 else f"{n_s}-Session Range"

    return f"""
    <div class="card" style="margin-top:24px;padding:22px;background:var(--bg-raised);border-left:4px solid {cg_cls}">
      <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:10px">
        <div>
          <span class="badge {badge_cls}">{badge_label}</span>
          <h2 style="margin:8px 0 2px 0;font-size:18px">Post-Listing Performance Track Record</h2>
          <p class="muted small" style="margin:0">{sub_note}</p>
        </div>
        <div class="right">
          <div class="xs muted">Return Multiple</div>
          <div style="font-size:24px;font-weight:700;color:{cg_cls}">{perf['gain_multiple']:.2f}x</div>
        </div>
      </div>

      <div class="grid g4" style="margin-top:18px;gap:12px">
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          <div class="xs muted">Issue Price</div>
          <div style="font-size:18px;font-weight:700;margin-top:4px">Rs {perf['issue_price']:,.2f}</div>
          <div class="xs faint">Per issue record</div>
        </div>
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          {listing_cell}
        </div>
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          <div class="xs muted">Latest Close (as of {_esc(_long_date(perf['cmp_date']))})</div>
          <div style="font-size:18px;font-weight:700;margin-top:4px">Rs {perf['cmp']:,.2f}</div>
          <div class="xs" style="color:{cg_cls};font-weight:600">{_signed_move(cg_pct, perf['current_gain_inr'])} vs issue price</div>
        </div>
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          <div class="xs muted">{range_label}</div>
          <div style="font-size:15px;font-weight:600;margin-top:4px">Rs {perf['low_52w']:,.0f} - {perf['high_52w']:,.0f}</div>
          <div class="xs faint">As of {perf['cmp_date']}</div>
        </div>
      </div>

      <div style="margin-top:16px;display:flex;justify-content:flex-end">
        <a href="/stock/{sym_slug}/" class="badge" style="text-decoration:none;padding:8px 14px;background:var(--bg);border:1px solid var(--border)">View Live Candlestick Chart & Stock Fundamentals &rarr;</a>
      </div>
    </div>
    """


def render_subscription_card(r, status=None, as_of_iso=None):
    """Overall subscription multiple as a dated snapshot.

    The multiple is read from the current-issue feed on the feed date. While bidding is open it is labelled
    with that date. Once the close date has passed, a figure taken before the close is shown only as a
    snapshot taken while bidding was open, never as the result of the issue. No category split is on file."""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of_iso = as_of_iso or ipo_facts.data_as_of(today_iso)
    status = status or ipo_facts.ipo_status(r, today_iso)
    info = ipo_facts.subscription_info(r, status, as_of_iso)
    if info is None:
        return ""
    shares_offered = float(r.get("shares_offered") or 0.0)
    shares_bid = float(r.get("shares_bid") or 0.0)
    d = _esc(ipo_facts.fmt_date(info["as_of"]))
    if info["final"]:
        badge, title = "Bidding Demand", "Overall Subscription (Exchange Figure)"
        note = "Overall subscription from the exchange public-issue feed."
        label = "Total Subscribed"
    elif info["open_now"]:
        badge, title = "Bidding Demand", "Overall Subscription Snapshot"
        note = "Snapshot from the exchange public-issue feed as of %s, while bidding is open. The multiple changes until the issue closes." % d
        label = "Total Subscribed (as of %s)" % d
    else:
        badge, title = "Snapshot", "Subscription Snapshot, Bidding Was Open"
        note = ("Snapshot from the exchange public-issue feed as of %s, while bidding was open. Bidding has closed since, "
                "so this is not the final subscription multiple, which is not on file." % d)
        label = "Snapshot (as of %s)" % d
    return f"""
    <div class="card" style="margin-top:24px;padding:22px;background:var(--bg-raised);border-left:4px solid var(--accent)">
      <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:10px">
        <div>
          <span class="badge badge-up">{badge}</span>
          <h2 style="margin:8px 0 2px 0;font-size:18px">{title}</h2>
          <p class="muted small" style="margin:0">{note} BrokerLens does not receive a QIB/NII/Retail category breakdown and does not estimate one.</p>
        </div>
        <div class="right">
          <div class="xs muted">{label}</div>
          <div style="font-size:26px;font-weight:700;color:var(--accent)">{info['value']:.2f}x</div>
        </div>
      </div>

      <div class="grid g2" style="margin-top:18px;gap:12px">
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          <div class="xs muted">Shares Bid (as of {d})</div>
          <div style="font-size:18px;font-weight:700;margin-top:4px">{shares_bid:,.0f}</div>
        </div>
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          <div class="xs muted">Total Shares Offered</div>
          <div style="font-size:18px;font-weight:700;margin-top:4px">{shares_offered:,.0f}</div>
        </div>
      </div>
    </div>
    """


def render_lot_size_table(r, pf):
    """Lot size and SEBI application categories.

    A lot size is printed only when the record carries a sourced lot_size field. The category
    limits below are SEBI statutory rules, not per-issue estimates."""
    lot = ipo_facts.lot_size_on_file(r)
    top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
    if lot:
        line = f"Lot size on file: {lot} shares."
        if top:
            line += f" One lot at the upper price of Rs {ipo_facts.fmt_price(top)} is Rs {ipo_facts.fmt_price(lot * top)}."
    else:
        line = ("Lot size for this issue is not on file here. It is printed in the issue prospectus and on your broker's bid screen, "
                "so BrokerLens shows none rather than an estimate.")
    lim = ipo_facts.SEBI_BID_LIMITS

    calc_table = ""
    if lot and top and top > 0:
        lot_cost = lot * top
        max_ret_lots = max(1, int(200000 // lot_cost))
        min_snii_lots = max_ret_lots + 1
        max_snii_lots = max(min_snii_lots, int(1000000 // lot_cost))
        min_bnii_lots = max_snii_lots + 1

        calc_table = f"""
      <div style="margin:16px 0">
        <div style="font-weight:700;font-size:14px;margin-bottom:8px">Prospectus Lot Calculation Matrix</div>
        <div class="table-scroll">
          <table class="data">
            <thead>
              <tr>
                <th>Application Category</th>
                <th class="num">Lots</th>
                <th class="num">Shares</th>
                <th class="num">UPI Mandate Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Retail Minimum</strong></td>
                <td class="num">1 Lot</td>
                <td class="num">{lot:,}</td>
                <td class="num">Rs {ipo_facts.fmt_price(lot_cost)}</td>
              </tr>
              <tr>
                <td><strong>Retail Maximum</strong></td>
                <td class="num">{max_ret_lots} Lots</td>
                <td class="num">{max_ret_lots * lot:,}</td>
                <td class="num">Rs {ipo_facts.fmt_price(max_ret_lots * lot_cost)}</td>
              </tr>
              <tr>
                <td><strong>Small HNI (sNII) Min</strong></td>
                <td class="num">{min_snii_lots} Lots</td>
                <td class="num">{min_snii_lots * lot:,}</td>
                <td class="num">Rs {ipo_facts.fmt_price(min_snii_lots * lot_cost)}</td>
              </tr>
              <tr>
                <td><strong>Small HNI (sNII) Max</strong></td>
                <td class="num">{max_snii_lots} Lots</td>
                <td class="num">{max_snii_lots * lot:,}</td>
                <td class="num">Rs {ipo_facts.fmt_price(max_snii_lots * lot_cost)}</td>
              </tr>
              <tr>
                <td><strong>Big HNI (bNII) Min</strong></td>
                <td class="num">{min_bnii_lots} Lots</td>
                <td class="num">{min_bnii_lots * lot:,}</td>
                <td class="num">Rs {ipo_facts.fmt_price(min_bnii_lots * lot_cost)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      """

    return f"""
    <div class="card" style="margin-top:24px;padding:22px;background:var(--bg-raised)">
      <h2 style="margin:0 0 6px 0;font-size:18px">Lot Size and Application Limits</h2>
      <p class="muted small" style="margin:0 0 16px 0">{_esc(line)}</p>
      {calc_table}
      <div style="font-weight:700;font-size:14px;margin-bottom:8px">SEBI Statutory Bidding Limits</div>
      <div class="table-scroll">
        <table class="data">
          <thead>
            <tr><th>Application Category</th><th>Application Size</th></tr>
          </thead>
          <tbody>
            <tr><td><strong>Retail individual</strong></td><td>Up to {lim['retail']}</td></tr>
            <tr><td><strong>Small HNI (sNII)</strong></td><td>Above {lim['retail']} and up to {lim['snii']}</td></tr>
            <tr><td><strong>Big HNI (bNII)</strong></td><td>Above {lim['snii']}</td></tr>
          </tbody>
        </table>
      </div>
      <p class="xs faint" style="margin:10px 0 0 0">Category limits: {lim['note']}.</p>
    </div>
    """


def render_full_ipo_page(r, equity_history, head_template, foot_template,
                         affiliate_banner_html, fivepaisa_banner_html,
                         breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in",
                         jiraaf_banner_html="", ibsl_wide_html=""):
    """Renders institutional-grade /ipo/[slug]/ page."""
    # IBSL is a broker banner, so it takes the place of 5paisa here and the page keeps three sponsored blocks.
    _five_b = "" if ibsl_wide_html else fivepaisa_banner_html
    symbol = r["symbol"].upper()
    company = ipo_facts.display_name(r)
    slug = symbol.lower()
    canonical = f"{site_url}/ipo/{slug}/"

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of_iso = ipo_facts.data_as_of(today_iso)
    status = ipo_facts.ipo_status(r, today_iso)
    non_equity = ipo_facts.is_non_equity_issue(r)
    open_for_bids = status in ipo_facts.OPEN_STATUSES

    # One reading of the stored price fields feeds the title, meta, facts card, FAQs and
    # performance numbers, so they cannot disagree. Band low and high come from the stored
    # price band; an issue price outside that band is treated as a data fault and ignored.
    # A listing date that contradicts the bidding dates is never used for a listing-day figure.
    pf = ipo_facts.price_facts(r)
    good_ld = ipo_facts.reliable_listing_date(r)
    perf = compute_listing_performance(symbol, pf["issue_price"] or 0.0, equity_history, good_ld)
    candle = ipo_facts.listing_candle(symbol, good_ld, equity_history) if status == "Listed" else None

    # Title and meta A/B split by zlib.crc32(slug) % 2 (see ipo_facts.title_group and
    # docs/IPO_TITLE_TEST.md). The latest-close figure stays in the body, never here.
    title = ipo_facts.build_title(r, pf, status)
    description = ipo_facts.build_description(r, pf, status, candle=candle, has_latest_close=bool(perf.get("has_current_data")))
    if non_equity:
        title = "%s (%s) Public Issue Dates and Price | %s" % (ipo_facts._short_name(company, symbol), symbol, ipo_facts.BRAND)
        description = ("%s (%s) public issue: dates and price from the exchange feed. It is not presented as an equity IPO. "
                       "Status: %s." % (company, symbol, status))[:295]

    facts_html = ipo_facts.render_facts_card(r, pf, status, candle, as_of_iso, company)
    gmp_html = ipo_facts.render_gmp_section(r, pf, status, candle, perf, company)
    perf_html = render_performance_card(perf, slug)
    sub_html = render_subscription_card(r, status, as_of_iso)
    lot_html = render_lot_size_table(r, pf)

    faqs = ipo_facts.build_faqs(r, pf, status, candle, perf, company, as_of_iso)

    faq_html = "".join(
        f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>'
        for q, a in faqs
    )

    crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", "/ipo/"), (company, None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FinancialProduct",
                "name": f"{company} IPO" if not non_equity else f"{company} ({symbol}) public issue",
                "url": canonical,
                "description": description,
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]
            },
            crumb_jsonld,
        ]
    }

    body = head_template % {
        "title": _esc(title),
        "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    if non_equity:
        # not an equity IPO: keep it out of the index (the self canonical stays)
        body = body.replace("</head>", '<meta name="robots" content="noindex,follow">\n</head>', 1)

    # The per-broker apply pages exist only for current, upcoming and the most recent IPOs
    # (see build_ipo_apply_suite), and only open or upcoming issues can still be applied for. Link them only
    # where they exist and the issue is open, so no page links a 404 or tells a visitor to apply for a closed issue.
    apply_html = ""
    if open_for_bids and not non_equity and ipo_facts.has_apply_pages(slug):
        _brokers = (("zerodha", "Zerodha Kite"), ("groww", "Groww"), ("angel-one", "Angel One"),
                    ("upstox", "Upstox"), ("dhan", "Dhan"))
        _links = "".join(
            f'<a class="badge" href="/ipo/{slug}/apply-via-{bid}/" style="text-decoration:none;padding:6px 10px;background:var(--bg)">Apply on {bname} &rarr;</a>'
            for bid, bname in _brokers)
        apply_html = (
            f'<div class="card" style="margin-top:24px;padding:20px;background:var(--bg-raised)">'
            f'<div class="section-title"><h2 style="margin:0;font-size:16px">How to Apply for {_esc(company)} IPO Online via UPI</h2></div>'
            f'<p class="muted small" style="margin:4px 0 12px 0">Step-by-step UPI application walkthroughs across India\'s leading SEBI-registered brokers:</p>'
            f'<div style="display:flex;flex-wrap:wrap;gap:8px">{_links}</div>'
            f'<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);display:flex;align-items:center;flex-wrap:wrap;gap:10px">'
            f'<span class="xs muted">Need a Demat account to apply?</span>'
            f'<a href="https://zerodha.com/open-account?c=ZE5729" target="_blank" rel="noopener sponsored" class="xs" style="color:var(--accent);text-decoration:none;font-weight:600">Zerodha &rarr;</a>'
            f'<a href="https://dhan.co/?ref=BROKERLENS" target="_blank" rel="noopener sponsored" class="xs" style="color:var(--accent);text-decoration:none;font-weight:600">Dhan &rarr;</a>'
            f'<a href="https://www.angelone.in/open-demat-account?referral=BROKERLENS" target="_blank" rel="noopener sponsored" class="xs" style="color:var(--accent);text-decoration:none;font-weight:600">Angel One &rarr;</a>'
            f'<a href="https://upstox.com/open-account/?f=BROKERLENS" target="_blank" rel="noopener sponsored" class="xs" style="color:var(--accent);text-decoration:none;font-weight:600">Upstox &rarr;</a>'
            f'</div></div>'
        )
    elif status == "Forthcoming" and not non_equity:
        apply_html = (
            f'<div class="card" style="margin-top:24px;padding:22px;background:var(--bg-raised);border-left:4px solid var(--accent)">'
            f'<div class="row-between" style="align-items:center;flex-wrap:wrap;gap:12px">'
            f'<div><span class="badge badge-accent">Upcoming IPO Alert</span>'
            f'<h2 style="margin:8px 0 4px 0;font-size:18px">Prepare Demat Account for {_esc(company)} IPO</h2>'
            f'<p class="muted small" style="margin:0;max-width:65ch">'
            f'To bid when the issue opens, you need an active SEBI-registered Demat account with UPI ASBA enabled. '
            f'Open an account with top brokers offering zero account opening charges and instant online IPO bidding:</p></div>'
            f'</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:16px">'
            f'<a href="https://zerodha.com/open-account?c=ZE5729" target="_blank" rel="noopener sponsored" class="btn btn-primary small">Apply via Zerodha &rarr;</a>'
            f'<a href="https://dhan.co/?ref=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Apply via Dhan &rarr;</a>'
            f'<a href="https://www.angelone.in/open-demat-account?referral=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Apply via Angel One &rarr;</a>'
            f'<a href="https://upstox.com/open-account/?f=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Apply via Upstox &rarr;</a>'
            f'</div></div>'
        )

    sec_label = {"SME": "SME Emerge", "EQ": "Mainboard Equity"}.get(r.get("security_type"), "")
    sec_prefix = f"{sec_label} &bull; " if sec_label else ""

    sme_notice = ""
    if r.get("security_type") == "SME":
        sme_notice = (
            f'<div class="card" style="padding:14px 18px;margin:0 0 16px 0;border-left:4px solid #8b5cf6;background:var(--bg-raised)">'
            f'<div style="font-weight:700;font-size:14px;color:var(--text)">SME Emerge Public Issue Notice</div>'
            f'<div class="small muted" style="margin-top:4px;line-height:1.5">'
            f'This public issue is listed on the SME platform (NSE Emerge / BSE SME). Under SEBI SME regulations, '
            f'minimum application and trading lot sizes are standardized (typically 1 lot of Rs 1 Lakh or more), '
            f'and secondary market liquidity is facilitated by an appointed market maker.'
            f'</div></div>'
        )

    if non_equity:
        h1 = f'{_esc(company)} <span class="muted" style="font-size:18px">({_esc(symbol)}) public issue</span>'
        type_note = (f'<div class="card" style="padding:14px;margin:0 0 16px 0;border-left:3px solid var(--accent)">'
                     f'<div style="font-weight:700">Not presented as an equity IPO</div>'
                     f'<div class="small muted" style="margin-top:2px">{_esc(ipo_facts.non_equity_note(r))}</div></div>')
    else:
        h1 = f'{_esc(company)} IPO <span class="muted" style="font-size:18px">({_esc(symbol)})</span>'
        type_note = ""

    # Allotment lookups make no sense for an issue the exchange feed marks withdrawn or postponed.
    show_allot = not (status == ipo_facts.STATUS_NO_LISTING and ipo_facts.name_flag(r))
    allot_html = ""
    if show_allot:
        allot_html = (
            f'<div class="card" style="margin-top:20px;padding:20px;background:var(--bg-raised);border-left:3px solid var(--accent)">'
            f'<div class="section-title"><h2 style="margin:0;font-size:16px">Check Official {_esc(company)} Allotment Status Online</h2></div>'
            f'<p class="muted small" style="margin:4px 0 14px 0">Direct allotment search portals across India\'s primary registrar platforms (PAN / Application / DP Client ID):</p>'
            f'<div style="display:flex;flex-wrap:wrap;gap:8px">'
            f'<a class="btn btn-outline small" href="https://linkintime.co.in/initial_offer/public-issues.html" target="_blank" rel="noopener noreferrer">Link Intime &rarr;</a>'
            f'<a class="btn btn-outline small" href="https://kosmic.kfintech.com/ipostatus/" target="_blank" rel="noopener noreferrer">KFintech &rarr;</a>'
            f'<a class="btn btn-outline small" href="https://www.bigshareonline.com/ipo_Allotment.html" target="_blank" rel="noopener noreferrer">Bigshare Services &rarr;</a>'
            f'<a class="btn btn-outline small" href="https://www.skylinerta.com/ipo.php" target="_blank" rel="noopener noreferrer">Skyline RTA &rarr;</a>'
            f'<a class="btn btn-primary small" href="/ipo/allotment-status/">BrokerLens Allotment Guide &rarr;</a>'
            f'</div></div>'
        )

    if open_for_bids:
        aff_h2 = "Apply for IPOs online with top SEBI-registered brokers"
        aff_p = "Open a free Demat account in 5 minutes with India's leading brokers and submit your IPO bid seamlessly via UPI."
    else:
        aff_h2 = "Be ready for the next IPO"
        aff_p = ("Bidding for this issue is over. To apply for a future IPO you need a demat account and a UPI ID. "
                 "These brokers are sponsored partners.")

    related_links = []
    if status == "Listed" and perf.get("has_current_data"):
        related_links.append(f'<a href="/stock/{slug}/"><strong>{_esc(company)}</strong> NSE listing details &rarr;</a>')
    related_links.append('<a href="/ipo/upcoming/">Upcoming IPOs &rarr;</a>')
    related_links.append('<a href="/ipo/archive/">More listed IPOs &rarr;</a>')
    related_links.append('<a href="/ipo/gmp/">IPO GMP Tracker &rarr;</a>')
    related_links.append('<a href="/ipo/sme/">SME IPO Hub &rarr;</a>')
    related_links.append('<a href="/ipo/allotment-status/">Check Allotment Status &rarr;</a>')
    related_links.append('<a href="/ipo/">IPO tracker hub &rarr;</a>')
    related_html = (
        f'<div class="card" style="margin-top:24px;padding:16px 20px;background:var(--bg-raised)">'
        f'<div class="section-title"><h3 style="margin:0;font-size:15px">Related IPO and Market Links</h3></div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:16px;margin-top:8px;font-size:14px">{" &bull; ".join(related_links)}</div>'
        f'</div>'
    )

    body += (
        crumb_html
        + f'<div style="margin-top:10px">'
        + f'<h1 style="margin:0 0 6px 0;font-size:26px">{h1}</h1>'
        + f'<p class="muted small" style="margin:0 0 16px 0">{sec_prefix}Sourced directly from official NSE public-issue disclosures.</p>'
        + _stage_banner(status, r, today_iso, as_of_iso)
        + type_note
        + sme_notice
        + f'</div>'
        + facts_html
        + perf_html
        + sub_html
        + gmp_html
        + lot_html
        + ibsl_wide_html
        + apply_html
        + allot_html
        + f'<div class="aff-block" style="margin-top:24px">'
        + f'<div class="section-title"><h2>{_esc(aff_h2)}</h2></div>'
        + f'<p class="muted small" style="margin-top:4px">{_esc(aff_p)}</p>'
        + f'<div class="grid g3 aff-pair" style="margin-top:14px">{affiliate_banner_html}{_five_b}{jiraaf_banner_html}</div></div>'
        + f'<h2 style="margin-top:28px;font-size:18px">Frequently Asked Questions</h2>'
        + f'<div style="max-width:70ch">{faq_html}</div>'
        + related_html
    )

    body += foot_template % {
        "source_note": source_note_fn(
            "This page's facts are NSE's own public-issue disclosures. "
            "BrokerLens does not publish grey market premium (GMP) and this page is not investment advice."
        )
    }

    return body


def _classify_ipos(records, today_iso):
    """(active, forthcoming, awaiting_listing) by the same status rules as every IPO page. Awaiting means
    bidding has closed and the issue is still inside its SEBI T+3 listing window with no listing yet.
    Issues past that window, withdrawn or postponed issues, and non-equity issues are in none of the three."""
    active, forthcoming, awaiting = [], [], []
    for r in records:
        if ipo_facts.is_non_equity_issue(r):
            continue
        st = ipo_facts.ipo_status(r, today_iso)
        if st == "Active":
            active.append(r)
        elif st == "Forthcoming":
            forthcoming.append(r)
        elif st == "Closed":
            awaiting.append(r)
    return active, forthcoming, awaiting


def build_ipo_event_feeds(records, site_url="https://www.brokerlens.in"):
    """RSS feed and iCalendar file of IPO dates, so people can follow IPOs with no
    account and no email: open dates, last day to bid, and the SEBI T+3 expected
    listing date (weekdays only, so it is labelled indicative). Facts only."""
    now = datetime.now(timezone.utc)
    today_iso = now.strftime("%Y-%m-%d")
    active, forthcoming, awaiting = _classify_ipos(records, today_iso)
    events = []   # (iso_date, kind, record)
    for r in active + forthcoming:
        if r.get("bidding_start"):
            events.append((r["bidding_start"], "opens", r))
        if r.get("bidding_end"):
            events.append((r["bidding_end"], "closes", r))
    for r in active + forthcoming + awaiting:
        exp = _add_working_days(r.get("bidding_end"), 3)
        if exp:
            events.append((exp, "listing", r))
    events.sort(key=lambda e: (e[0], e[2].get("symbol", "")))

    def title(kind, r):
        co = ipo_facts.display_name(r)
        return {"opens": f"{co} IPO opens for bidding", "closes": f"{co} IPO closes (last day to bid)",
                "listing": f"{co} IPO: listing expected on or around this date"}[kind]

    def detail(kind, r):
        band = r.get("price_band") or "price band not announced"
        base = f"Price band: {band}. "
        note = {"opens": "Dates and price band are as announced by the issuer and can change.",
                "closes": "Check the exchange notice for any extension.",
                "listing": "SEBI requires listing within three working days of issue close; this date skips weekends only, so the exchange notice is final."}[kind]
        return base + note + " Facts only, not a recommendation to apply."

    def rfc822(iso):
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000")

    items = "".join(
        "<item><title>%s</title><link>%s/ipo/%s/</link><guid isPermaLink=\"false\">%s-%s-%s</guid>"
        "<pubDate>%s</pubDate><description>%s</description></item>" % (
            _esc(title(k, r)), site_url, r["symbol"].lower(), r["symbol"].lower(), k, d, rfc822(d), _esc(detail(k, r)))
        for d, k, r in events)
    rss = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
           "<title>BrokerLens IPO dates</title><link>%s/ipo/upcoming/</link>"
           "<description>Open, close and expected listing dates for IPOs on NSE, from public-issue disclosures. Facts only.</description>"
           "<language>en-IN</language><lastBuildDate>%s</lastBuildDate>%s</channel></rss>" % (
               site_url, now.strftime("%a, %d %b %Y %H:%M:%S +0000"), items))

    def ics_escape(s):
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BrokerLens//IPO dates//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:BrokerLens IPO dates"]
    for d, k, r in events:
        day = d.replace("-", "")
        nxt = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        lines += ["BEGIN:VEVENT", f"UID:{r['symbol'].lower()}-{k}-{day}@brokerlens.in", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{day}", f"DTEND;VALUE=DATE:{nxt}", "SUMMARY:" + ics_escape(title(k, r)),
                  "DESCRIPTION:" + ics_escape(detail(k, r)), f"URL:{site_url}/ipo/{r['symbol'].lower()}/", "END:VEVENT"]
    lines.append("END:VCALENDAR")

    def fold(line):
        # RFC 5545: content lines longer than 75 octets are folded with CRLF + one space.
        raw = line.encode("utf-8")
        if len(raw) <= 75:
            return line
        out, first = [], True
        while raw:
            limit = 75 if first else 74
            cut = limit
            while cut > 0 and (raw[cut:cut + 1] and (raw[cut] & 0xC0) == 0x80):   # never split a UTF-8 character
                cut -= 1
            out.append(("" if first else " ") + raw[:cut].decode("utf-8"))
            raw, first = raw[cut:], False
        return "\r\n".join(out)
    return rss, "\r\n".join(fold(l) for l in lines) + "\r\n", len(events)


def _follow_card_html():
    return (
        '<section class="follow-card" aria-labelledby="follow-title"><h2 id="follow-title">Follow IPO dates, no account needed</h2>'
        '<p>Open, last-day-to-bid and expected listing dates, straight from the exchange disclosures. Add them to your calendar or '
        'subscribe in any feed reader. Facts only: no tips, no grey-market prices, no recommendations.</p>'
        '<div class="row-wrap"><a class="btn btn-primary small" href="/ipo/upcoming.ics">Add to my calendar (.ics) &rarr;</a>'
        '<a class="btn btn-outline small" href="/ipo/feed.xml">RSS feed &rarr;</a></div></section>'
    )


def _rs(x):
    """One price format for every table cell: Rs 405.00, Rs 78.00."""
    return "Rs {:,.2f}".format(x)


def _type_chip(r):
    return {"SME": "SME", "EQ": "Mainboard"}.get(r.get("security_type"), "")


def _freshness_line(as_of_iso, today_iso):
    """'Data as of 2 Oct 2026.' plus a plain warning when the feed on file is more than 2 days old."""
    line = "Data as of %s." % ipo_facts.fmt_date(as_of_iso)
    age = ipo_facts.data_age_days(as_of_iso, today_iso)
    if age > 2:
        line += (" This NSE feed snapshot is %d days old, so the open and upcoming counts reflect that date. "
                 "Check the exchange for anything newer." % age)
    return line


def render_enhanced_ipo_hub(records, equity_history, head_template, foot_template,
                            breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in", upcoming=False, ibsl_html=""):
    """Renders the enhanced /ipo/ hub: open, upcoming and recently listed IPOs, with the date of the NSE
    feed behind the numbers."""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of_iso = ipo_facts.data_as_of(today_iso)
    # Non-equity public issues (debt series such as SMCG04) are not IPOs: kept out of every list here.
    records = ipo_facts.ipo_records_only(records)
    active, forthcoming, awaiting_all, listed_candidates = [], [], [], []

    for r in records:
        st = ipo_facts.ipo_status(r, today_iso)
        if st == "Active":
            active.append(r)
        elif st == "Forthcoming":
            forthcoming.append(r)
        elif st == "Closed":
            awaiting_all.append(r)
        elif st == "Listed" and ipo_facts.reliable_listing_date(r):
            listed_candidates.append(r)
        # No listing on file, and listed records whose listing date looks inconsistent, are not
        # shown as listings here. Their own pages carry the facts.

    # Recently listed, newest listing first, with performance where the price history on file covers it
    listed_candidates.sort(key=ipo_facts.reliable_listing_date, reverse=True)
    recent_listed = []
    for r in listed_candidates[:40]:
        sym = r.get("symbol", "").upper()
        _ip = ipo_facts.price_facts(r)["issue_price"] or 0.0
        row_dict = dict(r)
        row_dict["perf"] = compute_listing_performance(sym, _ip, equity_history, ipo_facts.reliable_listing_date(r))
        recent_listed.append(row_dict)
    # Bidding has closed and the issue is still inside the SEBI T+3 window: shown on its own, never as "listed".
    awaiting = sorted(awaiting_all, key=lambda r: r.get("bidding_end") or "", reverse=True)[:15]

    canonical = f"{site_url}/ipo/upcoming/" if upcoming else f"{site_url}/ipo/"
    title = "IPO Tracker: Open and Upcoming IPOs, Price Bands and Listing Results | BrokerLens"
    description = (
        f"IPO dates, price bands and listing-day results for NSE mainboard and SME issues, from NSE's public disclosures. "
        f"{len(active)} open for bidding and {len(forthcoming)} upcoming as of {ipo_facts.fmt_date(as_of_iso)}."
    )[:295]
    fresh = _freshness_line(as_of_iso, today_iso)

    def render_active_table(rows):
        if not rows:
            return '<p class="small faint">No IPOs are currently open for bidding.</p>'
        out = """
        <div class="table-scroll"><table class="data">
          <thead>
            <tr>
              <th>Company & Symbol</th>
              <th>Status</th>
              <th class="right">Price Band</th>
              <th class="right">Bidding Window</th>
              <th class="right">Subscription (dated)</th>
              <th class="center">Action</th>
            </tr>
          </thead>
          <tbody>
        """
        for r in rows:
            sym = r["symbol"].upper()
            slug = sym.lower()
            co = ipo_facts.display_name(r)
            p_str = ipo_facts.band_text(r) or "Not on file"
            dates = ipo_facts.date_range_text(r.get("bidding_start"), r.get("bidding_end")) or "Not on file"
            info = ipo_facts.subscription_info(r, "Active", as_of_iso)
            if info:
                sub_str = "%.2fx" % info["value"]
                sub_note = '<span class="xs faint" style="display:block">as of %s</span>' % _esc(ipo_facts.fmt_date(info["as_of"]))
            else:
                sub_str, sub_note = "Not on file", ""
            chance_html = ""   # no allotment-odds estimate: the category split behind it is not published per bid

            out += f"""
            <tr>
              <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
              <td><span class="badge badge-up">Active Now</span></td>
              <td class="right num">{_esc(p_str)}</td>
              <td class="right small">{_esc(dates)}</td>
              <td class="right num font-semibold" style="color:var(--accent)" data-ipo-demand="{_esc(sym)}">{_esc(sub_str)}{sub_note}{chance_html}</td>
              <td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">Details & Bidding &rarr;</a></td>
            </tr>
            """
        out += "</tbody></table></div>"
        return out

    def render_upcoming_table(rows):
        if not rows:
            return '<p class="small faint">No forthcoming IPOs are announced right now.</p>'
        out = """
        <div class="table-scroll"><table class="data">
          <thead>
            <tr>
              <th>Company & Symbol</th>
              <th>Status</th>
              <th class="right">Price Band</th>
              <th class="right">Opening Date</th>
              <th class="right">Closing Date</th>
              <th class="center">Analysis</th>
            </tr>
          </thead>
          <tbody>
        """
        for r in rows:
            sym = r["symbol"].upper()
            slug = sym.lower()
            co = ipo_facts.display_name(r)
            p_str = ipo_facts.band_text(r) or "Announced"
            d_start = _long_date(r.get("bidding_start")) or "Announced Soon"
            d_end = _long_date(r.get("bidding_end")) or "Announced Soon"
            out += f"""
            <tr>
              <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
              <td><span class="badge badge-warn">Upcoming</span></td>
              <td class="right num">{_esc(p_str)}</td>
              <td class="right small">{_esc(d_start)}</td>
              <td class="right small">{_esc(d_end)}</td>
              <td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">View Issue &rarr;</a></td>
            </tr>
            """
        out += "</tbody></table></div>"
        return out

    def render_listed_table(rows):
        if not rows:
            return '<p class="small faint">No recent listings available.</p>'
        out = """
        <div class="table-scroll"><table class="data">
          <thead>
            <tr>
              <th>Company & Symbol</th>
              <th>Listing Date</th>
              <th class="right">Issue Price</th>
              <th class="right">Listing Day Open</th>
              <th class="right">Listing Open vs Issue Price</th>
              <th class="right">Current Price (CMP)</th>
              <th class="right">Total Return</th>
              <th class="center">Stock</th>
            </tr>
          </thead>
          <tbody>
        """
        for r in rows:
            sym = r["symbol"].upper()
            slug = sym.lower()
            co = ipo_facts.display_name(r)
            perf = r.get("perf") or {}
            d_list = _long_date(ipo_facts.reliable_listing_date(r)) or "Not on file"
            chip = _type_chip(r)
            sub_label = f"{_esc(sym)} &middot; {chip}" if chip else _esc(sym)

            pf_r = ipo_facts.price_facts(r)
            ip_val = pf_r["issue_price"] or pf_r["single"]
            ip_str = _rs(ip_val) if ip_val else "Not on file"
            lo_str = lg_str = cmp_str = cg_str = "Not on file"
            if perf.get("has_listing_data"):
                lo_str = _rs(perf["listing_open"])
                lg_pct = perf["listing_gain_pct"]
                lg_cls = "var(--green)" if lg_pct >= 0 else "var(--red)"
                lg_str = f"<span style='color:{lg_cls};font-weight:600'>{lg_pct:+.1f}%</span>"
            if perf.get("has_current_data"):
                cmp_str = _rs(perf["cmp"])
                cg_pct = perf["current_gain_pct"]
                cg_cls = "var(--green)" if cg_pct >= 0 else "var(--red)"
                cg_str = f"<span style='color:{cg_cls};font-weight:600'>{cg_pct:+.1f}%</span>"
            stock_link = (f'<a href="/stock/{slug}/" class="btn btn-xs">Stock &rarr;</a>' if perf.get("has_current_data")
                          else f'<a href="/ipo/{slug}/" class="btn btn-xs">View &rarr;</a>')
            if perf.get("has_listing_data") or perf.get("has_current_data"):
                mid = (f'<td class="right num">{lo_str}</td><td class="right num">{lg_str}</td>'
                       f'<td class="right num">{cmp_str}</td><td class="right num">{cg_str}</td>')
            else:
                # one note instead of four empty cells
                mid = '<td class="small faint" colspan="4">Listing-day and current prices are not on file</td>'

            out += f"""
            <tr>
              <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{sub_label}</span></td>
              <td class="small">{_esc(d_list)}</td>
              <td class="right num">{_esc(ip_str)}</td>
              {mid}
              <td class="center">{stock_link}</td>
            </tr>
            """
        out += "</tbody></table></div>"
        return out

    def render_awaiting_table(rows):
        if not rows:
            return ""
        out = ('<div class="table-scroll"><table class="data"><thead><tr><th>Company & Symbol</th>'
               '<th class="right">Price Band</th><th class="right">Bidding Closed</th>'
               '<th class="right">Listing Expected On Or Around</th><th class="center">Details</th></tr></thead><tbody>')
        for r in rows:
            sym = r["symbol"].upper()
            slug = sym.lower()
            exp = _add_working_days(r.get("bidding_end"), 3)
            out += (f'<tr><td><strong><a href="/ipo/{slug}/">{_esc(ipo_facts.display_name(r))}</a></strong> '
                    f'<span class="xs faint">{_esc(sym)}</span></td>'
                    f'<td class="right num">{_esc(ipo_facts.band_text(r) or "Announced")}</td>'
                    f'<td class="right small">{_esc(_long_date(r.get("bidding_end")) or "Not on file")}</td>'
                    f'<td class="right small">{_esc(_long_date(exp) if exp else "Not on file")}</td>'
                    f'<td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">Allotment &amp; timeline &rarr;</a></td></tr>')
        return out + "</tbody></table></div><p class=\"xs faint\" style=\"margin-top:6px\">SEBI requires listing within three working days of the issue closing; the date shown skips weekends only, so the exchange notice is the final word.</p>"

    faqs = [
        ("Does BrokerLens show IPO grey market premium (GMP)?",
         "No. GMP is an unregulated, off-exchange informal estimate with no regulatory oversight. BrokerLens publishes strictly verified, exchange-disclosed data only."),
        ("How are IPO listing results and total returns computed on this page?",
         "The listing result compares the opening trade price on the official exchange listing day with the issue price, and is shown only where the exchange price history on file covers that day. Total return compares the latest NSE closing price with the IPO issue price."),
        ("What is the difference between Mainboard and SME IPOs?",
         "Mainboard IPOs list on the main exchange boards with larger issue sizes. SME IPOs list on the SME platforms (NSE Emerge or BSE SME) and are generally smaller issues. The lot size for each issue is stated in its prospectus."),
        ("Does BrokerLens recommend applying to any IPO?",
         "No. BrokerLens does not recommend any IPO, stock or broker. This page states public facts only; it is not investment advice, and BrokerLens is not a SEBI-registered investment adviser or research analyst."),
    ]

    def faq_block(items):
        return "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in items)

    def faq_ld(items):
        return {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}

    if upcoming:
        n_open, n_soon = len(active), len(forthcoming)
        u_faqs = [
            ("How do I see which IPOs are open or opening soon?",
             "The sections on this page list issues open for bidding and issues opening soon, taken from NSE's public-issue disclosures. "
             "%s Dates and price bands are as announced by the issuers and can change." % fresh),
            ("What is a price band?",
             "A price band is the range within which investors can bid for an IPO. The final issue price is fixed within the band after bidding closes."),
            ("When are IPO dates announced?",
             "Issuers announce the opening and closing dates and the price band before bidding opens. An issue appears on this page once it is in NSE's public-issue disclosures."),
            ("How can I follow IPO dates without an account?",
             "Add the calendar file (.ics) to your calendar app or subscribe to the RSS feed linked on this page. Both carry dates only."),
            ("Does BrokerLens recommend applying to any IPO?",
             "No. BrokerLens does not recommend any IPO, stock or broker. This page states public facts only and is not investment advice."),
        ]
        u_title = "Upcoming IPOs in India: Open Now and Opening Soon | BrokerLens"
        u_desc = (f"{n_open} IPO{'s' if n_open != 1 else ''} open for bidding and {n_soon} opening soon, with dates, price bands "
                  f"and the SEBI listing timeline, from NSE disclosures. Data as of {_long_date(as_of_iso)}.")[:295]
        crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", "/ipo/"), ("Upcoming IPOs", None)])
        u_jsonld = {"@context": "https://schema.org", "@graph": [
            {"@type": "ItemList", "name": "Upcoming and open IPOs", "url": canonical,
             "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{site_url}/ipo/{r['symbol'].lower()}/",
                                  "name": ipo_facts.display_name(r)} for i, r in enumerate(active + forthcoming)]},
            faq_ld(u_faqs),
            crumb_jsonld]}
        body = head_template % {"title": _esc(u_title), "description": _esc(u_desc), "canonical": _esc(canonical),
                                "jsonld": json.dumps(u_jsonld, ensure_ascii=False)}
        body += (
            crumb_html
            + '<h1 style="margin-top:0">Upcoming IPOs in India</h1>'
            + f'<p class="muted" style="max-width:75ch">Mainboard and SME issues from NSE\'s public-issue disclosures. {_esc(fresh)} '
              'Dates and price bands are as announced by the issuers and can change; this page states facts only and is not a recommendation to apply.</p>'
            + '<div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 8px 0">'
            + '<a href="/ipo/allotment-status/" class="btn btn-primary small">Check allotment status &rarr;</a>'
            + '<a href="/ipo/how-to-apply/" class="btn btn-outline small">How to apply via UPI &rarr;</a>'
            + '<a href="/ipo/" class="btn btn-outline small">IPO tracker and listing results &rarr;</a></div>'
            + _follow_card_html()
            + ibsl_html
            + '<div class="section-title" style="margin-top:20px"><h2>Open for bidding now</h2></div>' + render_active_table(active)
            + '<div class="section-title" style="margin-top:28px"><h2>Opening soon</h2></div>' + render_upcoming_table(forthcoming)
            + ('<div class="section-title" style="margin-top:28px"><h2>Closed, awaiting listing</h2></div>' + render_awaiting_table(awaiting) if awaiting else "")
            + '<h2 style="margin-top:32px;font-size:18px">Frequently Asked Questions</h2>'
            + f'<div style="max-width:70ch">{faq_block(u_faqs)}</div>'
        )
        body += foot_template % {"source_note": source_note_fn(
            "This page's dates, price bands and subscription figures are NSE's own public-issue disclosures.")}
        return body

    crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [faq_ld(faqs), crumb_jsonld]}
    first_year = ipo_facts.earliest_year(records)
    since_txt = f"NSE issues on file since {first_year}" if first_year else "NSE issues on file"

    body = head_template % {
        "title": _esc(title),
        "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }

    body += (
        crumb_html
        + '<h1 style="margin-top:0">IPO Tracker & Performance Hub</h1>'
        + '<p class="muted" style="max-width:75ch">Mainboard and SME IPOs tracked from official NSE disclosures: price bands, dates, dated subscription snapshots, and post-listing results where the exchange price history on file covers them. No grey market premium, no speculative recommendations &bull; <a href="/methodology" data-link>see methodology</a>.</p>'
        + f'<p class="small muted" style="max-width:75ch;margin-top:-6px">{_esc(fresh)}</p>'
        + f'<div class="grid g4" style="margin:20px 0 24px 0;gap:12px">'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--accent)">'
        + f'<div class="xs muted">Active for Bidding</div>'
        + f'<div style="font-size:22px;font-weight:700;color:var(--accent);margin-top:4px">{len(active)} Issues Open</div>'
        + f'<div class="xs faint">As of {_esc(ipo_facts.fmt_date(as_of_iso))}</div>'
        + f'</div>'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--text-bright)">'
        + f'<div class="xs muted">Upcoming IPOs</div>'
        + f'<div style="font-size:22px;font-weight:700;margin-top:4px">{len(forthcoming)} Forthcoming</div>'
        + f'<div class="xs faint">Announced issue dates</div>'
        + f'</div>'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--green)">'
        + f'<div class="xs muted">Tracked Listings</div>'
        + f'<div style="font-size:22px;font-weight:700;color:var(--green);margin-top:4px">{len(records):,} Total</div>'
        + f'<div class="xs faint">{_esc(since_txt)}</div>'
        + f'</div>'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--blue, #3b82f6)">'
        + f'<div class="xs muted">Allotment Tools</div>'
        + f'<div style="font-size:16px;font-weight:700;margin-top:6px"><a href="/ipo/allotment-status/" style="text-decoration:none">Online Checker &rarr;</a></div>'
        + f'<div class="xs faint">Registrar PAN lookup</div>'
        + f'</div>'
        + f'</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:24px">'
        + '<a href="/ipo/upcoming/" class="btn btn-primary small">Upcoming IPOs &rarr;</a>'
        + '<a href="/ipo/sme/" class="btn btn-outline small">SME IPOs (NSE Emerge) &rarr;</a>'
        + '<a href="/ipo/gmp/" class="btn btn-outline small">GMP Tracker & Sentiment &rarr;</a>'
        + '<a href="/ipo/subscription/" class="btn btn-outline small">IPO Subscription Status &rarr;</a>'
        + '<a href="/ipo/allotment-status/" class="btn btn-outline small">Check Allotment Status &rarr;</a>'
        + '<a href="/ipo/how-to-apply/" class="btn btn-outline small">How to Apply via UPI &rarr;</a>'
        + '<a href="/ipo/archive/" class="btn btn-outline small">Full Historical Archive &rarr;</a>'
        + '</div>'
        + _follow_card_html()
        + ibsl_html
        + '<div class="section-title" style="margin-top:24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">'
        + '<h2>Currently Open for Bidding (Active IPOs)</h2>'
        + '</div>'
        + render_active_table(active)
        + '<div class="section-title" style="margin-top:32px"><h2>Upcoming IPOs (Announced Dates & Price Bands)</h2></div>'
        + render_upcoming_table(forthcoming)
        + ('<div class="section-title" style="margin-top:32px"><h2>Closed, Awaiting Listing</h2></div>' + render_awaiting_table(awaiting) if awaiting else "")
        + '<div class="section-title" style="margin-top:32px"><h2>Recently Listed IPOs: Listing Day Open vs Issue Price & Current Performance</h2></div>'
        + render_listed_table(recent_listed)
        + f'<p class="xs faint" style="margin-top:14px"><a href="/ipo/archive/">Browse the full historical archive ({len(records):,} IPOs on file) &rarr;</a></p>'
        + '<h2 style="margin-top:32px;font-size:18px">Frequently Asked Questions</h2>'
        + f'<div style="max-width:70ch">{faq_block(faqs)}</div>'
    )

    body += foot_template % {
        "source_note": source_note_fn(
            "This page's price bands, dates, subscription figures, and listing performance facts are NSE's own public-issue disclosures."
        )
    }

    return body


def render_enhanced_ipo_archive(records, equity_history, head_template, foot_template,
                                breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in"):
    """Renders the full /ipo/archive/ page: every IPO record on file, with listing-day results where the
    exchange price history on file covers them."""
    canonical = f"{site_url}/ipo/archive/"
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of_iso = ipo_facts.data_as_of(today_iso)
    records = ipo_facts.ipo_records_only(records)
    n = len(records)
    y0 = ipo_facts.earliest_year(records)
    ys = [d.year for d in (ipo_facts._parse(r.get("bidding_end")) for r in records) if d]
    y1 = max(ys) if ys else None
    span = f"{y0} to {y1}" if (y0 and y1 and y0 != y1) else (str(y0) if y0 else "")
    title = f"IPO Archive: {n:,} NSE Issues on File" + (f", {span}" if span else "") + " | BrokerLens"
    description = (
        f"Archive of {n:,} NSE mainboard and SME IPO records on file" + (f" ({span})" if span else "") +
        f": issue prices, bidding and listing dates, and listing-day results where the exchange price history on file covers them. "
        f"Data as of {ipo_facts.fmt_date(as_of_iso)}."
    )[:295]

    crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", "/ipo/"), ("Archive", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "name": title,
                "url": canonical,
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "url": f"{site_url}/ipo/{r['symbol'].lower()}/",
                        "name": ipo_facts.display_name(r),
                    }
                    for i, r in enumerate(records[:100])
                ]
            },
            crumb_jsonld,
        ]
    }

    rows_html = ""
    for r in records:
        sym = r["symbol"].upper()
        slug = sym.lower()
        co = ipo_facts.display_name(r)
        status = ipo_facts.ipo_status(r, today_iso)
        pf_r = ipo_facts.price_facts(r)
        _ip = pf_r["issue_price"] or 0.0
        good_ld = ipo_facts.reliable_listing_date(r)
        perf = compute_listing_performance(sym, _ip, equity_history, good_ld)

        closed_str = _long_date(r.get("bidding_end")) or "-"
        if good_ld:
            list_str = _long_date(good_ld)
        elif ipo_facts.listing_date_state(r) == "inconsistent":
            list_str = "Inconsistent in feed"
        else:
            list_str = "-"
        ip_show = _ip or pf_r["single"]
        ip_str = _rs(ip_show) if ip_show else "-"

        gain_str = cmp_str = "-"
        if perf.get("has_listing_data"):
            lg_pct = perf["listing_gain_pct"]
            lg_cls = "var(--green)" if lg_pct >= 0 else "var(--red)"
            gain_str = f"<span style='color:{lg_cls};font-weight:600'>{lg_pct:+.1f}%</span>"
        if perf.get("has_current_data"):
            cmp_str = _rs(perf["cmp"])

        info = ipo_facts.subscription_info(r, status, as_of_iso)
        sub_str = f"{info['value']:.2f}x" if (info and info["final"]) else "-"

        rows_html += f"""
        <tr>
          <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
          <td><span class="badge">{_esc(status)}</span></td>
          <td class="right num">{_esc(ip_str)}</td>
          <td class="small">{_esc(closed_str)}</td>
          <td class="small">{_esc(list_str)}</td>
          <td class="right num">{gain_str}</td>
          <td class="right num">{_esc(cmp_str)}</td>
          <td class="right num font-semibold">{sub_str}</td>
        </tr>
        """

    body = head_template % {
        "title": _esc(title),
        "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }

    body += (
        crumb_html
        + '<h1 style="margin-top:0">Full IPO Historical Archive</h1>'
        + f'<p class="muted" style="max-width:75ch">{n:,} mainboard and SME IPO records on file from official NSE public-issue disclosures'
          + (f', {_esc(span)}' if span else '')
          + '. Earlier years are thin because the archive holds only what the NSE feed carries. Listing-day results and current prices appear only where the exchange price history on file covers them; a dash (-) means the value is not on file. '
          + f'Data as of {_esc(ipo_facts.fmt_date(as_of_iso))}. <a href="/ipo/" data-link>&larr; Back to active & upcoming IPOs</a></p>'
        + '<div class="table-scroll" style="margin-top:20px"><table class="data"><thead><tr>'
        + '<th>Company & Symbol</th><th>Status</th><th class="right">Issue Price</th>'
        + '<th>Bidding Closed</th><th>Listing Date</th><th class="right">Listing Open vs Issue Price</th><th class="right">Current Price</th><th class="right">Final Subscription</th>'
        + '</tr></thead><tbody>'
        + rows_html
        + '</tbody></table></div>'
    )

    body += foot_template % {
        "source_note": source_note_fn(
            "This page's historical facts and prices are sourced from NSE public issue disclosures."
        )
    }

    return body


def render_sme_ipo_hub(records, equity_history, head_template, foot_template,
                       breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in", ibsl_html=""):
    """Renders /ipo/sme/ dedicated hub for NSE Emerge and BSE SME public issues."""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of_iso = ipo_facts.data_as_of(today_iso)
    canonical = f"{site_url}/ipo/sme/"

    sme_records = [r for r in records if r.get("security_type") == "SME"]
    active, forthcoming, listed = [], [], []
    for r in sme_records:
        st = ipo_facts.ipo_status(r, today_iso)
        if st == "Active":
            active.append(r)
        elif st == "Forthcoming":
            forthcoming.append(r)
        elif st == "Listed" and ipo_facts.reliable_listing_date(r):
            listed.append(r)

    listed.sort(key=ipo_facts.reliable_listing_date, reverse=True)

    title = "SME IPOs in India: NSE Emerge and BSE SME Issues, Dates and Trading Rules | BrokerLens"
    description = (
        f"Track SME IPOs on NSE Emerge and BSE SME platforms: issue sizes, price bands, market-lot minimum investments, "
        f"and listing performance from official disclosures. Data as of {ipo_facts.fmt_date(as_of_iso)}."
    )[:295]
    fresh = _freshness_line(as_of_iso, today_iso)

    crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", "/ipo/"), ("SME IPOs", None)])

    faqs = [
        ("What is an SME IPO and how is it different from a Mainboard IPO?",
         "SME IPOs are public issues by small and medium enterprises listed on dedicated exchange platforms such as NSE Emerge or BSE SME. Unlike Mainboard IPOs with smaller retail bids, SME IPOs have a minimum application size of Rs 1,00,000 to Rs 1,50,000 and trade in fixed market lots."),
        ("What is the minimum investment in an SME IPO?",
         "Under SEBI regulations, the minimum application amount for an SME IPO is pegged to fixed price slabs, typically requiring a minimum investment of Rs 1,00,000 to Rs 1,50,000 per application lot."),
        ("Who provides liquidity in SME stocks post-listing?",
         "SEBI mandates that merchant bankers or registered market makers provide two-way quotes on the exchange for a minimum period of three years from the date of listing to ensure liquidity for investors."),
        ("Can SME companies migrate to the Mainboard exchange?",
         "Yes. An SME listed company can migrate to the mainboard of NSE or BSE after completing at least two years on the SME platform, subject to shareholder approval and meeting exchange net-worth and paid-up capital thresholds."),
    ]

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "name": title,
                "url": canonical,
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "url": f"{site_url}/ipo/{r['symbol'].lower()}/",
                        "name": ipo_facts.display_name(r)
                    }
                    for i, r in enumerate((active + forthcoming + listed)[:25])
                ]
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]
            },
            crumb_jsonld,
        ]
    }

    body = head_template % {
        "title": _esc(title),
        "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }

    active_rows = ""
    for r in active:
        sym = r["symbol"].upper()
        slug = sym.lower()
        co = ipo_facts.display_name(r)
        p_str = ipo_facts.band_text(r) or "Not on file"
        dates = ipo_facts.date_range_text(r.get("bidding_start"), r.get("bidding_end")) or "Not on file"
        active_rows += f"""
        <tr>
          <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
          <td><span class="badge badge-up">Active Now</span></td>
          <td class="right num">{_esc(p_str)}</td>
          <td class="right small">{_esc(dates)}</td>
          <td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">Bidding &amp; Details &rarr;</a></td>
        </tr>
        """

    forthcoming_rows = ""
    for r in forthcoming:
        sym = r["symbol"].upper()
        slug = sym.lower()
        co = ipo_facts.display_name(r)
        p_str = ipo_facts.band_text(r) or "Announced"
        d_start = _long_date(r.get("bidding_start")) or "Announced Soon"
        d_end = _long_date(r.get("bidding_end")) or "Announced Soon"
        forthcoming_rows += f"""
        <tr>
          <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
          <td><span class="badge badge-warn">Upcoming</span></td>
          <td class="right num">{_esc(p_str)}</td>
          <td class="right small">{_esc(d_start)}</td>
          <td class="right small">{_esc(d_end)}</td>
          <td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">View Issue &rarr;</a></td>
        </tr>
        """

    listed_rows = ""
    for r in listed[:25]:
        sym = r["symbol"].upper()
        slug = sym.lower()
        co = ipo_facts.display_name(r)
        ld = ipo_facts.reliable_listing_date(r)
        ip = ipo_facts.price_facts(r)["issue_price"]
        candle = ipo_facts.listing_candle(sym, ld, equity_history)
        open_p = candle["open"] if candle else None
        gain_str = "-"
        if open_p and ip:
            diff = open_p - ip
            pct = (diff / ip) * 100
            col = "var(--up)" if diff >= 0 else "var(--down)"
            gain_str = f"<span style='color:{col};font-weight:600'>+{pct:.1f}%</span>" if diff >= 0 else f"<span style='color:{col};font-weight:600'>{pct:.1f}%</span>"
        listed_rows += f"""
        <tr>
          <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
          <td class="right num">Rs {ipo_facts.fmt_price(ip)}</td>
          <td class="small">{_esc(_long_date(ld))}</td>
          <td class="right num">{gain_str}</td>
          <td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">View Performance &rarr;</a></td>
        </tr>
        """

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    body += (
        crumb_html
        + '<h1 style="margin-top:0">SME IPOs (NSE Emerge &amp; BSE SME)</h1>'
        + '<p class="muted" style="max-width:75ch">Track small and medium enterprise public issues from official exchange disclosures. SME IPOs feature fixed lot sizing, minimum application capital between Rs 1,00,000 and Rs 1,50,000, and mandatory 3-year market-maker liquidity support.</p>'
        + f'<p class="small muted" style="max-width:75ch;margin-top:-6px">{_esc(fresh)}</p>'
        + '<div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 24px 0">'
        + '<a href="/ipo/" class="btn btn-outline small">&larr; Mainboard IPO Hub</a>'
        + '<a href="/ipo/upcoming/" class="btn btn-outline small">Upcoming IPOs &rarr;</a>'
        + '<a href="/ipo/gmp/" class="btn btn-outline small">GMP Tracker &rarr;</a>'
        + '<a href="/ipo/subscription/" class="btn btn-outline small">Subscription Matrix &rarr;</a>'
        + '<a href="/ipo/allotment-status/" class="btn btn-outline small">Allotment Status &rarr;</a>'
        + '</div>'
        + '<div class="card" style="margin-bottom:24px;padding:16px 20px;background:rgba(0,82,254,0.05);border-left:4px solid #0052FE;border-radius:6px">'
        + '<strong>SME Investor Checklist:</strong> SME shares trade in designated market lots rather than single units. Ensure your demat account is activated for SME cash segment trading with your broker.'
        + '</div>'
        + '<h2 style="font-size:18px;margin-top:28px">SME Issues Open for Bidding</h2>'
        + (('<div class="table-scroll"><table class="data"><thead><tr><th>Company &amp; Symbol</th><th>Status</th><th class="right">Price Band</th><th class="right">Bidding Window</th><th class="center">Action</th></tr></thead><tbody>' + active_rows + '</tbody></table></div>') if active_rows else '<p class="small faint">No SME IPOs are currently open for bidding.</p>')
        + '<h2 style="font-size:18px;margin-top:32px">Upcoming SME Issues Announced</h2>'
        + (('<div class="table-scroll"><table class="data"><thead><tr><th>Company &amp; Symbol</th><th>Status</th><th class="right">Price Band</th><th class="right">Opening Date</th><th class="right">Closing Date</th><th class="center">Action</th></tr></thead><tbody>' + forthcoming_rows + '</tbody></table></div>') if forthcoming_rows else '<p class="small faint">No upcoming SME IPOs announced right now.</p>')
        + '<h2 style="font-size:18px;margin-top:32px">Recent SME Listings &amp; First-Day Results</h2>'
        + ('<div class="table-scroll"><table class="data"><thead><tr><th>Company &amp; Symbol</th><th class="right">Issue Price</th><th>Listing Date</th><th class="right">Listing Day Open vs Issue Price</th><th class="center">Action</th></tr></thead><tbody>' + listed_rows + '</tbody></table></div>')
        + '<div style="margin-top:36px"><h2 style="font-size:18px;margin-bottom:12px">SME IPO Frequently Asked Questions</h2>'
        + faq_html
        + '</div>'
    )

    body += foot_template % {
        "source_note": source_note_fn(
            "SME public issue records and dates are sourced from official NSE Emerge disclosures."
        )
    }
    return body


def render_gmp_hub(records, equity_history, head_template, foot_template,
                   breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in", ibsl_html=""):
    """Renders /ipo/gmp/ central Grey Market Premium tracker board."""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of_iso = ipo_facts.data_as_of(today_iso)
    canonical = f"{site_url}/ipo/gmp/"

    gmp_rows = []
    seen_syms = set()

    for r in records:
        sym = r.get("symbol", "").upper()
        if sym in seen_syms:
            continue
        gmp_info = ipo_facts.get_ipo_gmp(sym)
        if gmp_info:
            seen_syms.add(sym)
            pf = ipo_facts.price_facts(r)
            top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
            gmp_val = float(gmp_info.get("gmp", 0.0))
            est_p = (top + gmp_val) if top else 0.0
            gain_pct = ((gmp_val / top) * 100) if (top and top > 0) else 0.0
            st = ipo_facts.ipo_status(r, today_iso)
            gmp_rows.append({
                "symbol": sym,
                "company": ipo_facts.display_name(r),
                "slug": sym.lower(),
                "status": st,
                "price_band": ipo_facts.band_text(r) or (f"Rs {top}" if top else "Announced Soon"),
                "top": top,
                "gmp": gmp_val,
                "est_listing": est_p,
                "gain_pct": gain_pct,
                "kostak": gmp_info.get("kostak"),
                "trend": gmp_info.get("trend", "up"),
                "last_updated": gmp_info.get("last_updated", as_of_iso),
            })

    gmp_rows.sort(key=lambda x: x["gain_pct"], reverse=True)

    title = "IPO GMP Today: Live Grey Market Premium, Kostak Rates and Estimated Listing Gains | BrokerLens"
    description = (
        "Track live Grey Market Premium (GMP) estimates, Kostak rates, subject-to-sauda quotes, and estimated listing prices "
        "for upcoming and open IPOs with strict regulatory safeguards."
    )[:295]
    fresh = _freshness_line(as_of_iso, today_iso)

    crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", "/ipo/"), ("GMP Tracker", None)])

    faqs = [
        ("What is IPO Grey Market Premium (GMP)?",
         "Grey Market Premium (GMP) is an unofficial, off-exchange rate at which IPO applications or shares trade between buyers and sellers before official stock exchange listing. A positive GMP indicates buyer enthusiasm above the issue price, while a negative discount indicates soft demand."),
        ("Does GMP guarantee listing day profits?",
         "No. GMP is an informal observation with zero regulatory oversight. It is influenced by localized sentiment and can fluctuate sharply before listing. Official listing day prices are determined by the exchange pre-open call auction mechanism on the listing morning."),
        ("What is the difference between Kostak rate and GMP?",
         "GMP is the premium expected per share. Kostak rate is the fixed lump-sum profit agreed for selling an entire IPO retail application before allotment, irrespective of whether the application gets allotted shares."),
        ("How can I apply for an IPO online?",
         "You can apply for any open IPO online using UPI 2.0 ASBA through leading SEBI-registered brokers such as Zerodha, Angel One, Dhan, or Upstox with zero application fees."),
    ]

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "name": title,
                "url": canonical,
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "url": f"{site_url}/ipo/{row['slug']}/",
                        "name": f"{row['company']} IPO GMP"
                    }
                    for i, row in enumerate(gmp_rows)
                ]
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]
            },
            crumb_jsonld,
        ]
    }

    body = head_template % {
        "title": _esc(title),
        "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }

    table_rows = ""
    for row in gmp_rows:
        slug = row["slug"]
        co = row["company"]
        sym = row["symbol"]
        p_band = row["price_band"]
        gmp_val = row["gmp"]
        est_p = row["est_listing"]
        gain_pct = row["gain_pct"]
        trend = row["trend"]
        updated = row["last_updated"]
        kostak = row["kostak"]

        trend_pill = '<span style="color:var(--up);font-weight:600">&uarr; Rising</span>' if trend == "up" else ('<span style="color:var(--down);font-weight:600">&darr; Soft</span>' if trend == "down" else '<span class="faint">&bull; Steady</span>')
        gain_str = f"<span style='color:var(--up);font-weight:700'>+{gain_pct:.1f}%</span>" if gain_pct > 0 else f"<span class='faint'>{gain_pct:.1f}%</span>"
        kostak_str = f"Rs {kostak}" if kostak else "-"

        table_rows += f"""
        <tr>
          <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
          <td class="right num">{_esc(p_band)}</td>
          <td class="right num font-semibold" style="color:var(--up)">+Rs {gmp_val:,.1f}</td>
          <td class="right num font-semibold">{f'Rs {est_p:,.1f}' if est_p else 'Awaited'}</td>
          <td class="right num">{gain_str}</td>
          <td class="right num small">{kostak_str}</td>
          <td class="center small">{trend_pill}</td>
          <td class="small faint">{_esc(updated)}</td>
          <td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">View GMP Details &rarr;</a></td>
        </tr>
        """

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    body += (
        crumb_html
        + '<h1 style="margin-top:0">IPO GMP Today: Live Grey Market Premium Tracker</h1>'
        + '<p class="muted" style="max-width:75ch">Track indicative Grey Market Premium (GMP) estimates, expected listing prices, Kostak rates, and market sentiment for upcoming and open IPOs. Published with strict transparency safeguards alongside official subscription disclosures.</p>'
        + f'<p class="small muted" style="max-width:75ch;margin-top:-6px">{_esc(fresh)}</p>'
        + '<div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 24px 0">'
        + '<a href="/ipo/" class="btn btn-outline small">&larr; Mainboard IPO Hub</a>'
        + '<a href="/ipo/upcoming/" class="btn btn-outline small">Upcoming IPOs &rarr;</a>'
        + '<a href="/ipo/sme/" class="btn btn-outline small">SME IPOs (NSE Emerge) &rarr;</a>'
        + '<a href="/ipo/subscription/" class="btn btn-outline small">Subscription Matrix &rarr;</a>'
        + '<a href="/ipo/allotment-status/" class="btn btn-outline small">Allotment Status &rarr;</a>'
        + '</div>'
        + '<div class="card" style="margin-bottom:24px;padding:16px 20px;background:rgba(239,68,68,0.05);border-left:4px solid var(--accent);border-radius:6px">'
        + '<strong>Mandatory Regulatory Notice:</strong> Grey Market Premium (GMP) is an unofficial, off-exchange indicative market observation with zero regulatory oversight. It is not an exchange-verified price, not endorsed by SEBI or stock exchanges, and does not guarantee listing returns. BrokerLens publishes observed market indications for transparency alongside official subscription figures and fundamental offer document disclosures.'
        + '</div>'
        + '<div class="table-scroll"><table class="data"><thead><tr>'
        + '<th>Company &amp; Symbol</th><th class="right">Price Band</th><th class="right">Current GMP</th><th class="right">Estimated Listing Price</th>'
        + '<th class="right">Estimated Gain</th><th class="right">Kostak</th><th class="center">Trend</th><th>Updated</th><th class="center">Action</th>'
        + '</tr></thead><tbody>'
        + table_rows
        + '</tbody></table></div>'
        + '<div style="margin-top:36px"><h2 style="font-size:18px;margin-bottom:12px">Frequently Asked Questions About IPO GMP</h2>'
        + faq_html
        + '</div>'
    )

    body += foot_template % {
        "source_note": source_note_fn(
            "Grey market estimates are indicative off-exchange observations compiled for investor transparency."
        )
    }
    return body
