"""IPO Subscription Status & Basis of Allotment Calculator Engine.

Generates high-intent, authoritative programmatic IPO analysis pages:
  - /ipo/subscription/ (Master IPO Subscription & Bidding Directory)
  - /ipo/allotment/ (Master Basis of Allotment & Lottery Odds Hub)
  - /ipo/[ipo-slug]/subscription-status/ (Category-wise bidding & demand breakdown)
  - /ipo/[ipo-slug]/basis-of-allotment/ (Retail lottery ratio, lot calculation & unblocking timeline)

Features:
  - Sourced directly from NSE public issue bidding feeds.
  - How the SEBI retail lottery works (no allotment odds are estimated).
  - ASBA bank unfreeze and UPI mandate revocation schedules.
  - Subscription is the overall multiple only, as a dated snapshot; no category split is on file.
  - Pages of Listed and "No listing on file" IPOs are noindex,follow with a self canonical and are
    left out of the returned (sitemap) list.
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

try:
    from . import ipo_facts
except ImportError:  # run as a script: python3 pipeline/ipo_subscription_engine.py
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

    Listed IPOs and IPOs with no listing on file: these pages earn no search traffic once the issue is
    over, so they are noindex,follow and left out of the sitemap (see build_ipo_subscription_suite). The
    canonical stays on the page's own URL: a noindex page that canonicals to a different page is a mixed
    signal, and these pages are not duplicates of the main page. Open and upcoming IPOs keep self-canonical
    indexable pages, since allotment and subscription demand sits in that window."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    canonical = f"{site_url}{page_path}"
    if ipo_facts.is_settled(ipo_row, today):
        return (f"{site_url}/ipo/{slug}/", '<meta name="robots" content="noindex,follow">')
    return (canonical, "")


def render_subscription_hub(all_ipos, site_url="https://www.brokerlens.in"):
    """Renders /ipo/subscription/ master hub."""
    canonical = f"{site_url}/ipo/subscription/"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of = ipo_facts.data_as_of(today)

    active_rows = []
    past_rows = []

    for r in ipo_facts.ipo_records_only(all_ipos):
        sym = r.get("symbol", "")
        if not sym:
            continue
        slug = sym.lower()
        co = ipo_facts.display_name(r)
        status = ipo_facts.ipo_status(r, today)
        # A multiple is shown only as the final figure, or dated while bidding is open. A snapshot taken
        # before the close is never shown as the result of a closed issue.
        info = ipo_facts.subscription_info(r, status, as_of)
        if info and (info["final"] or info["open_now"]):
            sub_str = f"{info['value']:.2f}x" + ("" if info["final"] else f" (as of {ipo_facts.fmt_date(info['as_of'])})")
        else:
            sub_str = "Not on file"

        price_str = ipo_facts.band_text(r) or "Not on file"

        dates = ipo_facts.date_range_text(r.get("bidding_start"), r.get("bidding_end")) or "Announced"
        # Listed IPOs and IPOs with no listing on file link to the main IPO page: their sub-pages are noindex.
        settled = status in ("Listed", ipo_facts.STATUS_NO_LISTING)
        detail_href = f"/ipo/{slug}/" if settled else f"/ipo/{slug}/subscription-status/"
        detail_label = "View IPO" if settled else "View Bids"

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

    title = "IPO Subscription Status and Bidding Demand | BrokerLens"
    desc = (f"Overall IPO subscription multiple, shares offered versus bid and bidding dates for NSE issues, where on file "
            f"(feed data as of {ipo_facts.fmt_date(as_of)}). No category-wise split is published here.")

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
    Overall subscription multiples from the National Stock Exchange (NSE) public-issue feed, shown with the date of the feed ({_esc(ipo_facts.fmt_date(as_of))}). The feed carries no category-wise (QIB, NII, Retail) split, so none is shown or estimated. A multiple taken while bidding was open is not shown for a closed issue.
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
    for r in ipo_facts.ipo_records_only(all_ipos)[:100]:
        sym = r.get("symbol", "")
        if not sym:
            continue
        slug = sym.lower()
        co = ipo_facts.display_name(r)
        status = ipo_facts.ipo_status(r, today)
        # Only a listing date that is on file and plausible is shown. The bidding end is never used here.
        list_date = ipo_facts.listing_date_display(r, "Not on file")
        price_str = ipo_facts.band_text(r) or "Not on file"
        # Listed IPOs and IPOs with no listing on file link to the main IPO page: their sub-pages are noindex.
        settled = status in ("Listed", ipo_facts.STATUS_NO_LISTING)
        detail_href = f"/ipo/{slug}/" if settled else f"/ipo/{slug}/basis-of-allotment/"
        detail_label = "IPO Details" if settled else "Basis of Allotment"
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

    title = "IPO Basis of Allotment and Refund Timeline Hub | BrokerLens"
    desc = "How the SEBI retail allotment lottery works, ASBA and UPI refund timelines, and links to registrar allotment checkers for Indian public issues. Odds are not estimated."

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
  <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0">IPO Basis of Allotment & Refund Timeline</h1>
  <p class="muted" style="margin:0;font-size:15px;max-width:76ch">
    How the SEBI retail allotment lottery works and when blocked funds are released. BrokerLens does not estimate your allotment odds.
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
    co = ipo_facts.display_name(ipo_row)
    canonical, robots_meta = _robots_and_canonical(ipo_row, slug, f"/ipo/{slug}/subscription-status/", site_url)

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    as_of = ipo_facts.data_as_of(today_iso)
    status = ipo_facts.ipo_status(ipo_row, today_iso)
    allot_href = _allotment_href(slug, status)
    price_desc = ipo_facts.band_text(ipo_row) or "Not on file"

    # A status word never goes in a numeric slot: no overall multiple on file means
    # "Not on file" here, and the FAQ and meta say so in words. The multiple is a snapshot from the feed
    # date: it is the result of the issue only when the feed date is after the close. A snapshot taken while
    # bidding was open is labelled with its date once the issue has closed, and kept out of the title and meta.
    info = ipo_facts.subscription_info(ipo_row, status, as_of)
    sub_num = info["value"] if info else None
    shows_value = bool(info and (info["final"] or info["open_now"]))
    snap_date = ipo_facts.fmt_date(as_of)
    if shows_value:
        sub_str = f"{sub_num:.2f}x"
        sub_note = "Total public issue" if info["final"] else f"As of {snap_date}, bidding is open"
    else:
        sub_str = "Not on file"
        sub_note = (f"Snapshot of {sub_num:.2f}x as of {snap_date}, while bidding was open. Not the final figure."
                    if info else "Total public issue")

    shares_offered_val = ipo_row.get("issue_size_shares") or ipo_row.get("shares_offered")
    shares_offered = float(shares_offered_val) if shares_offered_val else None
    shares_bid_val = ipo_row.get("shares_bid")
    shares_bid = float(shares_bid_val) if shares_bid_val else None

    start_date = ipo_facts.fmt_date(ipo_row.get("bidding_start")) or "Announced"
    end_date = ipo_facts.fmt_date(ipo_row.get("bidding_end")) or "Announced"

    title = f"{co} ({sym}) IPO Subscription Status and Bidding Demand | BrokerLens"
    if shows_value and info["final"]:
        desc = f"Check {co} ({sym}) IPO's overall subscription multiple ({sub_str}), price band and bidding window, from the exchange public-issue feed."
    elif shows_value:
        desc = f"{co} ({sym}) IPO overall subscription multiple ({sub_str} as of {snap_date}), price band and bidding window, from the exchange public-issue feed."
    else:
        desc = f"{co} ({sym}) IPO price band and bidding window from the exchange public-issue feed. The final overall subscription multiple is not on file."

    if status in ("Active", "Forthcoming"):
        state_note = ""
    elif status == ipo_facts.STATUS_NO_LISTING:
        state_note = ipo_facts.NO_LISTING_NOTE + (" " + ipo_facts._flag_sentence(ipo_row) if ipo_facts.name_flag(ipo_row) else "")
    else:
        state_note = ("Bidding for this issue closed on %s." % end_date) if end_date != "Announced" else "Bidding for this issue has closed."
    state_html = (f'<div class="card" style="padding:12px 16px;margin:0 0 20px 0;border-left:3px solid var(--accent)">'
                  f'<div class="small muted">{_esc(state_note)} The figures below are what the feed holds for this issue.</div></div>') if state_note else ""

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPOs</a></li><li class="muted">/</li><li><a href="/ipo/{slug}/">{_esc(sym)}</a></li><li class="muted">/</li><li class="muted">Subscription Status</li></ol></nav>'

    if shows_value and info["final"]:
        a1 = f"The public issue recorded a total subscription of approximately {sub_str} based on official exchange disclosures."
    elif shows_value:
        a1 = (f"As of {snap_date}, while bidding is open, the overall subscription is approximately {sub_str}. "
              f"The multiple changes until the issue closes.")
    elif info:
        a1 = (f"The final subscription multiple for {co} IPO is not on file. The last snapshot, taken {snap_date} while bidding was open, "
              f"showed approximately {sub_num:.2f}x. Bidding has closed since, so that is not the result of the issue.")
    else:
        a1 = f"BrokerLens does not have an overall subscription figure on file for {co} IPO. The exchanges publish final bidding data on their public-issue pages."
    if status in ("Active", "Forthcoming"):
        a3 = (f"Bidding for {co} IPO closes on {end_date}. The exact closing time and the UPI mandate cut-off are stated in the "
              f"offer document and on your broker's bid screen.")
    elif status == ipo_facts.STATUS_NO_LISTING:
        a3 = f"The bidding end date on file for {co} IPO is {end_date}. {ipo_facts.NO_LISTING_NOTE}"
    else:
        a3 = f"Bidding for {co} IPO closed on {end_date}."
    faqs = [
        (f"What is the total subscription of {co} IPO?", a1),
        (f"Does BrokerLens show a QIB/NII/Retail category breakdown for {co} IPO?",
         "No. NSE's public-issue feed that BrokerLens ingests reports only the overall subscription multiple, not a category-wise (QIB/NII/Retail) breakdown. Check NSE's or BSE's own bidding portal directly for category-wise figures rather than a third-party estimate."),
        (f"When does bidding close for {co} IPO?", a3),
        (f"Where can I verify official bidding figures for {sym}?",
         "Official cumulative bidding data is published directly by the National Stock Exchange (NSE) and Bombay Stock Exchange (BSE) on their respective public issue portals.")
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
    <p class="muted" style="margin:0;max-width:76ch">Overall subscription multiple, shares offered versus bid and the bidding window, from the exchange public-issue feed. No category-wise breakdown is on file.</p>
  </div>
  <div style="display:flex;gap:8px">
    <a href="{allot_href}" class="btn btn-secondary">Check Allotment &rarr;</a>
    <a href="/ipo/{slug}/basis-of-allotment/" class="btn btn-primary">Basis of Allotment &rarr;</a>
  </div>
</div>

{state_html}
<div class="grid g4" style="gap:12px;margin-bottom:24px">
  <div class="card" style="padding:16px">
    <div class="xs muted">Overall Subscription</div>
    <div class="font-bold" style="font-size:24px;color:var(--accent);margin-top:4px">{_esc(sub_str)}</div>
    <div class="xs muted" style="margin-top:2px">{_esc(sub_note)}</div>
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
    Under Securities and Exchange Board of India (SEBI) ICDR regulations, applications made through UPI can be up to {ipo_facts.SEBI_BID_LIMITS['upi']}, and the retail category limit is {ipo_facts.SEBI_BID_LIMITS['retail']} per application ({ipo_facts.SEBI_BID_LIMITS['note']}). Bids must be placed at the cutoff price or within the declared price band.
  </p>
  <p class="muted" style="font-size:14px;line-height:1.6;margin:0 0 12px 0">
    NSE's public-issue feed that BrokerLens ingests reports only the overall subscription multiple shown above, not a category-wise (QIB/NII/Retail) breakdown. For category-wise bidding, check
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
    co = ipo_facts.display_name(ipo_row)
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
    # Only a plausible listing date on file is shown. "Day T+3" is the SEBI rule for an issue still inside
    # its listing window; an issue with no listing on file shows "Not on file", never a date it does not have.
    if status == ipo_facts.STATUS_NO_LISTING:
        list_date = ipo_facts.listing_date_display(ipo_row, "Not on file")
    else:
        list_date = ipo_facts.listing_date_display(ipo_row, "Day T+3")
    lim = ipo_facts.SEBI_BID_LIMITS
    if status in ("Active", "Forthcoming"):
        close_action = "UPI autopay mandates must be accepted before the closing cutoff."
        state_html = ""
    else:
        close_action = "Bidding for this issue has closed."
        note = (ipo_facts.NO_LISTING_NOTE + (" " + ipo_facts._flag_sentence(ipo_row) if ipo_facts.name_flag(ipo_row) else "")
                if status == ipo_facts.STATUS_NO_LISTING else "Bidding for this issue has closed.")
        state_html = (f'<div class="card" style="padding:12px 16px;margin:0 0 20px 0;border-left:3px solid var(--accent)">'
                      f'<div class="small muted">{_esc(note)} This page explains the process and shows the dates on file.</div></div>')

    title = f"{co} ({sym}) IPO Basis of Allotment: Lottery Process & Refund Timeline | BrokerLens"
    desc = f"Basis of Allotment for {co} ({sym}) IPO: how the SEBI retail lottery works, the ASBA unblocking schedule and where to check the registrar's allotment."

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPOs</a></li><li class="muted">/</li><li><a href="/ipo/{slug}/">{_esc(sym)}</a></li><li class="muted">/</li><li class="muted">Basis of Allotment</li></ol></nav>'

    faqs = [
        (f"How is the Basis of Allotment calculated for {co} IPO?",
         f"Under SEBI rules, when the retail category is oversubscribed, each valid applicant has equal odds of receiving at most 1 minimum lot through a computerized lottery run by the registrar; applicants beyond what the retail quota can cover receive zero shares." + (f" The lot size on file is {lot} shares." if lot else " The lot size is printed in the issue prospectus; none is on file here.")),
        (f"What are my allotment chances for {co} IPO?",
         f"Your exact odds depend on the retail category's own subscription multiple, which NSE's public feed does not break out by category (BrokerLens does not estimate this number). Check NSE's or BSE's bidding portal for the retail-category multiple during bidding, or the registrar's published Basis of Allotment PDF once {co}'s allotment is finalized, for your exact odds."),
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

{state_html}
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
    <div class="font-bold" style="font-size:24px;color:var(--text);margin-top:4px">{lim['retail']}</div>
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
        <tr><td><strong>Retail bid limit</strong></td><td class="num">Up to {lim['retail']}</td><td>Limit for the retail category ({lim['note']})</td></tr>
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
          <td>{close_action}</td>
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
        # Non-equity public issues (a debt series published in the IPO feed) get no IPO sub-pages.
        if ipo_facts.is_non_equity_issue(r):
            continue
        # Pages of Listed IPOs and of IPOs with no listing on file are still written (noindex,follow,
        # self canonical) so old links do not 404, but are kept out of the returned list, which feeds the sitemap.
        listed = ipo_facts.is_settled(r)

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

    print(f"[ipo_subscription_engine] Successfully generated {len(generated_urls)} indexable subscription & allotment pages (listed and no-listing IPOs are noindex and not in the sitemap)!")
    return generated_urls


if __name__ == "__main__":
    urls = build_ipo_subscription_suite()
    print(f"Generated {len(urls)} pages.")
