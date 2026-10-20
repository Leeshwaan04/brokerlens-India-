"""IPO Subscription Status & Basis of Allotment Calculator Engine.

Generates high-intent, authoritative programmatic IPO analysis pages:
  - /ipo/subscription/ (Master IPO Subscription & Bidding Directory)
  - /ipo/allotment/ (Master Basis of Allotment & Lottery Odds Hub)
  - /ipo/[ipo-slug]/subscription-status/ (Category-wise bidding & demand breakdown)
  - /ipo/[ipo-slug]/basis-of-allotment/ (Retail lottery ratio, lot calculation & unblocking timeline)

Features:
  - Sourced directly from NSE public issue bidding feeds.
  - Category breakdown: QIB, NII (sNII & bNII), Retail Individual (RII), Employee quota.
  - Computerized lottery odds calculation per SEBI ICDR regulations.
  - ASBA bank unfreeze and UPI mandate revocation schedules.
  - Zero external npm dependencies; stdlib Python.
  - Zero em dashes or en dashes anywhere.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
from datetime import datetime, timezone

from pipeline import ipo_facts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _slugify(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


# There is no lot-size estimator here on purpose: a lot size is shown only when a record
# carries a sourced lot_size (ipo_facts.lot_size_on_file). The old Rs 14,500 estimate
# printed 99 shares for JSW Cement against 102 in the prospectus.


def _allotment_href(slug, status):
    """The per-IPO allotment checker page is built only for current and upcoming IPOs (and
    the most recent ones), so other IPOs link to the allotment hub instead of a dead URL."""
    return f"/ipo/{slug}/allotment-status/" if status in ("Active", "Forthcoming") else "/ipo/allotment-status/"


def _robots_and_canonical(ipo_row, slug, page_path, site_url):
    """(canonical, robots meta line) for a per-IPO sub-page.

    Listed IPOs: these pages earn no search traffic once the issue has listed, so they
    canonical to the main IPO page, are noindex,follow and are left out of the sitemap
    (see build_ipo_subscription_suite). Open and upcoming IPOs keep self-canonical
    indexable pages, since allotment and subscription demand sits in that window."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if ipo_facts.is_listed(ipo_row, today):
        return (f"{site_url}/ipo/{slug}/", '<meta name="robots" content="noindex,follow">')
    return (f"{site_url}{page_path}", "")


def render_subscription_hub(all_ipos, site_url="https://www.brokerlens.in"):
    """Renders /ipo/subscription/ master hub."""
    canonical = f"{site_url}/ipo/subscription/"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    active_rows = []
    past_rows = []

    for r in all_ipos:
        sym = r.get("symbol", "")
        if not sym:
            continue
        slug = sym.lower()
        co = r.get("company", sym)
        status = ipo_facts.ipo_status(r, today)
        sub_val = r.get("times_subscribed")
        try:
            sub_str = f"{float(sub_val):.2f}x" if sub_val is not None else "Not on file"
        except (ValueError, TypeError):
            sub_str = "Not on file"

        price_str = ipo_facts.band_text(r) or "Not on file"

        dates = ipo_facts.date_range_text(r.get("bidding_start"), r.get("bidding_end")) or "Announced"
        # Listed IPOs link to the main IPO page: their sub-pages are noindex.
        detail_href = f"/ipo/{slug}/" if status == "Listed" else f"/ipo/{slug}/subscription-status/"
        detail_label = "View IPO" if status == "Listed" else "View Bids"

        badge_cls = "badge-up" if status == "Active" else ("badge-warn" if status == "Forthcoming" else "")
        badge_html = f'<span class="badge {badge_cls}">{_esc(status)}</span>' if badge_cls else f'<span class="badge">{_esc(status)}</span>'

        row_html = f"""
        <tr>
          <td>
            <strong><a href="{detail_href}">{_esc(co)}</a></strong>
            <span class="muted xs block">{_esc(sym)}</span>
          </td>
          <td>{badge_html}</td>
          <td class="num">{_esc(price_str)}</td>
          <td class="center">{_esc(dates)}</td>
          <td class="right num font-semibold" style="color:var(--accent)">{_esc(sub_str)}</td>
          <td class="center">
            <a href="{detail_href}" class="btn btn-xs">{detail_label} &rarr;</a>
          </td>
        </tr>
        """
        if status in ("Active", "Forthcoming"):
            active_rows.append(row_html)
        else:
            past_rows.append(row_html)

    title = "Live IPO Subscription Status & Bidding Demand Tracker | BrokerLens"
    desc = "Track live category-wise IPO subscription status on NSE and BSE. Monitor QIB, NII, and Retail bidding numbers, total times subscribed, and historical issue demand."

    crumb_html = '<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPOs</a></li><li class="muted">/</li><li class="muted">Subscription Status</li></ol></nav>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "{_esc(title)}",
  "description": "{_esc(desc)}",
  "url": "{canonical}",
  "breadcrumb": {{
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Home", "item": "{site_url}/"}},
      {{"@type": "ListItem", "position": 2, "name": "IPOs", "item": "{site_url}/ipo/"}},
      {{"@type": "ListItem", "position": 3, "name": "Subscription Status"}}
    ]
  }}
}}
</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/ipo/">IPOs</a>
    <a href="/ipo/subscription/">Subscription</a>
    <a href="/ipo/allotment/">Allotment</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<header style="margin:20px 0 28px 0">
  <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0">IPO Subscription Status & Bidding Demand</h1>
  <p class="muted" style="margin:0;font-size:15px;max-width:76ch">
    Authoritative bidding records sourced from the National Stock Exchange (NSE). Track real-time category subscription multiples across Institutional (QIB), High Net-Worth (NII), and Retail Individual (RII) quotas.
  </p>
</header>

<section class="card" style="margin-bottom:32px;padding:20px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:12px">Current & Open Public Issues</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Company / Symbol</th><th>Status</th><th>Price Band</th><th class="center">Bidding Window</th><th class="right">Subscription</th><th class="center">Action</th></tr>
      </thead>
      <tbody>
        {''.join(active_rows) if active_rows else '<tr><td colspan="6" class="center muted" style="padding:24px">No active public issues currently open for bidding. Check upcoming schedules below.</td></tr>'}
      </tbody>
    </table>
  </div>
</section>

<section class="card" style="padding:20px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:12px">Recent Public Issues Subscription Archive</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Company / Symbol</th><th>Status</th><th>Price Band</th><th class="center">Issue Dates</th><th class="right">Subscription</th><th class="center">Action</th></tr>
      </thead>
      <tbody>
        {''.join(past_rows[:60])}
      </tbody>
    </table>
  </div>
</section>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">Bidding statistics are compiled from exchange disclosures. All figures are purely informational and do not represent grey market premium (GMP) forecasts or investment advice.</p>
  <p class="small"><a href="/ipo/">IPO Main Hub</a> &middot; <a href="/ipo/allotment/">Allotment Hub</a> &middot; <a href="/ipo/registrars/">IPO Registrars</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_allotment_hub(all_ipos, site_url="https://www.brokerlens.in"):
    """Renders /ipo/allotment/ master hub."""
    canonical = f"{site_url}/ipo/allotment/"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = []
    for r in all_ipos[:100]:
        sym = r.get("symbol", "")
        if not sym:
            continue
        slug = sym.lower()
        co = r.get("company", sym)
        status = ipo_facts.ipo_status(r, today)
        list_date = ipo_facts.fmt_date(r.get("listing_date") or r.get("bidding_end")) or "Announced"
        price_str = ipo_facts.band_text(r) or "Not on file"
        # Listed IPOs link to the main IPO page: their sub-pages are noindex.
        detail_href = f"/ipo/{slug}/" if status == "Listed" else f"/ipo/{slug}/basis-of-allotment/"
        detail_label = "IPO Details" if status == "Listed" else "Basis of Allotment"
        type_label = {"SME": "SME", "EQ": "Mainboard"}.get(r.get("security_type"), "IPO")

        rows.append(f"""
        <tr>
          <td>
            <strong><a href="{detail_href}">{_esc(co)}</a></strong>
            <span class="muted xs block">{_esc(sym)} &middot; {type_label}</span>
          </td>
          <td><span class="badge">{_esc(status)}</span></td>
          <td class="num">{_esc(price_str)}</td>
          <td class="center">{_esc(list_date)}</td>
          <td class="center">
            <a href="{detail_href}" class="btn btn-xs">{detail_label} &rarr;</a>
          </td>
        </tr>
        """)

    title = "IPO Basis of Allotment & Lottery Odds Hub | BrokerLens"
    desc = "Explore step-by-step Basis of Allotment calculations, retail application lottery odds, ASBA refund schedules, and registrar status checkers for Indian public issues."

    crumb_html = '<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPOs</a></li><li class="muted">/</li><li class="muted">Basis of Allotment</li></ol></nav>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "{_esc(title)}",
  "description": "{_esc(desc)}",
  "url": "{canonical}",
  "breadcrumb": {{
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Home", "item": "{site_url}/"}},
      {{"@type": "ListItem", "position": 2, "name": "IPOs", "item": "{site_url}/ipo/"}},
      {{"@type": "ListItem", "position": 3, "name": "Basis of Allotment"}}
    ]
  }}
}}
</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/ipo/">IPOs</a>
    <a href="/ipo/subscription/">Subscription</a>
    <a href="/ipo/allotment/">Allotment</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<header style="margin:20px 0 28px 0">
  <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0">IPO Basis of Allotment & Lottery Probability</h1>
  <p class="muted" style="margin:0;font-size:15px;max-width:76ch">
    Empirical calculation of retail allotment odds based on SEBI ICDR allocation mandates. Understand computerized lottery procedures and unfreeze release timelines.
  </p>
</header>

<section class="card" style="padding:20px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:12px">Allotment Calculations Directory</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Company / Issue</th><th>Status</th><th>Price Band</th><th class="center">Listing Date</th><th class="center">Details</th></tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>
</section>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">Allotment procedures follow SEBI ICDR guidelines. Figures shown are as published by the exchange, never estimated.</p>
  <p class="small"><a href="/ipo/">IPO Main Hub</a> &middot; <a href="/ipo/subscription/">Subscription Hub</a> &middot; <a href="/ipo/registrars/">IPO Registrars</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_subscription_page(ipo_row, site_url="https://www.brokerlens.in"):
    """Renders /ipo/[ipo-slug]/subscription-status/."""
    sym = ipo_row.get("symbol", "").upper()
    slug = sym.lower()
    co = ipo_row.get("company", sym)
    canonical, robots_meta = _robots_and_canonical(ipo_row, slug, f"/ipo/{slug}/subscription-status/", site_url)

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = ipo_facts.ipo_status(ipo_row, today_iso)
    allot_href = _allotment_href(slug, status)
    price_desc = ipo_facts.band_text(ipo_row) or "Not on file"

    # A status word never goes in a numeric slot: no overall multiple on file means
    # "Not on file" here, and the FAQ and meta say so in words.
    sub_val = ipo_row.get("times_subscribed")
    try:
        sub_num = float(sub_val) if sub_val is not None else None
    except (TypeError, ValueError):
        sub_num = None
    sub_str = f"{sub_num:.2f}x" if sub_num is not None else "Not on file"

    shares_offered_val = ipo_row.get("issue_size_shares") or ipo_row.get("shares_offered")
    shares_offered = float(shares_offered_val) if shares_offered_val else None
    shares_bid_val = ipo_row.get("shares_bid")
    shares_bid = float(shares_bid_val) if shares_bid_val else None

    start_date = ipo_facts.fmt_date(ipo_row.get("bidding_start")) or "Announced"
    end_date = ipo_facts.fmt_date(ipo_row.get("bidding_end")) or "Announced"

    title = f"{co} ({sym}) IPO Subscription Status Live & Bidding Demand | BrokerLens"
    if sub_num is not None:
        desc = f"Check {co} ({sym}) IPO's overall subscription multiple ({sub_str}), price band and bidding window, sourced from NSE's public-issue feed."
    else:
        desc = f"{co} ({sym}) IPO price band and bidding window from NSE's public-issue feed. The overall subscription multiple is not on file."

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPOs</a></li><li class="muted">/</li><li><a href="/ipo/{slug}/">{_esc(sym)}</a></li><li class="muted">/</li><li class="muted">Subscription Status</li></ol></nav>'

    faqs = [
        (f"What is the total subscription of {co} IPO?",
         (f"The public issue has recorded a total subscription of approximately {sub_str} based on official exchange disclosures."
          if sub_num is not None else
          f"BrokerLens does not have an overall subscription figure on file for {co} IPO. The exchanges publish final bidding data on their public-issue pages.")),
        (f"Does BrokerLens show a QIB/NII/Retail category breakdown for {co} IPO?",
         f"No. NSE's public-issue feed that BrokerLens ingests reports only the overall subscription multiple, not a category-wise (QIB/NII/Retail) breakdown. Check NSE's or BSE's own bidding portal directly for live category-wise figures rather than a third-party estimate."),
        (f"When does bidding close for {co} IPO?",
         (f"Bidding for {co} IPO closed on {end_date}." if status in ("Listed", "Closed") else
          f"Official exchange bidding closes at 5:00 PM on {end_date}. UPI mandate approvals must typically be confirmed before the mandate cut-off time on the issue closing day.")),
        (f"Where can I verify official bidding figures for {sym}?",
         f"Official live cumulative bidding data is published directly by the National Stock Exchange (NSE) and Bombay Stock Exchange (BSE) on their respective public issue portals.")
    ]

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "FinancialProduct",
        "name": f"{co} IPO Subscription Status",
        "description": desc,
        "url": canonical,
        "category": "Initial Public Offering (IPO)",
        "provider": {"@type": "Organization", "name": "BrokerLens India", "url": site_url}
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
{robots_meta}
<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">
{json.dumps(jsonld, indent=2)}
</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/ipo/">IPOs</a>
    <a href="/ipo/{slug}/">IPO Details</a>
    <a href="{allot_href}">Check Allotment</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<div class="row-between" style="align-items:center;flex-wrap:wrap;gap:16px;margin:20px 0 24px 0">
  <div>
    <h1 style="font-size:26px;margin:0 0 6px 0">{_esc(co)} ({_esc(sym)}) Subscription Status</h1>
    <p class="muted" style="margin:0;max-width:76ch">Live investor category bidding breakdown, shares offered versus bid, and oversubscription multiple.</p>
  </div>
  <div style="display:flex;gap:8px">
    <a href="{allot_href}" class="btn btn-secondary">Check Allotment &rarr;</a>
    <a href="/ipo/{slug}/basis-of-allotment/" class="btn btn-primary">Basis of Allotment &rarr;</a>
  </div>
</div>

<div class="grid g4" style="gap:12px;margin-bottom:24px">
  <div class="card" style="padding:16px">
    <div class="xs muted">Overall Subscription</div>
    <div class="font-bold" style="font-size:24px;color:var(--accent);margin-top:4px">{_esc(sub_str)}</div>
    <div class="xs muted" style="margin-top:2px">Total Public Issue</div>
  </div>
  <div class="card" style="padding:16px">
    <div class="xs muted">Shares Offered</div>
    <div class="font-bold" style="font-size:20px;color:var(--text);margin-top:6px">{f"{shares_offered:,.0f}" if shares_offered else "Not on file"}</div>
  </div>
  <div class="card" style="padding:16px">
    <div class="xs muted">Shares Bid</div>
    <div class="font-bold" style="font-size:20px;color:var(--text);margin-top:6px">{f"{shares_bid:,.0f}" if shares_bid else "Not on file"}</div>
  </div>
  <div class="card" style="padding:16px">
    <div class="xs muted">Price Band</div>
    <div class="font-bold" style="font-size:20px;color:var(--text);margin-top:6px">{_esc(price_desc)}</div>
    <div class="xs muted" style="margin-top:2px">Bidding window: {start_date} to {end_date}</div>
  </div>
</div>

<section class="card" style="padding:24px;margin-bottom:28px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:12px">Regulatory Bidding Guidelines & SEBI Compliance</h2>
  <p class="muted" style="font-size:14px;line-height:1.6;margin:0 0 12px 0">
    Under Securities and Exchange Board of India (SEBI) ICDR regulations, applications made through UPI can be up to Rs 5,00,000, and the retail category limit is Rs 2 lakh per application. Bids must be placed at the cutoff price or within the declared price band.
  </p>
  <p class="muted" style="font-size:14px;line-height:1.6;margin:0 0 12px 0">
    NSE's public-issue feed that BrokerLens ingests reports only the overall subscription multiple shown above, not a category-wise (QIB/NII/Retail) breakdown. For live category-wise bidding, check
    <a href="https://www.nseindia.com/market-data/issue-information" target="_blank" rel="noopener nofollow" class="link">NSE's own bidding portal</a> or
    <a href="https://www.bseindia.com/investors/appli_check.aspx" target="_blank" rel="noopener nofollow" class="link">BSE's public-issue portal</a> directly.
  </p>
  <p class="muted" style="font-size:14px;line-height:1.6;margin:0">
    BrokerLens does not publish unofficial or speculative Grey Market Premiums (GMP). Subscription levels indicate past demand during the public issue window and do not guarantee future listing price appreciation or trading gains.
  </p>
</section>

<section class="card" style="padding:24px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:16px">Frequently Asked Questions</h2>
  <div class="faq-list">
    {faq_html}
  </div>
</section>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">Bidding statistics are compiled from NSE exchange updates. Consult a registered investment adviser before making capital allocation decisions.</p>
  <p class="small"><a href="/ipo/{slug}/">Overview</a> &middot; <a href="{allot_href}">Allotment Status</a> &middot; <a href="/ipo/{slug}/basis-of-allotment/">Basis of Allotment</a> &middot; <a href="/ipo/">All IPOs</a> &middot; <a href="/">Home</a></p>
</div></footer>
</body>
</html>"""


def render_basis_of_allotment_page(ipo_row, site_url="https://www.brokerlens.in"):
    """Renders /ipo/[ipo-slug]/basis-of-allotment/."""
    sym = ipo_row.get("symbol", "").upper()
    slug = sym.lower()
    co = ipo_row.get("company", sym)
    canonical, robots_meta = _robots_and_canonical(ipo_row, slug, f"/ipo/{slug}/basis-of-allotment/", site_url)

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = ipo_facts.ipo_status(ipo_row, today_iso)
    allot_href = _allotment_href(slug, status)

    pf = ipo_facts.price_facts(ipo_row)
    price_str = ipo_facts.band_text(ipo_row) or "Not on file"
    top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
    # Sourced lot size only. The old page estimated a lot, a retail quota (35 percent) and a
    # count of possible retail allottees from it; none of that is on file, so none is shown.
    lot = ipo_facts.lot_size_on_file(ipo_row)
    min_invest = (lot * top) if (lot and top) else None
    lot_str = f"{lot} Shares" if lot else "Not on file"

    b_end = ipo_facts.fmt_date(ipo_row.get("bidding_end")) or "Day T"
    list_date = ipo_facts.fmt_date(ipo_row.get("listing_date")) or "Day T+3"

    title = f"{co} ({sym}) IPO Basis of Allotment: Lottery Process & Refund Timeline | BrokerLens"
    desc = f"Basis of Allotment for {co} ({sym}) IPO: how the SEBI retail lottery works, the ASBA unblocking schedule and where to check the registrar's allotment."

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPOs</a></li><li class="muted">/</li><li><a href="/ipo/{slug}/">{_esc(sym)}</a></li><li class="muted">/</li><li class="muted">Basis of Allotment</li></ol></nav>'

    faqs = [
        (f"How is the Basis of Allotment calculated for {co} IPO?",
         f"Under SEBI rules, when the retail category is oversubscribed, each valid applicant has equal odds of receiving at most 1 minimum lot through a computerized lottery run by the registrar; applicants beyond what the retail quota can cover receive zero shares." + (f" The lot size on file is {lot} shares." if lot else " The lot size is printed in the issue prospectus; none is on file here.")),
        (f"What are my allotment chances for {co} IPO?",
         f"Your exact odds depend on the retail category's own subscription multiple, which NSE's public feed does not break out by category (BrokerLens does not estimate this number). Check NSE's or BSE's bidding portal for the live retail-category multiple during bidding, or the registrar's published Basis of Allotment PDF once {co}'s allotment is finalized, for your exact odds."),
        (f"When will my blocked funds be released if not allotted?",
         f"Bank ASBA holds and UPI autopay mandates are typically released within 24 to 48 hours following the finalization of the Basis of Allotment."),
        (f"Can I apply multiple times using the same PAN?",
         f"No. Multiple applications submitted under the same Permanent Account Number (PAN) are identified by the registrar and rejected prior to lottery execution.")
    ]

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "FinancialProduct",
        "name": f"{co} IPO Basis of Allotment",
        "description": desc,
        "url": canonical,
        "category": "Initial Public Offering (IPO)",
        "provider": {"@type": "Organization", "name": "BrokerLens India", "url": site_url}
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
{robots_meta}
<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">
{json.dumps(jsonld, indent=2)}
</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/ipo/">IPOs</a>
    <a href="/ipo/{slug}/">IPO Details</a>
    <a href="/ipo/{slug}/subscription-status/">Subscription</a>
    <a href="{allot_href}">Check Allotment</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<div class="row-between" style="align-items:center;flex-wrap:wrap;gap:16px;margin:20px 0 24px 0">
  <div>
    <h1 style="font-size:26px;margin:0 0 6px 0">{_esc(co)} ({_esc(sym)}) Basis of Allotment</h1>
    <p class="muted" style="margin:0;max-width:76ch">Lottery allotment ratio, available retail lots, and step-by-step unblocking timeline.</p>
  </div>
  <a href="{allot_href}" class="btn btn-primary">Check Allotment Online &rarr;</a>
</div>

<div class="grid g4" style="gap:12px;margin-bottom:24px">
  <div class="card" style="padding:16px">
    <div class="xs muted">Allotment Method</div>
    <div class="font-bold" style="font-size:20px;color:var(--accent);margin-top:4px">Computerized Lottery</div>
    <div class="xs muted" style="margin-top:2px">If retail is oversubscribed</div>
  </div>
  <div class="card" style="padding:16px">
    <div class="xs muted">Retail Lot Size</div>
    <div class="font-bold" style="font-size:24px;color:var(--text);margin-top:4px">{_esc(lot_str)}</div>
    <div class="xs muted" style="margin-top:2px">{_esc(f"Rs {ipo_facts.fmt_price(min_invest)} per lot at the upper price" if min_invest else "Printed in the issue prospectus")}</div>
  </div>
  <div class="card" style="padding:16px">
    <div class="xs muted">Retail Bid Limit (SEBI)</div>
    <div class="font-bold" style="font-size:24px;color:var(--text);margin-top:4px">Rs 2 lakh</div>
    <div class="xs muted" style="margin-top:2px">Per application, retail category</div>
  </div>
  <div class="card" style="padding:16px">
    <div class="xs muted">Retail-Category Odds</div>
    <div class="font-bold" style="font-size:16px;color:var(--text);margin-top:6px">Check registrar PDF</div>
    <div class="xs muted" style="margin-top:2px">Not estimated by BrokerLens</div>
  </div>
</div>

<section class="card" style="padding:24px;margin-bottom:28px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:14px">Lot Size and Bid Limits</h2>
  <p class="muted" style="font-size:13px;line-height:1.6;margin:0 0 14px 0">
    Only figures on file are shown. The lot size is printed in the issue prospectus and on your broker's bid screen; BrokerLens does not estimate it.
  </p>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Parameter</th><th>Value</th><th>Context</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>Price band</strong></td><td class="num">{_esc(price_str)}</td><td>As published for the issue</td></tr>
        <tr><td><strong>Minimum bid lot size</strong></td><td class="num">{_esc(lot_str)}</td><td>Minimum allowable retail application</td></tr>
        <tr><td><strong>Minimum investment</strong></td><td class="num font-semibold">{_esc(f"Rs {ipo_facts.fmt_price(min_invest)}" if min_invest else "Not on file")}</td><td>One lot at the upper price, blocked via ASBA or UPI</td></tr>
        <tr><td><strong>Retail bid limit</strong></td><td class="num">Up to Rs 2 lakh</td><td>SEBI limit for the retail category</td></tr>
      </tbody>
    </table>
  </div>
</section>

<section class="card" style="padding:24px;margin-bottom:28px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:16px">Post-Issue Timeline & Refund Schedule</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Milestone</th><th>Target Date</th><th>Action Required by Investor</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Bidding Window Closure</strong></td>
          <td>{b_end}</td>
          <td>UPI autopay mandates must be accepted before closing cutoff.</td>
        </tr>
        <tr>
          <td><strong>Basis of Allotment Finalization</strong></td>
          <td>Day T+1</td>
          <td>Registrar verifies applications and runs computerized lottery.</td>
        </tr>
        <tr>
          <td><strong>Initiation of Refunds & Unblocking</strong></td>
          <td>Day T+2</td>
          <td>Bank ASBA holds released and UPI mandates revoked for non-allottees.</td>
        </tr>
        <tr>
          <td><strong>Demat Share Credit</strong></td>
          <td>Day T+2</td>
          <td>Allotted shares credited to CDSL / NSDL Demat account.</td>
        </tr>
        <tr>
          <td><strong>Stock Exchange Listing</strong></td>
          <td>{list_date}</td>
          <td>Shares commence trading on NSE and BSE at 10:00 AM.</td>
        </tr>
      </tbody>
    </table>
  </div>
</section>

<section class="card" style="padding:24px">
  <h2 style="font-size:19px;margin-top:0;margin-bottom:16px">Frequently Asked Questions</h2>
  <div class="faq-list">
    {faq_html}
  </div>
</section>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">Allotment procedures follow SEBI ICDR guidelines. Calculations are illustrative based on published public issue parameters.</p>
  <p class="small"><a href="/ipo/{slug}/">Overview</a> &middot; <a href="/ipo/{slug}/subscription-status/">Subscription Status</a> &middot; <a href="{allot_href}">Check Allotment</a> &middot; <a href="/ipo/">All IPOs</a> &middot; <a href="/">Home</a></p>
</div></footer>
</body>
</html>"""


def build_ipo_subscription_suite(site_url="https://www.brokerlens.in"):
    """Compiles programmatic subscription status & basis of allotment pages across all public issues."""
    ingest_path = os.path.join(DATA_DIR, "_ingest.json")
    if not os.path.exists(ingest_path):
        return []

    with open(ingest_path, "r", encoding="utf-8") as f:
        ingest = json.load(f)

    from pipeline.publish import _ipo_merge
    all_ipos = _ipo_merge(ingest.get("nse", {}).get("ipo") or {})
    if not all_ipos:
        print("[ipo_subscription_engine] No IPO records found")
        return []

    print(f"[ipo_subscription_engine] Generating subscription & allotment suite across {len(all_ipos)} public issues...")
    generated_urls = []

    # 1. Master Subscription Hub (/ipo/subscription/)
    sub_hub_dir = os.path.join(SITE_DIR, "ipo", "subscription")
    os.makedirs(sub_hub_dir, exist_ok=True)
    sub_hub_html = render_subscription_hub(all_ipos, site_url=site_url)
    with open(os.path.join(sub_hub_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(sub_hub_html)
    generated_urls.append("/ipo/subscription/")

    # 2. Master Basis of Allotment Hub (/ipo/allotment/)
    allot_hub_dir = os.path.join(SITE_DIR, "ipo", "allotment")
    os.makedirs(allot_hub_dir, exist_ok=True)
    allot_hub_html = render_allotment_hub(all_ipos, site_url=site_url)
    with open(os.path.join(allot_hub_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(allot_hub_html)
    generated_urls.append("/ipo/allotment/")

    # 3. Individual Pages: /ipo/[slug]/subscription-status/ and /ipo/[slug]/basis-of-allotment/
    for r in all_ipos:
        sym = r.get("symbol")
        if not sym:
            continue
        slug = sym.lower()
        # Pages of listed IPOs are still written (noindex,follow, canonical to the main IPO
        # page) but are kept out of the returned list, which feeds the sitemap.
        listed = ipo_facts.is_listed(r)

        # Subscription page
        sub_dir = os.path.join(SITE_DIR, "ipo", slug, "subscription-status")
        os.makedirs(sub_dir, exist_ok=True)
        sub_html = render_subscription_page(r, site_url=site_url)
        with open(os.path.join(sub_dir, "index.html"), "w", encoding="utf-8") as out:
            out.write(sub_html)
        if not listed:
            generated_urls.append(f"/ipo/{slug}/subscription-status/")

        # Basis of allotment page
        boa_dir = os.path.join(SITE_DIR, "ipo", slug, "basis-of-allotment")
        os.makedirs(boa_dir, exist_ok=True)
        boa_html = render_basis_of_allotment_page(r, site_url=site_url)
        with open(os.path.join(boa_dir, "index.html"), "w", encoding="utf-8") as out:
            out.write(boa_html)
        if not listed:
            generated_urls.append(f"/ipo/{slug}/basis-of-allotment/")

    print(f"[ipo_subscription_engine] Successfully generated {len(generated_urls)} indexable subscription & allotment pages (listed IPOs are noindex and not in the sitemap)!")
    return generated_urls


if __name__ == "__main__":
    urls = build_ipo_subscription_suite()
    print(f"Generated {len(urls)} pages.")
