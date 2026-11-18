"""Programmatic SIP & Compounding Wealth Scenario Engine.

Generates 320+ high-intent, long-tail programmatic financial planning pages:
  - /calculators/sip/ (Master SIP Scenario Finder & Matrix Hub)
  - /calculators/sip/[amount]-per-month-for-[years]-years/

Calculates:
  - Exact monthly compounding: M = P * ((1 + i)^n - 1) / i * (1 + i)
  - 4 return benchmarks: 8% (Hybrid), 10% (Large Cap), 12% (Nifty 50), 15% (Mid/Small Cap)
  - Year-by-year compounding progression schedule
  - Post-2024 Union Budget LTCG Tax Audit (Section 112A: Rs 1.25L exemption, 12.5% tax)
  - Inflation-adjusted real future purchasing power (assuming 6% CPI)
  - Head-to-head comparison against Bank RD (6.5%) and PPF (7.1%)

Structured Data:
  - Schema.org FinancialProduct
  - Schema.org FAQPage
  - Schema.org BreadcrumbList
"""
from __future__ import annotations

import html
import json
import math
import os
from datetime import datetime, timezone

try:
    from .indexation import NOINDEX_META, sip_indexable
except ImportError:  # run as a script
    from indexation import NOINDEX_META, sip_indexable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")

AMOUNTS = [
    500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000,
    6000, 7000, 7500, 8000, 9000, 10000, 12000, 12500, 15000, 18000,
    20000, 22000, 25000, 30000, 35000, 40000, 45000, 50000, 60000, 70000,
    75000, 80000, 90000, 100000, 125000, 150000, 200000
]

DURATIONS = [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 25, 28, 30, 35
]


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def calculate_sip(monthly_amount: float, annual_rate_pct: float, years: int):
    """Calculates future value of SIP using monthly compounding formula."""
    months = years * 12
    monthly_rate = (annual_rate_pct / 100.0) / 12.0
    if monthly_rate == 0:
        return monthly_amount * months
    # Formula: M = P * [ (1 + i)^n - 1 ] / i * (1 + i)
    fv = monthly_amount * (((1.0 + monthly_rate) ** months - 1.0) / monthly_rate) * (1.0 + monthly_rate)
    return round(fv, 2)


def render_sip_scenario_page(amount: int, years: int, site_url="https://www.brokerlens.in"):
    """Renders /calculators/sip/[amount]-per-month-for-[years]-years/."""
    slug = f"{amount}-per-month-for-{years}-years"
    canonical = f"{site_url}/calculators/sip/{slug}/"

    invested = amount * years * 12
    fv_8 = calculate_sip(amount, 8.0, years)
    fv_10 = calculate_sip(amount, 10.0, years)
    fv_12 = calculate_sip(amount, 12.0, years)
    fv_15 = calculate_sip(amount, 15.0, years)

    # Alternate assets
    fv_rd = calculate_sip(amount, 6.5, years)
    fv_ppf = calculate_sip(amount, 7.1, years)

    profit_12 = fv_12 - invested

    # Tax impact (Union Budget 2024 LTCG: Rs 1.25L exempt, 12.5% on remainder)
    taxable_profit = max(0.0, profit_12 - 125000.0)
    ltcg_tax = taxable_profit * 0.125
    post_tax_fv = fv_12 - ltcg_tax

    # Inflation adjusted real purchasing power at 6% CPI
    real_purchasing_power = fv_12 / ((1.0 + 0.06) ** years)

    # Only the amounts and horizons people search stay indexable (see indexation.py).
    robots_meta = "" if sip_indexable(amount, years) else NOINDEX_META + "\n"

    title = f"SIP of ₹{amount:,} per Month for {years} Years: Returns & Wealth Growth | BrokerLens"
    desc = f"Investing ₹{amount:,}/month for {years} years: Total investment of ₹{invested:,} grows to ₹{int(round(fv_12)):,} at 12% CAGR. Check tax impact, year-by-year schedule, and FD comparison."

    # Year-by-year schedule table
    year_rows = []
    for y in range(1, years + 1):
        y_inv = amount * y * 12
        y_fv = calculate_sip(amount, 12.0, y)
        y_profit = y_fv - y_inv
        year_rows.append(f"""
        <tr>
          <td>Year {y}</td>
          <td class="right num">₹{y_inv:,}</td>
          <td class="right num" style="color:var(--green)">+₹{int(round(y_profit)):,}</td>
          <td class="right num" style="font-weight:600">₹{int(round(y_fv)):,}</td>
        </tr>
        """)

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/calculators/">Calculators</a></li><li class="muted">/</li><li><a href="/calculators/sip/">SIP Scenarios</a></li><li class="muted">/</li><li class="muted">₹{amount:,}/mo for {years}Y</li></ol></nav>'

    faqs = [
        (f"How much will ₹{amount:,} invested monthly in SIP become after {years} years?",
         f"At a standard historical equity index return of 12% CAGR, a monthly SIP of ₹{amount:,} for {years} years generates a maturity corpus of approximately ₹{int(round(fv_12)):,} against an invested principal of ₹{invested:,}, earning a wealth gain of ₹{int(round(profit_12)):,}."),
        (f"What is the tax on the returns of ₹{amount:,} SIP after {years} years?",
         f"Under Section 112A (revised post-Budget 2024), Long Term Capital Gains (LTCG) from equity mutual funds held for more than 12 months are tax-exempt up to ₹1.25 Lakh per financial year. Profits exceeding ₹1.25 Lakh are taxed at flat 12.5%. For this scenario, estimated tax is ₹{int(round(ltcg_tax)):,}, leaving a net post-tax maturity value of ₹{int(round(post_tax_fv)):,}."),
        (f"How does an equity SIP compare to a Bank Recurring Deposit (RD)?",
         f"In a Bank RD at 6.5% interest, your total corpus would be ₹{int(round(fv_rd)):,}. An equity SIP at 12% delivers ₹{int(round(fv_12)):,}, generating ₹{int(round(fv_12 - fv_rd)):,} in extra wealth due to compounding power."),
        (f"What will be the real purchasing power of the corpus after inflation?",
         f"Assuming an average inflation rate of 6% over {years} years, the purchasing power of your ₹{int(round(fv_12)):,} maturity corpus will be equivalent to approximately ₹{int(round(real_purchasing_power)):,} in today's money.")
    ]

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FinancialProduct",
                "name": f"SIP Investment Scenario: ₹{amount:,}/Month for {years} Years",
                "description": desc,
                "url": canonical
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
                    {"@type": "ListItem", "position": 2, "name": "Calculators", "item": f"{site_url}/calculators/"},
                    {"@type": "ListItem", "position": 3, "name": "SIP Scenarios", "item": f"{site_url}/calculators/sip/"},
                    {"@type": "ListItem", "position": 4, "name": f"₹{amount:,}/mo for {years}Y", "item": canonical}
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
{robots_meta}<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers/">Brokers</a>
    <a href="/compare/">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:26px">SIP of ₹{amount:,} per Month for {years} Years</h1>
<p class="muted" style="max-width:75ch;margin:0 0 28px 0;line-height:1.6">
  Complete compounding breakdown for a Systematic Investment Plan (SIP) of <strong>₹{amount:,} monthly</strong> over a <strong>{years}-year</strong> investment horizon.
</p>

<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:16px;margin-bottom:32px">
  <div class="card" style="padding:18px;background:var(--bg-raised)">
    <div class="xs muted">Total Principal Invested</div>
    <div style="font-size:22px;font-weight:700;margin-top:4px">₹{invested:,}</div>
    <div class="xs muted" style="margin-top:2px">{years * 12} monthly installments</div>
  </div>
  <div class="card" style="padding:18px;background:var(--bg-raised)">
    <div class="xs muted">Est. Wealth Gain (@ 12%)</div>
    <div style="font-size:22px;font-weight:700;color:var(--green);margin-top:4px">+₹{int(round(profit_12)):,}</div>
    <div class="xs muted" style="margin-top:2px">{profit_12 / invested * 100:.1f}% gain on invested</div>
  </div>
  <div class="card" style="padding:18px;background:var(--bg-raised);border-left:4px solid var(--accent)">
    <div class="xs muted">Expected Maturity Value</div>
    <div style="font-size:22px;font-weight:700;color:var(--accent);margin-top:4px">₹{int(round(fv_12)):,}</div>
    <div class="xs muted" style="margin-top:2px">Assumes 12% diversified equity CAGR</div>
  </div>
  <div class="card" style="padding:18px;background:var(--bg-raised)">
    <div class="xs muted">Post-Tax Value (12.5% LTCG)</div>
    <div style="font-size:22px;font-weight:700;margin-top:4px">₹{int(round(post_tax_fv)):,}</div>
    <div class="xs muted" style="margin-top:2px">After ₹1.25L exemption</div>
  </div>
</div>

<div class="card" style="padding:24px;background:var(--bg-raised);margin-bottom:36px">
  <h2 style="font-size:19px;margin-top:0">Returns Across Different Asset Classes</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Asset Class / Style</th><th class="right">Expected CAGR</th><th class="right">Total Invested</th><th class="right">Estimated Returns</th><th class="right">Maturity Corpus</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Bank Recurring Deposit (RD)</strong></td>
          <td class="right num">6.5%</td>
          <td class="right num">₹{invested:,}</td>
          <td class="right num">+₹{int(round(fv_rd - invested)):,}</td>
          <td class="right num">₹{int(round(fv_rd)):,}</td>
        </tr>
        <tr>
          <td><strong>Public Provident Fund (PPF)</strong></td>
          <td class="right num">7.1%</td>
          <td class="right num">₹{invested:,}</td>
          <td class="right num">+₹{int(round(fv_ppf - invested)):,}</td>
          <td class="right num">₹{int(round(fv_ppf)):,}</td>
        </tr>
        <tr>
          <td><strong>Conservative Hybrid Funds</strong></td>
          <td class="right num">8.0%</td>
          <td class="right num">₹{invested:,}</td>
          <td class="right num">+₹{int(round(fv_8 - invested)):,}</td>
          <td class="right num">₹{int(round(fv_8)):,}</td>
        </tr>
        <tr>
          <td><strong>Large Cap / Nifty 50 Index</strong></td>
          <td class="right num">10.0%</td>
          <td class="right num">₹{invested:,}</td>
          <td class="right num">+₹{int(round(fv_10 - invested)):,}</td>
          <td class="right num">₹{int(round(fv_10)):,}</td>
        </tr>
        <tr style="background:rgba(var(--accent-rgb), 0.05)">
          <td><strong>Diversified Equity (Flexi Cap / Multicap)</strong></td>
          <td class="right num" style="font-weight:700">12.0%</td>
          <td class="right num">₹{invested:,}</td>
          <td class="right num" style="color:var(--green);font-weight:700">+₹{int(round(profit_12)):,}</td>
          <td class="right num" style="color:var(--accent);font-weight:700">₹{int(round(fv_12)):,}</td>
        </tr>
        <tr>
          <td><strong>Mid Cap / Small Cap Funds</strong></td>
          <td class="right num">15.0%</td>
          <td class="right num">₹{invested:,}</td>
          <td class="right num" style="color:var(--green)">+₹{int(round(fv_15 - invested)):,}</td>
          <td class="right num">₹{int(round(fv_15)):,}</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>

<h2 style="font-size:20px;margin-bottom:14px">Year-by-Year Wealth Accumulation Schedule (@ 12% CAGR)</h2>
<div class="card" style="padding:20px;background:var(--bg-raised);margin-bottom:36px">
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Timeline</th><th class="right">Invested Principal</th><th class="right">Growth / Gains</th><th class="right">Total Corpus Value</th></tr>
      </thead>
      <tbody>
        {''.join(year_rows)}
      </tbody>
    </table>
  </div>
</div>

<div class="card" style="padding:20px;background:var(--bg-raised);margin-bottom:36px">
  <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:16px">
    <div>
      <h3 style="margin:0 0 6px 0;font-size:18px">Invest in 0% Commission Direct Mutual Funds</h3>
      <p class="xs muted" style="margin:0">Start a monthly SIP on Zerodha Coin or Groww with zero distributor commissions.</p>
    </div>
    <a href="/broker/zerodha/" class="btn btn-primary">Review Zerodha Coin &rarr;</a>
  </div>
</div>

<h2 style="font-size:20px;margin-bottom:16px">Frequently Asked Questions</h2>
<div style="max-width:72ch;margin-bottom:36px">
  {faq_html}
</div>

<p class="small muted">
  Explore other durations: <a href="/calculators/sip/">View All SIP Scenarios</a> &middot; <a href="/calculators/">All Financial Calculators</a> &middot; <a href="/funds/">Mutual Funds Directory</a>
</p>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All calculations use standard compound interest algorithms. Mutual fund investments are subject to market risks.</p>
  <p class="small"><a href="/calculators/sip/">SIP Calculator Hub</a> &middot; <a href="/compare/">Compare Brokers</a> &middot; <a href="/trade-costs/">Trade Costs</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_sip_hub(all_scenarios, site_url="https://www.brokerlens.in"):
    """Renders master /calculators/sip/ scenario matrix."""
    canonical = f"{site_url}/calculators/sip/"
    title = "SIP Calculator Scenarios: Compare Monthly Investment Returns Across Years | BrokerLens"
    desc = "Explore 300+ pre-calculated SIP scenarios from ₹500 to ₹1,00,000 per month across 1 to 30 years. Exact maturity corpus, compounding tables, and 2024 LTCG tax impact."

    # Group by popular amounts
    amount_sections = []
    popular_amts = [1000, 2000, 3000, 5000, 10000, 15000, 20000, 25000, 50000]

    for amt in popular_amts:
        links = []
        for yr in [1, 3, 5, 7, 10, 15, 20, 25, 30]:
            slug = f"{amt}-per-month-for-{yr}-years"
            fv = calculate_sip(amt, 12.0, yr)
            links.append(f"""
            <a href="/calculators/sip/{slug}/" class="badge" style="padding:10px 12px;font-size:13px;text-decoration:none;background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;display:flex;flex-direction:column;gap:4px">
              <span style="font-weight:600;color:var(--fg)">{yr} Year{'s' if yr > 1 else ''}</span>
              <span class="xs" style="color:var(--accent)">₹{int(round(fv)):,}</span>
            </a>
            """)

        amount_sections.append(f"""
        <div style="margin-bottom:28px">
          <h3 style="margin:0 0 10px 0;font-size:17px">₹{amt:,} per Month SIP Growth</h3>
          <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(130px, 1fr));gap:8px">
            {''.join(links)}
          </div>
        </div>
        """)

    crumb_html = '<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/calculators/">Calculators</a></li><li class="muted">/</li><li class="muted">SIP Scenarios</li></ol></nav>'

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
                    {"@type": "ListItem", "position": 2, "name": "Calculators", "item": f"{site_url}/calculators/"},
                    {"@type": "ListItem", "position": 3, "name": "SIP Scenarios", "item": canonical}
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
    <a href="/brokers/">Brokers</a>
    <a href="/compare/">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:28px">SIP Wealth Calculator & Scenario Matrix</h1>
<p class="muted" style="max-width:75ch;margin:0 0 32px 0;line-height:1.6">
  Browse pre-calculated mutual fund SIP compounding scenarios. Select any monthly amount and investment duration below to see exact returns, post-tax corpus, inflation-adjusted wealth, and year-by-year schedules.
</p>

{''.join(amount_sections)}
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All calculations are based on standard financial compounding formulas. Past mutual fund performance is not an indicator of future returns.</p>
  <p class="small"><a href="/calculators/">All Calculators</a> &middot; <a href="/compare/">Compare Brokers</a> &middot; <a href="/trade-costs/">Trade Costs</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def build_sip_calculator_suite(site_url="https://www.brokerlens.in"):
    """Compiles all 320 SIP scenario pages and master hub."""
    out_dir = os.path.join(SITE_DIR, "calculators", "sip")
    os.makedirs(out_dir, exist_ok=True)

    generated_urls = []

    # 1. Master SIP scenario hub (/calculators/sip/)
    hub_html = render_sip_hub(None, site_url=site_url)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(hub_html)
    generated_urls.append("/calculators/sip/")

    # 2. Individual scenario pages
    for amt in AMOUNTS:
        for yr in DURATIONS:
            slug = f"{amt}-per-month-for-{yr}-years"
            page_dir = os.path.join(out_dir, slug)
            os.makedirs(page_dir, exist_ok=True)

            page_html = render_sip_scenario_page(amt, yr, site_url=site_url)
            with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as out:
                out.write(page_html)

            # Pages stay live either way; only the searched amount x year pairs are
            # indexable, so only those are returned for the sitemap.
            if sip_indexable(amt, yr):
                generated_urls.append(f"/calculators/sip/{slug}/")

    print(f"[sip_calculator_engine] Generated {len(AMOUNTS) * len(DURATIONS)} SIP scenario pages; "
          f"{len(generated_urls) - 1} indexable and in the sitemap, the rest noindex,follow")
    return generated_urls


if __name__ == "__main__":
    urls = build_sip_calculator_suite()
    print(f"Generated {len(urls)} pages.")
