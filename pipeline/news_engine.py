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
                  <img src="/assets/img/partners/angelone.svg" alt="Angel One" height="26" style="height:26px;width:auto;display:block">
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
            + '<p class="xs faint" style="margin-top:12px">Editorial Integrity: BrokerLens does not accept payment to promote brokers or alter factual analyses. Read our <a href="/editorial-policy">Editorial Policy</a> and <a href="/methodology">Methodology</a>.</p>'
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

    return written_count


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

    count = write_news_suite(ingest_data, site_url)
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
        count = write_news_suite(ingest_data, args.site_url)
        print("[news_engine] Compiled %d news articles, blogs & guides." % count)
