"""Share Price Target & Forecast Engine.

Generates high-intent, EEAT-compliant share price target pages:
  - /stock/[sym]/share-price-target-[year]/

Each page includes:
  - Historical CAGR-based price projections at 3 scenarios (Bear, Base, Bull)
  - Technical support and resistance levels (52-week high/low)
  - Year-by-year compounding projection table
  - Schema.org FinancialProduct + FAQPage + BreadcrumbList JSON-LD
  - Mandatory SEBI disclaimer: Not investment advice

Zero external dependencies; stdlib Python.
Zero em dashes or en dashes anywhere.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")

TARGET_YEAR_OFFSETS = (0, 1, 2, 4)
MIN_HISTORY_SESSIONS = 756


def _target_years(current_year=None):
    if current_year is None:
        current_year = datetime.now(timezone.utc).year
    return tuple(current_year + offset for offset in TARGET_YEAR_OFFSETS)


def _has_three_year_history(closes):
    if len(closes) < MIN_HISTORY_SESSIONS:
        return False
    return all(
        math.isfinite(price) and price > 0
        for price in (closes[-MIN_HISTORY_SESSIONS], closes[-252], closes[-1])
    )


def _scenario_prices(current_price, hist_cagr_1y, hist_cagr_3y, years_forward):
    base_cagr = hist_cagr_3y
    spread = max(abs(hist_cagr_1y - hist_cagr_3y), 5.0)
    cagr_values = (
        base_cagr - spread,
        base_cagr,
        base_cagr + spread,
    )
    if not all(math.isfinite(value) and value > -100 for value in cagr_values):
        raise ValueError("historical CAGR inputs do not produce valid scenarios")

    prices = tuple(
        _project_price(current_price, cagr, years_forward)
        for cagr in cagr_values
    )
    if not all(
        math.isfinite(price) and format(price, ",.0f") != "0"
        for price in prices
    ):
        raise ValueError("scenario price would be non-finite or display as zero")
    return cagr_values, prices


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _stock_slug(sym: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (sym or "").lower()).strip("-")


def _compute_cagr(start_price, end_price, years):
    if start_price <= 0 or end_price <= 0 or years <= 0:
        return 0.0
    return ((end_price / start_price) ** (1.0 / years) - 1.0) * 100.0


def _project_price(current, cagr_pct, years_forward):
    if years_forward <= 0:
        return current
    return current * ((1 + cagr_pct / 100.0) ** years_forward)


def render_target_page(sym, name, current_price, high_52w, low_52w,
                       hist_cagr_1y, hist_cagr_3y, target_year,
                       history_sessions, data_as_of,
                       site_url="https://www.brokerlens.in"):
    """Renders /stock/[sym]/share-price-target-[year]/."""
    slug = _stock_slug(sym)
    canonical = f"{site_url}/stock/{slug}/share-price-target-{target_year}/"
    now_year = datetime.now(timezone.utc).year
    if target_year not in _target_years(now_year):
        raise ValueError("target year exceeds the supported forecast horizon")
    if history_sessions < MIN_HISTORY_SESSIONS:
        raise ValueError("at least three years of daily history are required")
    if not isinstance(data_as_of, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_as_of):
        raise ValueError("a valid source-data date is required")
    try:
        datetime.strptime(data_as_of, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("a valid source-data date is required") from exc
    if not all(
        math.isfinite(value) and value > 0
        for value in (current_price, high_52w, low_52w)
    ):
        raise ValueError("market prices must be finite and positive")
    years_forward = max(target_year - now_year, 1)

    cagr_values, target_prices = _scenario_prices(
        current_price, hist_cagr_1y, hist_cagr_3y, years_forward
    )
    bear_cagr, base_cagr, bull_cagr = cagr_values
    bear_target, base_target, bull_target = target_prices

    title = f"{sym} Share Price Target {target_year}: Forecast, Projections and Analysis | BrokerLens"
    desc = (
        f"{sym} ({name}) share price target for {target_year}. "
        f"Bear case: Rs {bear_target:,.0f}, Base case: Rs {base_target:,.0f}, "
        f"Bull case: Rs {bull_target:,.0f}. "
        f"Based on historical CAGR, 52-week range, and technical levels."
    )[:295]

    # Year-by-year projection table
    projection_rows = ""
    for y in range(1, years_forward + 1):
        proj_year = now_year + y
        bear_p = _project_price(current_price, bear_cagr, y)
        base_p = _project_price(current_price, base_cagr, y)
        bull_p = _project_price(current_price, bull_cagr, y)
        projection_rows += f"""
        <tr>
          <td><strong>{proj_year}</strong></td>
          <td class="num right">Rs {bear_p:,.0f}</td>
          <td class="num right" style="color:var(--text-bright)"><strong>Rs {base_p:,.0f}</strong></td>
          <td class="num right" style="color:var(--green)">Rs {bull_p:,.0f}</td>
        </tr>"""

    faqs = [
        (
            f"What is the {sym} share price target for {target_year}?",
            f"Based on historical growth analysis, the {sym} share price target for {target_year} ranges from "
            f"Rs {bear_target:,.0f} (conservative) to Rs {base_target:,.0f} (base case) to Rs {bull_target:,.0f} (optimistic). "
            f"These projections are based on trailing CAGR and should not be treated as guaranteed outcomes."
        ),
        (
            f"What is the current share price of {sym}?",
            f"The current market price of {sym} ({name}) is Rs {current_price:,.2f}. "
            f"The 52-week high is Rs {high_52w:,.2f} and 52-week low is Rs {low_52w:,.2f}."
        ),
        (
            f"Is {sym} a good stock to buy for the long term?",
            f"Long-term investment decisions depend on individual risk tolerance, financial goals, and portfolio diversification. "
            f"Examine the company's fundamentals, debt-to-equity ratio, promoter holding, and competitive positioning within its sector. "
            f"BrokerLens provides data-driven analysis; consult a SEBI-registered financial advisor before investing."
        ),
        (
            f"What methodology does BrokerLens use for {sym} price targets?",
            f"BrokerLens computes price targets using historical Compound Annual Growth Rate (CAGR) derived from official NSE closing prices. "
            f"Three scenarios are modeled: Bear (conservative at {bear_cagr:.1f}% CAGR), Base ({base_cagr:.1f}% CAGR), "
            f"and Bull (optimistic at {bull_cagr:.1f}% CAGR). These are statistical projections, not guaranteed forecasts."
        ),
    ]

    faq_html = "".join(
        f'<details class="faq-item" style="margin-bottom:12px;border:1px solid var(--border);border-radius:8px;padding:12px 16px;">'
        f'<summary style="cursor:pointer;font-weight:600;font-size:15px;">{_esc(q)}</summary>'
        f'<p style="margin:8px 0 0 0;font-size:14px;line-height:1.6;color:var(--text-muted);">{_esc(a)}</p>'
        f'</details>'
        for q, a in faqs
    )

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FinancialProduct",
                "name": f"{sym} Share Price Target {target_year}",
                "url": canonical,
                "description": desc
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": site_url},
                    {"@type": "ListItem", "position": 2, "name": "Stocks", "item": f"{site_url}/stocks/"},
                    {"@type": "ListItem", "position": 3, "name": sym, "item": f"{site_url}/stock/{slug}/"},
                    {"@type": "ListItem", "position": 4, "name": f"Price Target {target_year}", "item": canonical}
                ]
            }
        ]
    }

    # Related year links
    related_years = "".join(
        f'<a class="chip" href="/stock/{slug}/share-price-target-{y}/" '
        f'style="padding:6px 14px;text-decoration:none;background:var(--bg-raised);border:1px solid var(--border);border-radius:20px;font-size:13px;">'
        f'{y}</a> '
        for y in _target_years(now_year) if y != target_year
    )

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
    <a href="/brokers/">Brokers</a>
    <a href="/stocks/" style="color:var(--accent);font-weight:600">Stocks</a>
    <a href="/compare/">Compare</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px">
  <li><a href="/">Home</a></li><li class="muted">/</li>
  <li><a href="/stocks/">Stocks</a></li><li class="muted">/</li>
  <li><a href="/stock/{slug}/">{sym}</a></li><li class="muted">/</li>
  <li class="muted">Price Target {target_year}</li>
</ol></nav>

<h1 style="margin:20px 0 8px 0;font-size:26px">{sym} Share Price Target {target_year}</h1>
<p class="muted" style="max-width:75ch;margin:0 0 24px 0;line-height:1.6">
  CAGR-based price projection for <strong>{_esc(name)}</strong> ({sym}) targeting {target_year},
  derived from official NSE exchange closing prices.
</p>

<div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:16px;margin-bottom:28px">
  <div class="card" style="padding:18px;text-align:center;background:var(--bg-raised);border-left:3px solid var(--red)">
    <div class="xs muted">Bear Case ({bear_cagr:.1f}% CAGR)</div>
    <div style="font-size:22px;font-weight:700;margin:6px 0">Rs {bear_target:,.0f}</div>
    <div class="xs muted">{target_year} Target</div>
  </div>
  <div class="card" style="padding:18px;text-align:center;background:var(--bg-raised);border-left:3px solid var(--accent)">
    <div class="xs muted">Base Case ({base_cagr:.1f}% CAGR)</div>
    <div style="font-size:22px;font-weight:700;color:var(--text-bright);margin:6px 0">Rs {base_target:,.0f}</div>
    <div class="xs muted">{target_year} Target</div>
  </div>
  <div class="card" style="padding:18px;text-align:center;background:var(--bg-raised);border-left:3px solid var(--green)">
    <div class="xs muted">Bull Case ({bull_cagr:.1f}% CAGR)</div>
    <div style="font-size:22px;font-weight:700;color:var(--green);margin:6px 0">Rs {bull_target:,.0f}</div>
    <div class="xs muted">{target_year} Target</div>
  </div>
</div>

<div class="card" style="padding:20px;background:var(--bg-raised);margin-bottom:28px">
  <h2 style="font-size:18px;margin-top:0">Current Market Snapshot</h2>
  <p class="xs muted">NSE price history through {_esc(data_as_of)}; projections are mechanical scenarios, not analyst forecasts.</p>
  <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));gap:12px;font-size:14px">
    <div><span class="muted">CMP:</span> <strong>Rs {current_price:,.2f}</strong></div>
    <div><span class="muted">52W High:</span> <strong>Rs {high_52w:,.2f}</strong></div>
    <div><span class="muted">52W Low:</span> <strong>Rs {low_52w:,.2f}</strong></div>
    <div><span class="muted">1Y CAGR:</span> <strong>{hist_cagr_1y:.1f}%</strong></div>
    <div><span class="muted">3Y CAGR:</span> <strong>{hist_cagr_3y:.1f}%</strong></div>
  </div>
</div>

<div class="card" style="padding:20px;background:var(--bg-raised);margin-bottom:28px">
  <h2 style="font-size:18px;margin-top:0">Year-by-Year Price Projection</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Year</th><th class="right">Bear Case</th><th class="right">Base Case</th><th class="right">Bull Case</th></tr>
      </thead>
      <tbody>{projection_rows}</tbody>
    </table>
  </div>
</div>

<div style="margin-bottom:28px">
  <h2 style="font-size:18px;margin-bottom:12px">Other {sym} Price Targets</h2>
  <div style="display:flex;flex-wrap:wrap;gap:8px">{related_years}</div>
</div>

<h2 style="font-size:18px;margin-bottom:12px">Frequently Asked Questions</h2>
<div style="max-width:72ch">{faq_html}</div>

<div style="margin-top:28px;padding:16px;background:var(--surface-warn, #fff3cd);border-radius:8px;font-size:13px;line-height:1.6">
  <strong>Disclaimer:</strong> Share price targets on BrokerLens are statistical CAGR projections based on
  historical NSE closing prices. They are NOT guaranteed outcomes, investment advice, or analyst recommendations.
  Past performance does not guarantee future results. Consult a SEBI-registered investment advisor before
  making investment decisions. Mutual fund and equity investments are subject to market risks.
</div>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">Data sourced from NSE official exchange feeds. Not investment advice.</p>
  <p class="small"><a href="/stock/{slug}/">{sym} Overview</a> &middot; <a href="/stocks/">All Stocks</a> &middot; <a href="/trade-costs/">Trade Costs</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def build_share_price_target_suite(site_url="https://www.brokerlens.in", limit_stocks=2500):
    """Generates projections only for stocks with three years of daily prices."""
    ingest_path = os.path.join(DATA_DIR, "_ingest.json")
    if not os.path.exists(ingest_path):
        print("[share_price_target_engine] Error: _ingest.json not found")
        return []

    with open(ingest_path, "r", encoding="utf-8") as f:
        ingest = json.load(f)

    nse = ingest.get("nse", {})
    companies = {c.get("symbol", "").upper().strip(): c for c in nse.get("universe", {}).get("companies", [])}
    eq_hist = nse.get("equity_history", {})

    # Rank stocks by turnover
    stock_list = []
    insufficient_history = 0
    for sym, hist in eq_hist.items():
        if not hist or not isinstance(hist, list):
            continue
        closes = []
        dated_closes = []
        for row in hist:
            try:
                close = float(row.get("close") or 0)
            except (AttributeError, TypeError, ValueError):
                continue
            if math.isfinite(close) and close > 0:
                closes.append(close)
                dated_closes.append((close, row.get("date")))
        if not _has_three_year_history(closes):
            insufficient_history += 1
            continue
        recent_vols = [float(c.get("volume") or 0) for c in hist[-30:]]
        avg_vol = sum(recent_vols) / max(len(recent_vols), 1)
        stock_list.append((sym, avg_vol * closes[-1], closes, dated_closes[-1][1]))

    stock_list.sort(key=lambda x: x[1], reverse=True)
    stock_list = stock_list[:limit_stocks]

    generated_urls = []
    now_year = datetime.now(timezone.utc).year
    target_years = _target_years(now_year)

    print(
        f"[share_price_target_engine] Generating targets for {len(stock_list)} stocks "
        f"x {len(target_years)} years; skipped {insufficient_history} stocks "
        f"without {MIN_HISTORY_SESSIONS} valid daily closes."
    )

    for idx, (sym, _, closes, data_as_of) in enumerate(stock_list):
        c = companies.get(sym, {"symbol": sym, "name": sym})
        name = c.get("name") or sym
        current_price = closes[-1]
        high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        low_52w = min(closes[-252:]) if len(closes) >= 252 else min(closes)

        # Compute historical CAGRs
        hist_cagr_1y = _compute_cagr(closes[-252], closes[-1], 1)
        hist_cagr_3y = _compute_cagr(closes[-MIN_HISTORY_SESSIONS], closes[-1], 3)

        slug = _stock_slug(sym)

        for target_year in target_years:
            try:
                page_html = render_target_page(
                    sym=sym, name=name, current_price=current_price,
                    high_52w=high_52w, low_52w=low_52w,
                    hist_cagr_1y=hist_cagr_1y, hist_cagr_3y=hist_cagr_3y,
                    target_year=target_year, history_sessions=len(closes),
                    data_as_of=data_as_of,
                    site_url=site_url
                )
            except ValueError as exc:
                print(
                    f"[share_price_target_engine] Skipping {sym} {target_year}: {exc}"
                )
                continue

            page_dir = os.path.join(SITE_DIR, "stock", slug, f"share-price-target-{target_year}")
            os.makedirs(page_dir, exist_ok=True)

            with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as out:
                out.write(page_html)

            generated_urls.append(f"/stock/{slug}/share-price-target-{target_year}/")

        if (idx + 1) % 500 == 0:
            print(f"[share_price_target_engine]   ... {idx + 1}/{len(stock_list)} stocks processed ({len(generated_urls)} pages)")

    print(f"[share_price_target_engine] Successfully generated {len(generated_urls)} share price target pages!")
    return generated_urls


if __name__ == "__main__":
    urls = build_share_price_target_suite()
    print(f"Generated {len(urls)} pages.")
