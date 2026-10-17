"""Mutual Fund 1v1 Peer Comparison Engine & Category Directory.

Generates high-intent, authoritative mutual fund comparison pages:
  - /compare/mutual-funds/ (Master comparison hub)
  - /compare/mutual-funds/[fund-a]-vs-[fund-b]/ (Head-to-head scheme evaluations)
  - /funds-by/category/[category-slug]/ (Category directories: Flexi Cap, Large Cap, Small Cap, etc.)

Features:
  - Sourced directly from AMFI daily NAV dataset (ISIN, Direct vs Regular, Growth vs IDCW).
  - Statistically sound SIP compounding simulations (1Y, 3Y, 5Y, 10Y at 12% CAGR).
  - Explicit Direct vs Regular expense ratio compounding cost audit (saving ~1% yearly).
  - Budget 2024 Section 112A capital gains tax compliance (LTCG 12.5% > Rs 1.25L, STCG 20%).
  - Zero-commission direct mutual fund broker platform comparison (Zerodha Coin, Groww, Angel One).
  - Schema.org FinancialProduct + Table + FAQPage + BreadcrumbList JSON-LD.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _slugify(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


CATEGORIES = {
    "flexi-cap": {
        "title": "Flexi Cap Mutual Funds",
        "keywords": ["flexi cap", "flexicap"],
        "desc": "Flexi Cap equity mutual funds invest minimum 65% in equity and equity-related instruments with dynamic asset allocation across large cap, mid cap, and small cap companies without statutory market cap caps.",
        "benchmark": "NIFTY 500 TRI / BSE 500 TRI",
        "tax_type": "Equity",
        "horizon": "5+ Years",
    },
    "large-cap": {
        "title": "Large Cap Mutual Funds",
        "keywords": ["large cap", "bluechip", "top 100"],
        "desc": "Large Cap mutual funds invest at least 80% of total assets in the top 100 Indian companies by market capitalization, offering portfolio stability, steady dividends, and defensive capital preservation.",
        "benchmark": "NIFTY 100 TRI / S&P BSE 100 TRI",
        "tax_type": "Equity",
        "horizon": "3 to 5 Years",
    },
    "mid-cap": {
        "title": "Mid Cap Mutual Funds",
        "keywords": ["mid cap", "midcap", "emerging equity"],
        "desc": "Mid Cap funds allocate a minimum of 65% of assets to companies ranked 101 to 250 by market capitalization, offering higher growth momentum than large caps along with moderate cyclical volatility.",
        "benchmark": "NIFTY Midcap 150 TRI",
        "tax_type": "Equity",
        "horizon": "5 to 7 Years",
    },
    "small-cap": {
        "title": "Small Cap Mutual Funds",
        "keywords": ["small cap", "smallcap"],
        "desc": "Small Cap mutual funds invest at least 65% of total assets in companies ranked 251 and below by market capitalization, capturing high multi-bagger potential during industrial expansion cycles.",
        "benchmark": "NIFTY Smallcap 250 TRI",
        "tax_type": "Equity",
        "horizon": "7+ Years",
    },
    "index-funds": {
        "title": "Index Funds & ETFs",
        "keywords": ["nifty 50 index", "sensex index", "nifty next 50", "equal weight"],
        "desc": "Index mutual funds passively replicate the exact composition of major market indices (such as NIFTY 50 or BSE SENSEX), delivering market returns with ultra-low expense ratios and zero fund manager bias.",
        "benchmark": "NIFTY 50 TRI / BSE SENSEX TRI",
        "tax_type": "Equity",
        "horizon": "5+ Years",
    },
    "elss-tax-saver": {
        "title": "ELSS Tax Saver Funds",
        "keywords": ["elss", "tax saver", "tax advantage"],
        "desc": "Equity Linked Savings Schemes (ELSS) qualify for tax deductions up to Rs 1,50,000 under Section 80C of the Income Tax Act with the shortest mandatory lock-in period (3 years) among all 80C instruments.",
        "benchmark": "NIFTY 500 TRI",
        "tax_type": "Equity (80C Eligible)",
        "horizon": "3+ Years (Mandatory Lock-in)",
    },
    "liquid-funds": {
        "title": "Liquid & Overnight Funds",
        "keywords": ["liquid fund", "overnight fund", "cash management"],
        "desc": "Liquid mutual funds invest in short-term debt and money market instruments with maturity up to 91 days, designed for emergency funds, capital safety, and systematic transfer plans (STP).",
        "benchmark": "NIFTY Liquid Index A-I",
        "tax_type": "Debt (Sec 50AA Slab Rate)",
        "horizon": "1 Day to 3 Months",
    },
    "multi-cap": {
        "title": "Multi Cap Mutual Funds",
        "keywords": ["multi cap", "multicap"],
        "desc": "Multi Cap mutual funds mandate strict 25-25-25 portfolio allocation across large cap, mid cap, and small cap equities under SEBI rules, ensuring disciplined multi-cap diversification.",
        "benchmark": "NIFTY 500 Multicap 50:25:25 TRI",
        "tax_type": "Equity",
        "horizon": "5+ Years",
    },
    "large-mid-cap": {
        "title": "Large & Mid Cap Mutual Funds",
        "keywords": ["large & mid cap", "large and mid", "large & mid"],
        "desc": "Large and Mid Cap mutual funds invest minimum 35% in large caps and minimum 35% in mid caps, combining stability of bluechips with high growth momentum of mid-sized leaders.",
        "benchmark": "NIFTY LargeMidcap 250 TRI",
        "tax_type": "Equity",
        "horizon": "5+ Years",
    },
    "value-contra": {
        "title": "Value & Contra Mutual Funds",
        "keywords": ["value fund", "contra fund", "value discovery"],
        "desc": "Value and Contra funds follow contrarian investing strategies, picking fundamentally strong businesses trading at temporary market discounts with attractive margin of safety.",
        "benchmark": "NIFTY 500 TRI / S&P BSE 500 TRI",
        "tax_type": "Equity",
        "horizon": "5+ Years",
    },
    "balanced-advantage": {
        "title": "Balanced Advantage & Dynamic Asset Allocation Funds",
        "keywords": ["balanced advantage", "dynamic asset allocation", "baf"],
        "desc": "Balanced Advantage Funds dynamically shift allocation between equity and debt using valuation models like PE and PB, providing downside protection during market corrections.",
        "benchmark": "NIFTY 50 Hybrid Composite Debt 50:50 Index",
        "tax_type": "Equity Oriented (Dynamic)",
        "horizon": "3 to 5 Years",
    },
    "arbitrage-funds": {
        "title": "Arbitrage Mutual Funds",
        "keywords": ["arbitrage fund", "arbitrage"],
        "desc": "Arbitrage funds generate returns by simultaneously buying in cash equity and selling in futures derivative markets, offering low risk debt-like returns taxed at equity tax rates.",
        "benchmark": "NIFTY 50 Arbitrage Index",
        "tax_type": "Equity (Arbitrage Taxation)",
        "horizon": "3 Months to 1 Year",
    },
}


def _calculate_sip_corpus(monthly_amt, annual_rate, years):
    """Calculates future corpus and invested principal for monthly SIP."""
    months = years * 12
    r = annual_rate / 12.0
    fv = monthly_amt * (((1 + r) ** months - 1) / r) * (1 + r)
    principal = monthly_amt * months
    gain = fv - principal
    return principal, fv, gain


def _render_fund_comparison_page(f1, f2, cat_key, cat_meta, site_url, same_category=True, noindex=False, cat_meta2=None):
    """Renders /compare/mutual-funds/[fund-a]-vs-[fund-b]/index.html.

    same_category=False marks a cross-category "all-pairs" universe pairing
    (f2's real category is cat_meta2, not cat_meta) so copy and the table
    don't falsely claim both funds share a category. noindex=True marks that
    same random-pairing case as noindex,follow: the page still exists and
    works for a direct visit, but is excluded from search results rather
    than being submitted at scale as near-duplicate thin content."""
    cat_meta2 = cat_meta2 if cat_meta2 is not None else cat_meta
    n1, n2 = f1["name"], f2["name"]
    amc1, amc2 = f1["amc"], f2["amc"]
    slug1, slug2 = f1["slug"], f2["slug"]

    # Choose default growth variant
    v1 = next((v for v in f1["variants"] if "growth" in (v.get("option") or "").lower() and "direct" in (v.get("plan") or "").lower()), f1["variants"][0] if f1["variants"] else {})
    v2 = next((v for v in f2["variants"] if "growth" in (v.get("option") or "").lower() and "direct" in (v.get("plan") or "").lower()), f2["variants"][0] if f2["variants"] else {})

    nav1 = v1.get("nav") or 0.0
    nav2 = v2.get("nav") or 0.0
    date1 = v1.get("nav_date") or "Latest AMFI"
    date2 = v2.get("nav_date") or "Latest AMFI"
    isin1 = v1.get("isin_growth") or v1.get("isin_div_reinvest") or "Disclosed on AMFI"
    isin2 = v2.get("isin_growth") or v2.get("isin_div_reinvest") or "Disclosed on AMFI"

    pair_slug = f"{slug1}-vs-{slug2}"
    canonical = f"{site_url}/compare/mutual-funds/{pair_slug}/"
    title = f"{n1} vs {n2}: NAV, Expense, SIP Return & Portfolio Comparison"
    desc = (
        f"Compare {n1} ({amc1}) vs {n2} ({amc2}). Analyze latest NAV, Direct vs Regular plan compounding difference, "
        f"SIP Rs 5,000 return scenarios, Budget 2024 LTCG tax rules, and zero-commission broker availability."
    )[:295]

    # SIP scenarios: Rs 5,000/month at 12% CAGR
    p1, fv1_1y, g1_1y = _calculate_sip_corpus(5000, 0.12, 1)
    _, fv1_3y, g1_3y = _calculate_sip_corpus(5000, 0.12, 3)
    _, fv1_5y, g1_5y = _calculate_sip_corpus(5000, 0.12, 5)

    # 15-year direct vs regular cost impact
    # Regular plan typically has 1.0% higher expense ratio
    _, fv_dir, _ = _calculate_sip_corpus(5000, 0.12, 15)
    _, fv_reg, _ = _calculate_sip_corpus(5000, 0.11, 15)
    diff_reg = fv_dir - fv_reg

    category_claim = (
        f"Both {n1} (managed by {amc1}) and {n2} (managed by {amc2}) operate within the {cat_meta['title']} category following {cat_meta['benchmark']}. Selection depends on your risk tolerance: examine portfolio concentration, fund manager tenure, cash allocation, and tracking difference. Always opt for the Direct-Growth plan to eliminate distributor trail commissions."
        if same_category else
        f"{n1} (managed by {amc1}) is classified under the {cat_meta['title']} category; {n2} (managed by {amc2}) may fall under a different category, so check each fund's own category and benchmark before comparing them directly. Selection depends on your risk tolerance: examine portfolio concentration, fund manager tenure, cash allocation, and tracking difference. Always opt for the Direct-Growth plan to eliminate distributor trail commissions."
    )

    faq_items = [
        (
            f"Which fund is better between {n1} and {n2}?",
            category_claim
        ),
        (
            f"How much extra corpus do I earn by choosing Direct Plan over Regular Plan?",
            f"Direct plans have an expense ratio approximately 0.75% to 1.25% lower than Regular plans because no distributor commission is paid. On a Rs 5,000 monthly SIP running for 15 years at an assumed 12% annual return, choosing the Direct plan creates an estimated extra wealth of Rs {diff_reg:,.0f} compared to the Regular plan."
        ),
        (
            f"What is the capital gains tax on {n1} and {n2} under Budget 2024 rules?",
            f"Under Budget 2024 (Section 112A), equity mutual funds held for more than 12 months qualify for Long Term Capital Gains (LTCG) tax at 12.5% on capital gains exceeding the exemption threshold of Rs 1,25,000 per financial year. Units redeemed within 12 months are subject to Short Term Capital Gains (STCG) tax at 20% under Section 111A."
        ),
        (
            f"Can I invest in {n1} and {n2} with zero brokerage?",
            f"Yes. Discount brokers including Zerodha (Coin), Groww, and Angel One provide 100% zero-commission direct mutual fund investments without charging transaction fees or distributor commissions."
        ),
    ]

    faq_html = "".join(
        f'<div class="faq-item" style="margin-bottom:16px;">'
        f'<h4 style="margin:0 0 6px 0;font-size:15px;color:var(--text-bright);">{q}</h4>'
        f'<p class="muted" style="margin:0;font-size:14px;line-height:1.6;">{a}</p>'
        f'</div>'
        for q, a in faq_items
    )

    schema_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FinancialProduct",
                "name": f"{n1} vs {n2} Peer Comparison",
                "url": canonical,
                "description": desc,
                "category": cat_meta["title"]
            },
            {
                "@type": "Table",
                "about": f"Comparison of {n1} and {n2}"
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faq_items
                ]
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "Compare", "item": f"{site_url}/compare"},
                    {"@type": "ListItem", "position": 3, "name": "Mutual Funds", "item": f"{site_url}/compare/mutual-funds/"},
                    {"@type": "ListItem", "position": 4, "name": f"{n1} vs {n2}", "item": canonical}
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
{'<meta name="robots" content="noindex, follow">' if noindex else ''}
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare" class="active">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/calculators">Calculators</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/compare">Compare</a> &rsaquo;
    <a href="/compare/mutual-funds/">Mutual Funds</a> &rsaquo;
    <span>{n1} vs {n2}</span>
  </div>

  <header style="margin-bottom:28px;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
      <h1 style="font-size:28px;line-height:1.2;margin:0;">{n1} vs {n2}</h1>
      <span class="badge" style="background:var(--surface-raised);border:1px solid var(--border);padding:4px 10px;border-radius:16px;font-size:12px;">{cat_meta["title"] if same_category else f'{cat_meta["title"]} vs {cat_meta2["title"]}'}</span>
    </div>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Detailed head-to-head comparison of {n1} ({amc1}) versus {n2} ({amc2}). Sourced from official AMFI daily NAV disclosures with statutory taxation and SIP compounding schedule.
    </p>
  </header>

  <div class="card" style="margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:14px;color:var(--text-bright);">Key Fund Metrics Comparison</h2>
    <div class="table-wrap">
      <table class="table striped">
        <thead>
          <tr>
            <th>Parameter</th>
            <th><a class="link" href="/fund/{slug1}/">{n1}</a></th>
            <th><a class="link" href="/fund/{slug2}/">{n2}</a></th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Asset Management Company (AMC)</strong></td>
            <td><strong>{amc1}</strong></td>
            <td><strong>{amc2}</strong></td>
          </tr>
          <tr>
            <td><strong>Category & Benchmark</strong></td>
            <td>{cat_meta["title"]}<br><span class="muted xs">{cat_meta["benchmark"]}</span></td>
            <td>{cat_meta2["title"]}<br><span class="muted xs">{cat_meta2["benchmark"]}</span></td>
          </tr>
          <tr>
            <td><strong>Latest NAV (Direct Growth)</strong></td>
            <td><strong class="num" style="color:var(--brand);font-size:16px;">Rs {nav1:.4f}</strong><br><span class="muted xs">As of {date1}</span></td>
            <td><strong class="num" style="color:var(--brand);font-size:16px;">Rs {nav2:.4f}</strong><br><span class="muted xs">As of {date2}</span></td>
          </tr>
          <tr>
            <td><strong>Growth ISIN (Primary)</strong></td>
            <td><span class="mono xs">{isin1}</span></td>
            <td><span class="mono xs">{isin2}</span></td>
          </tr>
          <tr>
            <td><strong>Recommended Horizon</strong></td>
            <td>{cat_meta["horizon"]}</td>
            <td>{cat_meta["horizon"]}</td>
          </tr>
          <tr>
            <td><strong>Budget 2024 LTCG Tax</strong></td>
            <td>12.5% on gains &gt; Rs 1.25 Lakh (Sec 112A)</td>
            <td>12.5% on gains &gt; Rs 1.25 Lakh (Sec 112A)</td>
          </tr>
          <tr>
            <td><strong>STCG Tax (&lt; 12 Months)</strong></td>
            <td>20% flat (Sec 111A)</td>
            <td>20% flat (Sec 111A)</td>
          </tr>
          <tr>
            <td><strong>Zero-Commission Platforms</strong></td>
            <td>Zerodha Coin, Groww, Angel One</td>
            <td>Zerodha Coin, Groww, Angel One</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <section class="card" style="margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;color:var(--text-bright);">SIP Wealth Projection (Rs 5,000 / Month)</h2>
    <p style="font-size:14px;line-height:1.6;margin-bottom:14px;">
      Hypothetical compounding schedule for systematic investment plans (SIP) in either fund assuming a long-term normalized 12% annual CAGR:
    </p>
    <div class="table-wrap">
      <table class="table striped">
        <thead>
          <tr><th>Tenure</th><th>Total Invested Principal</th><th>Estimated Wealth @ 12% CAGR</th><th>Capital Appreciation</th></tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>1 Year</strong></td>
            <td class="num">Rs 60,000</td>
            <td class="num"><strong>Rs {fv1_1y:,.0f}</strong></td>
            <td class="num" style="color:var(--up);">+Rs {g1_1y:,.0f}</td>
          </tr>
          <tr>
            <td><strong>3 Years</strong></td>
            <td class="num">Rs 1,80,000</td>
            <td class="num"><strong>Rs {fv1_3y:,.0f}</strong></td>
            <td class="num" style="color:var(--up);">+Rs {g1_3y:,.0f}</td>
          </tr>
          <tr>
            <td><strong>5 Years</strong></td>
            <td class="num">Rs 3,00,000</td>
            <td class="num"><strong>Rs {fv1_5y:,.0f}</strong></td>
            <td class="num" style="color:var(--up);">+Rs {g1_5y:,.0f}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="card" style="margin-bottom:28px;background:var(--surface-raised);">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:10px;color:var(--text-bright);">Direct vs Regular Plan Compounding Impact</h2>
    <p style="font-size:14px;line-height:1.6;margin-bottom:12px;">
      Both {n1} and {n2} offer Direct and Regular plans. Choosing Regular plans deducts up to 1.0% each year from your NAV to pay broker distributor commissions. Over a 15-year SIP of Rs 5,000/month, choosing Direct Plan generates an extra <strong>Rs {diff_reg:,.0f}</strong> directly in your pocket.
    </p>
    <div class="row-wrap" style="gap:10px;">
      <a class="btn primary" href="https://zerodha.com/open-account?c=ZE5729" target="_blank" rel="noopener nofollow">Invest Direct via Zerodha Coin</a>
      <a class="btn secondary" href="/calculators/sip/">Calculate Custom SIP &rarr;</a>
    </div>
  </section>

  <section class="card" style="margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:16px;color:var(--text-bright);">Frequently Asked Questions</h2>
    {faq_html}
  </section>

  <section style="margin-top:32px;padding:20px;background:var(--surface-raised);border-radius:10px;border:1px solid var(--border);">
    <h3 style="font-size:16px;margin:0 0 12px 0;">More {cat_meta["title"]} Comparisons</h3>
    <p class="muted xs" style="margin-bottom:14px;">Explore other top peer head-to-head comparisons in this category:</p>
    <div class="row-wrap" style="gap:8px;">
      <a class="chip" href="/funds-by/category/{cat_key}/">All {cat_meta["title"]} &rarr;</a>
      <a class="chip" href="/fund/{slug1}/">{n1} Details</a>
      <a class="chip" href="/fund/{slug2}/">{n2} Details</a>
    </div>
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India. Sourced from AMFI daily NAV master records. Mutual fund investments are subject to market risks, read all scheme related documents carefully.</p>
    <p style="margin-top:8px;">
      <a href="/compare/mutual-funds/">All Mutual Fund Comparisons</a> &bull;
      <a href="/funds-by/">Mutual Funds by AMC</a> &bull;
      <a href="/calculators/sip/">SIP Calculator</a> &bull;
      <a href="/methodology">Methodology</a> &bull;
      <a href="/privacy-policy">Privacy Policy</a>
    </p>
  </div>
</footer>
</body>
</html>"""


def _render_category_hub(cat_key, cat_meta, funds, site_url):
    """Renders /funds-by/category/[category-slug]/index.html."""
    canonical = f"{site_url}/funds-by/category/{cat_key}/"
    title = f"{cat_meta['title']}: NAV, Expense & Scheme Directory | BrokerLens"
    desc = (
        f"Complete list of {cat_meta['title']} on AMFI. Compare latest NAV, Direct vs Regular plan options, "
        f"and statutory tax rules across {len(funds)} top asset management companies in India."
    )[:295]

    fund_rows = ""
    for f in funds:
        v = next((v for v in f["variants"] if "growth" in (v.get("option") or "").lower()), f["variants"][0] if f["variants"] else {})
        nav = v.get("nav") or 0.0
        date = v.get("nav_date") or "Latest AMFI"
        fund_rows += f"""
        <tr>
          <td><a class="link" href="/fund/{f['slug']}/"><strong>{_esc(f['name'])}</strong></a></td>
          <td>{_esc(f['amc'])}</td>
          <td class="num right">Rs {nav:.4f}</td>
          <td class="xs muted">{_esc(date)}</td>
        </tr>
        """

    schema_jsonld = {
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
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "Mutual Funds", "item": f"{site_url}/funds-by/"},
                    {"@type": "ListItem", "position": 3, "name": cat_meta["title"], "item": canonical}
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
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/calculators">Calculators</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/funds-by/">Mutual Funds</a> &rsaquo;
    <span>{cat_meta["title"]}</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0;">{cat_meta["title"]}</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      {cat_meta["desc"]} Official daily NAV master list covering {len(funds)} schemes across India's leading AMCs.
    </p>
  </header>

  <div class="card" style="margin-bottom:28px;">
    <div class="table-wrap">
      <table class="table striped">
        <thead>
          <tr><th>Scheme Name</th><th>AMC</th><th class="right">Growth NAV</th><th>Date</th></tr>
        </thead>
        <tbody>
          {fund_rows}
        </tbody>
      </table>
    </div>
  </div>

  <section class="card">
    <h3 style="margin-top:0;">Browse Other Mutual Fund Categories</h3>
    <div class="row-wrap" style="gap:8px;margin-top:12px;">
      {"".join(f'<a class="chip" href="/funds-by/category/{k}/">{v["title"]}</a>' for k, v in CATEGORIES.items())}
    </div>
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India. Sourced from AMFI daily NAV master records.</p>
  </div>
</footer>
</body>
</html>"""


def _render_master_compare_hub(comparisons_by_cat, site_url):
    """Renders /compare/mutual-funds/index.html."""
    canonical = f"{site_url}/compare/mutual-funds/"
    title = "Mutual Fund 1v1 Comparisons: Compare Schemes by NAV, Returns & Expense"
    desc = (
        "Compare top Indian mutual funds head-to-head. Analyze NAV differences, SIP returns, "
        "Direct vs Regular plan costs, and taxation across Flexi Cap, Large Cap, Small Cap, and Index funds."
    )[:295]

    sections_html = ""
    for cat_key, pairs in comparisons_by_cat.items():
        cat_meta = CATEGORIES[cat_key]
        pair_chips = "".join(
            f'<a class="chip" href="/compare/mutual-funds/{p_slug}/" style="padding:6px 12px;margin:4px;">{n1} vs {n2}</a>'
            for p_slug, n1, n2 in pairs[:16]
        )
        sections_html += f"""
        <div class="card" style="margin-bottom:20px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <h3 style="margin:0;font-size:18px;color:var(--text-bright);">{cat_meta["title"]}</h3>
            <a class="link xs" href="/funds-by/category/{cat_key}/">View Category Directory ({len(pairs)} comparisons) &rarr;</a>
          </div>
          <p class="muted xs" style="margin-bottom:12px;">{cat_meta["desc"]}</p>
          <div class="row-wrap">{pair_chips}</div>
        </div>
        """

    schema_jsonld = {
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
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "Compare", "item": f"{site_url}/compare"},
                    {"@type": "ListItem", "position": 3, "name": "Mutual Funds", "item": canonical}
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
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare" class="active">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/calculators">Calculators</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/compare">Compare</a> &rsaquo;
    <span>Mutual Funds</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:30px;line-height:1.2;margin:0 0 10px 0;">Mutual Fund 1v1 Comparisons</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Head-to-head empirical evaluations of India's leading mutual funds. Compare NAVs, SIP wealth trajectories, Direct versus Regular expense friction, and statutory tax rules.
    </p>
  </header>

  <section>
    {sections_html}
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India. Sourced from AMFI daily NAV master records.</p>
  </div>
</footer>
</body>
</html>"""


CURATED_TOP_N = 20  # funds per category that get indexed 1v1 comparison pages


def assign_fund_slugs(funds):
    """Stable URL slug per fund group, in place. Shared with publish.py so a
    fund page can link to the exact comparison pages this engine writes."""
    used_slugs = {}
    for f in funds:
        base = _slugify(f"{f['amc']} {f['name']}")
        slug, n = base, 2
        while slug in used_slugs:
            slug = f"{base}-{n}"
            n += 1
        used_slugs[slug] = True
        f["slug"] = slug


def categorize_funds(funds):
    """Bucket funds into the keyword categories above (first match wins)."""
    categorized = {k: [] for k in CATEGORIES}
    for f in funds:
        n_low = f["name"].lower()
        for cat_key, meta in CATEGORIES.items():
            if any(kw in n_low for kw in meta["keywords"]):
                categorized[cat_key].append(f)
                break
    return categorized


def curated_pair_index(funds):
    """Per-fund view of the curated (indexed) comparison set, keyed by
    (amc, name): its category and the exact comparison page slugs that
    generate_all() writes for it. Only same-category pairs among the first
    CURATED_TOP_N funds of a category are real pages; the noindex cross-category
    all-pairs are deliberately never returned, so nothing links to them."""
    assign_fund_slugs(funds)
    index = {}
    for cat_key, cat_funds in categorize_funds(funds).items():
        meta = CATEGORIES[cat_key]
        top = cat_funds[:CURATED_TOP_N]
        for i, f in enumerate(top):
            partners = []
            for j, g in enumerate(top):
                if i == j:
                    continue
                a, b = (f, g) if i < j else (g, f)
                partners.append((f"{a['slug']}-vs-{b['slug']}", g))
            index[(f["amc"], f["name"])] = {"cat": cat_key, "title": meta["title"], "partners": partners}
        for f in cat_funds[CURATED_TOP_N:]:
            index[(f["amc"], f["name"])] = {"cat": cat_key, "title": meta["title"], "partners": []}
    return index


def generate_all(site_url="https://www.brokerlens.in", universe_top_n=200):
    """Extracts mutual funds from ingest, categorizes them, and builds comparisons and hubs.

    Phase 1 - Category comparisons (existing): top 20 per category, intra-
              category pairs, displayed on the master hub.
    Phase 2 - Universe all-pairs (new): top ``universe_top_n`` funds across
              all categories, generating every unique pair not already emitted.

    Returns (comparison_urls, category_urls).
    """
    from pipeline.publish import _group_mutual_funds

    ingest_path = os.path.join(DATA_DIR, "_ingest.json")
    if not os.path.exists(ingest_path):
        return [], []

    with open(ingest_path, "r", encoding="utf-8") as f:
        ingest = json.load(f)

    schemes = ingest.get("amfi", {}).get("schemes", [])
    if not schemes:
        return [], []

    funds = _group_mutual_funds(schemes)

    assign_fund_slugs(funds)
    categorized = categorize_funds(funds)

    comparison_urls = []
    category_urls = []
    comparisons_by_cat = {}
    search_entries = []  # curated (real same-category) pairs only - never the noindex cross-category all-pairs
    emitted_pair_slugs = set()  # track to avoid duplicates across phases

    # ------------------------------------------------------------------
    # PHASE 1: Category Hubs + intra-category comparisons
    # ------------------------------------------------------------------
    phase1_count = 0
    for cat_key, meta in CATEGORIES.items():
        cat_funds = categorized.get(cat_key, [])
        if not cat_funds:
            continue
        dest_dir = os.path.join(SITE_DIR, "funds-by", "category", cat_key)
        os.makedirs(dest_dir, exist_ok=True)
        html_page = _render_category_hub(cat_key, meta, cat_funds[:60], site_url)
        with open(os.path.join(dest_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_page)
        category_urls.append(f"/funds-by/category/{cat_key}/")

        # Select top 20 funds for 1v1 comparisons (up to 190 comparisons per category)
        top_funds = cat_funds[:CURATED_TOP_N]
        cat_pairs = []
        for i in range(len(top_funds)):
            for j in range(i + 1, len(top_funds)):
                f1, f2 = top_funds[i], top_funds[j]
                pair_slug = f"{f1['slug']}-vs-{f2['slug']}"
                if pair_slug in emitted_pair_slugs:
                    continue
                emitted_pair_slugs.add(pair_slug)

                comp_dir = os.path.join(SITE_DIR, "compare", "mutual-funds", pair_slug)
                os.makedirs(comp_dir, exist_ok=True)
                comp_html = _render_fund_comparison_page(f1, f2, cat_key, meta, site_url)
                with open(os.path.join(comp_dir, "index.html"), "w", encoding="utf-8") as f:
                    f.write(comp_html)
                url_path = f"/compare/mutual-funds/{pair_slug}/"
                comparison_urls.append(url_path)
                cat_pairs.append((pair_slug, f1["name"][:32], f2["name"][:32]))
                search_entries.append([f"{f1['name']} vs {f2['name']}", url_path, meta["title"]])
                phase1_count += 1

        comparisons_by_cat[cat_key] = cat_pairs

    print(f"[fund_compare_engine] Phase 1: {phase1_count} intra-category pairs, {len(category_urls)} category hubs")

    # ------------------------------------------------------------------
    # PHASE 2: Universe all-pairs (top N funds by NAV, cross-category)
    # ------------------------------------------------------------------
    # Select top N funds by Direct Growth NAV (proxy for AUM / popularity)
    def _fund_nav(fund):
        v = next((v for v in fund.get("variants", [])
                  if "growth" in (v.get("option") or "").lower()
                  and "direct" in (v.get("plan") or "").lower()),
                 fund["variants"][0] if fund.get("variants") else {})
        return float(v.get("nav") or 0)

    all_funds_with_nav = [(f, _fund_nav(f)) for f in funds if f.get("variants")]
    all_funds_with_nav.sort(key=lambda x: x[1], reverse=True)
    top_universe = [f for f, _ in all_funds_with_nav[:universe_top_n]]

    # Determine default category for cross-category pairs
    def _fund_category(fund):
        n_low = fund["name"].lower()
        for cat_key, meta in CATEGORIES.items():
            if any(kw in n_low for kw in meta["keywords"]):
                return cat_key, meta
        # Fallback to the first category
        first_key = next(iter(CATEGORIES))
        return first_key, CATEGORIES[first_key]

    phase2_count = 0
    print(f"[fund_compare_engine] Phase 2: generating all-pairs for top {len(top_universe)} funds ...")

    for i in range(len(top_universe)):
        f1 = top_universe[i]
        for j in range(i + 1, len(top_universe)):
            f2 = top_universe[j]
            pair_slug = f"{f1['slug']}-vs-{f2['slug']}"
            if pair_slug in emitted_pair_slugs:
                continue
            emitted_pair_slugs.add(pair_slug)

            # Use fund 1's category as the comparison context, but look up
            # fund 2's own real category too, since cross-category pairs are
            # common here and the page must not claim they share a category
            # when they don't.
            cat_key, cat_meta = _fund_category(f1)
            cat2_key, cat2_meta = _fund_category(f2)
            same_category = cat_key == cat2_key

            comp_dir = os.path.join(SITE_DIR, "compare", "mutual-funds", pair_slug)
            os.makedirs(comp_dir, exist_ok=True)
            comp_html = _render_fund_comparison_page(
                f1, f2, cat_key, cat_meta, site_url,
                same_category=same_category, noindex=True, cat_meta2=cat2_meta,
            )
            with open(os.path.join(comp_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(comp_html)
            # Random all-pairs combinations are written to disk and remain
            # reachable, but are noindex and deliberately left out of
            # comparison_urls/the sitemap (same reasoning as stock_compare_engine).
            phase2_count += 1

        # Progress log every 25 funds
        if (i + 1) % 25 == 0:
            print(f"[fund_compare_engine]   ... processed {i + 1}/{len(top_universe)} funds ({phase2_count} cross-category pairs so far)")

    print(f"[fund_compare_engine] Phase 2: {phase2_count} cross-category all-pairs generated")

    # ------------------------------------------------------------------
    # Master Comparison Hub: /compare/mutual-funds/
    # ------------------------------------------------------------------
    master_dir = os.path.join(SITE_DIR, "compare", "mutual-funds")
    os.makedirs(master_dir, exist_ok=True)
    with open(os.path.join(master_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(_render_master_compare_hub(comparisons_by_cat, site_url))
    comparison_urls.append("/compare/mutual-funds/")

    total = phase1_count + phase2_count + 1
    print(
        f"[fund_compare_engine] TOTAL: {total} comparison pages written "
        f"({phase1_count} category + {phase2_count} cross-category + 1 hub); "
        f"{len(comparison_urls)} submitted to the sitemap (cross-category all-pairs are noindex, "
        f"written to disk but not submitted)"
    )
    return comparison_urls, category_urls, search_entries


if __name__ == "__main__":
    c_urls, cat_urls, _search_entries = generate_all()
    print(f"Generated {len(c_urls)} comparison pages and {len(cat_urls)} category hubs.")
