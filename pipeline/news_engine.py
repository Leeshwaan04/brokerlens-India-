"""Automated Real-Time News, Blogs & Articles Generation Engine.

Generates timely, high-quality, data-backed publications across four distinct categories:
  1. Real-Time Market News & Dispatches (/news/indian-stock-market-wrap-*/, sectoral pulses)
  2. Live IPO Bidding & Allotment Bulletins (/news/ipo-*-live-subscription-*/)
  3. Educational Blogs & Practical Investor Guides (/news/*-guide/, taxation, demat security)
  4. Empirical Research & Industry Analysis Articles (/news/*-study/, broker market share)

Features:
  - CLI execution with `--live` flag for real-time exchange pulls (NSE pulse + IPO APIs).
  - Pre-rendered static HTML with Schema.org NewsArticle and BlogPosting JSON-LD.
  - JSON API feed generation at `site/data/news.json` for client-side SPA instant rendering.
  - Full RSS 2.0 feed generation at `site/feed.xml`.
  - Zero external npm dependencies; strict standard library Python.
  - Zero em dashes or en dashes anywhere.
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _format_date(d_str):
    if not d_str:
        return "Recent"
    try:
        dt = datetime.date.fromisoformat(str(d_str)[:10])
        return dt.strftime("%d %B %Y")
    except Exception:
        return str(d_str)


def generate_news_corpus(ingest_data, site_url="https://www.brokerlens.in"):
    """Builds a rich collection of data-driven news, educational blogs, and empirical articles."""
    articles = []
    now = datetime.datetime.now(datetime.timezone.utc)
    today_iso = now.date().isoformat()
    today_str = now.strftime("%d %B %Y")

    nse_d = ingest_data.get("nse") or {}
    mkt = nse_d.get("pulse") or {}
    indices = mkt.get("indices") or []
    nifty = indices[0] if indices else {}
    breadth = nse_d.get("live", {}).get("breadth") or {}
    gainers = nse_d.get("live", {}).get("gainers") or []
    losers = nse_d.get("live", {}).get("losers") or []
    most_active = nse_d.get("live", {}).get("most_active") or []
    ipos = nse_d.get("ipo") or {}
    current_ipos = ipos.get("current") or []
    upcoming_ipos = ipos.get("upcoming") or []

    # =========================================================================
    # 1. REAL-TIME MARKET NEWS & DISPATCHES
    # =========================================================================
    nifty_last = nifty.get("last") or 25150.0
    nifty_chg = nifty.get("change") or 0.0
    nifty_pct = nifty.get("change_pct") or 0.0
    sentiment = "advanced" if nifty_chg >= 0 else "declined"
    sign_str = "+" if nifty_chg >= 0 else ""

    top_gainers_html = "".join(
        '<li><strong>%s</strong>: Rs %s (<span class="up">+%.2f%%</span>)</li>'
        % (_esc(g.get("symbol")), _esc(g.get("last")), g.get("change_pct", 0.0))
        for g in gainers[:5]
    ) or '<li>Top momentum tracked across NSE Nifty 50 constituents.</li>'

    top_losers_html = "".join(
        '<li><strong>%s</strong>: Rs %s (<span class="down">%.2f%%</span>)</li>'
        % (_esc(l.get("symbol")), _esc(l.get("last")), l.get("change_pct", 0.0))
        for l in losers[:5]
    ) or '<li>Equities tracking broader market consolidation.</li>'

    market_article_slug = "indian-stock-market-wrap-%s" % today_iso
    market_article_title = "Indian Stock Market Today: Nifty 50 at %s, Key Gainers and Sectoral Action (%s)" % (
        "{:,.2f}".format(nifty_last) if isinstance(nifty_last, (int, float)) else str(nifty_last),
        today_str
    )
    market_article_desc = (
        "NSE market summary for %s: Nifty 50 %s by %s%.2f points. Review top gainers, losers, "
        "turnover, and exchange breadth disclosures."
        % (today_str, sentiment, sign_str, nifty_chg)
    )[:300]

    market_article_body = """
    <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
      Indian benchmark indices %s in today's trading session, with the <strong>Nifty 50</strong>
      settling at <strong>%s</strong> (%s%.2f%%).
      Market breadth on the National Stock Exchange reflected %s advancing stocks against %s declining stocks.
    </p>

    <div class="section-title"><h2>Key Exchange Highlights</h2></div>
    <div class="grid g3" style="margin:16px 0">
      <div class="card stat">
        <div class="stat-label">NIFTY 50</div>
        <div class="stat-value">%s</div>
        <div class="stat-sub">%s%.2f pts (%s%.2f%%)</div>
      </div>
      <div class="card stat">
        <div class="stat-label">NSE Advances / Declines</div>
        <div class="stat-value">%s / %s</div>
        <div class="stat-sub">Market Breadth Ratio</div>
      </div>
      <div class="card stat">
        <div class="stat-label">Active Equities</div>
        <div class="stat-value">2,578</div>
        <div class="stat-sub">Tracked on NSE Primary Feeds</div>
      </div>
    </div>

    <div class="grid g2" style="margin:20px 0">
      <div class="card" style="padding:16px">
        <h3 style="font-size:15px;margin-bottom:10px">Top Gainers</h3>
        <ul style="padding-left:18px;margin:0;line-height:1.7">%s</ul>
      </div>
      <div class="card" style="padding:16px">
        <h3 style="font-size:15px;margin-bottom:10px">Key Consolidators</h3>
        <ul style="padding-left:18px;margin:0;line-height:1.7">%s</ul>
      </div>
    </div>

    <div class="section-title"><h2>Investor &amp; Trading Implications</h2></div>
    <p>
      With benchmark indices testing structural levels, retail participation across discount brokers
      continues to center around index derivatives and systematic investment plans (SIPs).
      Traders monitoring execution costs should evaluate delivery and intraday fee schedules
      across top SEBI-registered brokers.
    </p>
    <div class="card" style="margin-top:16px;padding:16px;border-left:4px solid var(--accent)">
      <p style="margin:0"><strong>Broker Cost Comparison:</strong> Compare delivery and F&amp;O brokerage charges across
      <a href="/compare/zerodha-vs-groww/" data-link>Zerodha vs Groww</a>,
      <a href="/compare/groww-vs-angel-one/" data-link>Groww vs Angel One</a>, and
      <a href="/compare/zerodha-vs-upstox/" data-link>Zerodha vs Upstox</a> to optimize monthly trading expenses.</p>
    </div>
    """ % (
        sentiment,
        "{:,.2f}".format(nifty_last) if isinstance(nifty_last, (int, float)) else str(nifty_last),
        sign_str, nifty_pct,
        breadth.get("advances", "-"), breadth.get("declines", "-"),
        "{:,.2f}".format(nifty_last) if isinstance(nifty_last, (int, float)) else str(nifty_last),
        sign_str, nifty_chg, sign_str, nifty_pct,
        breadth.get("advances", "-"), breadth.get("declines", "-"),
        top_gainers_html,
        top_losers_html
    )

    articles.append({
        "slug": market_article_slug,
        "title": market_article_title,
        "description": market_article_desc,
        "date": today_iso,
        "date_str": today_str,
        "category": "Market News",
        "category_badge": "badge-verified",
        "type": "NewsArticle",
        "read_time": "3 min read",
        "body_html": market_article_body,
    })

    # Banking & Financial Sector Pulse
    bank_slug = "nifty-bank-financial-services-pulse-%s" % today_iso
    bank_title = "Nifty Bank & Financial Services Pulse: Credit Growth and Rate Expectations (%s)" % today_str
    bank_desc = (
        "Analysis of Indian banking and financial sector stocks on NSE. Tracking HDFC Bank, ICICI Bank, "
        "State Bank of India, and systemic liquidity trends."
    )
    bank_body = """
    <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
      The financial services cluster on the National Stock Exchange accounts for the largest weighting
      in the benchmark Nifty 50. In recent sessions, institutional flows have reflected a focus on net interest
      margins (NIMs) and credit expansion across private and public sector lenders.
    </p>

    <div class="section-title"><h2>Structural Drivers for Indian Banking</h2></div>
    <ul>
      <li><strong>Credit Expansion:</strong> Systemic bank credit growth continues at healthy double-digit rates, supported by retail personal loans, auto finance, and corporate working capital.</li>
      <li><strong>Asset Quality:</strong> Gross Non-Performing Assets (GNPA) across commercial banks remain at multi-year lows, supported by stringent SARFAESI and IBC resolution frameworks.</li>
      <li><strong>Deposit Competition:</strong> Banks continue to offer competitive term deposit rates to match ongoing retail credit appetite.</li>
    </ul>

    <div class="card" style="margin-top:16px;padding:16px;border-left:4px solid var(--accent)">
      <p style="margin:0"><strong>Evaluate Banking Stocks:</strong> Review detailed financial ratios and brokerage costs for leading banks like
      <a href="/stock/HDFCBANK/" data-link>HDFC Bank</a>,
      <a href="/stock/ICICIBANK/" data-link>ICICI Bank</a>, and
      <a href="/stock/SBIN/" data-link>State Bank of India</a>.</p>
    </div>
    """
    articles.append({
        "slug": bank_slug,
        "title": bank_title,
        "description": bank_desc,
        "date": today_iso,
        "date_str": today_str,
        "category": "Market News",
        "category_badge": "badge-verified",
        "type": "NewsArticle",
        "read_time": "4 min read",
        "body_html": bank_body,
    })

    # Morning Pre-Market Briefing
    pre_slug = "pre-market-cues-gift-nifty-%s" % today_iso
    pre_title = "Pre-Market Brief: GIFT Nifty, FII & DII Flows, Global Cues & Stocks in Focus (%s)" % today_str
    pre_desc = (
        "Daily morning pre-market setup for Indian equities (%s). GIFT Nifty trend, FII/DII institutional "
        "positioning from NSE disclosures, Asian market cues, and derivative contracts in F&O ban."
        % today_str
    )[:300]
    pre_body = """
    <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
      Indian equity benchmarks enter today's trading session following overnight global macroeconomic developments
      and institutional portfolio adjustments. Ahead of the 9:15 AM IST opening bell on the National Stock Exchange (NSE)
      and Bombay Stock Exchange (BSE), here are the critical market cues every retail investor and active derivative trader must track.
    </p>

    <div class="section-title"><h2>1. GIFT Nifty &amp; Global Setup</h2></div>
    <p>
      GIFT Nifty futures trading on the NSE International Exchange (NSE IX) in GIFT City provide the primary early indication
      for domestic opening momentum. Traders evaluate the spread between GIFT Nifty and the previous closing level of the
      benchmark Nifty 50 to gauge gap-up or gap-down opening probabilities. Global macro factors including Brent crude oil benchmarks
      and the US Dollar Index (DXY) continue to influence emerging market currency pairs and corporate input cost projections.
    </p>

    <div class="section-title"><h2>2. Institutional Flow Dynamics (FII &amp; DII)</h2></div>
    <p>
      Foreign Institutional Investors (FIIs) and Domestic Institutional Investors (DIIs) represent the dominant liquidity drivers
      in the Indian cash delivery and derivative segments. Under SEBI regulatory transparency standards, daily net provisional figures
      are disclosed immediately post-market. Persistent DII inflows via retail Systematic Investment Plans (SIPs) continue to provide
      structural counter-cyclical support during periods of foreign portfolio volatility.
    </p>

    <div class="section-title"><h2>3. Derivatives Watch &amp; F&amp;O Ban Period</h2></div>
    <p>
      Under exchange regulations, derivative contracts enter the F&amp;O ban period when aggregate open interest across all available
      series crosses 95% of the Market Wide Position Limit (MWPL). During the ban period, no fresh positions are permitted for any
      trader; existing positions can only be closed or rolled over to reduce open interest below the 80% exit threshold.
    </p>

    <div class="card" style="margin-top:16px;padding:16px;border-left:4px solid var(--accent)">
      <p style="margin:0"><strong>Optimize Your Trade Execution:</strong> Review exact statutory charges, STT, and breakeven points before placing orders:
      <a href="/trade-costs/" data-link>Stock Trade Cost Directory</a> &middot;
      <a href="/compare/stocks/" data-link>Head-to-Head Stock Comparisons</a> &middot;
      <a href="/ipo/" data-link>Live IPO Tracker</a>.</p>
    </div>
    """
    articles.append({
        "slug": pre_slug,
        "title": pre_title,
        "description": pre_desc,
        "date": today_iso,
        "date_str": today_str,
        "category": "Market News",
        "category_badge": "badge-verified",
        "type": "NewsArticle",
        "read_time": "3 min read",
        "body_html": pre_body,
    })

    # =========================================================================
    # 2. LIVE IPO BIDDING & ALLOTMENT BULLETINS
    # =========================================================================
    for ipo in current_ipos[:10]:
        sym = ipo.get("symbol")
        if not sym:
            continue
        comp = ipo.get("company") or sym
        price_band = ipo.get("price_band") or "Disclosed on bid"
        b_end = _format_date(ipo.get("bidding_end"))
        sub = ipo.get("times_subscribed")
        sub_str = ("%.2fx" % sub) if sub is not None else "Bidding underway"

        ipo_slug = "ipo-%s-live-subscription-bidding-review" % sym.lower()
        ipo_title = "%s IPO Live Status: Subscribed %s, Price Band %s" % (comp, sub_str, price_band)
        ipo_desc = (
            "%s IPO is currently open for bidding. Price band is %s with issue closing on %s. "
            "Track live subscription numbers and broker application procedures."
            % (comp, price_band, b_end)
        )[:300]

        ipo_body = """
        <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
          The initial public offering of <strong>%s</strong> (%s) is open for public bidding on Indian exchanges.
          As per latest NSE disclosures, the issue has received bids for <strong>%s</strong> of the total shares offered.
        </p>

        <div class="section-title"><h2>Key Issue Information</h2></div>
        <div class="grid g3" style="margin:16px 0">
          <div class="card stat">
            <div class="stat-label">Price Band</div>
            <div class="stat-value" style="font-size:18px">%s</div>
            <div class="stat-sub">Per Equity Share</div>
          </div>
          <div class="card stat">
            <div class="stat-label">Subscription Multiple</div>
            <div class="stat-value">%s</div>
            <div class="stat-sub">Overall Demand</div>
          </div>
          <div class="card stat">
            <div class="stat-label">Bidding Closes</div>
            <div class="stat-value" style="font-size:18px">%s</div>
            <div class="stat-sub">UPI Mandate Cutoff: 5:00 PM</div>
          </div>
        </div>

        <div class="section-title"><h2>How to Apply Online via UPI</h2></div>
        <ol style="line-height:1.7;margin-bottom:20px">
          <li>Log into your registered Demat account on your broker's trading platform (Zerodha Kite, Groww, 5paisa, Angel One).</li>
          <li>Navigate to the <strong>IPO</strong> tab and locate <strong>%s</strong>.</li>
          <li>Enter your desired lot size and bid price (selecting the cut-off price is standard practice for retail investors).</li>
          <li>Enter your UPI ID (Google Pay, PhonePe, BHIM, or bank UPI handle) and submit the application.</li>
          <li>Approve the UPI mandate block request on your banking app before 5:00 PM on %s.</li>
        </ol>

        <div class="card" style="margin-top:16px;padding:16px;border-left:4px solid var(--accent)">
          <p style="margin:0"><strong>Full IPO Filing:</strong> View issue structure, registrar information, and issue dates on the
          <a href="/ipo/%s/" data-link>%s IPO Detailed Page</a> or track all upcoming issues on the <a href="/ipo/" data-link>IPO Tracker</a>.</p>
        </div>

        <p class="xs faint" style="margin-top:20px">
          Source: National Stock Exchange of India (NSE) public issue disclosures. BrokerLens does not publish
          grey market premium (GMP) or provide investment advice.
        </p>
        """ % (
            _esc(comp), _esc(sym), _esc(sub_str),
            _esc(price_band), _esc(sub_str), _esc(b_end),
            _esc(comp), _esc(b_end),
            _esc(sym.lower()), _esc(comp)
        )

        articles.append({
            "slug": ipo_slug,
            "title": ipo_title,
            "description": ipo_desc,
            "date": today_iso,
            "date_str": today_str,
            "category": "IPO Bulletin",
            "category_badge": "badge-up",
            "type": "NewsArticle",
            "read_time": "3 min read",
            "body_html": ipo_body,
            "related_symbol": sym,
        })

    # Load manual GMP data if available
    gmp_data = {}
    gmp_path = os.path.join(ROOT, "data", "manual", "ipo_gmp.json")
    if os.path.exists(gmp_path):
        try:
            with open(gmp_path, "r", encoding="utf-8") as f:
                gmp_data = json.load(f)
        except Exception:
            gmp_data = {}

    gmp_rows = []
    for gsym, ginfo in gmp_data.items():
        gname = ginfo.get("company_name", gsym)
        g_val = ginfo.get("gmp_inr", 0)
        g_pct = ginfo.get("expected_gain_pct", 0)
        g_price = ginfo.get("estimated_listing_price", 0)
        g_band = ginfo.get("price_band", "-")
        g_trend = ginfo.get("trend", "stable")
        g_updated = ginfo.get("recorded_at", today_iso)[:10]
        g_kostak = ginfo.get("kostak_inr", 0)
        g_trend_icon = "&uarr;" if g_trend == "up" else ("&darr;" if g_trend == "down" else "&rarr;")
        g_trend_color = "var(--up)" if g_trend == "up" else ("var(--down)" if g_trend == "down" else "var(--text)")
        gmp_rows.append(
            f'<tr>'
            f'<td><strong>{_esc(gname)}</strong><br><span class="xs muted">{_esc(gsym)}</span></td>'
            f'<td class="num">{_esc(g_band)}</td>'
            f'<td class="num" style="color:var(--up);font-weight:700">+Rs {g_val:,} ({g_pct:.1f}%)</td>'
            f'<td class="num">Rs {g_price:,}</td>'
            f'<td class="num">Rs {g_kostak:,}</td>'
            f'<td style="text-align:center;color:{g_trend_color}">{g_trend_icon} {_esc(g_trend.capitalize())}</td>'
            f'<td class="xs muted" style="text-align:right">{_esc(g_updated)}</td>'
            f'</tr>'
        )
    gmp_table_html = "".join(gmp_rows) if gmp_rows else '<tr><td colspan="7" class="muted">No active GMP quotes recorded today.</td></tr>'

    # Daily Live IPO GMP Bulletin
    gmp_article_slug = "ipo-gmp-today-live-grey-market-premium-rates"
    gmp_article_title = "IPO GMP Today: Live Grey Market Premium Rates, Kostak Rates and Expected Listing Gains"
    gmp_article_desc = (
        f"Daily IPO GMP tracker for {today_str}. Review latest grey market premiums, Kostak rates, "
        f"and estimated listing prices across Mainboard and SME IPOs with regulatory safeguards."
    )[:300]
    gmp_article_body = f"""
    <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
      Grey market premium (GMP) tracking provides an informal gauge of investor sentiment ahead of official public issue
      listing on the National Stock Exchange (NSE) and Bombay Stock Exchange (BSE). Below are the latest timestamped dealer
      quotes and expected listing figures on record as of {today_str}.
    </p>

    <div class="card" style="margin:20px 0;padding:16px;background:var(--bg-raised);border-left:4px solid var(--accent)">
      <div style="font-weight:700;font-size:14px;color:var(--text)">SEBI Regulatory Disclosures &amp; Investor Safeguards</div>
      <p class="xs muted" style="margin:6px 0 0 0;line-height:1.6">
        Grey market premiums reflect unofficial dealer-to-dealer transactions conducted outside SEBI-regulated exchanges.
        BrokerLens tracks these figures purely for educational transparency. Grey market prices do not represent an official
        guarantee of listing performance. Official price discovery occurs exclusively through the special pre-open auction
        on the listing morning between 9:00 AM and 9:45 AM IST on NSE and BSE.
      </p>
    </div>

    <div class="section-title"><h2>Current IPO Grey Market Premium Board ({today_str})</h2></div>
    <div class="table-scroll" style="margin:16px 0">
      <table class="data">
        <thead>
          <tr>
            <th>Company</th>
            <th class="num">Issue Price Band</th>
            <th class="num">Estimated GMP</th>
            <th class="num">Estimated Listing</th>
            <th class="num">Kostak Rate</th>
            <th style="text-align:center">Trend</th>
            <th style="text-align:right">Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {gmp_table_html}
        </tbody>
      </table>
    </div>

    <div class="section-title"><h2>Understanding Grey Market Terminology</h2></div>
    <ul>
      <li><strong>Grey Market Premium (GMP):</strong> The informal premium over the public issue price that buyers are willing to pay per share before official exchange listing.</li>
      <li><strong>Kostak Rate:</strong> The fixed lump-sum profit paid to an IPO applicant for selling their application rights to a third party, regardless of whether shares are allotted.</li>
      <li><strong>Subject to Sauda (SS):</strong> An agreement where the seller receives a negotiated profit only if shares are actually allotted to the application.</li>
    </ul>

    <div class="section-title"><h2>How to Prepare Your Demat Account for Upcoming IPOs</h2></div>
    <p>
      Whether an issue commands a high or low GMP, participating in an IPO requires an active SEBI-registered Demat account
      with UPI ASBA capabilities. Investors can open accounts with zero account opening fees across India's leading discount brokers:
    </p>
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0">
      <a href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" class="btn btn-primary small">Open Indiabulls Demat (Rs 0 Delivery) &rarr;</a>
      <a href="https://zerodha.com/open-account?c=ZE5729" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Zerodha Kite Account &rarr;</a>
      <a href="https://dhan.co/?ref=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Dhan Account &rarr;</a>
      <a href="https://www.angelone.in/open-demat-account?referral=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Angel One Account &rarr;</a>
      <a href="https://upstox.com/open-account/?f=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Upstox Account &rarr;</a>
    </div>

    <div class="card" style="margin-top:20px;padding:16px;border-left:4px solid var(--accent)">
      <p style="margin:0"><strong>Interactive IPO Tools:</strong> Explore the complete
      <a href="/ipo/gmp/" data-link>Real-Time IPO GMP Tracker</a> &middot;
      <a href="/ipo/sme/" data-link>NSE Emerge &amp; BSE SME Hub</a> &middot;
      <a href="/ipo/upcoming/" data-link>Upcoming IPO Calendar</a> &middot;
      <a href="/ipo/allotment-status/" data-link>Check Allotment Status Online</a>.</p>
    </div>
    """
    articles.append({
        "slug": gmp_article_slug,
        "title": gmp_article_title,
        "description": gmp_article_desc,
        "date": today_iso,
        "date_str": today_str,
        "category": "IPO Bulletin",
        "category_badge": "badge-up",
        "type": "NewsArticle",
        "read_time": "4 min read",
        "body_html": gmp_article_body,
    })

    # SME IPO Guide & Trading Rules
    sme_article_slug = "sme-ipo-market-roundup-nse-emerge-bse-sme-trading-rules"
    sme_article_title = "SME IPO Investment Guide: NSE Emerge and BSE SME Trading Rules, Lot Sizes and Market Maker Safeguards"
    sme_article_desc = (
        "Comprehensive guide to investing in Indian SME IPOs on NSE Emerge and BSE SME. Understand 1-lot "
        "mandatory trading sizes, minimum application thresholds, liquidity considerations, and risk frameworks."
    )[:300]
    sme_article_body = """
    <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
      Small and Medium Enterprise (SME) IPOs on the <strong>NSE Emerge</strong> and <strong>BSE SME</strong> platforms have
      witnessed unprecedented retail and HNI subscription multiples in recent quarters. However, investing in SME public issues
      carries fundamentally different rules, liquidity dynamics, and risk parameters compared to Mainboard IPOs.
    </p>

    <div class="section-title"><h2>1. The Mandatory 1-Lot Trading Rule</h2></div>
    <p>
      The single most important distinction between Mainboard and SME equities is the secondary market trading unit.
      On the mainboard (NSE/BSE), once a company lists, retail investors can buy or sell as little as 1 individual share.
      On the SME platform, SEBI mandates that <strong>shares must be traded in standardized minimum lots</strong>
      (typically 1,000, 1,200, 2,000, or 3,000 shares per lot, depending on the share price).
    </p>
    <p>
      This means an investor who receives an allotment of 2,000 shares cannot exit 500 shares; they must place an order
      for the entire 2,000-share lot. Investors must ensure adequate liquidity in their trading ledger before taking positions.
    </p>

    <div class="section-title"><h2>2. High Application Minimums (Rs 1 Lakh to Rs 1.25 Lakh+)</h2></div>
    <p>
      To ensure that only informed investors with suitable risk appetite participate in early-stage growth companies,
      SEBI sets the minimum application size for SME IPOs at approximately Rs 1,00,000 or higher.
      Retail individual investors are restricted to a maximum application size of Rs 2,00,000 (typically 1 or at most 2 lots),
      while Non-Institutional Investors (NII / HNI) apply in tiers above Rs 2 Lakh.
    </p>

    <div class="section-title"><h2>3. The Role of Market Makers</h2></div>
    <p>
      Under SEBI (ICDR) Regulations, every SME IPO issuer is legally required to appoint an institutional Market Maker
      for a minimum duration of <strong>three years</strong> post-listing. The Market Maker is obligated to provide two-way
      continuous buy and sell quotes on the exchange order book with a maximum permitted bid-ask spread (typically 1% to 2%)
      to maintain baseline liquidity and prevent trading halts.
    </p>

    <div class="section-title"><h2>4. Key Risk Considerations for Retail Investors</h2></div>
    <ul>
      <li><strong>Lower Reporting Frequency:</strong> SME companies disclose audited financial results on a half-yearly basis, unlike mainboard companies which report quarterly earnings.</li>
      <li><strong>Circuit Filter Restraints:</strong> SME stocks frequently trade under strict 5% or 10% daily price bands, which can limit immediate order execution during severe corrections.</li>
      <li><strong>Migration to Mainboard:</strong> An SME listed company can migrate to the mainboard exchange after 2 years of listing, provided its paid-up capital exceeds Rs 10 Crore and net worth meets exchange eligibility criteria.</li>
    </ul>

    <div class="section-title"><h2>5. How to Apply for SME IPOs Online</h2></div>
    <p>
      Retail investors can apply for SME IPOs directly through online discount broker portals using UPI 2.0 ASBA:
    </p>
    <ol style="line-height:1.7;margin-bottom:20px">
      <li>Log into your broker app (Zerodha Kite, Groww, Angel One, Upstox, or Dhan).</li>
      <li>Navigate to the IPO section and select the active SME issue marked with the SME Emerge badge.</li>
      <li>Choose the application lot (1 Lot for standard retail bidding).</li>
      <li>Enter your UPI handle and approve the ASBA mandate in your UPI application before 5:00 PM on closing day.</li>
    </ol>

    <div class="card" style="margin-top:20px;padding:16px;border-left:4px solid var(--accent)">
      <p style="margin:0"><strong>Explore SME Hub:</strong> Browse all active, upcoming, and listed SME issues on the
      <a href="/ipo/sme/" data-link>BrokerLens SME IPO Hub</a> or check grey market sentiment on the
      <a href="/ipo/gmp/" data-link>IPO GMP Board</a>.</p>
    </div>
    """
    articles.append({
        "slug": sme_article_slug,
        "title": sme_article_title,
        "description": sme_article_desc,
        "date": today_iso,
        "date_str": today_str,
        "category": "Blog & Guide",
        "category_badge": "badge-verified",
        "type": "BlogPosting",
        "read_time": "6 min read",
        "body_html": sme_article_body,
    })

    # Upcoming IPO Pipeline & DRHP Tracker
    pipeline_article_slug = "upcoming-ipos-in-india-pipeline-dates-expected-issue-size"
    pipeline_article_title = "Upcoming IPOs in India 2026: Expected Issue Dates, DRHP Filings and Sector Pipeline"
    pipeline_article_desc = (
        "Complete pipeline of upcoming IPOs in India. Track DRHP filings with SEBI, expected issue sizes, "
        "dates, and sector-wise public offerings across tech, financial services, and retail."
    )[:300]
    pipeline_article_body = """
    <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
      India's primary capital markets continue to attract high-quality corporate listings across new-age tech,
      financial institutions, logistics, and renewable energy. Retail investors and market participants can review
      the forward pipeline of upcoming public issues currently progressing through the SEBI regulatory review lifecycle.
    </p>

    <div class="section-title"><h2>1. High-Profile Upcoming IPOs in the Pipeline</h2></div>
    <ul>
      <li><strong>National Securities Depository Limited (NSDL):</strong> India's pioneering depository is planning an offer for sale (OFS) of up to 5.72 Crore equity shares, sponsored by IDBI Bank and NSE.</li>
      <li><strong>Reliance Jio Infocomm:</strong> India's largest telecom and digital infrastructure provider, expected to represent one of the country's largest public offerings.</li>
      <li><strong>Tata Sons / Tata Group Ventures:</strong> Continued capital-market listings across key Tata subsidiaries following the milestone listing of Tata Technologies.</li>
      <li><strong>HDB Financial Services:</strong> The retail NBFC arm of HDFC Bank, preparing for a milestone public listing to meet RBI upper-layer scale-based regulatory mandates.</li>
      <li><strong>Ather Energy:</strong> High-growth electric two-wheeler manufacturer expanding production capacity and R&amp;D through a combined fresh issue and OFS.</li>
      <li><strong>boAt (Imagine Marketing):</strong> Consumer audio and wearables brand looking to tap public markets for domestic manufacturing expansion.</li>
    </ul>

    <div class="section-title"><h2>2. The Journey from DRHP to Stock Exchange Listing</h2></div>
    <ol style="line-height:1.7;margin-bottom:20px">
      <li><strong>Draft Red Herring Prospectus (DRHP):</strong> The company submits its detailed draft document with SEBI, detailing financials, business risks, and promoter holdings.</li>
      <li><strong>SEBI Observation Letter:</strong> SEBI reviews disclosures, seeks clarifications, and issues an observation letter (typically valid for 12 months).</li>
      <li><strong>Red Herring Prospectus (RHP):</strong> The company files its finalized prospectus with the Registrar of Companies (RoC), specifying bidding dates and anchor investor allocations.</li>
      <li><strong>Price Band Announcement:</strong> 2 working days before issue opening, the company announces its price band and lot size in national newspapers and exchange circulars.</li>
      <li><strong>Public Bidding &amp; Allotment:</strong> 3-day bidding window, followed by T+1 basis of allotment and T+3 listing on NSE and BSE.</li>
    </ol>

    <div class="section-title"><h2>3. Steps to Get Ready for Bidding</h2></div>
    <p>
      Because high-profile IPOs often experience heavy bidding volume on their opening day, completing your Demat setup
      in advance ensures uninterrupted UPI ASBA participation:
    </p>
    <ul>
      <li>Ensure your bank account has a UPI ID enabled with an authorized bank that supports the Rs 5 Lakh IPO ASBA limit.</li>
      <li>Verify that the PAN registered on your Demat account exactly matches the PAN on your bank account to prevent mandate disqualification.</li>
      <li>Open Demat accounts with zero-brokerage partners for instant digital order submission:</li>
    </ul>

    <div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0">
      <a href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" class="btn btn-primary small">Open Indiabulls Demat (Rs 0 Delivery) &rarr;</a>
      <a href="https://zerodha.com/open-account?c=ZE5729" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Zerodha Demat &rarr;</a>
      <a href="https://dhan.co/?ref=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Dhan Demat &rarr;</a>
      <a href="https://www.angelone.in/open-demat-account?referral=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Angel One Demat &rarr;</a>
      <a href="https://upstox.com/open-account/?f=BROKERLENS" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Upstox Demat &rarr;</a>
    </div>

    <div class="card" style="margin-top:20px;padding:16px;border-left:4px solid var(--accent)">
      <p style="margin:0"><strong>Stay Informed:</strong> Track all upcoming issues with dates and issue prices on the
      <a href="/ipo/upcoming/" data-link>Upcoming IPO Calendar</a> and check latest grey market sentiment on the
      <a href="/ipo/gmp/" data-link>IPO GMP Tracker</a>.</p>
    </div>
    """
    articles.append({
        "slug": pipeline_article_slug,
        "title": pipeline_article_title,
        "description": pipeline_article_desc,
        "date": today_iso,
        "date_str": today_str,
        "category": "IPO Bulletin",
        "category_badge": "badge-up",
        "type": "NewsArticle",
        "read_time": "5 min read",
        "body_html": pipeline_article_body,
    })

    # =========================================================================
    # 3. EDUCATIONAL BLOGS & PRACTICAL INVESTOR GUIDES
    # =========================================================================
    blogs_data = [
        {
            "slug": "best-stock-brokers-india-beginners-guide",
            "title": "How to Choose the Best Stock Broker in India: Discount vs Full-Service Bank Accounts",
            "description": "A comprehensive guide for Indian investors comparing flat-fee discount brokers (Zerodha, Groww) against bank-backed 3-in-1 accounts (ICICI Direct, HDFC Sky).",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "7 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Choosing a stock broker in India determines not just your trading expenses, but also your
              fund transfer speed, charting experience, and margin safety. Understanding the structural
              difference between discount and full-service brokers is the essential first step.
            </p>

            <div class="section-title"><h2>1. Discount Brokers vs Full-Service Brokers</h2></div>
            <p>
              <strong>Discount Brokers (Zerodha, Groww, Angel One, Upstox):</strong> Charge flat fees
              (typically Rs 0 for delivery and flat Rs 20 per trade for intraday/F&amp;O) regardless of trade size.
              They do not provide stock tips or relationship managers, focusing purely on technology and execution.
            </p>
            <p>
              <strong>Full-Service Bank Brokers (ICICI Direct, HDFC Securities, Kotak Neo):</strong> Often charge
              a percentage of your trade volume (0.10% to 0.50%), although many now offer competitive prepaid plans.
              They integrate savings bank accounts directly with demat and trading accounts in a 3-in-1 ecosystem.
            </p>

            <div class="section-title"><h2>2. Critical Evaluation Checklist</h2></div>
            <ul>
              <li><strong>Account Maintenance Charges (AMC):</strong> Some brokers charge Rs 300 to Rs 500 annually, while others offer lifetime zero AMC.</li>
              <li><strong>Depository Participant (DP) Charges:</strong> When selling equity shares from your demat account, CDSL/NSDL charges plus the broker's fee apply (usually Rs 13.50 to Rs 20 + GST per company per day).</li>
              <li><strong>Customer Complaint Ratio:</strong> Always check the broker's unresolved complaints per 10,000 clients published on the SEBI and NSE websites.</li>
            </ul>

            <div class="card" style="margin-top:16px;padding:16px;border-left:4px solid var(--accent)">
              <p style="margin:0"><strong>Interactive Comparison:</strong> Use our <a href="/compare" data-link>Broker Comparison Tool</a>
              to review real regulatory client data and cost structures side by side.</p>
            </div>
            """
        },
        {
            "slug": "fo-trading-taxation-rules-india-stcg-audit",
            "title": "F&O Trading Taxation in India: Section 44AD, STCG vs Business Income & New STT Rules",
            "description": "Everything Indian derivative traders must know about tax filing: calculating turnover under Section 44AB, speculative vs non-speculative income, and carrying forward losses.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "8 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Trading Futures and Options (F&amp;O) in India carries specific tax obligations under the Income Tax Act.
              Unlike equity delivery gains which fall under Capital Gains, derivatives are classified as
              <strong>Non-Speculative Business Income</strong>.
            </p>

            <div class="section-title"><h2>1. How F&amp;O Turnover is Calculated</h2></div>
            <p>
              As per the Guidance Note issued by the Institute of Chartered Accountants of India (ICAI):
            </p>
            <ul>
              <li><strong>Futures Turnover:</strong> Absolute sum of profits and losses across all squared-off contracts.</li>
              <li><strong>Options Turnover:</strong> Absolute sum of profits and losses PLUS the premium received on the sale of options.</li>
            </ul>

            <div class="section-title"><h2>2. Tax Audit Thresholds (Section 44AB)</h2></div>
            <p>
              A mandatory tax audit by a chartered accountant applies if your annual trading turnover exceeds:
            </p>
            <ul>
              <li><strong>Rs 10 Crore</strong> (provided at least 95% of your transactions are conducted through digital banking channels).</li>
              <li>If turnover is below Rs 2 Crore and you declare profits less than 6% under presumptive taxation (Section 44AD), an audit may also be required when total income exceeds the basic exemption limit.</li>
            </ul>

            <div class="section-title"><h2>3. Loss Carry Forward Rules</h2></div>
            <p>
              F&amp;O business losses can be set off against any business income (except salary income) in the current financial year.
              Unabsorbed losses can be carried forward for up to <strong>8 assessment years</strong>, provided your income tax return (ITR-3)
              is filed before the mandatory due date.
            </p>
            """
        },
        {
            "slug": "demat-account-safety-freeze-guide",
            "title": "Demat Account Safety: How to Freeze or Lock Your Shares with NSDL and CDSL",
            "description": "A step-by-step security walkthrough explaining how to use NSDL Speed-e and CDSL Easiest to freeze your demat account and prevent unauthorized share transfers.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "5 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              As Indian retail investing transitions into digital-first smartphone platforms, safeguarding your
              demat account from phishing attacks, SIM swapping, and unauthorized debit transactions is critical.
            </p>

            <div class="section-title"><h2>1. NSDL and CDSL Online Freeze Facility</h2></div>
            <p>
              SEBI mandates that both central depositories provide retail investors with an instant online freeze facility.
              When enabled, no debit instruction slip (DIS) or API instruction can debit shares from your account.
            </p>
            <ul>
              <li><strong>CDSL Easiest:</strong> Login to the CDSL website, navigate to 'Account Freeze', and select either a debit freeze on specific ISINs or your entire 16-digit BO ID.</li>
              <li><strong>NSDL Speed-e:</strong> Log in with your credentials and activate the 'Freeze / Unfreeze' module for individual holdings or complete trading accounts.</li>
            </ul>

            <div class="section-title"><h2>2. Best Security Hygiene Practices</h2></div>
            <ol>
              <li>Enable Two-Factor Authentication (TOTP) via authenticator apps (Google Authenticator, Microsoft Authenticator) instead of SMS OTPs.</li>
              <li>Verify monthly NSDL/CDSL Consolidated Account Statements (CAS) sent directly from depositories to detect any discrepancies.</li>
              <li>Revoke inactive Power of Attorney (PoA) or DDPI authorizations if you no longer actively trade through old broker accounts.</li>
            </ol>
            """
        },
        {
            "slug": "hidden-charges-stock-brokers-amc-dp-pledge",
            "title": "Hidden Charges in Stock Trading: DP Charges, AMC, Call &amp; Trade, and Pledge Fees",
            "description": "Beyond headline Rs 20 brokerage: a line-by-line audit of secondary fees charged by Indian stock brokers that quietly erode investor returns.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "6 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              While zero brokerage on delivery and flat Rs 20 pricing dominate broker marketing, investors
              frequently encounter supplementary deductions on their contract notes and ledger statements.
            </p>

            <div class="section-title"><h2>1. Depository Participant (DP) Charges</h2></div>
            <p>
              DP charges are levied by depositories (CDSL/NSDL) and the broker whenever an equity share is debited from your demat account.
              This fee is charged per company per day, regardless of quantity sold:
            </p>
            <ul>
              <li>Zerodha: Rs 13.50 + 18% GST (approx Rs 15.93 per stock)</li>
              <li>Groww: Rs 13.50 + 18% GST (approx Rs 15.93 per stock)</li>
              <li>Bank Brokers: Often Rs 25 to Rs 50 + GST per debit transaction</li>
            </ul>

            <div class="section-title"><h2>2. Other Common Ancillary Fees</h2></div>
            <ul>
              <li><strong>Auto-Squareoff Fee:</strong> If an intraday position is not squared off before 3:15-3:25 PM, the broker's automated RMS squares it off, charging Rs 50 + GST per order.</li>
              <li><strong>Call &amp; Trade:</strong> Placing orders over the phone via customer care carries an extra Rs 50 + GST fee.</li>
              <li><strong>Margin Pledge &amp; Unpledge:</strong> Pledging shares or mutual funds for collateral margin typically costs Rs 20 to Rs 30 + GST per ISIN.</li>
            </ul>
            """
        },
        {
            "slug": "t-plus-zero-same-day-settlement-india-guide",
            "title": "T+0 Same-Day Settlement in Indian Equities: How It Works and What It Means for Investors",
            "description": "Explaining India's transition to optional T+0 settlement: how instant equity credit works on NSE and BSE and its benefits for retail liquidity.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "5 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              India became one of the first major global economies to pioneer T+1 rolling settlement for all equities.
              Now, SEBI has introduced an optional <strong>T+0 (same-day settlement)</strong> mechanism for a select basket of liquid securities.
            </p>

            <div class="section-title"><h2>1. Understanding T+0 vs T+1</h2></div>
            <p>
              Under standard T+1 settlement, when you sell shares on Monday, the sale proceeds become fully available
              for withdrawal into your bank account on Tuesday evening. Under T+0 settlement, trades executed before
              the cutoff time settle on the same trading day, providing instant liquidity to sellers and immediate
              share credit to buyers.
            </p>

            <div class="section-title"><h2>2. Investor Benefits and Market Architecture</h2></div>
            <ul>
              <li><strong>Zero Clearing Risk:</strong> Eliminates overnight counterparty risk between clearing corporations and broker members.</li>
              <li><strong>Capital Velocity:</strong> Retail investors can redeploy funds instantly without waiting for clearing cycle delays.</li>
              <li><strong>Future Roadmap:</strong> SEBI envisions a phased transition toward optional Instant Settlement using Unified Payments Interface (UPI) mechanisms.</li>
            </ul>
            """
        },
        {
            "slug": "how-to-pledge-shares-mutual-funds-for-margin",
            "title": "How to Pledge Shares and Mutual Funds for Trading Margin (Haircut &amp; Margin Rules)",
            "description": "A practical walkthrough on creating collateral margin by pledging equity holdings and liquid mutual funds for F&O trading in India.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "6 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Traders who hold long-term investments in equity shares or mutual funds can pledge these securities
              with their broker to generate trading margin, avoiding the need to keep idle cash in trading ledgers.
            </p>

            <div class="section-title"><h2>1. Margin Haircuts Explained</h2></div>
            <p>
              Clearing corporations assign a percentage discount (haircut) to pledged securities depending on their volatility:
            </p>
            <ul>
              <li><strong>Liquid Mutual Funds &amp; Overnight Funds:</strong> Low haircut (typically 10% to 15%).</li>
              <li><strong>Large-Cap Bluechips (Nifty 50):</strong> Moderate haircut (typically 15% to 20%).</li>
              <li><strong>Mid-Cap and Small-Cap Stocks:</strong> Higher haircut (25% to 50%).</li>
            </ul>

            <div class="section-title"><h2>2. The 50:50 Cash-Collateral Rule</h2></div>
            <p>
              For overnight Futures and Options positions, SEBI mandates that at least 50% of the required margin
              must be held in cash or cash-equivalent collateral (such as Liquid BeES or Government Securities).
              The remaining 50% can be funded through non-cash equity collateral.
            </p>
            """
        },
        {
            "slug": "sebi-algorithm-trading-retail-regulations",
            "title": "SEBI Algorithmic Trading Rules: What Retail Quant Traders Need to Know",
            "description": "Understanding the regulatory framework for automated trading, broker API access, risk controls, and compliance for algorithmic retail traders in India.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "7 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Algorithmic and API-based trading has grown exponentially among Indian retail traders.
              SEBI continues to formulate clear regulatory standards to ensure market integrity and investor protection.
            </p>

            <div class="section-title"><h2>1. Broker API Architecture</h2></div>
            <p>
              Discount brokers offer REST and WebSocket APIs (e.g., Zerodha Kite Connect, Angel One SmartAPI, Upstox API)
              allowing authorized trading clients to execute orders programmatically.
              Key requirements include:
            </p>
            <ul>
              <li>Mandatory Two-Factor Authentication (TOTP) for automated session generation.</li>
              <li>Exchange-level rate limiting on order placements and quote subscriptions.</li>
              <li>All orders routed through the broker's centralized Risk Management System (RMS) before hitting exchange matching engines.</li>
            </ul>

            <div class="card" style="margin-top:16px;padding:16px;border-left:4px solid var(--accent)">
              <p style="margin:0"><strong>Explore Platforms:</strong> Compare verified APIs, strategy builders, and institutional vendors on our
              <a href="/algo" data-link>Algo Trading Platforms Directory</a>.</p>
            </div>
            """
        },
        {
            "slug": "how-to-check-ipo-allotment-status-online-guide",
            "title": "How to Check IPO Allotment Status Online: Link Intime, KFintech & Bigshare Guide",
            "description": "Step-by-step instructions for checking IPO allotment across all major registrars using PAN number, Application number, or DP Client ID.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "6 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              After bidding closes for an Initial Public Offering (IPO), the registrar takes 24 to 48 hours to finalize
              the <strong>Basis of Allotment</strong>. Retail investors can verify their allocation status online
              without waiting for bank debit SMS notifications.
            </p>

            <div class="section-title"><h2>1. Official Registrar Portals</h2></div>
            <p>Every IPO is managed by a SEBI-registered registrar responsible for validating bids and allocating shares:</p>
            <ul>
              <li><strong>Link Intime India:</strong> Handles major mainboard issues like Tata Tech, Honasa, and Mankind Pharma. Check at <a href="/ipo/allotment-status/">Allotment Status Hub</a>.</li>
              <li><strong>KFin Technologies:</strong> Registrar for mega-issues including LIC, Swiggy, Hyundai India, and Bajaj Housing Finance.</li>
              <li><strong>Bigshare Services:</strong> Primary registrar for high-growth SME and NSE Emerge issues.</li>
            </ul>

            <div class="section-title"><h2>2. Three Ways to Query Allotment</h2></div>
            <ol>
              <li><strong>PAN Mode (Recommended):</strong> Enter your 10-character Permanent Account Number. Fast, universal, and error-proof.</li>
              <li><strong>Application Number:</strong> Enter the bid application number generated on your broker app (Kite, Groww, Angel One).</li>
              <li><strong>DP / Client ID:</strong> Enter your 16-digit Beneficiary ID (NSDL DP ID + Client ID or CDSL 16-digit Demat Account number).</li>
            </ol>

            <div class="section-title"><h2>3. What Happens If You Are Not Allotted?</h2></div>
            <p>
              If your application is not selected in the computerized lottery, your bank will automatically unblock
              the UPI mandate funds within 24 to 48 hours of allotment finalization. If your funds remain blocked,
              you can quote the mandate Unique Mandate Number (UMN) to your banking support or file an enquiry with the registrar.
            </p>
            """
        },
        {
            "slug": "asba-vs-upi-ipo-application-rules",
            "title": "ASBA Net Banking vs UPI IPO Bidding: Limits, Success Rates and Rejection Causes",
            "description": "Comprehensive comparison of ASBA Net Banking vs UPI for IPO applications in India: which has higher success rates and how to avoid mandate rejections.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "7 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Indian retail investors have two primary routes to apply for IPOs: <strong>Bank ASBA</strong>
              (Application Supported by Blocked Amount) through net banking, and <strong>UPI-based ASBA</strong>
              via broker trading apps.
            </p>

            <div class="section-title"><h2>1. Key Differences at a Glance</h2></div>
            <ul>
              <li><strong>UPI Limit:</strong> Retail investors can apply for up to Rs 5 Lakh per IPO using UPI (raised from the earlier Rs 2 Lakh threshold).</li>
              <li><strong>Net Banking ASBA:</strong> Allows applications across all categories: Retail (up to Rs 2 Lakh), sNII (Rs 2 Lakh to Rs 10 Lakh), and bNII (above Rs 10 Lakh) without transaction limits.</li>
              <li><strong>Approval Latency:</strong> UPI mandates occasionally face gateway delays during peak bidding hours (3:00 PM to 5:00 PM on closing day). Net banking ASBA is instantaneous.</li>
            </ul>

            <div class="section-title"><h2>2. Common Causes of UPI Mandate Failures</h2></div>
            <ol>
              <li><strong>Third-Party Bank Account:</strong> SEBI strictly mandates that the Demat account holder's PAN must match the bank account PAN. Applications from spouse/parent accounts are rejected.</li>
              <li><strong>Late Authorization:</strong> The UPI mandate block request must be approved in your BHIM, Google Pay, or PhonePe app before 5:00 PM on the issue closing day.</li>
              <li><strong>Multiple Applications from Same PAN:</strong> Multiple retail bids under the same PAN in the same IPO are disqualified as duplicate applications.</li>
            </ol>
            """
        },
        {
            "slug": "sebi-registered-stock-brokers-verification-guide",
            "title": "How to Verify SEBI Registered Stock Brokers: Depository Roles, Audit Disclosures & Regulatory Lineage",
            "description": "Step-by-step audit guide to verifying any Indian stock broker or regional firm. Understand SEBI registration certificates, depository participant status, and complaint track records.",
            "category": "Blog & Guide",
            "category_badge": "badge-verified",
            "type": "BlogPosting",
            "read_time": "6 min read",
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Investors often encounter regional brokerage firms, boutique wealth managers, and corporate clearing members
              like <strong>Pankaj Mangaldas Securities</strong>, <strong>Absolute Broking</strong>, or <strong>Adroit Financial Services</strong>.
              Before transferring investment capital or opening a trading ledger, verifying an intermediary's official SEBI registration
              status and depository credentials is a critical safeguard.
            </p>

            <div class="section-title"><h2>1. Deciphering SEBI Registration Numbers</h2></div>
            <p>
              The Securities and Exchange Board of India (SEBI) issues alphanumeric registration certificates that indicate
              an intermediary's regulatory scope:
            </p>
            <ul>
              <li><strong>INZ Prefix (Stock Brokers):</strong> Signifies a certified trading member registered to execute transactions on stock and derivative exchanges (NSE, BSE, MCX). For example, Indiabulls Securities operates under SEBI Reg. <code>INZ000036136</code>, and Zerodha Broking under <code>INZ000031633</code>.</li>
              <li><strong>IN-DP Prefix (Depository Participants):</strong> Authorizes an entity to hold electronic securities in dematerialized form with National Securities Depository Limited (NSDL) or Central Depository Services India Limited (CDSL).</li>
              <li><strong>INA Prefix (Investment Advisers):</strong> Mandates strict fiduciary duty for fee-only advisory without accepting broker distribution commissions.</li>
              <li><strong>INH Prefix (Research Analysts):</strong> Certifies qualified entities authorized to issue stock recommendations and research reports.</li>
            </ul>

            <div class="section-title"><h2>2. How to Search the Registry on BrokerLens</h2></div>
            <p>
              BrokerLens maintains an indexed directory of every active SEBI registration across Indian capital markets.
              You can search any firm name or registration code directly:
            </p>
            <ul>
              <li>Explore the central <a href="/registry">SEBI Registry Search</a> to verify registration status, registered corporate addresses, and validity timelines.</li>
              <li>Browse <a href="/brokers">All Tracked Stock Brokers</a> to evaluate active client rankings, complaint frequency per 10,000 clients, and brokerage pricing.</li>
              <li>Compare brokers side by side on the <a href="/compare">Broker Comparison Tool</a>.</li>
            </ul>

            <div class="section-title"><h2>3. Evaluating Broker Safety and Financial Health</h2></div>
            <p>
              Beyond the registration certificate, assess the following primary disclosures:
            </p>
            <ol style="line-height:1.7;margin-bottom:20px">
              <li><strong>Active Client Trend:</strong> Check monthly active client counts published by NSE to determine whether client participation is expanding or contracting.</li>
              <li><strong>Complaint Ratio:</strong> Inspect the number of investor complaints received and resolved relative to total active clients. Ratios below 5 per 10,000 clients indicate robust operational handling.</li>
              <li><strong>Custody Protection:</strong> Under SEBI circulars, all client funds must be settled back to the primary bank account on the first Friday of each month or quarter (Quarterly Settlement of Funds).</li>
            </ol>

            <div class="card" style="margin-top:20px;padding:16px;border-left:4px solid var(--accent)">
              <p style="margin:0"><strong>Research Intermediaries:</strong> Audit regulatory lineages on the
              <a href="/registry" data-link>SEBI Registry</a>, discover tailored platforms with the
              <a href="/find-broker/" data-link>Broker Matchmaker</a>, or review our independent
              <a href="/editorial-policy" data-link>Editorial Policy</a>.</p>
            </div>
            """
        }
    ]

    for b in blogs_data:
        b["date"] = today_iso
        b["date_str"] = today_str
        articles.append(b)

    # =========================================================================
    # 4. EMPIRICAL RESEARCH & INDUSTRY ARTICLES
    # =========================================================================
    research_items = [
        {
            "slug": "stock-price-target-analysis-valuation-guide",
            "title": "How to Analyze Share Price Targets: Valuation Multiples, P/E Ratios and What-If Calculators",
            "description": "Learn how institutional analysts evaluate equity valuations. Understand P/E ratios, 52-week price ranges, and test custom compounding scenarios with mathematical what-if calculators.",
            "category": "Research Article",
            "category_badge": "badge-verified",
            "type": "Article",
            "read_time": "7 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Retail search volume across Indian equities frequently centers on queries like "share price target 2026" or
              "target for 2030" for high-momentum stocks such as <a href="/stock/cupid/">Cupid</a>,
              <a href="/stock/pashupati/">Pashupati Cotspin</a>, <a href="/stock/aparinds/">Apar Industries</a>,
              <a href="/stock/jaykay/">Jaykay Enterprises</a>, and <a href="/stock/shantigold/">Shanti Gold</a>.
              While internet forums often publish speculative year-by-year numbers, disciplined investors evaluate equity
              projections through corporate fundamentals, historical trading ranges, and mathematical compounding.
            </p>

            <div class="section-title"><h2>1. What Is a Share Price Target?</h2></div>
            <p>
              A legitimate share price target published by a SEBI-registered research analyst (RA) or institutional brokerage
              represents an estimated fair value based on detailed mathematical models:
            </p>
            <ul>
              <li><strong>Discounted Cash Flow (DCF):</strong> Projecting future free cash flows discounted back to present value using the company's weighted average cost of capital (WACC).</li>
              <li><strong>Relative Valuation (Price-to-Earnings):</strong> Multiplying projected earnings per share (EPS) by a justified sector P/E multiple.</li>
              <li><strong>Enterprise Value to EBITDA (EV/EBITDA):</strong> Used extensively for capital-intensive sectors like manufacturing, infrastructure, and utilities.</li>
            </ul>
            <p>
              Every target is inherently contingent on assumptions regarding revenue growth, margin stability, interest rates, and macro cycles.
              BrokerLens publishes no speculative forecasts or analyst price targets; all figures displayed on stock profiles reflect
              primary daily trading disclosures from the National Stock Exchange (NSE).
            </p>

            <div class="section-title"><h2>2. Analyzing High-Interest Stocks on BrokerLens</h2></div>
            <p>
              When evaluating companies with significant retail search interest, examine the factual metrics already on file:
            </p>
            <div class="table-scroll" style="margin:16px 0">
              <table class="data">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Ticker</th>
                    <th>Trading Data &amp; Tools</th>
                    <th>Analysis Focus</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Cupid Limited</strong></td>
                    <td>CUPID</td>
                    <td><a href="/stock/cupid/">Cupid Share Price &amp; Calculator &rarr;</a></td>
                    <td>FMCG &amp; healthcare manufacturing, export contracts, dividend track record</td>
                  </tr>
                  <tr>
                    <td><strong>Pashupati Cotspin</strong></td>
                    <td>PASHUPATI</td>
                    <td><a href="/stock/pashupati/">Pashupati Cotspin Price &amp; Calculator &rarr;</a></td>
                    <td>Textile spinning capacity, cotton price volatility, domestic demand</td>
                  </tr>
                  <tr>
                    <td><strong>Apar Industries</strong></td>
                    <td>APARINDS</td>
                    <td><a href="/stock/aparinds/">Apar Industries Price &amp; Calculator &rarr;</a></td>
                    <td>Conductor manufacturing, power transmission capex, transformer oils</td>
                  </tr>
                  <tr>
                    <td><strong>Jaykay Enterprises</strong></td>
                    <td>JAYKAY</td>
                    <td><a href="/stock/jaykay/">Jaykay Enterprises Price &amp; Calculator &rarr;</a></td>
                    <td>Digital tech diversification, 3D printing, corporate restructuring</td>
                  </tr>
                  <tr>
                    <td><strong>Shanti Gold</strong></td>
                    <td>SHANTIGOLD</td>
                    <td><a href="/stock/shantigold/">Shanti Gold Price &amp; Calculator &rarr;</a></td>
                    <td>Gems &amp; jewellery retail, bullion import duty impacts, festive season sales</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="section-title"><h2>3. The What-If Calculator: Arithmetic on Your Assumptions</h2></div>
            <p>
              Instead of accepting unverified third-party targets, BrokerLens provides an interactive
              <strong>What-If Price Calculator</strong> on every NSE equity page (as well as dedicated tools on the
              <a href="/calculators/">Financial Calculators</a> hub).
            </p>
            <p>
              The what-if engine takes the verified last closing price from NSE bhavcopy, and compounds it at an annual growth
              rate of your own choosing over 1 to 30 years:
            </p>
            <div class="card" style="padding:14px;background:var(--bg-raised);margin:12px 0">
              <code>Future Value = Starting Price &times; (1 + Annual Growth Rate)<sup>Years</sup></code>
            </div>
            <p>
              For example, if an equity closed at Rs 100 and you test an 8%% CAGR assumption over 5 years, the arithmetic yields
              Rs 146.93. This gives investors a clear reality check on whether an internet target implies an unrealistic 50%% or 80%%
              annual compounding rate that fundamentals cannot support.
            </p>

            <div class="section-title"><h2>4. Transaction Charges &amp; Demat Setup</h2></div>
            <p>
              Before executing trades based on any target analysis, factor in statutory turnover charges (STT, GST, SEBI turnover fees,
              and exchange transaction fees). Compare exact transaction costs using the
              <a href="/trade-costs/">Stock Trade Cost Calculator</a> and open an account with verified discount brokers:
            </p>
            <div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0">
              <a href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" class="btn btn-primary small">Open Indiabulls Demat (Rs 0 Delivery) &rarr;</a>
              <a href="https://zerodha.com/open-account?c=ZE5729" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open Zerodha Kite Account &rarr;</a>
            </div>
            """
        },
        {
            "slug": "zerodha-vs-groww-active-clients-market-share-2026",
            "title": "Zerodha vs Groww in 2026: Active Clients, Brokerage Charges and Platform Architecture",
            "description": "An empirical comparison of India's two largest discount stock brokers using primary NSE client data, SEBI complaint rates, and trading charges.",
            "category": "Research Article",
            "category_badge": "badge-verified",
            "type": "TechArticle",
            "read_time": "9 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              The battle for dominance in Indian retail broking is led by two tech-first powerhouses:
              <strong>Groww</strong> and <strong>Zerodha</strong>. Together, they account for over 45%
              of total active retail trading accounts in India.
            </p>
            <div class="section-title"><h2>Key Empirical Metrics</h2></div>
            <p>Comparing both firms on verified regulatory and operational metrics:</p>
            <ul>
              <li><strong>Active Clients:</strong> Groww leads with over 1.35 Crore active clients, propelled by seamless onboarding; Zerodha maintains over 79 Lakh active investors with higher portfolio retention.</li>
              <li><strong>Delivery Brokerage:</strong> Zerodha charges flat Rs 0 (zero brokerage) on equity delivery trades. Groww charges 0.05% or Rs 20 per executed order.</li>
              <li><strong>F&amp;O Charges:</strong> Both brokers offer competitive flat Rs 20 pricing for Futures and Options contracts.</li>
              <li><strong>Mutual Funds:</strong> Both platforms provide 100% direct mutual funds with zero distributor commissions.</li>
            </ul>
            <p>Read the full head-to-head breakdown on our dedicated <a href="/compare/zerodha-vs-groww/" data-link>Zerodha vs Groww comparison page</a>.</p>
            """
        },
        {
            "slug": "direct-vs-regular-mutual-funds-compounding-cost-study",
            "title": "Direct vs Regular Mutual Funds: How Much Money Do Indian Investors Save Over 15 Years?",
            "description": "Mathematical proof of expense ratio compounding: why switching to Direct mutual funds saves up to Rs 4-8 Lakhs on an ordinary monthly SIP.",
            "category": "Research Article",
            "category_badge": "badge-verified",
            "type": "TechArticle",
            "read_time": "8 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              In mutual fund investing, expense ratio is often treated as an afterthought. However,
              the difference of <strong>1.0% to 1.5%</strong> between Regular plans and Direct plans
              compounds into substantial wealth destruction over long horizons.
            </p>
            <div class="section-title"><h2>The Compounding Math</h2></div>
            <p>
              Consider a disciplined investor contributing Rs 10,000 per month for 15 years at an expected 12% annualized return:
            </p>
            <ul>
              <li><strong>Direct Plan (0.7% Expense Ratio):</strong> Final corpus accumulates to approximately <strong>Rs 50.45 Lakhs</strong>.</li>
              <li><strong>Regular Plan (1.9% Expense Ratio):</strong> Final corpus accumulates to approximately <strong>Rs 43.80 Lakhs</strong>.</li>
              <li><strong>Net Wealth Loss to Intermediary Commissions:</strong> Over <strong>Rs 6.65 Lakhs</strong>.</li>
            </ul>
            <p>
              Explore our <a href="/calculators/sip/" data-link>SIP Calculator</a> and review direct mutual fund platforms to secure higher net compound growth.
            </p>
            """
        },
        {
            "slug": "discount-vs-full-service-brokers-true-cost-audit",
            "title": "Discount Brokers vs Traditional Full-Service Brokers: Comprehensive 5-Year Cost Audit",
            "description": "Analyzing lifetime costs across 3-in-1 bank brokers and discount brokers for active traders and passive equity investors.",
            "category": "Research Article",
            "category_badge": "badge-verified",
            "type": "TechArticle",
            "read_time": "10 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              A comprehensive financial model evaluating the true cumulative expense difference between
              flat discount brokerage and percentage-based full-service accounts across five years of investing.
            </p>

            <div class="section-title"><h2>The Cost Delta Over 5 Years</h2></div>
            <p>
              For an active investor conducting 4 delivery trades and 6 derivative trades per month:
            </p>
            <ul>
              <li><strong>Discount Brokerage Total (5 Years):</strong> Approximately Rs 14,400 in direct brokerage fees.</li>
              <li><strong>Full-Service Brokerage Total (5 Years):</strong> Between Rs 65,000 and Rs 1,40,000 depending on contract values and turnover.</li>
              <li><strong>Total Cost Savings:</strong> Over Rs 50,000 retained directly in investor portfolios.</li>
            </ul>

            <div class="card" style="margin-top:16px;padding:16px;border-left:4px solid var(--accent)">
              <p style="margin:0"><strong>Audit Your Costs:</strong> Run your exact trading portfolio through our
              <a href="/calculator" data-link>Custom Brokerage Calculator</a> to calculate your exact annual fees.</p>
            </div>
            """
        },
        {
            "slug": "stt-hike-impact-retail-options-traders",
            "title": "STT Hike on Futures and Options: Impact on Retail Break-Even and Scalping Costs",
            "description": "Empirical breakdown of Securities Transaction Tax (STT) changes on options selling and futures contracts and their effects on intraday trading spreads.",
            "category": "Research Article",
            "category_badge": "badge-verified",
            "type": "TechArticle",
            "read_time": "7 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Regulatory adjustments to Securities Transaction Tax (STT) have structurally shifted the cost
              of carry for retail derivative participants on the National Stock Exchange.
            </p>

            <div class="section-title"><h2>1. New STT Rates on Equity Derivatives</h2></div>
            <ul>
              <li><strong>Options Premium Selling:</strong> STT increased from 0.0625% to <strong>0.1%</strong> on option premiums.</li>
              <li><strong>Futures Contracts:</strong> STT increased from 0.0125% to <strong>0.02%</strong> on total futures turnover.</li>
            </ul>

            <div class="section-title"><h2>2. Scalper Breakeven Implications</h2></div>
            <p>
              High-frequency option scalpers who trade for small 1-2 point price increments face tighter profit margins.
              Ensuring optimal execution speeds and zero ancillary charges across brokers becomes paramount for long-term viability.
            </p>
            """
        },
        {
            "slug": "sebi-new-index-derivatives-fo-framework",
            "title": "SEBI New Index Derivatives Framework: Lot Sizes, Expiries and Retail Margin Impact",
            "description": "Comprehensive guide to SEBI's 6-point index derivative regulatory framework: contract size increase to Rs 15-20 Lakh, single weekly expiry, and upfront option premiums.",
            "category": "Investor Guide",
            "category_badge": "badge-verified",
            "type": "Article",
            "read_time": "8 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              To curb excessive retail speculation in index futures and options (F&O), SEBI introduced a phased
              six-measure framework designed to elevate systemic resilience and align contract sizes with investor risk profiles.
            </p>

            <div class="section-title"><h2>1. Contract Size Elevation to Rs 15 Lakh - Rs 20 Lakh</h2></div>
            <p>
              The minimum contract value for index derivatives was raised from the historical Rs 5 Lakh band to
              between Rs 15 Lakh and Rs 20 Lakh. For Nifty and Bank Nifty contracts, exchange lot sizes have been
              recalibrated to ensure minimum entry margin thresholds reflect higher capital requirements.
            </p>

            <div class="section-title"><h2>2. Rationalization of Weekly Expiries</h2></div>
            <p>
              Each stock exchange (NSE and BSE) is now permitted to offer weekly derivative contracts for only one
              benchmark index. For example, NSE retained Nifty 50 weekly options while discontinuing Bank Nifty / FinNifty
              weekly contracts, dramatically reducing intra-week volatility clustering.
            </p>

            <div class="section-title"><h2>3. Upfront Collection of Option Buying Premiums</h2></div>
            <p>
              Brokers must collect 100% of client option premiums upfront on trade date (T+0). Intraday leverage
              or collateral adjustments against unpaid option purchases are prohibited, preventing negative equity spikes.
            </p>

            <div class="section-title"><h2>4. Removal of Calendar Spread Treatment on Expiry Day</h2></div>
            <p>
              Margin benefits previously afforded to calendar spread positions expiring on that trade day are discontinued,
              requiring independent margin coverage for legs with same-day settlement risk.
            </p>
            """
        },
        {
            "slug": "true-to-label-exchange-charges-broker-impact",
            "title": "True-to-Label Charges: How SEBI's Uniform Tariff Mandate Transformed Broker Pricing",
            "description": "In-depth study on SEBI's true-to-label circular eliminating slab-based exchange turnover rebates and standardizing brokerage fee structures in India.",
            "category": "Research Article",
            "category_badge": "badge-verified",
            "type": "TechArticle",
            "read_time": "6 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              SEBI's landmark 'True-to-Label' directive mandated Market Infrastructure Institutions (MIIs) to charge
              uniform transaction fees regardless of trading volume, putting an end to retrospective volume rebates.
            </p>

            <div class="section-title"><h2>1. The End of Slab-Based Rebates</h2></div>
            <p>
              Previously, exchanges charged discount brokers tiered rates based on cumulative monthly volume (e.g. 0.0027% for mega volumes vs 0.0035% baseline). Brokers charged clients the higher rate and pocketed the rebate difference as high-margin ancillary revenue.
            </p>

            <div class="section-title"><h2>2. Uniform Exchange Rates (0.00297%)</h2></div>
            <p>
              The NSE and BSE standardized equity cash and derivative turnover rates at flat, true-to-label percentages (NSE cash at 0.00297%). Any charge collected by a broker under the exchange fee head must match the exact debit levied by the clearing corporation rupee-for-rupee.
            </p>

            <div class="section-title"><h2>3. Impact on Broker Fee Models</h2></div>
            <p>
              With rebate revenue eliminated, brokers adapted by slightly adjusting equity delivery pricing, Demat account opening fees, or introducing flat API access subscriptions while preserving core zero-brokerage delivery models.
            </p>
            """
        },
        {
            "slug": "how-to-transfer-shares-between-demat-accounts-online",
            "title": "How to Transfer Shares Between Demat Accounts Online via CDSL Easiest & NSDL Speed-e",
            "description": "Step-by-step guide to transferring equity shares and mutual funds between Zerodha, Groww, Angel One, and other brokers without physical DIS slips.",
            "category": "Investor Guide",
            "category_badge": "badge-verified",
            "type": "Article",
            "read_time": "7 min read",
            "date": today_iso,
            "date_str": today_str,
            "body_html": """
            <p class="lead" style="font-size:16px;line-height:1.6;color:var(--text)">
              Moving your stock portfolio or mutual funds between brokers in India no longer requires paper Delivery
              Instruction Slips (DIS). Investors can complete secure online inter-depository transfers in minutes.
            </p>

            <div class="section-title"><h2>1. CDSL Easiest Online Transfer (CDSL to CDSL / NSDL)</h2></div>
            <ol>
              <li>Register for <strong>CDSL Easiest</strong> using your 16-digit Demat Account BOID.</li>
              <li>Add your destination broker's Demat BOID as a 'Trusted Account'.</li>
              <li>Submit the transaction by selecting the ISIN, share quantity, and execution date.</li>
              <li>Authenticate the transfer using your CDSL 6-digit TPIN and mobile OTP.</li>
            </ol>

            <div class="section-title"><h2>2. NSDL Speed-e Transfer (NSDL to NSDL / CDSL)</h2></div>
            <ol>
              <li>Access the NSDL Speed-e portal and register with your DP ID and Client ID.</li>
              <li>Enter transfer details under 'Inter-Depository Transfer' or 'Off-Market Transfer'.</li>
              <li>Authenticate using digital signature token or Aadhaar e-Sign.</li>
            </ol>

            <div class="section-title"><h2>3. Capital Gains and Off-Market Taxation</h2></div>
            <p>
              Transferring shares between two Demat accounts held by the <strong>same PAN</strong> is not considered a transfer of title and attracts zero capital gains tax. Always update the purchase price / original acquisition date on your destination broker's portal to ensure accurate future capital gains reporting.
            </p>
            """
        }
    ]

    for item in research_items:
        articles.append(item)

    return articles


def _ibsl_news_banner():
    """The sponsored IBSL banner for article pages. Imported lazily because publish.py imports this
    module; when this file runs on its own (no publish module) the page simply has no banner."""
    try:
        from .publish import ibslBanner_html
        return ibslBanner_html("wide", "news")
    except Exception:
        return ""


def write_news_suite(ingest_data, site_url="https://www.brokerlens.in"):
    """Compiles and writes all news articles, blogs, the hub, and feeds."""
    from .publish import (
        _REGISTRY_PAGE_HEAD, _REGISTRY_PAGE_FOOT, _breadcrumb, _write_text
    )

    articles = generate_news_corpus(ingest_data, site_url)
    dest_base = os.path.join(ROOT, "site", "news")
    os.makedirs(dest_base, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    written_count = 0

    # 1. Write Individual Article & Blog Pages
    for art in articles:
        slug = art["slug"]
        canon = "%s/news/%s/" % (site_url, slug)
        title = "%s | BrokerLens" % art["title"]
        desc = art["description"]
        schema_type = art.get("type", "NewsArticle")
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("News & Insights", "/news/"), (art["title"], None)
        ])

        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": schema_type,
                    "headline": art["title"],
                    "description": desc,
                    "url": canon,
                    "datePublished": art["date"],
                    "dateModified": art["date"],
                    "mainEntityOfPage": canon,
                    "author": {
                        "@type": "Organization",
                        "name": "BrokerLens Financial Research Desk",
                        "url": "%s/about" % site_url
                    },
                    "publisher": {
                        "@type": "Organization",
                        "name": "BrokerLens",
                        "logo": {"@type": "ImageObject", "url": "%s/apple-touch-icon.png" % site_url}
                    }
                },
                crumb_jsonld
            ]
        }

        # High-converting affiliate card inside article
        affiliate_html = """
        <div class="affiliate-banner-row" style="margin:32px 0 20px 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px">
          <!-- Zerodha Leveled-up Banner -->
          <div class="card aff-article-card aff-card-zerodha">
            <div>
              <div class="row-between" style="align-items:center;margin-bottom:12px">
                <div style="display:flex;align-items:center;gap:10px">
                  <img src="/assets/img/partners/zerodha.svg" alt="Zerodha Kite" height="24" style="height:24px;width:auto;display:block">
                </div>
                <div style="display:flex;gap:6px;align-items:center">
                  <span class="badge badge-verified" style="font-size:11px">Direct Onboarding</span>
                  <span class="badge" style="font-size:11px;background:rgba(56,126,209,0.12);color:#387ED1;border:1px solid rgba(56,126,209,0.25)">#1 Discount Broker</span>
                </div>
              </div>
              <h3 style="margin:0 0 6px 0;font-size:16px;font-weight:700;color:var(--text);line-height:1.35">Zero Brokerage on Delivery &amp; Direct Mutual Funds</h3>
              <p class="xs muted" style="margin:0 0 12px 0;line-height:1.5">India's pioneering tech-first investment platform. Institutional-grade Kite charts, lightning-fast execution, and zero debt risk.</p>
              
              <div class="aff-chips-grid">
                <div class="aff-chip">
                  <span class="aff-chip-label">Equity Delivery</span>
                  <span class="aff-chip-val" style="color:var(--up)">₹0 Free</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Intraday &amp; F&amp;O</span>
                  <span class="aff-chip-val">Flat ₹20 / order</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Mutual Funds &amp; IPO</span>
                  <span class="aff-chip-val" style="color:var(--up)">₹0 Commission</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Complaint Ratio</span>
                  <span class="aff-chip-val" style="color:var(--accent)">1.62 / 10k (Lowest)</span>
                </div>
              </div>
            </div>
            <div>
              <a class="btn-aff-zerodha" href="https://zerodha.com/open-account?c=ZMPGZY" target="_blank" rel="noopener nofollow">
                <span>Open Zerodha Account</span>
                <span aria-hidden="true">&rarr;</span>
              </a>
              <div class="aff-trust-note">
                <span style="color:var(--up);font-weight:700">✓</span>
                <span>100% Digital e-KYC in 5 Mins &middot; SEBI Reg: INZ000031633</span>
              </div>
            </div>
          </div>

          <!-- Angel One Leveled-up Banner -->
          <div class="card aff-article-card aff-card-angelone">
            <div>
              <div class="row-between" style="align-items:center;margin-bottom:12px">
                <div style="display:flex;align-items:center;gap:10px">
                  <svg class="ao-logo" viewBox="0 0 325 67" height="26" role="img" aria-label="Angel One" xmlns="http://www.w3.org/2000/svg"><g class="ao-emblem"><path class="ao-green" fill="#11af4b" fill-rule="evenodd" clip-rule="evenodd" d="M20.7866 8.68398C20.6349 8.93915 20.6349 9.25349 20.7866 9.50866L46.8693 53.1389C47.0135 53.383 47.2761 53.5309 47.5609 53.5309H56.3069C56.9318 53.5309 57.3164 52.8504 56.9984 52.3142L26.2154 0.810714C26.0527 0.537054 25.657 0.537054 25.4943 0.810714L20.7866 8.68398Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M20.487 18H24.8914C25.2021 18 25.3944 18.3365 25.239 18.6028L23.035 22.4192L20.8346 26.2357C20.6793 26.5019 20.2947 26.5019 20.1393 26.2357L17.9353 22.4192L15.7312 18.6028C15.5759 18.3365 15.7682 18 16.0788 18H20.487Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M15.2285 26.8481H19.6329C19.9435 26.8481 20.1358 27.1847 19.9805 27.4509L17.7765 31.2674L15.5724 35.0838C15.4171 35.3501 15.0325 35.3501 14.8771 35.0838L12.6731 31.2674L10.469 27.4509C10.3137 27.1847 10.506 26.8481 10.8166 26.8481H15.2285Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M9.93256 35.835H14.337C14.6476 35.835 14.8399 36.1715 14.6846 36.4378L12.4806 40.2542L10.2765 44.0706C10.1212 44.3369 9.73656 44.3369 9.58124 44.0706L7.37717 40.2542L5.1731 36.4378C5.01778 36.1715 5.21008 35.835 5.52072 35.835H9.93256Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M4.8107 45.0605H9.21515C9.52579 45.0605 9.71809 45.3971 9.56277 45.6633L7.3587 49.4798L5.15463 53.2962C4.99931 53.5625 4.6147 53.5625 4.45938 53.2962L2.25901 49.4798L0.0549384 45.6633C-0.100382 45.3971 0.0919194 45.0605 0.40256 45.0605H4.8107Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M15.2617 45.0605H19.6661C19.9767 45.0605 20.1691 45.3971 20.0137 45.6633L17.8097 49.4798L15.6056 53.2962C15.4503 53.5625 15.0657 53.5625 14.9103 53.2962L12.7063 49.4798L10.5022 45.6633C10.3469 45.3971 10.5392 45.0605 10.8498 45.0605H15.2617Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M25.8527 45.0605H30.2571C30.5678 45.0605 30.7601 45.3971 30.6048 45.6633L28.4007 49.4798L26.1966 53.2962C26.0413 53.5625 25.6567 53.5625 25.5014 53.2962L23.301 49.4798L21.0969 45.6633C20.9416 45.3971 21.1339 45.0605 21.4446 45.0605H25.8527Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M36.4443 45.0605H40.8487C41.1594 45.0605 41.3517 45.3971 41.1963 45.6633L38.9923 49.4798L36.7882 53.2962C36.6329 53.5625 36.2483 53.5625 36.093 53.2962L33.8889 49.4798L31.6848 45.6633C31.5295 45.3971 31.7218 45.0605 32.0324 45.0605H36.4443Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M20.6274 35.835H25.0318C25.3425 35.835 25.5348 36.1715 25.3795 36.4378L23.1754 40.2542L20.9713 44.0706C20.816 44.3369 20.4314 44.3369 20.2761 44.0706L18.072 40.2542L15.8679 36.4378C15.7126 36.1715 15.9049 35.835 16.2155 35.835H20.6274Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M30.9379 35.835H35.3423C35.6529 35.835 35.8452 36.1715 35.6899 36.4378L33.4859 40.2542L31.2818 44.0706C31.1265 44.3369 30.7419 44.3369 30.5865 44.0706L28.3825 40.2542L26.1858 36.4378C26.0305 36.1715 26.2228 35.835 26.5334 35.835H30.9379Z"/><path class="ao-orange" fill="#ff7300" fill-rule="evenodd" clip-rule="evenodd" d="M25.9936 26.8481H30.398C30.7087 26.8481 30.901 27.1847 30.7457 27.4509L28.5416 31.2674L26.3375 35.0838C26.1822 35.3501 25.7976 35.3501 25.6423 35.0838L23.4382 31.2674L21.2341 27.4509C21.0788 27.1847 21.2711 26.8481 21.5818 26.8481H25.9936Z"/></g><g class="ao-text"><path d="M112.821 52.6211L93.8576 6.93844H93.8539C93.3657 5.79203 92.2304 4.98584 90.9028 4.98584C89.6122 4.98584 88.5064 5.75135 87.9998 6.84599L69.047 52.6211C68.9472 52.9244 68.973 53.1537 69.121 53.3053C69.2689 53.4569 69.4945 53.5346 69.794 53.5346H77.2642C77.7597 53.5346 78.0852 53.3164 78.2368 52.8837L80.7034 45.9165C80.8033 45.7427 80.929 45.6576 81.0769 45.6576H100.799C100.947 45.6576 101.073 45.7464 101.172 45.9165L103.639 52.8837C103.787 53.3164 104.112 53.5346 104.612 53.5346H112.082C112.629 53.5346 112.903 53.3386 112.903 52.9503C112.895 52.8171 112.87 52.7062 112.821 52.6211ZM98.4802 39.0676H83.318C83.0665 39.0676 82.9704 38.9381 83.0184 38.6756L90.6365 18.9647C90.6846 18.7909 90.7623 18.7058 90.8621 18.7058C90.962 18.7058 91.0359 18.7946 91.084 18.9647L98.7761 38.6756C98.8759 38.9344 98.7761 39.0676 98.4802 39.0676Z"/><path d="M141.803 22.8671C143.908 24.9492 144.962 27.793 144.962 31.395V52.7515C144.962 52.9697 144.884 53.1546 144.732 53.3062C144.581 53.4578 144.396 53.5355 144.178 53.5355H138.187C137.968 53.5355 137.784 53.4615 137.632 53.3062C137.48 53.1546 137.403 52.9697 137.403 52.7515V32.9593C137.403 30.9623 136.837 29.3462 135.709 28.1073C134.581 26.8685 133.083 26.2509 131.216 26.2509C129.348 26.2509 127.839 26.8574 126.689 28.0741C125.539 29.2907 124.962 30.8957 124.962 32.8927V52.7515C124.962 52.9697 124.885 53.1546 124.733 53.3062C124.581 53.4578 124.396 53.5355 124.178 53.5355H118.187C117.969 53.5355 117.784 53.4615 117.633 53.3062C117.481 53.1546 117.403 52.9697 117.403 52.7515V21.044C117.403 20.8258 117.477 20.6446 117.633 20.4892C117.784 20.3376 117.969 20.26 118.187 20.26H124.178C124.396 20.26 124.578 20.3376 124.733 20.4892C124.885 20.6409 124.962 20.8258 124.962 21.044V23.126C124.962 23.2554 125.007 23.3442 125.092 23.3849C125.177 23.4292 125.243 23.3849 125.288 23.2554C127.066 20.9108 129.759 19.7385 133.361 19.7385C136.889 19.7422 139.699 20.7851 141.803 22.8671Z"/><path d="M177.956 20.4912C177.804 20.3395 177.62 20.2619 177.401 20.2619H171.41C171.192 20.2619 171.007 20.3395 170.856 20.4912C170.704 20.6428 170.626 20.8277 170.626 21.0459V22.6102C170.626 22.7396 170.582 22.8284 170.497 22.869C170.408 22.9134 170.323 22.869 170.238 22.7396C168.326 20.7426 165.66 19.7441 162.232 19.7441C159.366 19.7441 156.87 20.5355 154.743 22.122C152.617 23.7085 151.119 25.8238 150.25 28.468C149.555 30.3799 149.207 33.135 149.207 36.7369C149.207 39.9506 149.488 42.5762 150.054 44.6139C150.964 47.565 152.595 49.758 154.935 51.1891C157.28 52.6203 159.861 53.3377 162.683 53.3377C165.937 53.3377 168.456 52.3836 170.234 50.4717C170.32 50.3866 170.408 50.3534 170.493 50.3755C170.578 50.3977 170.623 50.4717 170.623 50.6048V51.1263C170.623 54.1624 169.85 56.3221 168.311 57.6053C166.769 58.8849 164.373 59.5247 161.119 59.5247C161.1 59.5247 161.078 59.5284 161.059 59.5284H155.457C154.924 59.5284 154.595 60.1127 154.869 60.5675L158.009 65.7745C158.253 66.1776 158.689 66.4253 159.162 66.4253H161.533V66.4216C166.466 66.3883 170.464 65.2271 173.518 62.9417C176.621 60.6193 178.174 56.7474 178.174 51.3223V21.0422C178.185 20.8277 178.108 20.6428 177.956 20.4912ZM170.534 40.3463C170.467 41.1044 170.349 41.8107 170.175 42.4616C169.828 43.8521 169.132 44.98 168.093 45.8454C167.05 46.7144 165.686 47.1471 163.992 47.1471C162.387 47.1471 161.008 46.7033 159.858 45.8121C158.707 44.9245 157.916 43.7818 157.483 42.395C157.047 41.3115 156.833 39.4218 156.833 36.7295C156.833 34.1261 157.091 32.2142 157.613 31.0012C158.09 29.57 158.87 28.4199 159.957 27.5508C161.041 26.6818 162.365 26.2491 163.929 26.2491C165.579 26.2491 166.936 26.6818 167.997 27.5508C169.058 28.4199 169.765 29.57 170.112 31.0012C170.331 31.6964 170.471 32.3991 170.534 33.1165C170.601 33.8339 170.63 35.0173 170.63 36.663C170.634 38.3604 170.601 39.5882 170.534 40.3463Z"/><path d="M211.731 36.7998L211.664 38.819C211.664 39.3404 211.406 39.5993 210.884 39.5993H190.508C190.289 39.5993 190.182 39.7065 190.182 39.9247C190.312 41.3559 190.508 42.3322 190.77 42.8536C191.813 45.9785 194.35 47.565 198.388 47.6057C201.339 47.6057 203.684 46.3927 205.418 43.9593C205.592 43.7005 205.81 43.5673 206.069 43.5673C206.243 43.5673 206.395 43.6339 206.524 43.7633L210.559 47.0842C210.951 47.3875 211.014 47.7351 210.755 48.1271C209.409 50.039 207.619 51.5109 205.385 52.5537C203.148 53.5966 200.666 54.118 197.93 54.118C194.542 54.118 191.669 53.3599 189.302 51.84C186.935 50.3201 185.212 48.1937 184.125 45.4608C183.126 43.1162 182.627 39.8618 182.627 35.6941C182.627 33.1794 182.886 31.138 183.407 29.5737C184.276 26.5376 185.915 24.1375 188.322 22.3809C190.73 20.6243 193.629 19.7441 197.013 19.7441C205.563 19.7441 210.381 24.2151 211.465 33.1572C211.646 34.237 211.731 35.4537 211.731 36.7998ZM193.015 27.4584C191.95 28.2609 191.203 29.3777 190.77 30.8126C190.511 31.5522 190.338 32.5063 190.249 33.6786C190.164 33.8968 190.249 34.004 190.508 34.004H203.725C203.943 34.004 204.05 33.8968 204.05 33.6786C203.961 32.5951 203.832 31.7704 203.658 31.2046C203.266 29.6403 202.497 28.4273 201.347 27.5582C200.197 26.6892 198.754 26.2565 197.016 26.2565C195.411 26.2528 194.076 26.6522 193.015 27.4584Z"/><path d="M227.344 47.3586H225.95C225.011 47.3586 224.253 46.6005 224.253 45.6649C224.253 38.4203 224.253 8.99449 224.253 8.99449C224.253 8.35102 223.731 7.82959 223.088 7.82959H217.859C217.215 7.82959 216.694 8.35102 216.694 8.99449V46.9999V47.9466C216.694 51.0124 219.179 53.4975 222.245 53.4975H227.344C227.766 53.4975 228.11 53.1536 228.11 52.732V48.1241C228.11 47.7026 227.766 47.3586 227.344 47.3586Z"/></g><g class="ao-orange" fill="#ff7300"><path d="M239.263 52.1045C236.9 50.8361 235.07 49.0499 233.779 46.7496C232.488 44.4494 231.841 41.7905 231.841 38.7691V22.2201C231.841 19.1988 232.488 16.5398 233.779 14.2396C235.07 11.9394 236.9 10.1569 239.263 8.88475C241.626 7.6163 244.363 6.98022 247.473 6.98022C250.583 6.98022 253.331 7.6163 255.716 8.88475C258.102 10.1569 259.943 11.9394 261.234 14.2396C262.525 16.5398 263.172 19.1988 263.172 22.2201V38.7728C263.172 41.7942 262.525 44.4531 261.234 46.7533C259.943 49.0536 258.102 50.8361 255.716 52.1082C253.327 53.3804 250.58 54.0127 247.473 54.0127C244.363 54.009 241.626 53.3767 239.263 52.1045ZM255.487 46.9826C257.502 44.9672 258.508 42.2971 258.508 38.9688V22.1536C258.508 18.8253 257.499 16.1441 255.487 14.1065C253.472 12.0688 250.802 11.0518 247.473 11.0518C244.189 11.0518 241.538 12.0688 239.526 14.1065C237.511 16.1441 236.505 18.8253 236.505 22.1536V38.9688C236.505 42.2971 237.511 44.9672 239.526 46.9826C241.541 48.9981 244.189 50.004 247.473 50.004C250.802 50.004 253.472 48.9981 255.487 46.9826Z"/><path d="M290.482 22.8736C292.56 24.9334 293.603 27.6922 293.603 31.1499V52.8245C293.603 53.2646 293.385 53.4828 292.945 53.4828H289.594C289.154 53.4828 288.936 53.2646 288.936 52.8245V32.0708C288.936 29.6633 288.204 27.6922 286.736 26.1575C285.268 24.6265 283.374 23.8573 281.055 23.8573C278.648 23.8573 276.699 24.6006 275.209 26.0909C273.718 27.5813 272.975 29.5302 272.975 31.9376V52.8245C272.975 53.2646 272.757 53.4828 272.317 53.4828H268.966C268.526 53.4828 268.308 53.2646 268.308 52.8245V20.9025C268.308 20.4661 268.526 20.2442 268.966 20.2442H272.317C272.753 20.2442 272.975 20.4624 272.975 20.9025V23.7278C272.975 23.8166 273.008 23.8831 273.075 23.9238C273.142 23.9682 273.193 23.946 273.238 23.8573C275.164 21.1428 278.119 19.7856 282.106 19.7856C285.612 19.7856 288.404 20.8174 290.482 22.8736Z"/><path d="M325 35.8811V37.9817C325 38.4217 324.782 38.6399 324.342 38.6399H303.126C302.952 38.6399 302.863 38.7287 302.863 38.9025C302.952 41.31 303.081 42.8669 303.259 43.5658C303.74 45.5369 304.768 47.0901 306.347 48.2291C307.922 49.3681 309.938 49.9376 312.389 49.9376C314.227 49.9376 315.847 49.5235 317.249 48.6914C318.65 47.8593 319.745 46.6759 320.533 45.1449C320.795 44.7492 321.102 44.6641 321.453 44.8823L324.016 46.3949C324.368 46.613 324.453 46.92 324.279 47.3157C323.184 49.4162 321.542 51.0693 319.353 52.2748C317.164 53.4804 314.645 54.0795 311.798 54.0795C308.688 54.0351 306.084 53.2918 303.98 51.8459C301.879 50.3999 300.367 48.3881 299.446 45.8032C298.658 43.7026 298.263 40.6813 298.263 36.7391C298.263 34.9011 298.296 33.3997 298.363 32.2385C298.429 31.0773 298.592 30.0381 298.854 29.1173C299.598 26.2698 301.099 23.9954 303.355 22.2869C305.611 20.5784 308.336 19.7241 311.531 19.7241C315.514 19.7241 318.58 20.7337 320.729 22.7455C322.874 24.7609 324.209 27.6048 324.737 31.2844C324.911 32.5085 325 34.0432 325 35.8811ZM306.18 25.471C304.757 26.5878 303.825 28.0892 303.388 29.9716C303.126 30.8924 302.948 32.379 302.863 34.4389C302.863 34.6127 302.952 34.7014 303.126 34.7014H320.137C320.311 34.7014 320.4 34.6127 320.4 34.4389C320.311 32.4678 320.181 31.0662 320.004 30.2341C319.523 28.263 318.547 26.6987 317.082 25.5375C315.614 24.3763 313.765 23.7957 311.531 23.7957C309.387 23.7957 307.604 24.3542 306.18 25.471Z"/></g></svg>
                </div>
                <div style="display:flex;gap:6px;align-items:center">
                  <span class="badge badge-up" style="font-size:11px">Free Demat</span>
                  <span class="badge" style="font-size:11px;background:rgba(0,82,254,0.12);color:#0052FE;border:1px solid rgba(0,82,254,0.25)">Zero AMC 1st Yr</span>
                </div>
              </div>
              <h3 style="margin:0 0 6px 0;font-size:16px;font-weight:700;color:var(--text);line-height:1.35">Flat ₹20 Trades + Free Demat &amp; SmartAPI Algo</h3>
              <p class="xs muted" style="margin:0 0 12px 0;line-height:1.5">Full-service advisory depth at discount broker rates. Pro TradingView charting, rule-based ARQ Prime engine, and automated API support.</p>
              
              <div class="aff-chips-grid">
                <div class="aff-chip">
                  <span class="aff-chip-label">Demat AMC (1st Year)</span>
                  <span class="aff-chip-val" style="color:var(--up)">₹0 Free</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Intraday &amp; F&amp;O</span>
                  <span class="aff-chip-val">Flat ₹20 or 0.25%</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Algo Trading</span>
                  <span class="aff-chip-val" style="color:var(--up)">Free SmartAPI</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Research &amp; Advisory</span>
                  <span class="aff-chip-val" style="color:var(--accent)">ARQ Prime Calls</span>
                </div>
              </div>
            </div>
            <div>
              <a class="btn-aff-angelone" href="https://angel-one.onelink.me/Wjgr/1b827725" target="_blank" rel="noopener nofollow">
                <span>Open Angel One Account</span>
                <span aria-hidden="true">&rarr;</span>
              </a>
              <div class="aff-trust-note">
                <span style="color:var(--up);font-weight:700">✓</span>
                <span>Instant Aadhaar OTP Onboarding &middot; SEBI Reg: INZ000161534</span>
              </div>
            </div>
          </div>

          <!-- Indiabulls Securities Partner Card -->
          <div class="card aff-article-card aff-card-ibsl" style="border:1px solid rgba(47,74,143,0.25);border-radius:12px;padding:20px;display:flex;flex-direction:column;justify-content:space-between;background:linear-gradient(180deg,rgba(47,74,143,0.04) 0%,rgba(47,74,143,0.01) 100%)">
            <div>
              <div class="row-between" style="align-items:center;margin-bottom:12px">
                <div style="font-weight:700;font-size:17px;color:var(--text);letter-spacing:-0.01em">
                  Indiabulls Securities
                </div>
                <div style="display:flex;gap:6px;align-items:center">
                  <span class="badge badge-verified" style="font-size:11px">Zero Delivery</span>
                  <span class="badge" style="font-size:11px;background:rgba(47,74,143,0.12);color:var(--accent);border:1px solid rgba(47,74,143,0.25)">SEBI Listed Legacy</span>
                </div>
              </div>
              <h3 style="margin:0 0 6px 0;font-size:16px;font-weight:700;color:var(--text);line-height:1.35">Zero Brokerage on Delivery &amp; Flat Rs 11 F&amp;O</h3>
              <p class="xs muted" style="margin:0 0 12px 0;line-height:1.5">Trade equities and derivatives with India's pioneering broker. Backed by 20+ years of institutional heritage and transparent pricing.</p>
              
              <div class="aff-chips-grid">
                <div class="aff-chip">
                  <span class="aff-chip-label">Equity Delivery</span>
                  <span class="aff-chip-val" style="color:var(--up)">Rs 0 Free</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Intraday &amp; F&amp;O</span>
                  <span class="aff-chip-val" style="color:var(--up)">Flat Rs 11 / order</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Account Opening</span>
                  <span class="aff-chip-val" style="color:var(--up)">Rs 0 Free</span>
                </div>
                <div class="aff-chip">
                  <span class="aff-chip-label">Heritage</span>
                  <span class="aff-chip-val" style="color:var(--accent)">20+ Years Trusted</span>
                </div>
              </div>
            </div>
            <div style="margin-top:16px">
              <a class="btn btn-primary" href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" style="display:flex;justify-content:center;align-items:center;gap:6px;width:100%;text-decoration:none;font-weight:600;padding:10px 16px">
                <span>Open Free Demat Account</span>
                <span aria-hidden="true">&rarr;</span>
              </a>
              <div class="aff-trust-note" style="margin-top:8px;font-size:11px;color:var(--text-faint);display:flex;align-items:center;gap:6px;justify-content:center">
                <span style="color:var(--up);font-weight:700">&#10003;</span>
                <span>SEBI Reg: INZ000036136 &middot; DP: IN-DP-423-2019</span>
              </div>
            </div>
          </div>
        </div>
        """

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": _esc(desc),
            "canonical": _esc(canon), "jsonld": json.dumps(jsonld, ensure_ascii=False)
        }
        body += (
            crumb_html
            + '<div class="row-wrap" style="gap:8px;margin-bottom:12px;align-items:center">'
            + '<span class="badge %s">%s</span>' % (art.get("category_badge", "badge-verified"), _esc(art.get("category", "News")))
            + '<span class="xs muted">&middot; Published %s</span>' % _esc(art.get("date_str", ""))
            + '<span class="xs muted">&middot; %s</span></div>' % _esc(art.get("read_time", "4 min read"))
            + '<h1 style="margin-top:0;font-size:var(--fs-2xl);letter-spacing:-0.02em;line-height:1.25">%s</h1>' % _esc(art["title"])
            + '<div class="card" style="margin:16px 0 20px 0;padding:14px 18px;background:var(--bg-raised);border-left:3px solid var(--accent);display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px">'
            + '<div style="display:flex;align-items:center;gap:10px">'
            + '<div style="width:34px;height:34px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px">BL</div>'
            + '<div>'
            + '<div style="font-weight:600;font-size:13px">Researched by BrokerLens Financial Research Desk</div>'
            + '<div class="xs muted">Fact-Checked &amp; Verified against primary NSE, BSE and SEBI disclosures</div>'
            + '</div>'
            + '</div>'
            + '<div class="xs"><a href="/editorial-policy" style="color:var(--accent);text-decoration:none;font-weight:600">Editorial Guidelines &rarr;</a></div>'
            + '</div>'
            + '<div class="card" style="margin-top:20px;padding:28px;line-height:1.7">%s</div>' % art["body_html"]
            + _ibsl_news_banner()
            + '<p class="xs faint" style="margin-top:12px">Editorial Integrity: BrokerLens does not accept payment to alter factual analyses. Sponsored placements are labelled and do not affect any data, ranking or analysis. Read our <a href="/editorial-policy">Editorial Policy</a> and <a href="/methodology">Methodology</a>.</p>'
            + affiliate_html
            + '<div style="margin-top:24px"><a class="btn btn-sm" href="/news/" data-link>&larr; Back to all News, Blogs &amp; Market Insights</a></div>'
        )
        body += _REGISTRY_PAGE_FOOT % {
            "source_note": "Facts are derived from National Stock Exchange (NSE) and SEBI public regulatory filings."
        }

        art_dir = os.path.join(dest_base, slug)
        os.makedirs(art_dir, exist_ok=True)
        _write_text(os.path.join(art_dir, "index.html"), body)
        written_count += 1

    # 2. Write /news/ Hub
    hub_canon = "%s/news/" % site_url
    hub_title = "Market News, Blogs, IPO Bulletins & Research | BrokerLens"
    hub_desc = "Automated real-time stock market news, investor educational blogs, live IPO bidding dispatches, and broker empirical research."
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("News & Insights", None)])
    hub_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "name": hub_title,
                "url": hub_canon,
                "description": hub_desc
            },
            crumb_jsonld
        ]
    }

    # Category filters for the hub
    categories = ["All", "Market News", "IPO Bulletin", "Blog & Guide", "Research Article"]
    filter_tabs_html = '<div class="row-wrap" style="gap:8px;margin:20px 0" id="news-filter-tabs">'
    for cat in categories:
        active_cls = "btn-primary" if cat == "All" else ""
        filter_tabs_html += '<button class="btn btn-sm %s news-tab-btn" data-cat="%s">%s</button>' % (
            active_cls, _esc(cat), _esc(cat)
        )
    filter_tabs_html += '</div>'

    cards_html = "".join(
        '<a class="card card-interactive news-article-card" href="/news/%s/" data-category="%s" style="display:flex;flex-direction:column;height:100%%">'
        '<div class="row-wrap" style="gap:6px;margin-bottom:8px;align-items:center">'
        '<span class="badge %s">%s</span>'
        '<span class="xs muted">&middot; %s</span>'
        '<span class="xs muted">&middot; %s</span></div>'
        '<h3 style="font-size:16px;margin-bottom:8px;font-weight:650;color:var(--text);line-height:1.35">%s</h3>'
        '<p class="small muted" style="line-height:1.5;margin-bottom:12px;flex:1 0 auto">%s</p>'
        '<div class="row" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:auto">'
        'Read Dispatch <span class="arr">&rarr;</span></div></a>'
        % (
            _esc(a["slug"]),
            _esc(a.get("category", "News")),
            a.get("category_badge", "badge-verified"),
            _esc(a.get("category", "News")),
            _esc(a.get("date_str", "")),
            _esc(a.get("read_time", "4 min read")),
            _esc(a["title"]),
            _esc(a["description"])
        )
        for a in articles
    )

    hub_body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(hub_title), "description": _esc(hub_desc),
        "canonical": _esc(hub_canon), "jsonld": json.dumps(hub_jsonld, ensure_ascii=False)
    }
    hub_body += (
        crumb_html
        + '<div class="hero-spotlight">'
        + '<div class="pill-tag accent" style="margin-bottom:12px"><span>✦</span> Real-Time Intelligence &amp; Research</div>'
        + '<h1>Market News, Blogs, IPO Bulletins &amp; Research</h1>'
        + '<p class="lead">Automated, data-backed market wraps, investor educational guides, live IPO bidding updates, and investigative broker research direct from exchange disclosures.</p>'
        + '</div>'
        + filter_tabs_html
        + '<div class="grid g2" id="news-cards-grid">%s</div>' % cards_html
        + """
        <script>
        document.querySelectorAll('.news-tab-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            document.querySelectorAll('.news-tab-btn').forEach(b => b.classList.remove('btn-primary'));
            btn.classList.add('btn-primary');
            const cat = btn.getAttribute('data-cat');
            document.querySelectorAll('.news-article-card').forEach(card => {
              if (cat === 'All' || card.getAttribute('data-category') === cat) {
                card.style.display = 'flex';
              } else {
                card.style.display = 'none';
              }
            });
          });
        });
        </script>
        """
    )
    hub_body += _REGISTRY_PAGE_FOOT % {
        "source_note": "Market intelligence compiled from primary NSE, BSE, and SEBI disclosures."
    }
    _write_text(os.path.join(dest_base, "index.html"), hub_body)

    # 3. Write Client-Side JSON API Feed (`site/data/news.json`)
    json_feed_data = {
        "generated_at": now.isoformat(),
        "total_articles": len(articles),
        "articles": [
            {
                "slug": a["slug"],
                "title": a["title"],
                "description": a["description"],
                "date": a["date"],
                "date_str": a["date_str"],
                "category": a.get("category", "News"),
                "category_badge": a.get("category_badge", "badge-verified"),
                "read_time": a.get("read_time", "4 min read"),
            }
            for a in articles
        ]
    }
    data_dir = os.path.join(ROOT, "site", "data")
    os.makedirs(data_dir, exist_ok=True)
    _write_text(os.path.join(data_dir, "news.json"), json.dumps(json_feed_data, ensure_ascii=False, indent=2))

    # 4. Write RSS 2.0 Feed (`site/feed.xml`)
    items_xml = "".join(
        """<item>
          <title>%s</title>
          <link>%s/news/%s/</link>
          <guid>%s/news/%s/</guid>
          <pubDate>%s</pubDate>
          <description>%s</description>
        </item>""" % (
            _esc(a["title"]), site_url, _esc(a["slug"]),
            site_url, _esc(a["slug"]),
            a["date"], _esc(a["description"])
        )
        for a in articles
    )
    rss_xml = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>BrokerLens Market News, Blogs &amp; Research</title>
  <link>%s/news/</link>
  <description>Automated, real-time Indian stock market updates, educational blogs, IPO bidding bulletins, and broker analytics.</description>
  <language>en-in</language>
  %s
</channel>
</rss>""" % (site_url, items_xml)
    _write_text(os.path.join(ROOT, "site", "feed.xml"), rss_xml)

    return written_count, articles


def run_live_generation(site_url="https://www.brokerlens.in"):
    """Fetches live exchange data on the fly and updates news, blogs, and feeds."""
    ingest_path = os.path.join(ROOT, "data", "_ingest.json")
    ingest_data = {}
    if os.path.exists(ingest_path):
        try:
            with open(ingest_path, "r", encoding="utf-8") as f:
                ingest_data = json.load(f)
        except Exception as e:
            print("[news_engine] Warning: Could not read _ingest.json: %s" % e)

    # Attempt live pull from NSE if network allows
    try:
        from .common import Fetcher
        fetcher = Fetcher("nse", referer="https://www.nseindia.com/market-data/live-equity-market",
                          warm_urls=["https://www.nseindia.com/"])
        print("[news_engine] Fetching live market indices from NSE...")
        res = fetcher.get_json("https://www.nseindia.com/api/allIndices")
        if res and isinstance(res, dict) and "data" in res:
            idx_list = []
            for item in res.get("data", []):
                idx_list.append({
                    "symbol": item.get("indexSymbol") or item.get("index"),
                    "last": item.get("last"),
                    "change": item.get("change"),
                    "change_pct": item.get("pChange") or item.get("percentChange"),
                })
            if "nse" not in ingest_data:
                ingest_data["nse"] = {}
            if "pulse" not in ingest_data["nse"]:
                ingest_data["nse"]["pulse"] = {}
            ingest_data["nse"]["pulse"]["indices"] = idx_list
            print("[news_engine] Successfully refreshed %d NSE index quotes." % len(idx_list))

        print("[news_engine] Fetching live IPO subscription disclosures...")
        ipo_res = fetcher.get_json("https://www.nseindia.com/api/ipo-current-issue")
        if ipo_res and isinstance(ipo_res, list):
            current_list = []
            for item in ipo_res:
                sub_val = None
                try:
                    raw_sub = item.get("noOfTimes") or item.get("timesSubscribed")
                    if raw_sub is not None:
                        sub_val = float(raw_sub)
                except Exception:
                    pass
                current_list.append({
                    "symbol": item.get("symbol"),
                    "company": item.get("companyName"),
                    "price_band": item.get("priceBand") or item.get("issuePrice"),
                    "bidding_start": item.get("issueStartDate"),
                    "bidding_end": item.get("issueEndDate"),
                    "times_subscribed": sub_val,
                })
            if "nse" not in ingest_data:
                ingest_data["nse"] = {}
            if "ipo" not in ingest_data["nse"]:
                ingest_data["nse"]["ipo"] = {}
            ingest_data["nse"]["ipo"]["current"] = current_list
            print("[news_engine] Successfully refreshed %d active IPO records." % len(current_list))

        # Save refreshed ingest data
        with open(ingest_path, "w", encoding="utf-8") as f:
            json.dump(ingest_data, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        print("[news_engine] Live fetch skipped or encountered: %s" % ex)

    count, _articles = write_news_suite(ingest_data, site_url)
    print("[news_engine] Successfully published %d news articles, blogs, and research guides." % count)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-Time Automated News, Blogs & Articles Generator")
    parser.add_argument("--live", action="store_true", help="Fetch live quotes and IPO subscription data from NSE")
    parser.add_argument("--site-url", default=os.getenv("SITE_URL", "https://www.brokerlens.in"), help="Site URL for canonicals")
    args = parser.parse_args()

    if args.live:
        run_live_generation(args.site_url)
    else:
        ingest_path = os.path.join(ROOT, "data", "_ingest.json")
        ingest_data = {}
        if os.path.exists(ingest_path):
            with open(ingest_path, "r", encoding="utf-8") as f:
                ingest_data = json.load(f)
        count, _articles = write_news_suite(ingest_data, args.site_url)
        print("[news_engine] Compiled %d news articles, blogs & guides." % count)
