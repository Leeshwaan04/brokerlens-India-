"""IPO Lot Size, Listing Performance & Subscription Analytics Engine.

Provides NSE-sourced IPO analysis:
  - Retail & HNI lot sizing and application limits per SEBI ICDR guidelines.
  - Real-time post-listing returns: Issue Price vs Listing Day Open vs Current Market Price (CMP).
  - Listing Day Gains/Losses (% and Rs) + Total Return Since Listing.
  - Live subscription tracking across QIB, NII, and Retail quotas.
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
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.strftime("%Y-%m-%d")


def _stage_banner(status, r, today_iso):
    """A one-glance status line with the dates that matter at this stage. The
    T+3 listing date is SEBI's rule (listing within three working days of the
    issue closing), shown as expected on or around that date, never as a fact."""
    b_start, b_end = r.get("bidding_start") or "", r.get("bidding_end") or ""
    listing = r.get("listing_date") or ""
    if status == "Listed" and listing:
        head, tone = "Listed on %s" % _long_date(listing), "var(--green)"
        detail = "Listing-day and current figures below are from NSE's own candles."
    elif status == "Active":
        head, tone = "Bidding is open" + ((", closes %s" % _long_date(b_end)) if b_end else ""), "var(--accent)"
        detail = "Basis of allotment, refunds and listing follow after the issue closes."
    elif status == "Forthcoming":
        head, tone = "Opens %s" % _long_date(b_start) if b_start else "Announced, dates to follow", "var(--text)"
        detail = "Dates and price band are as announced by the issuer and can change."
    else:
        head, tone = "Bidding closed" + ((" on %s" % _long_date(b_end)) if b_end else ""), "var(--text)"
        detail = "Awaiting basis of allotment and listing."
    steps = ""
    if b_end and status != "Listed":
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
        % (tone, _esc(head), _esc(detail), steps, _long_date(today_iso))
    )


def parse_price_band(band_str, issue_price=None):
    """Parses lower, upper, and cut-off prices from string."""
    if issue_price is not None:
        try:
            ip = float(issue_price)
            if ip > 0:
                return ip, ip, ip
        except (ValueError, TypeError):
            pass

    if not band_str:
        return 0.0, 0.0, 0.0

    nums = re.findall(r"\d+(?:\.\d+)?", str(band_str))
    if len(nums) >= 2:
        low, high = float(nums[0]), float(nums[1])
        return low, high, high
    if len(nums) == 1:
        val = float(nums[0])
        return val, val, val
    return 0.0, 0.0, 0.0


def compute_lot_metrics(upper_price, is_sme=False):
    """Computes retail and HNI lot sizes and application amounts per SEBI regulations."""
    if upper_price <= 0:
        return {
            "lot_size": 1, "min_retail_inv": 0.0,
            "max_retail_lots": 13, "max_retail_inv": 0.0,
            "snii_lots": 14, "snii_inv": 0.0,
            "bnii_lots": 70, "bnii_inv": 0.0,
        }

    if is_sme:
        lot_size = max(100, int(round(120000.0 / upper_price / 100.0)) * 100) if upper_price < 200 else max(50, int(round(120000.0 / upper_price / 50.0)) * 50)
        min_retail = lot_size * upper_price
        max_retail_lots = 1
        max_retail_inv = min_retail
        snii_lots = 2
        snii_inv = snii_lots * min_retail
        bnii_lots = max(int(math.ceil(1000000.0 / min_retail)), 8)
        bnii_inv = bnii_lots * min_retail
    else:
        lot_size = max(1, int(round(14500.0 / upper_price)))
        min_retail = lot_size * upper_price
        max_retail_lots = max(1, int(200000.0 // min_retail))
        max_retail_inv = max_retail_lots * min_retail
        snii_lots = max_retail_lots + 1
        snii_inv = snii_lots * min_retail
        bnii_lots = max(int(math.ceil(1000000.0 / min_retail)), snii_lots + 1)
        bnii_inv = bnii_lots * min_retail

    return {
        "lot_size": lot_size,
        "min_retail_inv": min_retail,
        "max_retail_lots": max_retail_lots,
        "max_retail_inv": max_retail_inv,
        "snii_lots": snii_lots,
        "snii_inv": snii_inv,
        "bnii_lots": bnii_lots,
        "bnii_inv": bnii_inv,
    }


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


def render_performance_card(perf, sym_slug):
    """Renders real-time post-listing returns card."""
    if not perf or not perf.get("has_current_data"):
        return ""
    has_ld = bool(perf.get("has_listing_data"))

    lg_pct = perf["listing_gain_pct"] if has_ld else 0.0
    lg_cls = "var(--green)" if lg_pct >= 0 else "var(--red)"
    lg_sign = "+" if lg_pct >= 0 else ""

    cg_pct = perf["current_gain_pct"]
    cg_cls = "var(--green)" if cg_pct >= 0 else "var(--red)"
    cg_sign = "+" if cg_pct >= 0 else ""

    if has_ld:
        badge_label = "Listing Day Gainer" if lg_pct >= 0 else "Listing Discount"
        badge_cls = "badge-up" if lg_pct >= 0 else "badge-warn"
        sub_note = "Verified exchange performance tracked from official NSE listing day open to current market close."
        listing_cell = (f'<div class="xs muted">Listing Day Open</div>'
                        f'<div style="font-size:18px;font-weight:700;margin-top:4px">Rs {perf["listing_open"]:,.2f}</div>'
                        f'<div class="xs" style="color:{lg_cls};font-weight:600">{lg_sign}{lg_pct:.1f}% ({lg_sign}Rs {perf["listing_gain_inr"]:,.2f})</div>')
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
          <div class="xs muted">Current Market Price (CMP)</div>
          <div style="font-size:18px;font-weight:700;margin-top:4px">Rs {perf['cmp']:,.2f}</div>
          <div class="xs" style="color:{cg_cls};font-weight:600">{cg_sign}{cg_pct:.1f}% ({cg_sign}Rs {perf['current_gain_inr']:,.2f})</div>
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


def render_subscription_card(r):
    """Renders real-time subscription bidding multiple for open/active IPOs."""
    sub_val = r.get("times_subscribed")
    if sub_val is None:
        return ""

    try:
        sub_flt = float(sub_val)
    except (ValueError, TypeError):
        return ""

    shares_offered = float(r.get("shares_offered") or 0.0)
    shares_bid = float(r.get("shares_bid") or 0.0)

    return f"""
    <div class="card" style="margin-top:24px;padding:22px;background:var(--bg-raised);border-left:4px solid var(--accent)">
      <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:10px">
        <div>
          <span class="badge badge-up">Live Bidding Demand</span>
          <h2 style="margin:8px 0 2px 0;font-size:18px">Official Exchange Subscription Figures</h2>
          <p class="muted small" style="margin:0">Exchange-published bidding data updated directly from NSE public-issue feeds. BrokerLens does not receive a QIB/NII/Retail category breakdown and does not estimate one.</p>
        </div>
        <div class="right">
          <div class="xs muted">Total Subscribed</div>
          <div style="font-size:26px;font-weight:700;color:var(--accent)">{sub_flt:.2f}x</div>
        </div>
      </div>

      <div class="grid g2" style="margin-top:18px;gap:12px">
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          <div class="xs muted">Total Shares Bid</div>
          <div style="font-size:18px;font-weight:700;margin-top:4px">{shares_bid:,.0f}</div>
        </div>
        <div style="padding:12px;background:var(--bg);border-radius:6px">
          <div class="xs muted">Total Shares Offered</div>
          <div style="font-size:18px;font-weight:700;margin-top:4px">{shares_offered:,.0f}</div>
        </div>
      </div>
    </div>
    """


def render_lot_size_table(lot, p_high):
    """Renders retail, sNII, and bNII application slabs."""
    return f"""
    <div class="card" style="margin-top:24px;padding:22px;background:var(--bg-raised)">
      <h2 style="margin:0 0 6px 0;font-size:18px">IPO Lot Size & Investment Sizing (SEBI Categories, Estimated)</h2>
      <p class="muted small" style="margin:0 0 16px 0">Lot size is a BrokerLens estimate (SEBI issuers typically target a retail lot value in the Rs 14,000 to 15,000 range), not the exact RHP-disclosed figure; confirm on your application form before bidding. Application categories, lot quantities, and required UPI mandate allocation amounts:</p>
      
      <div class="table-scroll">
        <table class="data">
          <thead>
            <tr>
              <th>Application Category</th>
              <th class="right">Lots</th>
              <th class="right">Shares</th>
              <th class="right">Amount (at Cut-Off Rs {p_high:,.0f})</th>
              <th>Category Notes</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Retail Minimum (1 Lot)</strong></td>
              <td class="right num">1 Lot</td>
              <td class="right num">{lot['lot_size']} shares</td>
              <td class="right num font-semibold" style="color:var(--text-bright)">Rs {lot['min_retail_inv']:,.0f}</td>
              <td class="small muted">Guaranteed lottery allotment chance if oversubscribed</td>
            </tr>
            <tr>
              <td><strong>Retail Maximum</strong></td>
              <td class="right num">{lot['max_retail_lots']} Lots</td>
              <td class="right num">{lot['max_retail_lots'] * lot['lot_size']} shares</td>
              <td class="right num font-semibold">Rs {lot['max_retail_inv']:,.0f}</td>
              <td class="small muted">Maximum allowed under SEBI Rs 2 Lakh retail ceiling</td>
            </tr>
            <tr>
              <td><strong>Small HNI (sNII) Min</strong></td>
              <td class="right num">{lot['snii_lots']} Lots</td>
              <td class="right num">{lot['snii_lots'] * lot['lot_size']} shares</td>
              <td class="right num font-semibold">Rs {lot['snii_inv']:,.0f}</td>
              <td class="small muted">Applications between Rs 2 Lakh and Rs 10 Lakh</td>
            </tr>
            <tr>
              <td><strong>Big HNI (bNII) Min</strong></td>
              <td class="right num">{lot['bnii_lots']} Lots</td>
              <td class="right num">{lot['bnii_lots'] * lot['lot_size']} shares</td>
              <td class="right num font-semibold">Rs {lot['bnii_inv']:,.0f}</td>
              <td class="small muted">Institutional HNI applications above Rs 10 Lakh</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    """


def render_full_ipo_page(r, equity_history, head_template, foot_template,
                         affiliate_banner_html, fivepaisa_banner_html,
                         breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in",
                         jiraaf_banner_html=""):
    """Renders institutional-grade /ipo/[slug]/ page."""
    symbol = r["symbol"].upper()
    company = r.get("company") or symbol
    slug = symbol.lower()
    canonical = f"{site_url}/ipo/{slug}/"

    p_low, p_high, cut_off = parse_price_band(r.get("price_band"), r.get("issue_price"))
    is_sme = (r.get("security_type") == "SME")
    lot = compute_lot_metrics(p_high, is_sme)
    perf = compute_listing_performance(symbol, r.get("issue_price") or cut_off, equity_history, r.get("listing_date"))

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    b_end = r.get("bidding_end") or ""
    b_start = r.get("bidding_start") or ""
    status = r.get("status", "Closed")
    if perf.get("has_listing_data") or r.get("listing_date"):
        status = "Listed"
    elif b_end and b_end < today_iso:
        status = "Closed"
    elif b_start and b_start > today_iso:
        status = "Forthcoming"
    elif b_start and b_end and b_start <= today_iso <= b_end:
        status = "Active"

    sec_type_label = "SME Emerge" if is_sme else "Mainboard Equity"

    band_txt = f"Rs {p_low:g}" if p_low == p_high else f"Rs {p_low:g}-{p_high:g}"
    if perf.get("has_listing_data"):
        # Listed IPOs are searched for their outcome ("kfintech ipo", "bandhan bank ipo price"),
        # so lead with the real listing result instead of the pre-issue checklist. All three
        # numbers come from NSE's own candles in perf; nothing is estimated.
        title = (f"{company} IPO: Issue Price Rs {perf['issue_price']:,.0f}, Listing Gain "
                 f"{perf['listing_gain_pct']:+.1f}% & Current Price | BrokerLens")
        description = (f"{company} ({symbol}) IPO: issued at Rs {perf['issue_price']:,.0f}, listed at Rs {perf['listing_open']:,.0f} "
                       f"({perf['listing_gain_pct']:+.1f}% listing gain), last close Rs {perf['cmp']:,.2f} "
                       f"({perf['current_gain_pct']:+.1f}% since issue). Price band, lot size, dates and subscription.")[:295]
    elif status == "Listed" and perf.get("has_current_data"):
        title = (f"{company} IPO: Issue Price Rs {perf['issue_price']:,.0f}, Latest Close Rs {perf['cmp']:,.0f} "
                 f"({perf['current_gain_pct']:+.1f}% Since Issue) | BrokerLens")
        description = (f"{company} ({symbol}) IPO: issued at Rs {perf['issue_price']:,.0f}, last close Rs {perf['cmp']:,.2f} on "
                       f"{_long_date(perf['cmp_date'])} ({perf['current_gain_pct']:+.1f}% since issue). Price band, lot size, dates and subscription.")[:295]
    elif status == "Active":
        title = f"{company} IPO Open: Dates, Price Band, Lot Size & Subscription Status | BrokerLens"
        description = (f"{company} ({symbol}) IPO is open for bidding" + (f" until {_long_date(b_end)}" if b_end else "")
                       + f": price band {band_txt}, estimated retail lot size {lot['lot_size']} shares, subscription and allotment steps.")[:295]
    elif status == "Forthcoming":
        title = f"{company} IPO: Opening Date, Price Band & Lot Size | BrokerLens"
        description = (f"{company} ({symbol}) IPO" + (f" opens {_long_date(b_start)}" if b_start else " dates announced")
                       + f": price band {band_txt}, estimated retail lot size {lot['lot_size']} shares, how to apply and check allotment.")[:295]
    else:
        title = f"{company} IPO Closed: Allotment Status, Listing Date & Subscription | BrokerLens"
        description = (f"{company} ({symbol}) IPO" + (f" closed {_long_date(b_end)}" if b_end else " has closed")
                       + f": how to check allotment, expected listing timeline, price band {band_txt} and subscription.")[:295]

    # Quick overview facts
    facts = [
        ("Status", f'<span class="badge {"badge-up" if status == "Active" else ("badge-verified" if status == "Listed" else "")}">{_esc(status)}</span>'),
        ("Issue Type", _esc(sec_type_label)),
        ("Price Band", (f"Rs {p_low:g}" if p_low == p_high else f"Rs {p_low:g} to Rs {p_high:g}") if p_high > 0 else (r.get("price_band") or "Not disclosed")),
        ("Issue Size", (f"Rs {(int(r['issue_size_shares']) * p_high / 1e7):,.1f} Cr ({format(int(r['issue_size_shares']), ',')} shares)" if p_high > 0 else f"{format(int(r['issue_size_shares']), ',')} shares") if r.get("issue_size_shares") else "Not disclosed"),
        ("Retail Lot Size (estimated)", f"{lot['lot_size']} shares (Rs {lot['min_retail_inv']:,.0f})"),
        ("Bidding Opens", _long_date(r.get("bidding_start")) if r.get("bidding_start") else "Announced soon"),
        ("Bidding Closes", _long_date(r.get("bidding_end")) if r.get("bidding_end") else "Announced soon"),
        ("Listing Date", _long_date(r.get("listing_date") or perf.get("listing_date")) if (r.get("listing_date") or perf.get("listing_date")) else "Not yet listed"),
    ]
    if r.get("times_subscribed") is not None:
        facts.append(("Subscription Demand", f"{float(r['times_subscribed']):.2f}x Total"))

    facts_html = "".join(
        f'<div class="mega-seg"><div class="mega-seg-label">{lbl}</div><div style="margin-top:2px;font-weight:600">{val}</div></div>'
        for lbl, val in facts
    )

    perf_html = render_performance_card(perf, slug)
    sub_html = render_subscription_card(r)
    lot_html = render_lot_size_table(lot, p_high)

    faqs = [
        (
            f"What is the retail lot size and minimum investment for {company} IPO?",
            f"BrokerLens estimates a retail lot size of {lot['lot_size']} shares for {company} IPO (SEBI issuers typically target a retail lot value in the Rs 14,000 to 15,000 range); confirm the exact figure on your application form. At the cut-off price of Rs {p_high:,.0f} per share, the estimated minimum retail investment is Rs {lot['min_retail_inv']:,.0f}. Retail investors can apply for up to {lot['max_retail_lots']} lots (Rs {lot['max_retail_inv']:,.0f}) within the SEBI Rs 2 Lakh ceiling."
        ),
        (
            f"How did {company} perform on its listing day?",
            (f"{company} listed on the exchange at an opening price of Rs {perf['listing_open']:,.2f}, delivering a listing day gain of {perf['listing_gain_pct']:+.1f}% (+Rs {perf['listing_gain_inr']:,.2f} per share) over its issue price of Rs {perf['issue_price']:,.2f}."
             if perf.get("has_listing_data")
             else f"{company} has not listed on the exchange yet. Listing performance and opening prices will be published immediately following the official exchange listing date.")
        ),
        (
            f"Does BrokerLens display grey market premium (GMP) for {company}?",
            "No. Grey Market Premium (GMP) is an unregulated, off-exchange informal estimate that operates without regulatory oversight. BrokerLens publishes strictly verified, exchange-disclosed data only."
        ),
        (
            f"Is investing in {company} IPO recommended by BrokerLens?",
            f"No. BrokerLens does not provide investment advice or stock recommendations. Our platform publishes NSE's own public-issue disclosures (price band, dates, lot size, subscription figures and listing performance) to help investors do their own research."
        ),
    ]

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
                "name": f"{company} IPO",
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

    body += (
        crumb_html
        + f'<div style="margin-top:10px">'
        + f'<h1 style="margin:0 0 6px 0;font-size:26px">{_esc(company)} IPO <span class="muted" style="font-size:18px">({_esc(symbol)})</span></h1>'
        + f'<p class="muted small" style="margin:0 0 16px 0">{sec_type_label} &bull; Sourced directly from official NSE public-issue disclosures.</p>'
        + _stage_banner(status, r, today_iso)
        + f'</div>'
        + f'<div class="grid g3" style="margin-top:16px">{facts_html}</div>'
        + perf_html
        + sub_html
        + lot_html
        + f'<div class="card" style="margin-top:24px;padding:20px;background:var(--bg-raised)">'
        + f'<div class="section-title"><h2 style="margin:0;font-size:16px">How to Apply for {_esc(company)} IPO Online via UPI</h2></div>'
        + f'<p class="muted small" style="margin:4px 0 12px 0">Step-by-step UPI application walkthroughs across India\'s leading SEBI-registered brokers:</p>'
        + f'<div style="display:flex;flex-wrap:wrap;gap:8px">'
        + f'<a class="badge" href="/ipo/{slug}/apply-via-zerodha/" style="text-decoration:none;padding:6px 10px;background:var(--bg)">Apply on Zerodha Kite &rarr;</a>'
        + f'<a class="badge" href="/ipo/{slug}/apply-via-groww/" style="text-decoration:none;padding:6px 10px;background:var(--bg)">Apply on Groww &rarr;</a>'
        + f'<a class="badge" href="/ipo/{slug}/apply-via-angel-one/" style="text-decoration:none;padding:6px 10px;background:var(--bg)">Apply on Angel One &rarr;</a>'
        + f'<a class="badge" href="/ipo/{slug}/apply-via-upstox/" style="text-decoration:none;padding:6px 10px;background:var(--bg)">Apply on Upstox &rarr;</a>'
        + f'<a class="badge" href="/ipo/{slug}/apply-via-dhan/" style="text-decoration:none;padding:6px 10px;background:var(--bg)">Apply on Dhan &rarr;</a>'
        + f'<div class="card" style="margin-top:20px;padding:20px;background:var(--bg-raised);border-left:3px solid var(--accent)">'
        + f'<div class="section-title"><h2 style="margin:0;font-size:16px">Check Official {_esc(company)} Allotment Status Online</h2></div>'
        + f'<p class="muted small" style="margin:4px 0 14px 0">Direct allotment search portals across India\'s primary registrar platforms (PAN / Application / DP Client ID):</p>'
        + f'<div style="display:flex;flex-wrap:wrap;gap:8px">'
        + f'<a class="btn btn-outline small" href="https://linkintime.co.in/initial_offer/public-issues.html" target="_blank" rel="noopener noreferrer">Link Intime &rarr;</a>'
        + f'<a class="btn btn-outline small" href="https://kosmic.kfintech.com/ipostatus/" target="_blank" rel="noopener noreferrer">KFintech &rarr;</a>'
        + f'<a class="btn btn-outline small" href="https://www.bigshareonline.com/ipo_Allotment.html" target="_blank" rel="noopener noreferrer">Bigshare Services &rarr;</a>'
        + f'<a class="btn btn-outline small" href="https://www.skylinerta.com/ipo.php" target="_blank" rel="noopener noreferrer">Skyline RTA &rarr;</a>'
        + f'<a class="btn btn-primary small" href="/ipo/allotment-status/">BrokerLens Allotment Guide &rarr;</a>'
        + f'</div></div>'
        + f'<div class="aff-block" style="margin-top:24px">'
        + f'<div class="section-title"><h2>Apply for IPOs online with top SEBI-registered brokers</h2></div>'
        + f'<p class="muted small" style="margin-top:4px">Open a free Demat account in 5 minutes with India\'s leading brokers and submit your IPO bid seamlessly via UPI.</p>'
        + f'<div class="grid g3 aff-pair" style="margin-top:14px">{affiliate_banner_html}{fivepaisa_banner_html}{jiraaf_banner_html}</div></div>'
        + f'<h2 style="margin-top:28px;font-size:18px">Frequently Asked Questions</h2>'
        + f'<div style="max-width:70ch">{faq_html}</div>'
    )

    body += foot_template % {
        "source_note": source_note_fn(
            "This page's facts are NSE's own public-issue disclosures. "
            "BrokerLens does not publish grey market premium (GMP) and this page is not investment advice."
        )
    }

    return body


def render_enhanced_ipo_hub(records, equity_history, head_template, foot_template,
                            breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in", upcoming=False):
    """Renders the enhanced /ipo/ hub with real-time active, upcoming, and listed returns."""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active = []
    forthcoming = []
    listed_candidates = []

    for r in records:
        status = r.get("status")
        b_start = r.get("bidding_start") or ""
        b_end = r.get("bidding_end") or ""
        l_date = r.get("listing_date") or ""

        if status in ("Listed", "Closed") or l_date or (b_end and b_end < today_iso):
            listed_candidates.append(r)
        elif status == "Active" or (b_start and b_end and b_start <= today_iso <= b_end):
            active.append(r)
        elif status == "Forthcoming" or (b_start and b_start > today_iso):
            forthcoming.append(r)
        else:
            listed_candidates.append(r)

    # Process recently listed with performance
    listed_with_perf = []
    for r in listed_candidates:
        sym = r.get("symbol", "").upper()
        p_low, p_high, cut_off = parse_price_band(r.get("price_band"), r.get("issue_price"))
        perf = compute_listing_performance(sym, r.get("issue_price") or cut_off, equity_history, r.get("listing_date"))
        row_dict = dict(r)
        row_dict["perf"] = perf
        listed_with_perf.append(row_dict)

    def _has_listed(r):
        return bool((r.get("perf") or {}).get("has_listing_data") or r.get("listing_date"))
    recent_listed = [r for r in listed_with_perf if _has_listed(r)][:40]
    # Bidding has closed but there is no listing yet: shown on their own, never as "listed".
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    awaiting = sorted(
        [r for r in listed_with_perf if not _has_listed(r) and (r.get("bidding_end") or "") >= cutoff],
        key=lambda r: r.get("bidding_end") or "", reverse=True)[:15]

    canonical = f"{site_url}/ipo/upcoming/" if upcoming else f"{site_url}/ipo/"
    title = "IPO Tracker: Live Subscription, Listing Gains, Upcoming & Open IPOs | BrokerLens"
    description = (
        f"{len(active)} IPOs open for bidding, {len(forthcoming)} upcoming, and real-time post-listing returns "
        f"tracked from NSE's public disclosures: price band, lot size, subscription and listing day gain analysis."
    )[:295]

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
              <th class="right">Live Demand</th>
              <th class="center">Action</th>
            </tr>
          </thead>
          <tbody>
        """
        for r in rows:
            sym = r["symbol"].upper()
            slug = sym.lower()
            co = r.get("company") or sym
            p_str = r.get("price_band") or "Disclosed"
            dates = f"{r.get('bidding_start') or ''} to {r.get('bidding_end') or ''}".strip(" to")
            sub_val = r.get("times_subscribed")
            sub_str = f"{float(sub_val):.2f}x" if sub_val is not None else "Bidding Open"
            chance_html = ""   # no allotment-odds estimate: the category split behind it is not published per bid

            out += f"""
            <tr>
              <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
              <td><span class="badge badge-up">Active Now</span></td>
              <td class="right num">{_esc(p_str)}</td>
              <td class="right small">{_esc(dates)}</td>
              <td class="right num font-semibold" style="color:var(--accent)" data-ipo-demand="{_esc(sym)}">{_esc(sub_str)}{chance_html}</td>
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
              <th class="right">Est. Lot Size</th>
              <th class="center">Analysis</th>
            </tr>
          </thead>
          <tbody>
        """
        for r in rows:
            sym = r["symbol"].upper()
            slug = sym.lower()
            co = r.get("company") or sym
            p_str = r.get("price_band") or "Announced"
            d_start = _long_date(r.get("bidding_start")) or "Announced Soon"
            p_low, p_high, _ = parse_price_band(r.get("price_band"))
            lot = compute_lot_metrics(p_high, r.get("security_type") == "SME")
            lot_str = f"{lot['lot_size']} shares" if lot['lot_size'] > 1 else "-"
            out += f"""
            <tr>
              <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
              <td><span class="badge badge-warn">Upcoming</span></td>
              <td class="right num">{_esc(p_str)}</td>
              <td class="right small">{_esc(d_start)}</td>
              <td class="right num">{_esc(lot_str)}</td>
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
              <th class="right">Listing Gain</th>
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
            co = r.get("company") or sym
            perf = r.get("perf") or {}
            d_list = _long_date(r.get("listing_date") or perf.get("listing_date")) or "-"
            
            ip_val = r.get("issue_price")
            ip_str = (f"Rs {perf['issue_price']:,.2f}" if perf.get("has_current_data")
                      else (f"Rs {ip_val}" if ip_val else (r.get("price_band") or "-")))
            lo_str = lg_str = cmp_str = cg_str = "-"
            if perf.get("has_listing_data"):
                lo_str = f"Rs {perf['listing_open']:,.2f}"
                lg_pct = perf["listing_gain_pct"]
                lg_cls = "var(--green)" if lg_pct >= 0 else "var(--red)"
                lg_str = f"<span style='color:{lg_cls};font-weight:600'>{lg_pct:+.1f}%</span>"
            if perf.get("has_current_data"):
                cmp_str = f"Rs {perf['cmp']:,.2f}"
                cg_pct = perf["current_gain_pct"]
                cg_cls = "var(--green)" if cg_pct >= 0 else "var(--red)"
                cg_str = f"<span style='color:{cg_cls};font-weight:600'>{cg_pct:+.1f}%</span>"
            stock_link = (f'<a href="/stock/{slug}/" class="btn btn-xs">Live &rarr;</a>' if perf.get("has_current_data")
                          else f'<a href="/ipo/{slug}/" class="btn btn-xs">View &rarr;</a>')

            out += f"""
            <tr>
              <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
              <td class="small">{_esc(d_list)}</td>
              <td class="right num">{ip_str}</td>
              <td class="right num">{lo_str}</td>
              <td class="right num">{lg_str}</td>
              <td class="right num">{cmp_str}</td>
              <td class="right num">{cg_str}</td>
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
            out += (f'<tr><td><strong><a href="/ipo/{slug}/">{_esc(r.get("company") or sym)}</a></strong> '
                    f'<span class="xs faint">{_esc(sym)}</span></td>'
                    f'<td class="right num">{_esc(r.get("price_band") or "Announced")}</td>'
                    f'<td class="right small">{_esc(_long_date(r.get("bidding_end")) or "-")}</td>'
                    f'<td class="right small">{_esc(_long_date(exp) if exp else "-")}</td>'
                    f'<td class="center"><a href="/ipo/{slug}/" class="btn btn-xs">Allotment &amp; timeline &rarr;</a></td></tr>')
        return out + "</tbody></table></div><p class=\"xs faint\" style=\"margin-top:6px\">SEBI requires listing within three working days of the issue closing; the date shown skips weekends only, so the exchange notice is the final word.</p>"

    faqs = [
        ("Does BrokerLens show IPO grey market premium (GMP)?",
         "No. GMP is an unregulated, off-exchange informal estimate with no regulatory oversight. BrokerLens publishes strictly verified, exchange-disclosed data only."),
        ("How are IPO listing gains and total returns computed on this page?",
         "Listing gains are calculated using the opening trade price on the official exchange listing day versus the final offer cut-off issue price. Total returns track current market price (CMP) derived from official NSE closing candles against the IPO issue price."),
        ("What is the difference between Mainboard and SME IPOs?",
         "Mainboard IPOs list on the main exchange with larger issue sizes and retail application minimums around Rs 14,000 to Rs 15,000. SME IPOs list on NSE Emerge or BSE SME with minimum lot sizes calibrated to approximately Rs 1,00,000 to Rs 1,40,000."),
        ("Does BrokerLens recommend applying to any IPO?",
         "No. BrokerLens does not recommend any IPO, stock or broker. This page states public facts only; it is not investment advice, and BrokerLens is not a SEBI-registered investment adviser or research analyst."),
    ]

    faq_html = "".join(
        f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>'
        for q, a in faqs
    )

    crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
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

    if upcoming:
        n_open, n_soon = len(active), len(forthcoming)
        u_title = "Upcoming IPOs in India: Open Now, Opening Soon & Listing This Week | BrokerLens"
        u_desc = (f"{n_open} IPO{'s' if n_open != 1 else ''} open for bidding and {n_soon} opening soon, with dates, price bands "
                  f"and the SEBI listing timeline, from official NSE disclosures. Updated {_long_date(today_iso)}.")[:295]
        crumb_html, crumb_jsonld = breadcrumb_fn([("BrokerLens", "/"), ("IPO", "/ipo/"), ("Upcoming IPOs", None)])
        u_jsonld = {"@context": "https://schema.org", "@graph": [
            {"@type": "ItemList", "name": "Upcoming and open IPOs", "url": canonical,
             "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{site_url}/ipo/{r['symbol'].lower()}/",
                                  "name": r.get("company") or r["symbol"]} for i, r in enumerate(active + forthcoming)]},
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]},
            crumb_jsonld]}
        body = head_template % {"title": _esc(u_title), "description": _esc(u_desc), "canonical": _esc(canonical),
                                "jsonld": json.dumps(u_jsonld, ensure_ascii=False)}
        body += (
            crumb_html
            + '<h1 style="margin-top:0">Upcoming IPOs in India</h1>'
            + f'<p class="muted" style="max-width:75ch">Mainboard and SME issues from NSE\'s public-issue disclosures, updated {_esc(_long_date(today_iso))}. '
              'Dates and price bands are as announced by the issuers and can change; this page states facts only and is not a recommendation to apply.</p>'
            + '<div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 8px 0">'
            + '<a href="/ipo/allotment-status/" class="btn btn-primary small">Check allotment status &rarr;</a>'
            + '<a href="/ipo/how-to-apply/" class="btn btn-outline small">How to apply via UPI &rarr;</a>'
            + '<a href="/ipo/" class="btn btn-outline small">IPO tracker and listing gains &rarr;</a></div>'
            + '<div class="section-title" style="margin-top:20px"><h2>Open for bidding now</h2></div>' + render_active_table(active)
            + '<div class="section-title" style="margin-top:28px"><h2>Opening soon</h2></div>' + render_upcoming_table(forthcoming)
            + ('<div class="section-title" style="margin-top:28px"><h2>Closed, awaiting listing</h2></div>' + render_awaiting_table(awaiting) if awaiting else "")
            + '<h2 style="margin-top:32px;font-size:18px">Frequently Asked Questions</h2>'
            + f'<div style="max-width:70ch">{faq_html}</div>'
        )
        body += foot_template % {"source_note": source_note_fn(
            "This page's dates, price bands and subscription figures are NSE's own public-issue disclosures.")}
        return body

    body = head_template % {
        "title": _esc(title),
        "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }

    body += (
        crumb_html
        + '<h1 style="margin-top:0">IPO Tracker & Performance Hub</h1>'
        + '<p class="muted" style="max-width:75ch">Mainboard and SME IPOs tracked directly from official NSE disclosures and SEBI prospectuses: price bands, retail lot sizing, live bidding subscription, and verified post-listing gains. No grey market premium, no speculative recommendations &bull; <a href="/methodology" data-link>see methodology</a>.</p>'
        + f'<div class="grid g4" style="margin:20px 0 24px 0;gap:12px">'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--accent)">'
        + f'<div class="xs muted">Active for Bidding</div>'
        + f'<div style="font-size:22px;font-weight:700;color:var(--accent);margin-top:4px">{len(active)} Issues Open</div>'
        + f'<div class="xs faint">Live exchange bidding</div>'
        + f'</div>'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--text-bright)">'
        + f'<div class="xs muted">Upcoming IPOs</div>'
        + f'<div style="font-size:22px;font-weight:700;margin-top:4px">{len(forthcoming)} Forthcoming</div>'
        + f'<div class="xs faint">Announced issue dates</div>'
        + f'</div>'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--green)">'
        + f'<div class="xs muted">Tracked Listings</div>'
        + f'<div style="font-size:22px;font-weight:700;color:var(--green);margin-top:4px">{len(records):,} Total</div>'
        + f'<div class="xs faint">Historical issues since 2003</div>'
        + f'</div>'
        + f'<div class="card" style="padding:14px;background:var(--bg-raised);border-left:3px solid var(--blue, #3b82f6)">'
        + f'<div class="xs muted">Allotment Tools</div>'
        + f'<div style="font-size:16px;font-weight:700;margin-top:6px"><a href="/ipo/allotment-status/" style="text-decoration:none">Online Checker &rarr;</a></div>'
        + f'<div class="xs faint">Registrar PAN lookup</div>'
        + f'</div>'
        + f'</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:24px">'
        + '<a href="/ipo/upcoming/" class="btn btn-primary small">Upcoming IPOs &rarr;</a>'
        + '<a href="/ipo/allotment-status/" class="btn btn-outline small">Check Allotment Status Online &rarr;</a>'
        + '<a href="/ipo/how-to-apply/" class="btn btn-outline small">How to Apply via UPI & ASBA &rarr;</a>'
        + '<a href="/ipo/archive/" class="btn btn-outline small">Full IPO Historical Archive &rarr;</a>'
        + '</div>'
        + '<div class="section-title" style="margin-top:24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">'
        + '<h2>Currently Open for Bidding (Active IPOs)</h2>'
        + '</div>'
        + render_active_table(active)
        + '<div class="section-title" style="margin-top:32px"><h2>Upcoming IPOs (Announced Dates & Price Bands)</h2></div>'
        + render_upcoming_table(forthcoming)
        + ('<div class="section-title" style="margin-top:32px"><h2>Closed, Awaiting Listing</h2></div>' + render_awaiting_table(awaiting) if awaiting else "")
        + '<div class="section-title" style="margin-top:32px"><h2>Recently Listed IPOs: Listing Day Gains & Current Performance</h2></div>'
        + render_listed_table(recent_listed)
        + f'<p class="xs faint" style="margin-top:14px"><a href="/ipo/archive/">Browse the full historical archive ({len(records):,} IPOs since 2003) &rarr;</a></p>'
        + '<h2 style="margin-top:32px;font-size:18px">Frequently Asked Questions</h2>'
        + f'<div style="max-width:70ch">{faq_html}</div>'
    )

    body += foot_template % {
        "source_note": source_note_fn(
            "This page's price bands, dates, subscription figures, and listing performance facts are NSE's own public-issue disclosures."
        )
    }

    return body


def render_enhanced_ipo_archive(records, equity_history, head_template, foot_template,
                                breadcrumb_fn, source_note_fn, site_url="https://www.brokerlens.in"):
    """Renders the full /ipo/archive/ page with listing gains and post-listing performance."""
    canonical = f"{site_url}/ipo/archive/"
    title = f"Full IPO Archive Since 2003 ({len(records):,} Issues) | BrokerLens"
    description = (
        f"Complete historical archive of {len(records):,} NSE mainboard and SME IPOs since 2003: "
        f"Issue prices, listing dates, listing day gains, and post-listing return performance."
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
                        "name": r.get("company") or r["symbol"],
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
        co = r.get("company") or sym
        status = r.get("status", "Closed")
        p_low, p_high, cut_off = parse_price_band(r.get("price_band"), r.get("issue_price"))
        perf = compute_listing_performance(sym, r.get("issue_price") or cut_off, equity_history, r.get("listing_date"))

        d_str = _long_date(r.get("listing_date") or r.get("bidding_end") or perf.get("listing_date")) or "-"
        ip_val = r.get("issue_price") or cut_off
        ip_str = f"Rs {ip_val:,.0f}" if ip_val > 0 else (r.get("price_band") or "-")

        gain_str = cmp_str = "-"
        if perf.get("has_listing_data"):
            lg_pct = perf["listing_gain_pct"]
            lg_cls = "var(--green)" if lg_pct >= 0 else "var(--red)"
            gain_str = f"<span style='color:{lg_cls};font-weight:600'>{lg_pct:+.1f}%</span>"
        if perf.get("has_current_data"):
            cmp_str = f"Rs {perf['cmp']:,.1f}"

        sub_val = r.get("times_subscribed")
        sub_str = f"{float(sub_val):.2f}x" if sub_val is not None else "-"

        rows_html += f"""
        <tr>
          <td><strong><a href="/ipo/{slug}/">{_esc(co)}</a></strong> <span class="xs faint">{_esc(sym)}</span></td>
          <td><span class="badge">{_esc(status)}</span></td>
          <td class="right num">{ip_str}</td>
          <td class="small">{_esc(d_str)}</td>
          <td class="right num">{gain_str}</td>
          <td class="right num">{cmp_str}</td>
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
        + f'<p class="muted" style="max-width:75ch">Complete database of {len(records):,} mainboard and SME IPOs from official NSE public-issue disclosures since 2003. Includes historical issue prices, listing day returns, and current trading performance. <a href="/ipo/" data-link>&larr; Back to active & upcoming IPOs</a></p>'
        + '<div class="table-scroll" style="margin-top:20px"><table class="data"><thead><tr>'
        + '<th>Company & Symbol</th><th>Status</th><th class="right">Issue Price</th>'
        + '<th>Date</th><th class="right">Listing Day Gain</th><th class="right">Current Price</th><th class="right">Subscribed</th>'
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
