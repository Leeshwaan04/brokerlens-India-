"""IPO "How to Apply via Broker" Matrix & Allotment Status Engine.

Generates high-intent, authoritative programmatic guides:
  - /ipo/allotment-status/ (Registrar lookup hub & PAN verification guide)
  - /ipo/how-to-apply/ (Master guide: UPI mandate vs ASBA netbanking)
  - /ipo/[ipo-slug]/apply-via-[broker-id]/ (Step-by-step application walkthroughs, only for IPOs that are
    still open or upcoming; for a closed IPO the page says bidding is closed, is noindex,follow and is not
    returned for the sitemap)
  - /ipo/[ipo-slug]/allotment-status/ (noindex,follow and not returned for the sitemap once the IPO has
    listed or has no listing on file)

Structured Data:
  - Schema.org HowTo (with Step details)
  - Schema.org FAQPage
  - Schema.org BreadcrumbList
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone

try:
    from . import ipo_facts
except ImportError:  # run as a script: python3 pipeline/ipo_apply_engine.py
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from pipeline import ipo_facts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")

REGISTRARS = {
    "link-intime-india-pvt-ltd": {
        "name": "Link Intime India Pvt. Ltd.",
        "brand": "Link Intime",
        "sebi_reg": "INR000004058",
        "portal_url": "https://linkintime.co.in/initial_offer/public-issues.html",
        "alt_url": "https://linkintime.co.in/client-downloads.html",
        "email": "ipo.helpdesk@linkintime.co.in",
        "phone": "022 4918 6200 / 022 4918 6270",
        "address": "C-101, 1st Floor, 247 Park, Lal Bahadur Shastri Marg, Vikhroli West, Mumbai, Maharashtra 400083",
        "notable_ipos": "Tata Technologies, Swiggy, Hyundai Motor India, LIC, Zomato, Nykaa, Honasa Consumer, Ideaforge",
        "query_types": ["PAN Number", "Application Number", "DP Client ID (CDSL 16-digit / NSDL 8-char DP + 8-char Client)"]
    },
    "kfin-technologies-limited": {
        "name": "KFin Technologies Limited",
        "brand": "KFintech",
        "sebi_reg": "INR000000221",
        "portal_url": "https://kosmic.kfintech.com/ipostatus/",
        "alt_url": "https://kcas.kfintech.com/ipostatus/",
        "email": "einward.ris@kfintech.com",
        "phone": "1800 309 4001 / 040 6716 2222",
        "address": "Selenium Tower B, Plot 31-32, Gachibowli, Financial District, Nanakramguda, Hyderabad, Telangana 500032",
        "notable_ipos": "Bajaj Housing Finance, Mankind Pharma, IREDA, Ola Electric, Brainbees (FirstCry), Premier Energies",
        "query_types": ["PAN Card Number", "Application Number", "DP ID / Client ID", "Account No / IFSC"]
    },
    "bigshare-services-pvt-ltd": {
        "name": "Bigshare Services Pvt. Ltd.",
        "brand": "Bigshare Services",
        "sebi_reg": "INR000001385",
        "portal_url": "https://www.bigshareonline.com/ipo_Allotment.html",
        "alt_url": "https://ipo.bigshareonline.com/",
        "email": "investor@bigshareonline.com",
        "phone": "022 6263 8200 / 022 2847 0652",
        "address": "Office No. S6-2, 6th Floor, Pinnacle Business Park, Next to Ahura Centre, Mahakali Caves Road, Andheri East, Mumbai 400093",
        "notable_ipos": "Major NSE Emerge and BSE SME public issues, regional industrial mainboard issues",
        "query_types": ["Application Number", "CAF Number", "Beneficiary ID (DP ID)", "PAN Number"]
    },
    "cameo-corporate-services": {
        "name": "Cameo Corporate Services Limited",
        "brand": "Cameo",
        "sebi_reg": "INR000003753",
        "portal_url": "https://ipo.cameoindia.com/",
        "alt_url": "https://www.cameoindia.com/",
        "email": "cameo@cameoindia.com",
        "phone": "044 2846 0390 / 044 2846 0723",
        "address": "Subramanian Building, No. 1, Club House Road, Anna Salai, Chennai, Tamil Nadu 600002",
        "notable_ipos": "South Indian engineering, financial services, and healthcare IPOs",
        "query_types": ["PAN Number", "DP ID / Client ID", "Application Number"]
    },
    "skyline-financial-services": {
        "name": "Skyline Financial Services Pvt. Ltd.",
        "brand": "Skyline",
        "sebi_reg": "INR000003241",
        "portal_url": "https://www.skylinefinancial.co.in/ipo/",
        "alt_url": "https://www.skylinefinancial.co.in/",
        "email": "admin@skylinefinancial.co.in",
        "phone": "011 4045 0193 / 011 2681 2682",
        "address": "D-153A, 1st Floor, Okhla Industrial Area Phase-I, New Delhi 110020",
        "notable_ipos": "North Indian SME IPOs and infrastructure companies",
        "query_types": ["DP ID / Client ID", "Application Number", "PAN Number"]
    },
    "maashitla-securities": {
        "name": "Maashitla Securities Pvt. Ltd.",
        "brand": "Maashitla",
        "sebi_reg": "INR000004370",
        "portal_url": "https://maashitla.com/allotment-status/",
        "alt_url": "https://maashitla.com/",
        "email": "ipo@maashitla.com",
        "phone": "011 4512 1795",
        "address": "451, Krishna Apra Business Square, Netaji Subhash Place, Pitampura, Delhi 110034",
        "notable_ipos": "Specialized SME growth issues and industrial manufacturing IPOs",
        "query_types": ["Application Number", "PAN", "Demat Account No"]
    },
    "purva-sharegistry": {
        "name": "Purva Sharegistry (India) Pvt. Ltd.",
        "brand": "Purva Sharegistry",
        "sebi_reg": "INR000001112",
        "portal_url": "https://www.purvashare.com/queries/",
        "alt_url": "https://www.purvashare.com/",
        "email": "support@purvashare.com",
        "phone": "022 2301 6761 / 022 2301 2518",
        "address": "Unit No. 9, Shiv Shakti Industrial Estate, J.R. Boricha Marg, Lower Parel East, Mumbai 400011",
        "notable_ipos": "Specialized mid-cap and SME public offerings",
        "query_types": ["Company Name", "PAN", "Application Number"]
    }
}

BROKERS = {
    "zerodha": {
        "brand": "Zerodha",
        "platform": "Kite",
        "app_path": "Bids > IPO",
        "steps": [
            "Log in to the Zerodha Kite app or web platform.",
            "Navigate to the 'Bids' section and select 'IPO'.",
            "Find {company} in the list of open issues and click 'Apply'.",
            "Enter your UPI ID (must be linked to your own bank account registered with PAN).",
            "Specify the number of lots. Check the 'Cutoff-price' box to bid at the ceiling price.",
            "Submit the application and open your UPI app (Google Pay, PhonePe, BHIM) to approve the auto-debit mandate before the mandate cut-off time."
        ],
        "cta_url": "https://zerodha.com/open-account?c=ZE5729",
        "partner_badge": "BrokerLens Partner"
    },
    "groww": {
        "brand": "Groww",
        "platform": "Groww App",
        "app_path": "Explore Stocks > IPO",
        "steps": [
            "Open the Groww mobile app or website.",
            "Under the 'Stocks' tab, scroll to the 'IPO' quick-links section.",
            "Tap on {company} to review issue dates, price band, and lot size.",
            "Click 'Apply for IPO' and enter the number of lots you wish to bid for.",
            "Select 'Cutoff price' to ensure maximum allotment probability.",
            "Enter your UPI ID, submit the bid, and approve the mandate notification received in your UPI app."
        ],
        "cta_url": "https://groww.in",
        "partner_badge": None
    },
    "angel-one": {
        "brand": "Angel One",
        "platform": "Angel One App",
        "app_path": "Discover > IPO",
        "steps": [
            "Log in to the Angel One application.",
            "Go to the 'Discover' tab and tap 'IPO'.",
            "Locate {company} under the 'Open IPOs' tab and click 'Apply Now'.",
            "Enter your bid quantity (in multiples of lot size) and choose your investor category (Retail or HNI).",
            "Enter your virtual payment address (UPI ID).",
            "Accept terms and click 'Apply'. Authorize the mandate request in your UPI banking app."
        ],
        "cta_url": "https://www.angelone.in/open-demat-account?referral=BROKERLENS",
        "partner_badge": "BrokerLens Partner"
    },
    "upstox": {
        "brand": "Upstox",
        "platform": "Upstox Pro",
        "app_path": "Discover > IPO",
        "steps": [
            "Log in to Upstox Pro on mobile or web.",
            "Navigate to 'Discover' and tap on 'IPO'.",
            "Select {company} and review the bid schedule.",
            "Click 'Apply', specify the number of lots, and ensure 'Cutoff Price' is selected.",
            "Enter your UPI handle and confirm the order details.",
            "Check your UPI app for the mandate notification and approve payment before cutoff time."
        ],
        "cta_url": "https://upstox.com/open-account/?f=BROKERLENS",
        "partner_badge": "BrokerLens Partner"
    },
    "dhan": {
        "brand": "Dhan",
        "platform": "Dhan App",
        "app_path": "Bids > Live IPOs",
        "steps": [
            "Open the Dhan app and tap on the 'Bids' tab.",
            "Select 'Live IPOs' and tap on {company}.",
            "Review the bidding window and tap 'Apply for IPO'.",
            "Choose 'Regular (Retail)' category and enter number of lots.",
            "Enter your UPI ID and submit your bid.",
            "Approve the auto-debit block in your UPI application."
        ],
        "cta_url": "https://dhan.co/?ref=BROKERLENS",
        "partner_badge": "BrokerLens Partner"
    },
    "5paisa": {
        "brand": "5paisa",
        "platform": "5paisa App",
        "app_path": "User > IPO",
        "steps": [
            "Open the 5paisa app and go to the 'User' profile menu.",
            "Select 'IPO' to view currently active issues.",
            "Click 'Apply' on {company}.",
            "Input lots, enter your UPI ID, and confirm order.",
            "Authorize the mandate block in your UPI app."
        ],
        "cta_url": "https://www.5paisa.com/demat-account?ReferralCode=53293333&ReturnUrl=invest-open-account",
        "partner_badge": "BrokerLens Partner"
    },
    "icici-direct": {
        "brand": "ICICI Direct",
        "platform": "ICICI Direct Web & Neo",
        "app_path": "IPO > Current Issues",
        "steps": [
            "Log in to your ICICI Direct account.",
            "Go to 'IPO' in the top navigation bar.",
            "Select {company} from the list of open issues.",
            "Choose between ASBA (direct hold on 3-in-1 ICICI Bank savings account) or UPI mandate.",
            "Select Cutoff price and place your order.",
            "If using ASBA, funds are blocked immediately; if UPI, authorize the mandate in your UPI app."
        ],
        "cta_url": "https://www.icicidirect.com",
        "partner_badge": None
    },
    "kotak-securities": {
        "brand": "Kotak Securities",
        "platform": "Kotak Neo",
        "app_path": "Invest > IPO",
        "steps": [
            "Log in to the Kotak Neo mobile app.",
            "Tap on 'Invest' and choose 'IPO'.",
            "Select {company} and tap 'Apply'.",
            "Enter your UPI ID and lot quantity.",
            "Submit the bid and approve the mandate notification."
        ],
        "cta_url": "https://www.kotaksecurities.com",
        "partner_badge": None
    },
    "hdfc-securities": {
        "brand": "HDFC Securities",
        "platform": "HDFC Sky",
        "app_path": "IPO > Live Issues",
        "steps": [
            "Log in to HDFC Sky or HDFC Securities platform.",
            "Navigate to the IPO section and locate {company}.",
            "Click 'Apply', enter your UPI ID and bid quantity.",
            "Confirm the order and approve the UPI mandate in your payment app."
        ],
        "cta_url": "https://www.hdfcsec.com",
        "partner_badge": None
    }
}

SPONSORED_LINE = "Sponsored link: BrokerLens may earn a referral fee if you open an account through it."
ROBOTS_NOINDEX = '<meta name="robots" content="noindex,follow">'


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _fill_step(step, company):
    """Fills the {company} placeholder of a broker step. str.replace, not str.format, so any other brace
    in a step can never raise or leak."""
    return str(step).replace("{company}", company)


def _sponsored_html(margin="8px 0 0 0"):
    return f'<p class="xs faint" style="margin:{margin}">{_esc(SPONSORED_LINE)}</p>'


def parse_price_band(band_str):
    """Extracts ceiling price from price band string like 'Rs.258 to Rs.272'."""
    if not band_str:
        return 0.0, 0.0
    matches = re.findall(r"(\d+(?:\.\d+)?)", band_str.replace(",", ""))
    if len(matches) >= 2:
        return float(matches[0]), float(matches[1])
    elif len(matches) == 1:
        return float(matches[0]), float(matches[0])
    return 0.0, 0.0


def render_allotment_status_hub(site_url="https://www.brokerlens.in"):
    """Generates /ipo/allotment-status/ hub."""
    canonical = f"{site_url}/ipo/allotment-status/"
    title = "IPO Allotment Status Check Online: Direct Registrar Links & PAN Verification Guide | BrokerLens"
    desc = "Check IPO allotment status online via Link Intime, KFintech, Bigshare, BSE, and NSE. Step-by-step PAN lookup, refund timeline, and credit to Demat account guide."

    reg_cards = []
    for slug, r in REGISTRARS.items():
        reg_cards.append(f"""
        <div class="card" style="padding:20px;background:var(--bg-raised);display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <h3 style="margin:0 0 6px 0;font-size:17px">{_esc(r['name'])}</h3>
            <p class="xs muted" style="margin:0 0 14px 0"><strong>Notable Issues:</strong> {_esc(r['notable_ipos'])}</p>
          </div>
          <div class="row-wrap" style="gap:8px;margin-top:10px;">
            <a href="{r['portal_url']}" target="_blank" rel="noopener nofollow" class="btn btn-outline small" style="text-align:center">Open {r['brand']} &rarr;</a>
            <a href="/ipo/registrar/{slug}/" class="btn small" style="text-align:center">Guide</a>
          </div>
        </div>
        """)

    crumb_html = '<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPO</a></li><li class="muted">/</li><li class="muted">Allotment Status</li></ol></nav>'

    faqs = [
        ("When is IPO allotment status finalized?",
         "Under SEBI's T+3 listing framework, IPO allotment is typically finalized by late evening on the day after bidding closes (T+1 day). Registrars publish the final allotment records by 10:00 PM to 12:00 AM midnight."),
        ("What details are required to check IPO allotment?",
         "You need only one of the following: (1) PAN Card Number (10 alphanumeric characters), (2) Application Number / CAF Number, or (3) DP ID / Client ID (16-digit CDSL or NSDL BOID)."),
        ("Why is my IPO status showing 'Zero Shares Allotted' or 'No Record Found'?",
         "'No Record Found' means the registrar has not yet uploaded the allotment database for that company. Check back after a few hours. 'Zero Shares' indicates your bid was not selected in the computerized lottery draw due to oversubscription."),
        ("When will blocked funds be unblocked if not allotted?",
         "If no shares are allotted, the bank initiates fund unblocking by T+2 day. The UPI mandate automatically expires, and your blocked funds become available for withdrawal or trading without any penalty."),
        ("When do allotted shares get credited to my Demat account?",
         "Allotted equity shares are credited directly to your CDSL or NSDL Demat account by T+2 day before 8:00 PM, ahead of the stock's exchange listing at 10:00 AM on T+3 day.")
    ]

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "HowTo",
                "name": "How to Check IPO Allotment Status Online with PAN",
                "description": "Step-by-step instructions to verify IPO share allotment status on official registrar and exchange portals.",
                "step": [
                    {
                        "@type": "HowToStep",
                        "position": 1,
                        "name": "Identify the Official IPO Registrar",
                        "text": "Check whether Link Intime, KFintech, Bigshare, or Skyline is the assigned registrar for the public issue."
                    },
                    {
                        "@type": "HowToStep",
                        "position": 2,
                        "name": "Open the Registrar Allotment Portal",
                        "text": "Navigate to the secure public issue query link of the official registrar."
                    },
                    {
                        "@type": "HowToStep",
                        "position": 3,
                        "name": "Select Company and Enter PAN",
                        "text": "Choose the IPO company name from the dropdown and input your 10-digit Permanent Account Number (PAN)."
                    },
                    {
                        "@type": "HowToStep",
                        "position": 4,
                        "name": "View Allotment and Shares Credited",
                        "text": "Submit the form to view your applied shares, allotted shares, and refund status."
                    }
                ]
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
                    {"@type": "ListItem", "position": 2, "name": "IPO", "item": f"{site_url}/ipo/"},
                    {"@type": "ListItem", "position": 3, "name": "Allotment Status", "item": canonical}
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
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/" style="color:var(--accent);font-weight:600">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:28px">Check IPO Allotment Status Online</h1>
<p class="muted" style="max-width:75ch;margin:0 0 28px 0;line-height:1.6">
  Direct official registrar query portals and verified exchange verification links for Mainboard and SME IPOs in India. Check your allotment status instantly using your PAN Card number.
</p>

<div class="card" style="padding:24px;background:var(--bg-raised);margin-bottom:36px;border-left:4px solid var(--accent)">
  <h2 style="font-size:19px;margin-top:0">Official Exchange Verification Links (BSE & NSE)</h2>
  <p class="small muted" style="margin-bottom:16px">You can also verify share allotment directly on the stock exchange portals:</p>
  <div style="display:flex;flex-wrap:wrap;gap:12px">
    <a class="btn btn-primary" href="https://www.bseindia.com/investors/appli_check.aspx" target="_blank" rel="noopener nofollow">Check on BSE India Portal &rarr;</a>
    <a class="btn btn-outline" href="https://www.nseindia.com/invest/check-trades-bids-verify-ipo-bids" target="_blank" rel="noopener nofollow">Check on NSE India Portal &rarr;</a>
  </div>
</div>

<h2 style="font-size:20px;margin-bottom:16px">Official Registrar Allotment Portals</h2>
<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(320px, 1fr));gap:16px;margin-bottom:40px">
  {''.join(reg_cards)}
</div>

<div class="card" style="padding:24px;background:var(--bg-raised);margin-bottom:40px">
  <h2 style="font-size:19px;margin-top:0">How to Check IPO Allotment in 4 Simple Steps</h2>
  <ol style="margin:0;padding-left:20px;line-height:1.8;font-size:14px">
    <li><strong>Identify the registrar:</strong> Check the IPO prospect / DRHP or the BrokerLens IPO profile page to identify the assigned registrar (e.g. Link Intime, KFintech, Bigshare).</li>
    <li><strong>Open the allotment link:</strong> Click on the corresponding registrar button above.</li>
    <li><strong>Select query mode:</strong> Choose 'PAN' (recommended), 'Application Number', or 'DP Client ID'.</li>
    <li><strong>Submit & verify:</strong> Enter your 10-digit PAN number and captcha code. Your applied shares and allotted shares will be displayed immediately.</li>
  </ol>
</div>

<h2 style="font-size:20px;margin-bottom:16px">Frequently Asked Questions</h2>
<div style="max-width:72ch">
  {faq_html}
</div>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">BrokerLens provides direct links to SEBI-registered RTAs and official stock exchanges. Never enter your banking PIN or OTP on unverified portals.</p>
  <p class="small"><a href="/ipo/">IPO Tracker</a> &middot; <a href="/ipo/how-to-apply/">How to Apply IPO</a> &middot; <a href="/trade-costs/">Trade Costs</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_how_to_apply_master(site_url="https://www.brokerlens.in"):
    """Generates /ipo/how-to-apply/ master guide."""
    canonical = f"{site_url}/ipo/how-to-apply/"
    title = "How to Apply for an IPO Online via UPI & ASBA: Step-by-Step Guide | BrokerLens"
    desc = "Complete beginner guide to applying for IPOs in India. Learn UPI auto-debit mandates, Net Banking ASBA, cutoff price bidding, and retail vs HNI category rules."

    crumb_html = '<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPO</a></li><li class="muted">/</li><li class="muted">How to Apply</li></ol></nav>'

    broker_links = []
    for b_id, b in BROKERS.items():
        # This page is not about one IPO, so the per-issue placeholder reads "the IPO" (the raw
        # {company} placeholder used to show on the Dhan and HDFC Securities cards).
        step_a, step_b = (_fill_step(x, "the IPO") for x in b["steps"][:2])
        broker_links.append(f"""
        <div style="background:var(--bg-raised);padding:16px;border-radius:6px;border:1px solid var(--border)">
          <h3 style="margin:0 0 6px 0;font-size:17px">{_esc(b['brand'])}</h3>
          <p class="xs muted" style="margin:0 0 10px 0">Platform: <strong>{_esc(b['platform'])}</strong> ({_esc(b['app_path'])})</p>
          <p class="small" style="margin:0 0 12px 0;line-height:1.5">{_esc(step_a)} {_esc(step_b)}</p>
          <a href="{b['cta_url']}" target="_blank" rel="noopener sponsored" class="btn btn-outline small">Open {b['brand']} Account &rarr;</a>
          {_sponsored_html("8px 0 0 0")}
        </div>
        """)
    lim = ipo_facts.SEBI_BID_LIMITS

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/" style="color:var(--accent);font-weight:600">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:28px">How to Apply for an IPO Online: UPI vs ASBA Guide</h1>
<p class="muted" style="max-width:75ch;margin:0 0 28px 0;line-height:1.6">
  A complete, regulator-verified walkthrough for Indian retail investors applying for Mainboard and SME public issues through discount brokers or bank ASBA.
</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:36px">
  <div class="card" style="padding:20px;background:var(--bg-raised)">
    <h2 style="font-size:18px;margin-top:0">Method 1: UPI Mandate via Stock Broker</h2>
    <p class="small muted">Best for retail investors applying via Zerodha, Groww, Angel One, Upstox, or Dhan.</p>
    <ul style="font-size:13px;line-height:1.6;padding-left:18px">
      <li><strong>Maximum limit:</strong> {lim['upi']} per application through UPI ({lim['note']}).</li>
      <li><strong>Zero paperwork:</strong> Completely digital flow inside your trading app.</li>
      <li><strong>Fund block:</strong> Money stays in your savings account earning interest until allotment.</li>
      <li><strong>Cutoff time:</strong> Each issue states its bid closing time and its UPI mandate approval deadline. Check the offer document and your broker's bid screen.</li>
    </ul>
  </div>
  <div class="card" style="padding:20px;background:var(--bg-raised)">
    <h2 style="font-size:18px;margin-top:0">Method 2: Net Banking ASBA</h2>
    <p class="small muted">Used for bids above the UPI limit of {lim['upi']}, and by investors who prefer a bank block (ASBA) or a 3-in-1 account.</p>
    <ul style="font-size:13px;line-height:1.6;padding-left:18px">
      <li><strong>Maximum limit:</strong> The UPI cap does not apply to an ASBA bank block. Check your bank's own limits.</li>
      <li><strong>Direct lien:</strong> Bank blocks the funds directly without needing a third-party UPI app.</li>
      <li><strong>Supported banks:</strong> SBI, HDFC Bank, ICICI Bank, Axis Bank, Kotak Mahindra Bank.</li>
      <li><strong>Demat requirement:</strong> Must input your 16-digit CDSL/NSDL BOID manually during application.</li>
    </ul>
  </div>
</div>

<h2 style="font-size:20px;margin-bottom:16px">How to Apply in Leading Stock Broker Apps</h2>
<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(320px, 1fr));gap:16px;margin-bottom:40px">
  {''.join(broker_links)}
</div>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All IPO applications must be made from the primary bank account of the PAN holder. Third-party UPI applications are rejected by SEBI regulations.</p>
  <p class="small"><a href="/ipo/">IPO Tracker</a> &middot; <a href="/ipo/allotment-status/">Check Allotment Status</a> &middot; <a href="/trade-costs/">Trade Costs</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def _closed_text(ipo_record, status, company):
    """One neutral sentence on why there is nothing to apply for, from dates on file."""
    b_end = ipo_facts.fmt_date(ipo_record.get("bidding_end"))
    if status == ipo_facts.STATUS_NO_LISTING:
        t = ipo_facts.NO_LISTING_NOTE
        fs = ipo_facts._flag_sentence(ipo_record)
        return (t + " " + fs) if fs else t
    if b_end:
        return "Bidding for %s IPO closed on %s." % (company, b_end)
    return "Bidding for %s IPO has closed." % company


def render_ipo_broker_apply_page(ipo_record, broker_id, broker_info, site_url="https://www.brokerlens.in"):
    """Renders /ipo/[ipo-slug]/apply-via-[broker-id]/.

    Application steps are written only while the IPO is open or upcoming. Once bidding is over the page says
    so in a neutral notice, carries no application instruction, is noindex,follow and is not returned for
    the sitemap (see build_ipo_apply_suite)."""
    sym = ipo_record["symbol"]
    company = ipo_facts.display_name(ipo_record)
    ipo_slug = sym.lower()
    b_brand = broker_info["brand"]
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = ipo_facts.ipo_status(ipo_record, today_iso)
    open_for_bids = status in ipo_facts.OPEN_STATUSES

    pf = ipo_facts.price_facts(ipo_record)
    band_str = ipo_facts.band_text(ipo_record)
    top = pf["band_high"] if pf["band_high"] is not None else (pf["single"] or pf["issue_price"])
    # Lot size is shown only when a sourced lot_size is on the record. The old estimate
    # (Rs 14,500 divided by price) was wrong against prospectus figures and is gone.
    lot_size = ipo_facts.lot_size_on_file(ipo_record)
    min_invest = (lot_size * top) if (lot_size and top) else 0.0
    lim = ipo_facts.SEBI_BID_LIMITS

    canonical = f"{site_url}/ipo/{ipo_slug}/apply-via-{broker_id}/"
    if open_for_bids:
        title = f"How to Apply for {company} IPO in {b_brand}: Step-by-Step UPI Guide | BrokerLens"
        desc = f"Learn how to apply for {company} IPO on {b_brand} ({broker_info['platform']}). Step-by-step UPI mandate guide, price band, and bidding cutoff time."
        robots_meta = ""
    else:
        title = f"{company} IPO on {b_brand}: Bidding Closed | BrokerLens"
        desc = (f"Bidding for {company} IPO is closed, so there is nothing to apply for. Dates and price on file, "
                f"and where to check the issue's status.")
        robots_meta = ROBOTS_NOINDEX

    steps_html = "".join(f"<li>{_esc(_fill_step(s, company))}</li>" for s in broker_info["steps"]) if open_for_bids else ""

    crumb_html = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol style="display:flex;gap:6px;list-style:none;padding:0;margin:0;font-size:13px"><li><a href="/">Home</a></li><li class="muted">/</li><li><a href="/ipo/">IPO</a></li><li class="muted">/</li><li><a href="/ipo/{ipo_slug}/">{sym}</a></li><li class="muted">/</li><li class="muted">Apply via {b_brand}</li></ol></nav>'

    min_answer = (f"The minimum bid is 1 lot of {lot_size} shares. At the upper price of Rs {ipo_facts.fmt_price(top)}, one lot is Rs {ipo_facts.fmt_price(min_invest)}." if min_invest > 0
                  else f"The minimum bid is 1 lot. BrokerLens has no sourced lot size for {company} IPO, so no rupee minimum is shown. The lot size is printed in the issue prospectus and on the bid screen of {b_brand}." + (f" The price band is {band_str} per share." if band_str else ""))
    if open_for_bids:
        faqs = [
            (f"Can I apply for {company} IPO using UPI on {b_brand}?",
             f"Yes, {b_brand} supports digital IPO applications through a UPI mandate, with a UPI limit of {lim['upi']} per application ({lim['note']})."),
            (f"What is the minimum investment for {company} IPO?", min_answer),
            (f"What happens if my UPI mandate for {company} is delayed?",
             f"UPI mandates are usually delivered within 15 to 45 minutes of submitting the bid on {b_brand}. If you do not receive the notification, open your UPI app and check the 'Pending Mandates / Autopay' section."),
            (f"Can I cancel or modify my {company} IPO application on {b_brand}?",
             f"Bids can usually be modified or cancelled on {b_brand} while the bidding window is open. The closing time is stated in the offer document and on the bid screen.")
        ]
    else:
        faqs = [
            (f"Can I still apply for {company} IPO on {b_brand}?",
             f"No. {_closed_text(ipo_record, status, company)} Applications cannot be made for this issue."),
            (f"What is the price of {company} IPO?",
             (f"The price band on file is {band_str} per share." if band_str else f"No price band or issue price is on file for {company} IPO.")),
            (f"Where can I check the status of {company} IPO?",
             f"The IPO page on BrokerLens shows the dates and status on file for {company}. The exchange and the registrar are the official sources for any allotment or listing result."),
        ]

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    graph = []
    if open_for_bids:
        graph.append({
            "@type": "HowTo",
            "name": f"How to Apply for {company} IPO on {b_brand}",
            "description": f"Step-by-step instructions to apply for {company} IPO through {b_brand} Kite/App using UPI auto-debit mandate.",
            "step": [
                {
                    "@type": "HowToStep",
                    "position": i + 1,
                    "name": f"Step {i+1}",
                    "text": _fill_step(s, company)
                }
                for i, s in enumerate(broker_info["steps"])
            ]
        })
    graph.append({
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ]
    })
    graph.append({
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": site_url},
            {"@type": "ListItem", "position": 2, "name": "IPO", "item": f"{site_url}/ipo/"},
            {"@type": "ListItem", "position": 3, "name": sym, "item": f"{site_url}/ipo/{ipo_slug}/"},
            {"@type": "ListItem", "position": 4, "name": f"Apply via {b_brand}", "item": canonical}
        ]
    })
    jsonld = {"@context": "https://schema.org", "@graph": graph}

    if open_for_bids:
        h1 = f"How to Apply for {company} IPO on {b_brand}"
        intro = (f"Follow this step-by-step walkthrough to submit your application for the <strong>{_esc(company)}</strong> public issue on "
                 f"{_esc(b_brand)} ({_esc(broker_info['platform'])}) using UPI mandate.")
        main_block = (
            '<h2 style="font-size:20px;margin-bottom:14px">Step-by-Step Application Walkthrough</h2>\n'
            '<div class="card" style="padding:24px;background:var(--bg-raised);margin-bottom:32px">\n'
            '  <ol style="margin:0;padding-left:22px;line-height:1.8;font-size:15px">\n'
            f'    {steps_html}\n'
            '  </ol>\n</div>'
        )
        cta_title = f"Don't have a {b_brand} Demat Account?"
        cta_text = "Open an account online with instant e-KYC to bid for upcoming IPOs."
    else:
        h1 = f"{company} IPO on {b_brand}: Bidding Closed"
        intro = (f"{_esc(_closed_text(ipo_record, status, company))} There are no application steps for this issue.")
        main_block = (
            '<div class="card" style="padding:20px;background:var(--bg-raised);margin-bottom:32px;border-left:4px solid var(--accent)">\n'
            f'  <h2 style="font-size:19px;margin:0 0 8px 0">Bidding for {_esc(company)} IPO is closed</h2>\n'
            '  <p class="small muted" style="margin:0;line-height:1.6;max-width:72ch">Applications can no longer be made for this issue, so this page '
            'carries no application instructions. For the dates and status on file, see the '
            f'<a href="/ipo/{ipo_slug}/">{_esc(company)} IPO page</a>. To apply for a future IPO you need a demat account and a UPI ID; '
            'see <a href="/ipo/how-to-apply/">how IPO applications work</a>.</p>\n</div>'
        )
        cta_title = f"Planning to apply for a future IPO on {b_brand}?"
        cta_text = "You need a demat account and a UPI ID before an issue opens."

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
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
</head>
<body>
<header class="site-header"><div class="wrap row-between" style="align-items:center;padding:14px 20px">
  <a href="/" class="brand" style="font-size:18px;font-weight:700;color:inherit;text-decoration:none">BrokerLens<span style="color:var(--accent)">.in</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/" style="color:var(--accent);font-weight:600">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
{crumb_html}

<h1 style="margin:20px 0 8px 0;font-size:26px">{_esc(h1)}</h1>
<p class="muted" style="max-width:75ch;margin:0 0 24px 0;line-height:1.6">
  {intro}
</p>

<div class="card" style="padding:20px;background:var(--bg-raised);margin-bottom:28px;display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:14px">
  <div>
    <div class="xs muted">Price Band</div>
    <div style="font-weight:600;font-size:16px">{_esc(band_str or 'Not on file')}</div>
  </div>
  <div>
    <div class="xs muted">Lot Size</div>
    <div style="font-weight:600;font-size:16px">{_esc(f"{lot_size} Shares" if lot_size else "Not on file")}</div>
  </div>
  <div>
    <div class="xs muted">Retail Bid Limit</div>
    <div style="font-weight:600;font-size:16px;color:var(--accent)">Up to {lim['retail']}</div>
    <div class="xs faint">{_esc(lim['note'])}</div>
  </div>
  <div>
    <div class="xs muted">Bidding Opens / Closes</div>
    <div style="font-weight:600;font-size:14px">{_esc(ipo_facts.date_range_text(ipo_record.get('bidding_start'), ipo_record.get('bidding_end')) or 'Not on file')}</div>
  </div>
</div>

{main_block}

<div class="card" style="padding:20px;background:var(--bg-raised);margin-bottom:32px">
  <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:16px">
    <div>
      <h3 style="margin:0 0 6px 0;font-size:18px">{_esc(cta_title)}</h3>
      <p class="xs muted" style="margin:0">{_esc(cta_text)}</p>
    </div>
    <a href="{broker_info['cta_url']}" target="_blank" rel="noopener sponsored" class="btn btn-primary">Open {b_brand} Account &rarr;</a>
  </div>
  {_sponsored_html("10px 0 0 0")}
</div>

<h2 style="font-size:20px;margin-bottom:16px">Frequently Asked Questions</h2>
<div style="max-width:72ch;margin-bottom:36px">
  {faq_html}
</div>

<p class="small muted">
  Also see: <a href="/ipo/{ipo_slug}/">{_esc(company)} IPO Details & Subscription</a> &middot; <a href="/ipo/allotment-status/">Check Allotment Status</a> &middot; <a href="/broker/{broker_id}/">{b_brand} Broker Review</a>
</p>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All IPO data is sourced from NSE public issue disclosures. BrokerLens does not provide investment recommendations.</p>
  <p class="small"><a href="/ipo/">IPO Tracker</a> &middot; <a href="/ipo/allotment-status/">Allotment Status</a> &middot; <a href="/trade-costs/">Trade Costs</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_registrars_master_hub(site_url: str = "https://www.brokerlens.in") -> str:
    """Renders /ipo/registrars/index.html (Master directory of all SEBI-registered RTAs)."""
    canonical = f"{site_url}/ipo/registrars/"
    title = "IPO Registrars in India: Official List of SEBI Registered RTAs & Allotment Portals"
    desc = (
        "Comprehensive directory of all SEBI-registered IPO Registrars and Transfer Agents (RTAs) in India. "
        "Direct allotment status verification links, helplines, addresses, and query guides for Link Intime, KFintech, Bigshare, and more."
    )[:295]

    cards_html = "".join(
        f'<div class="card" style="padding:20px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;margin-bottom:16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
        f'<h3 style="margin:0;font-size:18px;"><a href="/ipo/registrar/{slug}/" style="color:var(--text);text-decoration:none;">{info["name"]}</a></h3>'
        f'<span class="badge" style="font-size:11px;">{info["sebi_reg"]}</span>'
        f'</div>'
        f'<p class="muted xs" style="margin:0 0 10px 0;"><strong>Corporate Office:</strong> {_esc(info["address"])}</p>'
        f'<p class="muted xs" style="margin:0 0 10px 0;"><strong>Helpline:</strong> {_esc(info["phone"])} | <strong>Email:</strong> {_esc(info["email"])}</p>'
        f'<p class="xs" style="margin:0 0 14px 0;line-height:1.5;"><strong>Notable IPOs Handled:</strong> {_esc(info["notable_ipos"])}</p>'
        f'<div class="row-wrap" style="gap:10px;">'
        f'<a href="{info["portal_url"]}" target="_blank" rel="noopener nofollow" class="btn btn-primary small">Check Allotment on {info["brand"]} &rarr;</a>'
        f'<a href="/ipo/registrar/{slug}/" class="btn small" style="background:var(--bg);border:1px solid var(--border);">Registrar Details</a>'
        f'</div>'
        f'</div>'
        for slug, info in sorted(REGISTRARS.items())
    )

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
                    {"@type": "ListItem", "position": 2, "name": "IPO", "item": f"{site_url}/ipo/"},
                    {"@type": "ListItem", "position": 3, "name": "Registrars", "item": canonical}
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
<header class="site"><div class="wrap row-between">
  <a href="/" class="brand" style="font-weight:700;font-size:20px;text-decoration:none;color:var(--text)">Broker<span style="color:var(--accent)">Lens</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/" style="color:var(--accent);font-weight:600">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/ipo/">IPO</a> &rsaquo;
    <span>Registrars</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0;">SEBI Registered IPO Registrars & Transfer Agents</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Every public issue in India appoints a SEBI-registered Registrar & Share Transfer Agent (RTA) responsible for processing bids, determining basis of allotment, processing bank mandate unblocks, and crediting shares to Demat.
    </p>
  </header>

  <section>
    {cards_html}
  </section>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">Registrar details sourced from SEBI official registration disclosures.</p>
  <p class="small"><a href="/ipo/">IPO Tracker</a> &middot; <a href="/ipo/allotment-status/">Allotment Status</a> &middot; <a href="/ipo/how-to-apply/">How to Apply</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_registrar_hub(reg_slug: str, info: dict, site_url: str = "https://www.brokerlens.in") -> str:
    """Renders /ipo/registrar/[registrar-slug]/index.html."""
    canonical = f"{site_url}/ipo/registrar/{reg_slug}/"
    brand = info["brand"]
    title = f"{info['name']} IPO Allotment Status: Direct Portal Link & Query Guide"
    desc = (
        f"Check IPO allotment status on {info['name']} ({brand}). Direct verification server link, "
        f"PAN lookup instructions, customer care helpline ({info['phone']}), and SEBI registration {info['sebi_reg']}."
    )[:295]

    query_chips = "".join(f'<span class="chip" style="font-size:12px;margin-right:6px;">{_esc(q)}</span>' for q in info["query_types"])

    faq_items = [
        (
            f"How do I check IPO allotment on {brand} online?",
            f"Visit {brand}'s official public issues portal ({info['portal_url']}). In the company dropdown, select the name of the IPO. Choose your preferred query identifier (PAN Number, Application Number, or Demat DP Client ID). Enter the captcha verification code and click 'Submit' to view your allotted share quantity."
        ),
        (
            f"When does {brand} update IPO allotment status?",
            f"{brand} usually uploads and finalizes the basis of allotment late in the evening on the designated allotment date (typically between 8:00 PM and midnight IST), or early the following morning."
        ),
        (
            f"What should I do if my bank mandate is not revoked by {brand}?",
            f"If shares are not allotted to you and your bank mandate block is not released within 24 to 48 hours after allotment finalization, contact {brand} helpdesk at {info['email']} or phone {info['phone']} with your Application Number and UPI URN (Unique Reference Number)."
        ),
    ]

    faq_html = "".join(
        f'<div class="faq-item" style="margin-bottom:16px;">'
        f'<h4 style="margin:0 0 6px 0;font-size:15px;color:var(--text);">{q}</h4>'
        f'<p class="muted" style="margin:0;font-size:14px;line-height:1.6;">{a}</p>'
        f'</div>'
        for q, a in faq_items
    )

    schema_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FinancialService",
                "name": info["name"],
                "url": canonical,
                "telephone": info["phone"],
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": info["address"],
                    "addressCountry": "IN"
                }
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
                    {"@type": "ListItem", "position": 2, "name": "IPO", "item": f"{site_url}/ipo/"},
                    {"@type": "ListItem", "position": 3, "name": "Registrars", "item": f"{site_url}/ipo/registrars/"},
                    {"@type": "ListItem", "position": 4, "name": brand, "item": canonical}
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
<header class="site"><div class="wrap row-between">
  <a href="/" class="brand" style="font-weight:700;font-size:20px;text-decoration:none;color:var(--text)">Broker<span style="color:var(--accent)">Lens</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/" style="color:var(--accent);font-weight:600">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/ipo/">IPO</a> &rsaquo;
    <a href="/ipo/registrars/">Registrars</a> &rsaquo;
    <span>{brand}</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0;">{info["name"]} Allotment Status</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Official guide and direct verification portal for IPOs managed by {info["name"]} (SEBI Registration: {info["sebi_reg"]}).
    </p>
  </header>

  <div class="card" style="padding:24px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;">Direct Allotment Verification Links</h2>
    <div style="font-size:14.5px;line-height:1.7;margin-bottom:18px;">
      <div><span class="muted">Primary Server:</span> <a class="link" href="{info['portal_url']}" target="_blank" rel="noopener nofollow"><strong>{info['portal_url']}</strong> &rarr;</a></div>
      <div><span class="muted">Alternate Server:</span> <a class="link" href="{info['alt_url']}" target="_blank" rel="noopener nofollow">{info['alt_url']} &rarr;</a></div>
      <div style="margin-top:6px;"><span class="muted">Supported Query Modes:</span> <div style="margin-top:4px;">{query_chips}</div></div>
    </div>
    <div>
      <a href="{info['portal_url']}" target="_blank" rel="noopener nofollow" class="btn btn-primary">Open {brand} Allotment Portal &rarr;</a>
    </div>
  </div>

  <div class="grid g2" style="gap:20px;margin-bottom:28px;">
    <div class="card" style="padding:20px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;">
      <h3 style="font-size:16px;margin-top:0;margin-bottom:10px;">Corporate & Regulatory Profile</h3>
      <div style="font-size:13.5px;line-height:1.6;">
        <p style="margin:0 0 8px 0;"><strong>SEBI Registration No:</strong> <span class="mono">{info["sebi_reg"]}</span></p>
        <p style="margin:0 0 8px 0;"><strong>Registered Office:</strong><br>{info["address"]}</p>
        <p style="margin:0;"><strong>Major IPOs Handled:</strong><br>{info["notable_ipos"]}</p>
      </div>
    </div>

    <div class="card" style="padding:20px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;">
      <h3 style="font-size:16px;margin-top:0;margin-bottom:10px;">Investor Grievance & Escalation Desk</h3>
      <div style="font-size:13.5px;line-height:1.6;">
        <p style="margin:0 0 8px 0;"><strong>Telephone Helpline:</strong><br>{info["phone"]}</p>
        <p style="margin:0 0 8px 0;"><strong>Dedicated Email:</strong><br><a href="mailto:{info['email']}">{info["email"]}</a></p>
        <p style="margin:0;"><strong>SEBI SCORES 2.0:</strong><br><a href="https://scores.sebi.gov.in" target="_blank" rel="noopener nofollow">scores.sebi.gov.in</a></p>
      </div>
    </div>
  </div>

  <section class="card" style="padding:24px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:16px;">Frequently Asked Questions</h2>
    {faq_html}
  </section>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">Registrar information sourced from SEBI disclosures.</p>
  <p class="small"><a href="/ipo/registrars/">All Registrars</a> &middot; <a href="/ipo/allotment-status/">Allotment Status</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def render_individual_ipo_allotment_page(ipo_record: dict, site_url: str = "https://www.brokerlens.in") -> str:
    """Renders /ipo/[ipo-slug]/allotment-status/index.html."""
    sym = (ipo_record.get("symbol") or "").strip().upper()
    ipo_slug = sym.lower()
    company = ipo_facts.display_name(ipo_record)
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = ipo_facts.ipo_status(ipo_record, today_iso)
    # Listed IPOs and IPOs with no listing on file: noindex,follow with a self canonical, not in the sitemap.
    robots_meta = ROBOTS_NOINDEX if status in ("Listed", ipo_facts.STATUS_NO_LISTING) else ""
    price_band = ipo_facts.band_text(ipo_record) or "Not on file"
    b_start = ipo_facts.fmt_date(ipo_record.get("bidding_start")) or "Announced"
    b_end = ipo_facts.fmt_date(ipo_record.get("bidding_end")) or "Announced"
    # Sourced lot size only; the old Rs 14,500 estimate is gone.
    lot_size = ipo_facts.lot_size_on_file(ipo_record)

    canonical = f"{site_url}/ipo/{ipo_slug}/allotment-status/"
    title = f"{company} IPO Allotment Status: Check Online via Registrar, BSE & NSE Link"
    desc = (
        f"Check {company} ({sym}) IPO allotment status online. Direct verification links for official Registrar, "
        f"BSE India application query, NSE bid verification, and bank mandate refund timeline."
    )[:295]

    # BrokerLens does not have access to a per-IPO registrar field from NSE's
    # public-issue disclosures, so we never guess which of the real registrars
    # below handled this specific issue (the registrar is printed on your own
    # application acknowledgment and the RHP cover page).
    registrar_list = list(REGISTRARS.values())

    if status in ("Active", "Forthcoming", "Closed"):
        when_answer = (f"The basis of allotment for {company} is finalized within 1 to 2 business days after the issue closing date ({b_end}). "
                       f"Check the official registrar portal late evening on the scheduled allotment date.")
    elif status == ipo_facts.STATUS_NO_LISTING:
        when_answer = (f"The bidding end date on file for {company} is {b_end}. {ipo_facts.NO_LISTING_NOTE} "
                       f"The registrar portal or the exchange notice shows the current position of the issue.")
    else:
        when_answer = (f"Bidding for {company} closed on {b_end}. The registrar portal or the exchange notice is the "
                       f"official place to see the allotment result.")
    faq_items = [
        (
            f"How do I check {company} IPO allotment status?",
            f"You can verify {company} IPO allotment status in three ways: (1) On the registrar's portal named on your application acknowledgment or the RHP cover page, by selecting '{company}' and entering your PAN; (2) On the BSE India allotment status page (bseindia.com/investors/appli_check.aspx) under 'Equity'; or (3) In your bank account statement by checking if the blocked funds under UPI mandate were debited or released."
        ),
        (
            f"When will {company} IPO allotment be announced?",
            when_answer
        ),
        (
            f"What happens if I get zero allotment in {company} IPO?",
            f"If no shares are allotted to your application, the bank mandate hold on your funds is revoked, releasing the blocked amount back to your available balance within 24 to 48 hours."
        ),
    ]

    faq_html = "".join(
        f'<div class="faq-item" style="margin-bottom:16px;">'
        f'<h4 style="margin:0 0 6px 0;font-size:15px;color:var(--text);">{q}</h4>'
        f'<p class="muted" style="margin:0;font-size:14px;line-height:1.6;">{a}</p>'
        f'</div>'
        for q, a in faq_items
    )

    if status in ("Active", "Forthcoming"):
        state_html = ""
    else:
        state_html = (f'<div class="card" style="padding:14px 18px;margin-bottom:24px;background:var(--bg-raised);border-left:3px solid var(--accent)">'
                      f'<div class="small muted">{_esc(_closed_text(ipo_record, status, company))} The registrar and exchange links below are the '
                      f'official place to check a result; BrokerLens holds no individual results.</div></div>')

    schema_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "HowTo",
                "name": f"How to Check {company} IPO Allotment Status Online",
                "description": desc,
                "step": [
                    {
                        "@type": "HowToStep",
                        "position": 1,
                        "name": "Open Your Registrar's Allotment Portal",
                        "text": "Find the registrar named on your application acknowledgment or the RHP cover page, then open that registrar's allotment portal."
                    },
                    {
                        "@type": "HowToStep",
                        "position": 2,
                        "name": f"Select {company} from Dropdown",
                        "text": f"Select '{company}' from the issue dropdown."
                    },
                    {
                        "@type": "HowToStep",
                        "position": 3,
                        "name": "Enter PAN Card Details",
                        "text": "Choose 'PAN' as query type, enter your 10-character PAN number and captcha code, then click Submit."
                    }
                ]
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
                    {"@type": "ListItem", "position": 2, "name": "IPO", "item": f"{site_url}/ipo/"},
                    {"@type": "ListItem", "position": 3, "name": company, "item": f"{site_url}/ipo/{ipo_slug}/"},
                    {"@type": "ListItem", "position": 4, "name": "Allotment Status", "item": canonical}
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
{robots_meta}
<link rel="stylesheet" href="/assets/css/app.css">
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<header class="site"><div class="wrap row-between">
  <a href="/" class="brand" style="font-weight:700;font-size:20px;text-decoration:none;color:var(--text)">Broker<span style="color:var(--accent)">Lens</span></a>
  <nav class="nav" style="display:flex;gap:16px;font-size:14px">
    <a href="/brokers">Brokers</a>
    <a href="/compare">Compare</a>
    <a href="/stocks/">Stocks</a>
    <a href="/trade-costs/">Trade Costs</a>
    <a href="/ipo/" style="color:var(--accent);font-weight:600">IPO</a>
    <a href="/news/">News</a>
  </nav>
</div></header>

<main class="wrap" style="padding:24px 20px 60px 20px">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/ipo/">IPO</a> &rsaquo;
    <a href="/ipo/{ipo_slug}/">{company}</a> &rsaquo;
    <span>Allotment Status</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0;">{company} IPO Allotment Status</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Verified guide and direct verification servers for <strong>{company}</strong> ({sym}) public issue. Verify allotment via official Registrar, BSE, and NSE.
    </p>
  </header>

  {state_html}
  <div class="card" style="padding:20px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;margin-bottom:28px;display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:14px;">
    <div>
      <div class="xs muted">Price Band</div>
      <div style="font-weight:600;font-size:16px">{_esc(price_band)}</div>
    </div>
    <div>
      <div class="xs muted">Lot Size</div>
      <div style="font-weight:600;font-size:16px">{f"{lot_size} Shares" if lot_size else "Not on file"}</div>
    </div>
    <div>
      <div class="xs muted">Bidding Closed</div>
      <div style="font-weight:600;font-size:15px">{_esc(b_end)}</div>
    </div>
    <div>
      <div class="xs muted">Registrar</div>
      <div style="font-weight:600;font-size:15px"><a href="/ipo/registrars/" class="link">See all registrars &rarr;</a></div>
    </div>
  </div>

  <div class="grid g2" style="gap:20px;margin-bottom:28px;">
    <div class="card" style="padding:24px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;">
      <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;">Method 1: Registrar Portal</h2>
      <p style="font-size:14px;line-height:1.6;margin-bottom:14px;">
        BrokerLens does not receive a per-IPO registrar field from NSE's public-issue disclosures, so check your
        application acknowledgment or the RHP cover page for which registrar handled <strong>{company}</strong>,
        then open that registrar's portal below:
      </p>
      <ol style="font-size:14px;line-height:1.7;padding-left:20px;margin-bottom:18px;">
        {"".join(f'<li>{_esc(reg["brand"])}: <a href="{reg["portal_url"]}" target="_blank" rel="noopener nofollow" class="link">{reg["portal_url"]}</a></li>' for reg in registrar_list)}
      </ol>
      <p style="font-size:14px;line-height:1.6;margin-bottom:0;">
        Once on the right portal: select <strong>{company}</strong> from the issue dropdown, choose <strong>PAN</strong>
        as query type, enter your 10-digit PAN number, and submit the captcha to view your allotted share count.
      </p>
    </div>

    <div class="card" style="padding:24px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;">
      <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;">Method 2: BSE India Official Verification</h2>
      <p style="font-size:14px;line-height:1.6;margin-bottom:14px;">
        Verify directly against exchange bidding records on the BSE portal:
      </p>
      <ol style="font-size:14px;line-height:1.7;padding-left:20px;margin-bottom:18px;">
        <li>Visit BSE portal: <a href="https://www.bseindia.com/investors/appli_check.aspx" target="_blank" rel="noopener nofollow" class="link">bseindia.com Application Check</a></li>
        <li>Select Issue Type: <strong>Equity</strong>.</li>
        <li>Select Issue Name: <strong>{company}</strong>.</li>
        <li>Enter Application Number or PAN and complete verification.</li>
      </ol>
      <a href="https://www.bseindia.com/investors/appli_check.aspx" target="_blank" rel="noopener nofollow" class="btn small" style="background:var(--bg);border:1px solid var(--border);">Open BSE Check Portal &rarr;</a>
    </div>
  </div>

  <section class="card" style="padding:24px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;">Bank Mandate Unblocking & Refund Timeline</h2>
    <p style="font-size:14px;line-height:1.6;margin-bottom:12px;">
      Under SEBI T+3 listing norms, if you receive zero shares or partial allotment, your bank automatically unblocks the lien on your UPI funds within 24 to 48 hours following allotment finalization. If your funds remain blocked past the mandate expiry date, contact your bank or the registrar named on your application acknowledgment, quoting your Application Number.
    </p>
  </section>

  <section class="card" style="padding:24px;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:16px;">Frequently Asked Questions</h2>
    {faq_html}
  </section>

  <p class="small muted">
    Also see: <a href="/ipo/{ipo_slug}/">{company} Overview</a> &middot; <a href="/ipo/registrars/">All IPO Registrars</a> &middot; <a href="/ipo/how-to-apply/">How to Apply via ASBA</a>
  </p>
</main>

<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">All IPO data sourced from exchange disclosures. BrokerLens does not provide investment advice.</p>
  <p class="small"><a href="/ipo/">IPO Tracker</a> &middot; <a href="/ipo/allotment-status/">Allotment Status</a> &middot; <a href="/">BrokerLens Home</a></p>
</div></footer>
</body>
</html>"""


def select_target_ipos(ipo_data, limit_recent_ipos):
    """Raw IPO records that get allotment-checker and apply-via pages: every current and
    upcoming issue, then past equity issues until the limit. Shared with ipo_facts, so the
    IPO page links the apply pages only where they exist."""
    current_ipos = ipo_data.get("current", [])
    upcoming_ipos = ipo_data.get("upcoming", [])
    past_ipos = ipo_data.get("past", [])

    seen_syms = set()
    target_ipos = []

    for r in current_ipos + upcoming_ipos:
        sym = (r.get("symbol") or "").strip().upper()
        # A debt series published in the IPO feed (SMCG04) gets no IPO apply pages.
        if sym and sym not in seen_syms and not ipo_facts.is_non_equity_issue(r):
            seen_syms.add(sym)
            target_ipos.append(r)

    for r in past_ipos:
        if len(target_ipos) >= limit_recent_ipos:
            break
        sym = (r.get("symbol") or "").strip().upper()
        sec_type = r.get("security_type")
        if sym and sym not in seen_syms and sec_type in ("EQ", "SME", None):
            seen_syms.add(sym)
            target_ipos.append(r)
    return target_ipos


def build_ipo_apply_suite(limit_recent_ipos: int = 50, site_url: str = "https://www.brokerlens.in"):
    """Compiles allotment status hub, how to apply master guide, broker apply matrix, and registrar hubs."""
    ingest_path = os.path.join(DATA_DIR, "_ingest.json")
    if not os.path.exists(ingest_path):
        print("[ipo_apply_engine] Error: _ingest.json not found")
        return []

    with open(ingest_path, "r", encoding="utf-8") as f:
        ingest = json.load(f)

    nse = ingest.get("nse", {})
    ipo_data = nse.get("ipo", {})

    # Unique valid equity IPOs (shared selection, see select_target_ipos)
    target_ipos = select_target_ipos(ipo_data, limit_recent_ipos)

    generated_urls = []

    # 1. Allotment Status Hub (/ipo/allotment-status/)
    allot_dir = os.path.join(SITE_DIR, "ipo", "allotment-status")
    os.makedirs(allot_dir, exist_ok=True)
    allot_html = render_allotment_status_hub(site_url=site_url)
    with open(os.path.join(allot_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(allot_html)
    generated_urls.append("/ipo/allotment-status/")

    # 2. Master How-to-Apply Guide (/ipo/how-to-apply/)
    apply_hub_dir = os.path.join(SITE_DIR, "ipo", "how-to-apply")
    os.makedirs(apply_hub_dir, exist_ok=True)
    apply_hub_html = render_how_to_apply_master(site_url=site_url)
    with open(os.path.join(apply_hub_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(apply_hub_html)
    generated_urls.append("/ipo/how-to-apply/")

    # 3. Master Registrars Directory (/ipo/registrars/)
    reg_hub_dir = os.path.join(SITE_DIR, "ipo", "registrars")
    os.makedirs(reg_hub_dir, exist_ok=True)
    reg_hub_html = render_registrars_master_hub(site_url=site_url)
    with open(os.path.join(reg_hub_dir, "index.html"), "w", encoding="utf-8") as out:
        out.write(reg_hub_html)
    generated_urls.append("/ipo/registrars/")

    # 4. Individual Registrar Hubs (/ipo/registrar/[slug]/)
    for reg_slug, reg_info in REGISTRARS.items():
        reg_dir = os.path.join(SITE_DIR, "ipo", "registrar", reg_slug)
        os.makedirs(reg_dir, exist_ok=True)
        r_html = render_registrar_hub(reg_slug, reg_info, site_url=site_url)
        with open(os.path.join(reg_dir, "index.html"), "w", encoding="utf-8") as out:
            out.write(r_html)
        generated_urls.append(f"/ipo/registrar/{reg_slug}/")

    # The raw feed rows are looked up in the merged IPO records, so the status (and so the page treatment)
    # is the one every other IPO page uses (a listing date from the past-issues feed wins over a stale
    # current-issues row).
    merged = {}
    try:
        from pipeline.publish import _ipo_merge
        merged = {(x.get("symbol") or "").upper(): x for x in _ipo_merge(ipo_data)}
    except Exception:
        merged = {}
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 5. Dedicated IPO Allotment Checker Pages (/ipo/[slug]/allotment-status/)
    # Every page is written, but the returned list (the sitemap) holds only pages that are worth indexing:
    # the allotment-status page while the IPO is open, upcoming or still inside its listing window, and the
    # apply-via pages only while the IPO is open or upcoming. Listed IPOs and IPOs with no listing on file
    # get noindex,follow pages that are left out of the list.
    for r in target_ipos:
        sym = r.get("symbol")
        if not sym:
            continue
        rec = merged.get(sym.upper()) or r
        ipo_slug = sym.lower()
        ipo_allot_dir = os.path.join(SITE_DIR, "ipo", ipo_slug, "allotment-status")
        os.makedirs(ipo_allot_dir, exist_ok=True)
        ipo_allot_html = render_individual_ipo_allotment_page(rec, site_url=site_url)
        with open(os.path.join(ipo_allot_dir, "index.html"), "w", encoding="utf-8") as out:
            out.write(ipo_allot_html)
        if not ipo_facts.is_settled(rec, today_iso):
            generated_urls.append(f"/ipo/{ipo_slug}/allotment-status/")

    # 6. IPO x Broker matrix (/ipo/[slug]/apply-via-[broker]/)
    for r in target_ipos:
        sym = r.get("symbol")
        if not sym:
            continue
        rec = merged.get(sym.upper()) or r
        ipo_slug = sym.lower()
        indexable = ipo_facts.is_open_for_bids(rec, today_iso)

        for b_id, b_info in BROKERS.items():
            page_dir = os.path.join(SITE_DIR, "ipo", ipo_slug, f"apply-via-{b_id}")
            os.makedirs(page_dir, exist_ok=True)

            page_html = render_ipo_broker_apply_page(rec, b_id, b_info, site_url=site_url)
            with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as out:
                out.write(page_html)

            if indexable:
                generated_urls.append(f"/ipo/{ipo_slug}/apply-via-{b_id}/")

    print(f"[ipo_apply_engine] Successfully generated pages across {len(target_ipos)} IPOs; {len(generated_urls)} indexable URLs returned (listed and no-listing IPOs are noindex and not returned)!")
    return generated_urls


if __name__ == "__main__":
    urls = build_ipo_apply_suite(limit_recent_ipos=50)
    print(f"Generated {len(urls)} pages.")

