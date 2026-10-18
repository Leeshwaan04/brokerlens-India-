"""Stock Peer 1v1 Comparison Engine.

Generates high-intent, authoritative peer comparison pages:
  - /compare/stocks/ (Master comparison hub)
  - /compare/stocks/[stock-a]-vs-[stock-b]/ (Deep head-to-head metric comparison)

Compares:
  - CMP, 52-Week High/Low, 52-Week Price Range meter
  - 1-Year Return % and 30-Day Annualized Volatility
  - Average Daily Volume & Liquidity Score
  - Statutory Trading Costs to buy Rs 1 Lakh on Discount Brokers (Brokerage, STT, Exchange fee, Stamp duty, GST)
  - Side-by-side metric tables and investor FAQ

Structured Data:
  - Schema.org Product / ComparisonPage
  - Schema.org FAQPage
  - Schema.org BreadcrumbList
"""
from __future__ import annotations

import html
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")


def _stock_slug(sym: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (sym or "").lower()).strip("-")

SECTOR_PEER_GROUPS = {
    "Private Sector Banking": [
        "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
        "FEDERALBNK", "IDFCFIRSTB", "BANDHANBNK", "AUBANK", "YESBANK"
    ],
    "Public Sector (PSU) Banking": [
        "SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK",
        "INDIANB", "BANKINDIA", "MAHABANK", "CENTRALBK", "UCOBANK"
    ],
    "Information Technology (IT)": [
        "TCS", "INFY", "HCLTECH", "WIPRO", "TECHM",
        "LTIM", "PERSISTENT", "COFORGE", "KPITTECH", "TATAELXSI", "MPHASIS"
    ],
    "Automobiles & Electric Mobility": [
        "TMCV", "TMPV", "MARUTI", "M&M", "BAJAJ-AUTO",
        "HEROMOTOCO", "EICHERMOT", "TVSMOTOR", "ASHOKLEY"
    ],
    "Auto Components & Tyres": [
        "BHARATFORG", "MOTHERSON", "BOSCHLTD", "MRF", "APOLLOTYRE",
        "BALKRISIND", "CEATLTD", "ENDURANCE", "EXIDEIND"
    ],
    "FMCG & Consumer Goods": [
        "ITC", "HINDUNILVR", "NESTLEIND", "BRITANNIA", "TATACONSUM",
        "DABUR", "MARICO", "GODREJCP", "VBL", "COLPAL"
    ],
    "Pharmaceuticals & Healthcare": [
        "SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN",
        "TORNTPHARM", "ZYDUSLIFE", "MANKIND", "AUROPHARMA", "ALKEM"
    ],
    "Hospitals & Diagnostics": [
        "APOLLOHOSP", "MAXHEALTH", "FORTIS", "MEDANTA", "LALPATHLAB", "METROPOLIS", "NH"
    ],
    "Oil, Gas & Energy": [
        "RELIANCE", "ONGC", "IOC", "BPCL", "HPCL",
        "GAIL", "OIL", "PETRONET", "IGL", "MGL"
    ],
    "Power Generation & Utilities": [
        "NTPC", "POWERGRID", "TATAPOWER", "ADANIGREEN", "ADANIPOWER",
        "JSWENERGY", "NHPC", "SJVN", "TORNTPOWER"
    ],
    "Metals & Mining": [
        "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL",
        "NMDC", "SAIL", "NATIONALUM"
    ],
    "Capital Goods & Infrastructure": [
        "LT", "SIEMENS", "ABB", "BHEL", "HAL",
        "BEL", "CGPOWER", "CUMMINSIND", "THERMAX", "SUZLON"
    ],
    "Railways & Logistics": [
        "IRCTC", "RVNL", "IRFC", "RAILTEL", "RITES", "TITAGARH", "CONCOR"
    ],
    "Defense & Aerospace": [
        "HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "GRSE"
    ],
    "Chemicals & Agro": [
        "PIIND", "SRF", "AARTIIND", "DEEPAKNTR", "TATACHEM", "ATUL", "UPL", "COROMANDEL"
    ],
    "Cement & Building Materials": [
        "ULTRACEMCO", "AMBUJACEM", "ACC", "SHREECEM", "DALBHARAT", "JKCEMENT", "RAMCOCEM"
    ],
    "Real Estate & Housing": [
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "PHOENIXLTD", "BRIGADE", "SOBHA"
    ],
    "Retail, Ecommerce & Consumer Tech": [
        "ZOMATO", "SWIGGY", "TRENT", "DMART", "NYKAA", "PAYTM", "POLICYBZR", "DELHIVERY"
    ],
    "Telecom & Media": [
        "BHARTIARTL", "IDEA", "TATACOMM", "SUNTV", "ZEEL", "PVRINOX"
    ],
    "Market Infrastructure & Broking": [
        "BSE", "CDSL", "CAMS", "ANGELONE", "MOTILALOFS", "IEX", "MCX"
    ],
    "Hotels & Tourism": [
        "INDHOTEL", "EIHOTEL", "LEMONTREE", "CHALET"
    ],
    "Electricals & Cables": [
        "ASTRAL", "SUPREMEIND", "POLYCAB", "KEI", "HAVELLS", "CROMPTON", "VOLTAS"
    ],
    "Non-Banking Financial Companies (NBFC)": [
        "BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "SHRIRAMFIN", "MUTHOOTFIN", "MANAPPURAM", "POONAWALLA"
    ],
    "Mega-Cap Cross Leaders": [
        "RELIANCE", "TCS", "HDFCBANK", "BHARTIARTL", "ICICIBANK",
        "SBIN", "INFY", "ITC", "LT", "HINDUNILVR"
    ]
}


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def calculate_stock_metrics(history, default_name=""):
    """Extracts closing price, 52w high/low, 1y return, volatility, and avg volume."""
    if not history or not isinstance(history, list):
        return None

    closes = []
    volumes = []
    for c in history:
        cl = c.get("close")
        if cl is not None:
            closes.append(float(cl))
            volumes.append(float(c.get("volume") or 0))

    if not closes:
        return None

    cmp_price = closes[-1]
    if cmp_price <= 0:
        return None

    high_52w = max(closes)
    low_52w = min(closes)

    # 1y Return
    ret_1y = ((cmp_price - closes[0]) / closes[0]) * 100 if closes[0] > 0 else 0.0

    # 30-day volatility
    recent_closes = closes[-30:] if len(closes) >= 30 else closes
    if len(recent_closes) > 1:
        returns = [(recent_closes[i] - recent_closes[i-1]) / recent_closes[i-1] for i in range(1, len(recent_closes))]
        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        vol_daily = math.sqrt(var)
        vol_annual = vol_daily * math.sqrt(252) * 100 # annualized %
    else:
        vol_annual = 15.0

    # Avg Volume
    recent_vols = volumes[-30:] if len(volumes) >= 30 else volumes
    avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 0

    # 52w range position (0% = at 52w low, 100% = at 52w high)
    range_span = high_52w - low_52w
    range_pct = ((cmp_price - low_52w) / range_span * 100) if range_span > 0 else 50.0

    return {
        "cmp": cmp_price,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "return_1y": round(ret_1y, 2),
        "volatility_30d": round(vol_annual, 2),
        "avg_volume": int(avg_vol),
        "range_pct": round(range_pct, 1),
        "window_days": len(closes),
    }


def _range_window_label(window_days):
    """52-Week is only accurate with >= 1 year of daily closes; below that,
    label the actual window so the figure isn't claimed to cover a year of
    trading it doesn't have."""
    return "52-Week" if window_days >= 252 else f"{window_days}-Day"


def _return_window_label(window_days):
    return "1-Year" if window_days >= 252 else f"{window_days}-Day"


def render_comparison_hub(all_pairs, site_url="https://www.brokerlens.in"):
    """Renders /compare/stocks/ master hub."""
    canonical = f"{site_url}/compare/stocks/"
    title = "Compare Indian Stocks Side by Side: Head-to-Head Peer Comparison | BrokerLens"
    desc = "Compare top NSE stocks head to head on price, historical high/low range, period returns, 30-day volatility, delivery liquidity, and statutory trading costs across top sectors."

    sector_sections = []
    for sector_name, pairs in all_pairs.items():
        if not pairs:
            continue
        p_links = []
        for p in pairs[:20]:
            slug = f"{_stock_slug(p['sym1'])}-vs-{_stock_slug(p['sym2'])}"
            p_links.append(f"""
            <a href="/compare/stocks/{slug}/" class="badge" style="padding:10px 14px;font-size:14px;text-decoration:none;background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;display:flex;justify-content:space-between;align-items:center">
              <span><strong>{p['sym1']}</strong> <span class="muted">vs</span> <strong>{p['sym2']}</strong></span>
              <span class="xs muted" style="margin-left:8px">&rarr;</span>
            </a>
            """)

        sector_sections.append(f"""
        <div style="margin-bottom:32px">
          <h2 style="font-size:19px;margin-bottom:12px">{_esc(sector_name)}</h2>
          <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));gap:10px">
            {''.join(p_links)}
          </div>
        </div>
        """)

    crumb_html = '<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/compare">Compare</a></li><li class="muted">/</li><li class="muted">Stocks</li></ol></nav>'

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
                    {"@type": "ListItem", "position": 2, "name": "Compare", "item": f"{site_url}/compare"},
                    {"@type": "ListItem", "position": 3, "name": "Stocks", "item": canonical}
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
    <a href="/brokers">Brokers</a>
    <a href="/compare" style="color:var(--accent);font-weight:600">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:28px">Compare Indian Stocks Side by Side</h1>
<p class="muted" style="max-width:75ch;margin:0 0 32px 0;line-height:1.6">
  Direct head-to-head peer comparisons of top NSE-listed companies. Evaluate price performance, historical high/low boundaries, period returns, trading volatility, and statutory brokerage costs across key industry sectors.
</p>

{''.join(sector_sections)}
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All stock data is sourced from NSE exchange feeds and official company filings. Not investment advice.</p>
  <p class="small"><a href="/stocks/">Stocks Directory</a> &middot; <a href="/compare">Compare Brokers</a> &middot; <a href="/trade-costs/">Trade Costs</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_stock_comparison_page(s1, m1, s2, m2, sector_name, site_url="https://www.brokerlens.in", noindex=False):
    """Renders /compare/stocks/[sym1]-vs-[sym2]/.

    noindex=True marks the random "all-pairs" universe combinations (no
    curated sector relationship) as noindex,follow: the page still exists
    and works for a direct visit, but is excluded from search results
    rather than being submitted at scale as near-duplicate thin content."""
    sym1, sym2 = s1["symbol"], s2["symbol"]
    name1, name2 = s1["name"], s2["name"]
    slug = f"{_stock_slug(sym1)}-vs-{_stock_slug(sym2)}"

    window_days = min(m1["window_days"], m2["window_days"])
    range_label = _range_window_label(window_days)
    return_label = _return_window_label(window_days)
    return_period = "the past 12 months" if window_days >= 252 else f"the last {window_days} trading days"

    canonical = f"{site_url}/compare/stocks/{slug}/"
    title = f"{sym1} vs {sym2}: Stock Comparison, Price, Returns & Volatility | BrokerLens"
    desc = f"Compare {sym1} ({name1}) vs {sym2} ({name2}) head to head. {range_label} range, {return_label.lower()} returns ({m1['return_1y']}% vs {m2['return_1y']}%), volatility, volume, and brokerage costs."

    # Compare returns winner
    if m1["return_1y"] > m2["return_1y"]:
        ret_verdict = f"{sym1} has outperformed {sym2} over {return_period} with a gain of {m1['return_1y']}% compared to {m2['return_1y']}%."
    else:
        ret_verdict = f"{sym2} has outperformed {sym1} over {return_period} with a gain of {m2['return_1y']}% compared to {m1['return_1y']}%."

    # Compare volatility
    if m1["volatility_30d"] < m2["volatility_30d"]:
        vol_verdict = f"{sym1} demonstrated lower price volatility ({m1['volatility_30d']}% annualized) compared to {sym2} ({m2['volatility_30d']}%)."
    else:
        vol_verdict = f"{sym2} demonstrated lower price volatility ({m2['volatility_30d']}% annualized) compared to {sym1} ({m1['volatility_30d']}%)."

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/compare">Compare</a></li><li class="muted">/</li><li><a href="/compare/stocks/">Stocks</a></li><li class="muted">/</li><li class="muted">{sym1} vs {sym2}</li></ol></nav>'

    is_real_sector_pair = sector_name != "Cross-Sector Peers"
    sector_faq = (
        (f"Are {sym1} and {sym2} direct sector competitors?",
         f"Yes, both companies operate within the {sector_name} sector in India.")
        if is_real_sector_pair else
        (f"Are {sym1} and {sym2} direct sector competitors?",
         f"Not necessarily. This is a broad cross-sector comparison between two of NSE's higher-volume stocks, not a curated sector-peer pairing; check each company's own sector/industry classification on its stock profile before treating them as direct competitors.")
    )

    faqs = [
        (f"Between {sym1} and {sym2}, which stock gave better returns over {return_period}?",
         f"{ret_verdict}"),
        (f"Which stock is less volatile: {sym1} or {sym2}?",
         f"{vol_verdict} Lower volatility generally indicates steadier price action during market downturns."),
        (f"What is the statutory cost to buy ₹1,00,000 of {sym1} vs {sym2}?",
         f"Statutory exchange and government charges (STT, NSE turnover fees, SEBI fee, Stamp duty, and GST) are identical for delivery purchases of equal rupee value across both stocks, totaling approximately ₹118.50 on discount brokers offering zero delivery brokerage (like Zerodha or Dhan)."),
        sector_faq,
    ]

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": f"{sym1} vs {sym2} Stock Peer Comparison",
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
                    {"@type": "ListItem", "position": 2, "name": "Compare", "item": f"{site_url}/compare"},
                    {"@type": "ListItem", "position": 3, "name": "Stocks", "item": f"{site_url}/compare/stocks/"},
                    {"@type": "ListItem", "position": 4, "name": f"{sym1} vs {sym2}", "item": canonical}
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
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare" style="color:var(--accent);font-weight:600">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:26px">{sym1} vs {sym2}: Stock Comparison</h1>
<p class="muted" style="max-width:75ch;margin:0 0 28px 0;line-height:1.6">
  Head-to-head financial and trading comparison between <strong>{name1}</strong> ({sym1}) and <strong>{name2}</strong> ({sym2}){f" in the {sector_name} sector" if is_real_sector_pair else ""}.
</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:32px">
  <div class="card" style="padding:20px;background:var(--bg-raised)">
    <div class="row-between" style="align-items:center;margin-bottom:8px">
      <h2 style="margin:0;font-size:20px"><a href="/stocks/{sym1.lower()}/" style="color:inherit;text-decoration:none">{sym1}</a></h2>
      <span class="badge badge-verified">NSE: {sym1}</span>
    </div>
    <div class="xs muted" style="margin-bottom:14px">{_esc(name1)}</div>
    <div style="font-size:24px;font-weight:700;margin-bottom:6px">₹{m1['cmp']:,.2f}</div>
    <div class="xs" style="color:{'var(--green)' if m1['return_1y'] >= 0 else 'var(--red)'};margin-bottom:16px">
      {return_label} Return: <strong>{'+' if m1['return_1y'] > 0 else ''}{m1['return_1y']}%</strong>
    </div>
    <div style="font-size:13px;line-height:1.6">
      <div>{range_label} High: <strong>₹{m1['high_52w']:,.2f}</strong></div>
      <div>{range_label} Low: <strong>₹{m1['low_52w']:,.2f}</strong></div>
      <div>Annual Volatility: <strong>{m1['volatility_30d']}%</strong></div>
    </div>
    <a href="/broker/zerodha/trade/{sym1.lower()}/" class="btn btn-outline small" style="margin-top:14px;width:100%;text-align:center">Check {sym1} Trade Fees &rarr;</a>
  </div>

  <div class="card" style="padding:20px;background:var(--bg-raised)">
    <div class="row-between" style="align-items:center;margin-bottom:8px">
      <h2 style="margin:0;font-size:20px"><a href="/stocks/{sym2.lower()}/" style="color:inherit;text-decoration:none">{sym2}</a></h2>
      <span class="badge badge-verified">NSE: {sym2}</span>
    </div>
    <div class="xs muted" style="margin-bottom:14px">{_esc(name2)}</div>
    <div style="font-size:24px;font-weight:700;margin-bottom:6px">₹{m2['cmp']:,.2f}</div>
    <div class="xs" style="color:{'var(--green)' if m2['return_1y'] >= 0 else 'var(--red)'};margin-bottom:16px">
      {return_label} Return: <strong>{'+' if m2['return_1y'] > 0 else ''}{m2['return_1y']}%</strong>
    </div>
    <div style="font-size:13px;line-height:1.6">
      <div>{range_label} High: <strong>₹{m2['high_52w']:,.2f}</strong></div>
      <div>{range_label} Low: <strong>₹{m2['low_52w']:,.2f}</strong></div>
      <div>Annual Volatility: <strong>{m2['volatility_30d']}%</strong></div>
    </div>
    <a href="/broker/zerodha/trade/{sym2.lower()}/" class="btn btn-outline small" style="margin-top:14px;width:100%;text-align:center">Check {sym2} Trade Fees &rarr;</a>
  </div>
</div>

<div class="card" style="padding:24px;background:var(--bg-raised);margin-bottom:36px">
  <h2 style="font-size:19px;margin-top:0">Key Metrics Comparison Table</h2>
  <div class="table-scroll">
    <table class="data">
      <thead>
        <tr><th>Metric</th><th class="right">{sym1}</th><th class="right">{sym2}</th><th>Edge / Winner</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Current Market Price (CMP)</strong></td>
          <td class="right num">₹{m1['cmp']:,.2f}</td>
          <td class="right num">₹{m2['cmp']:,.2f}</td>
          <td class="muted">N/A</td>
        </tr>
        <tr>
          <td><strong>{return_label} Price Return</strong></td>
          <td class="right num" style="color:{'var(--green)' if m1['return_1y'] >= 0 else 'var(--red)'}">{'+' if m1['return_1y'] > 0 else ''}{m1['return_1y']}%</td>
          <td class="right num" style="color:{'var(--green)' if m2['return_1y'] >= 0 else 'var(--red)'}">{'+' if m2['return_1y'] > 0 else ''}{m2['return_1y']}%</td>
          <td><strong>{sym1 if m1['return_1y'] > m2['return_1y'] else sym2}</strong> ({abs(m1['return_1y'] - m2['return_1y']):.2f}% higher)</td>
        </tr>
        <tr>
          <td><strong>{range_label} High</strong></td>
          <td class="right num">₹{m1['high_52w']:,.2f}</td>
          <td class="right num">₹{m2['high_52w']:,.2f}</td>
          <td class="muted">N/A</td>
        </tr>
        <tr>
          <td><strong>{range_label} Low</strong></td>
          <td class="right num">₹{m1['low_52w']:,.2f}</td>
          <td class="right num">₹{m2['low_52w']:,.2f}</td>
          <td class="muted">N/A</td>
        </tr>
        <tr>
          <td><strong>30-Day Annualized Volatility</strong></td>
          <td class="right num">{m1['volatility_30d']}%</td>
          <td class="right num">{m2['volatility_30d']}%</td>
          <td><strong>{sym1 if m1['volatility_30d'] < m2['volatility_30d'] else sym2}</strong> (Steadier)</td>
        </tr>
        <tr>
          <td><strong>30-Day Average Daily Volume</strong></td>
          <td class="right num">{m1['avg_volume']:,}</td>
          <td class="right num">{m2['avg_volume']:,}</td>
          <td><strong>{sym1 if m1['avg_volume'] > m2['avg_volume'] else sym2}</strong> (Higher Liquidity)</td>
        </tr>
        <tr>
          <td><strong>Statutory Cost to Trade ₹1 Lakh</strong></td>
          <td class="right num">₹118.50</td>
          <td class="right num">₹118.50</td>
          <td>Identical statutory tariff</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>

<h2 style="font-size:20px;margin-bottom:16px">Frequently Asked Questions</h2>
<div style="max-width:72ch">
  {faq_html}
</div>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All stock data is based on official exchange disclosures. BrokerLens does not provide buy or sell recommendations.</p>
  <p class="small"><a href="/compare/stocks/">All Stock Comparisons</a> &middot; <a href="/compare">Compare Brokers</a> &middot; <a href="/stocks/">Stocks Directory</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def curated_peer_index(eq_hist):
    """symbol -> [(other_symbol, url_path, sector_name)] for exactly the
    sector-peer comparison pages build_stock_compare_suite() writes in Phase 1
    (same eligibility: real history on both sides and computable metrics, same
    dedupe by slug). Stock pages use this to link only to pages that exist; the
    noindex all-pairs are never included."""
    index = {}
    emitted = set()
    metrics = {}

    def ok(sym):
        if sym not in metrics:
            hist = eq_hist.get(sym)
            metrics[sym] = bool(hist) and calculate_stock_metrics(hist, sym) is not None
        return metrics[sym]

    for sector_name, sym_list in SECTOR_PEER_GROUPS.items():
        valid = [s for s in sym_list if s in eq_hist and len(eq_hist[s]) > 0]
        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                s1, s2 = valid[i], valid[j]
                if not (ok(s1) and ok(s2)):
                    continue
                slug = f"{_stock_slug(s1)}-vs-{_stock_slug(s2)}"
                if slug in emitted:
                    continue
                emitted.add(slug)
                url = f"/compare/stocks/{slug}/"
                index.setdefault(s1, []).append((s2, url, sector_name))
                index.setdefault(s2, []).append((s1, url, sector_name))
    return index


def build_stock_compare_suite(site_url="https://www.brokerlens.in", universe_top_n=500):
    """Generates stock peer comparisons across sector groups AND the full
    top-N universe (all C(N,2) pairs), producing 100K+ high-intent pages.

    Phase 1 - Sector peers (existing): intra-sector pairs from
              SECTOR_PEER_GROUPS, used to populate the master hub.
    Phase 2 - Universe all-pairs (new): top ``universe_top_n`` stocks by
              average daily volume, generating every unique pair that was
              not already produced in Phase 1.
    """
    ingest_path = os.path.join(DATA_DIR, "_ingest.json")
    if not os.path.exists(ingest_path):
        print("[stock_compare_engine] Error: _ingest.json not found")
        return []

    with open(ingest_path, "r", encoding="utf-8") as f:
        ingest = json.load(f)

    nse = ingest.get("nse", {})
    companies = {c.get("symbol", "").upper().strip(): c for c in nse.get("universe", {}).get("companies", [])}
    eq_hist = nse.get("equity_history", {})
    # same rule as the stock pages: nothing computed across an unadjusted split/bonus break
    sys.path.insert(0, ROOT)
    from pipeline.common import trim_to_last_break
    eq_hist = {sym: trim_to_last_break(c)[0] for sym, c in eq_hist.items()}

    all_pairs_by_sector = {}
    generated_urls = []
    search_entries = []  # curated (real sector-peer) pairs only - never the noindex all-pairs
    emitted_slugs = set()  # track slugs to avoid duplicates across phases

    out_base_dir = os.path.join(SITE_DIR, "compare", "stocks")
    os.makedirs(out_base_dir, exist_ok=True)

    sector_pairs_count = 0

    # ------------------------------------------------------------------
    # PHASE 1: Sector-based peer groups (for hub display)
    # ------------------------------------------------------------------
    for sector_name, sym_list in SECTOR_PEER_GROUPS.items():
        valid_symbols = [s for s in sym_list if s in eq_hist and len(eq_hist[s]) > 0]

        sector_pairs = []
        for i in range(len(valid_symbols)):
            for j in range(i + 1, len(valid_symbols)):
                sym1 = valid_symbols[i]
                sym2 = valid_symbols[j]

                c1 = companies.get(sym1, {"symbol": sym1, "name": sym1})
                c2 = companies.get(sym2, {"symbol": sym2, "name": sym2})

                m1 = calculate_stock_metrics(eq_hist[sym1], c1.get("name"))
                m2 = calculate_stock_metrics(eq_hist[sym2], c2.get("name"))

                if not m1 or not m2:
                    continue

                slug = f"{_stock_slug(sym1)}-vs-{_stock_slug(sym2)}"
                if slug in emitted_slugs:
                    continue
                emitted_slugs.add(slug)

                page_dir = os.path.join(out_base_dir, slug)
                os.makedirs(page_dir, exist_ok=True)

                page_html = render_stock_comparison_page(c1, m1, c2, m2, sector_name, site_url=site_url)
                with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as out:
                    out.write(page_html)

                url_path = f"/compare/stocks/{slug}/"
                generated_urls.append(url_path)
                sector_pairs.append({"sym1": sym1, "sym2": sym2, "url": url_path})
                search_entries.append([f"{sym1} vs {sym2}", url_path, sector_name])
                sector_pairs_count += 1

        all_pairs_by_sector[sector_name] = sector_pairs

    print(f"[stock_compare_engine] Phase 1: {sector_pairs_count} sector peer pairs across {len(SECTOR_PEER_GROUPS)} groups")

    # ------------------------------------------------------------------
    # PHASE 2: Universe all-pairs (top N by avg volume)
    # ------------------------------------------------------------------
    # Rank all symbols with equity history by 30-day average volume
    sym_vol = []
    for sym, hist in eq_hist.items():
        if not hist or not isinstance(hist, list):
            continue
        recent = hist[-30:] if len(hist) >= 30 else hist
        avg_vol = sum(float(c.get("volume") or 0) for c in recent) / max(len(recent), 1)
        sym_vol.append((sym, avg_vol))

    sym_vol.sort(key=lambda x: x[1], reverse=True)
    top_syms = [s for s, _ in sym_vol[:universe_top_n]]

    # Pre-compute metrics for all top symbols to avoid redundant recalculation
    metrics_cache = {}
    for sym in top_syms:
        m = calculate_stock_metrics(eq_hist[sym])
        if m:
            metrics_cache[sym] = m

    valid_top = [s for s in top_syms if s in metrics_cache]
    universe_pairs_count = 0
    cross_sector_label = "Cross-Sector Peers"

    print(f"[stock_compare_engine] Phase 2: generating all-pairs for {len(valid_top)} top stocks ...")

    for i in range(len(valid_top)):
        sym1 = valid_top[i]
        for j in range(i + 1, len(valid_top)):
            sym2 = valid_top[j]

            slug = f"{_stock_slug(sym1)}-vs-{_stock_slug(sym2)}"
            if slug in emitted_slugs:
                continue
            emitted_slugs.add(slug)

            c1 = companies.get(sym1, {"symbol": sym1, "name": sym1})
            c2 = companies.get(sym2, {"symbol": sym2, "name": sym2})
            m1 = metrics_cache[sym1]
            m2 = metrics_cache[sym2]

            page_dir = os.path.join(out_base_dir, slug)
            os.makedirs(page_dir, exist_ok=True)

            page_html = render_stock_comparison_page(c1, m1, c2, m2, cross_sector_label, site_url=site_url, noindex=True)
            with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as out:
                out.write(page_html)

            # Random (non-curated) all-pairs combinations are written to disk and
            # remain reachable, but are noindex (see render_stock_comparison_page)
            # and deliberately left out of generated_urls/the sitemap: submitting
            # ~125K near-duplicate-template pages is the "scaled content abuse"
            # pattern Google's spam policy targets, regardless of data accuracy.
            universe_pairs_count += 1

        # Progress log every 50 symbols
        if (i + 1) % 50 == 0:
            print(f"[stock_compare_engine]   ... processed {i + 1}/{len(valid_top)} symbols ({universe_pairs_count} universe pairs so far)")

    print(f"[stock_compare_engine] Phase 2: {universe_pairs_count} universe all-pairs generated")

    # ------------------------------------------------------------------
    # Master comparison hub (/compare/stocks/) - uses sector pairs for display
    # ------------------------------------------------------------------
    hub_html = render_comparison_hub(all_pairs_by_sector, site_url=site_url)
    with open(os.path.join(out_base_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(hub_html)
    generated_urls.append("/compare/stocks/")

    total = sector_pairs_count + universe_pairs_count + 1
    print(
        f"[stock_compare_engine] TOTAL: {total} pages written "
        f"({sector_pairs_count} sector + {universe_pairs_count} universe + 1 hub); "
        f"{len(generated_urls)} submitted to the sitemap (universe all-pairs are noindex, "
        f"written to disk but not submitted)"
    )
    return generated_urls, search_entries


if __name__ == "__main__":
    urls, _search_entries = build_stock_compare_suite()
    print(f"Generated {len(urls)} pages.")
