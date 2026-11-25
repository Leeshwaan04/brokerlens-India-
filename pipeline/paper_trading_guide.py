"""/paper-trading-apps-india/: a dated guide to paper trading apps in India.

Hand-written, but nothing in it is guessed. Every platform row says only what
that platform's own website, help page or app store listing said about itself
when checked on LAST_CHECKED, phrased as the platform's claim ("its homepage
says"), and links to that page. Claims that only third parties made (reviews,
affiliate lists) are left out. Every rule is dated and linked to SEBI or to
reporting of SEBI's circulars, and the page says it is not legal advice.

Change LAST_CHECKED only after re-checking every row and every source: the
visible date and the structured data's dateModified both come from it.
No em or en dashes anywhere in the copy. Stdlib only.
"""
from __future__ import annotations

import json
import os
from datetime import date

URL_PATH = "/paper-trading-apps-india/"
LAST_CHECKED = date(2026, 11, 25)
FIRST_PUBLISHED = date(2026, 11, 25)

SOURCES = {
    "zerodha": ("Zerodha support: does Zerodha offer demo accounts for paper trading?",
                "https://support.zerodha.com/category/trading-and-markets/trading-faqs/general/articles/"
                "does-zerodha-offer-demo-accounts-for-paper-trading"),
    "dhan": ("Dhan support: DhanHQ sandbox, paper trading with virtual money and live market data",
             "https://dhan.co/support/platforms/dhanhq-api/"
             "can-i-use-dhanhq-sandbox-for-paper-trading-with-virtual-money-and-live-market-data/"),
    "tradingview": ("TradingView help centre: non-tradable symbol notification",
                    "https://www.tradingview.com/support/solutions/43000719856-what-is-a-non-tradable-symbol-notification/"),
    "neostox": ("Neostox homepage", "https://neostox.com/"),
    "sensibull": ("Sensibull help: how can I practice trading without losing money on Sensibull?",
                  "https://sensibull.freshdesk.com/support/solutions/articles/"
                  "43000719118-how-can-i-practice-trading-without-losing-money-on-sensibull-"),
    "niftypapertrade": ("Nifty Paper Trade website", "https://niftypapertrade.in/"),
    "niftypapertrade_mcx": ("Nifty Paper Trade: commodity paper trading",
                            "https://niftypapertrade.in/commodity-paper-trading-india"),
    "frontpage": ("FrontPage on the App Store (India)", "https://apps.apple.com/in/app/frontpage/id1401247335"),
    "algotest": ("AlgoTest documentation: pricing breakdown", "https://docs.algotest.in/getting-started/pricing-breakdown"),
    "sebi_may2024": ("SEBI circular, 24 May 2024: norms for sharing of real time price data to third parties",
                     "https://www.sebi.gov.in/legal/circulars/may-2024/"
                     "norms-for-sharing-of-real-time-price-data-to-third-parties_83572.html"),
    "sebi_nov2024": ("Business Standard, 4 November 2024: SEBI warns investors against unauthorised virtual trading "
                     "platforms (SEBI press release PR No. 27/2024)",
                     "https://business-standard.com/markets/stock-market-news/"
                     "sebi-warns-investors-against-using-unauthorised-virtual-trading-platforms-124110400804_1.html"),
    "sebi_jan2025": ("Business Standard, 30 January 2025: SEBI circular on live stock data and market education",
                     "https://www.business-standard.com/markets/news/"
                     "sebi-finfluencer-circular-live-stock-data-market-education-rules-125013000571_1.html"),
    "sebi_may2026": ("Taxmann: SEBI revises time lag norms for stock price data sharing",
                     "https://www.taxmann.com/post/blog/sebi-revises-time-lag-norms-for-stock-price-data-sharing"),
    "sebi_may2026_b": ("LiveLaw: SEBI revises norms for sharing and usage of market price data for educational purposes",
                       "https://www.livelawbiz.com/securities-law/sebi/"
                       "securities-and-exchange-board-of-india-revises-norms-sharing-and-usage-market-price-data-"
                       "educational-purposes-533509"),
    "sebi_fo_study": ("SEBI press release, 23 September 2024: updated study on individual traders in equity F&O",
                      "https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/"
                      "updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-"
                      "fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html"),
}

# Each row: what the platform says about itself, and the page it said it on.
PLATFORMS = [
    {"name": "Zerodha (Kite demo)", "prices": "Dummy data",
     "segments": "The Kite screens only; not a trading simulator", "cost": "Free",
     "notes": "Zerodha's support pages say it does not offer a demo account for paper trading. Its Kite demo uses "
              "dummy data so you can explore the layout.",
     "sources": ["zerodha"]},
    {"name": "Dhan", "prices": "Not offered", "segments": "None", "cost": "Not applicable",
     "notes": "Dhan's API help pages say paper trading with virtual funds and live market data is not permitted under "
              "the applicable regulatory framework, and that its API sandbox is not a paper trading environment.",
     "sources": ["dhan"]},
    {"name": "TradingView", "prices": "Not available for Indian exchange symbols",
     "segments": "None for symbols listed on Indian exchanges", "cost": "Not applicable for Indian symbols",
     "notes": "TradingView's help centre says symbols listed on Indian exchanges are not supported in its Paper "
              "Trading, because simulated trading on them contradicts NSE's data sharing and usage policy.",
     "sources": ["tradingview"]},
    {"name": "Neostox", "prices": "Delayed by 30 days, its homepage says",
     "segments": "Stocks, futures and options", "cost": "Free 3-day trial, then paid plans",
     "notes": "Its homepage says new users start with ₹5 lakh of virtual money.",
     "sources": ["neostox"]},
    {"name": "Sensibull", "prices": "Not stated in its help article",
     "segments": "Futures and options on NSE F&O instruments", "cost": "See Sensibull's own plans",
     "notes": "Its help article says you can practise futures and options with its Virtual Portfolios feature.",
     "sources": ["sensibull"]},
    {"name": "Nifty Paper Trade", "prices": "Live exchange feeds, its website says",
     "segments": "Index and stock options; MCX gold, silver and crude",
     "cost": "Free view-only account; virtual cash on paid plans at ₹299 a month, ₹1,999 a year or ₹2,999 once",
     "notes": "Its website lists ₹10 lakh, ₹25 lakh and ₹50 lakh of virtual cash on those three plans.",
     "sources": ["niftypapertrade", "niftypapertrade_mcx"]},
    {"name": "FrontPage", "prices": "Not stated in its App Store listing",
     "segments": "Equities, F&O and MCX commodities",
     "cost": "Free; Premium at ₹149 a month or ₹999 a year on its India App Store page",
     "notes": "Its App Store listing describes a free virtual portfolio with paid Premium features.",
     "sources": ["frontpage"]},
    {"name": "AlgoTest", "prices": "Slightly delayed live market data, its documentation says",
     "segments": "Options strategies (forward testing)",
     "cost": "Credits bought upfront and spent on backtests and paper trades",
     "notes": "Its documentation says forward testing needs no broker account.",
     "sources": ["algotest"]},
]

# (date, what happened, source keys). Plain summaries, not legal text.
RULES = [
    ("24 May 2024",
     "SEBI barred exchanges, other market infrastructure institutions and registered intermediaries from sharing "
     "real-time price data with third parties, except where needed for the functioning of the market or to meet "
     "regulatory requirements. Price data could be shared "
     "for investor education with a one-day lag, provided participants were offered no monetary incentive.",
     ["sebi_may2024"]),
    ("4 November 2024",
     "SEBI cautioned the public against platforms offering virtual trading, paper trading or fantasy games based on "
     "real-time share price data. It said such platforms violate the Securities Contracts (Regulation) Act, 1956 and "
     "the SEBI Act, 1992, and that users are not protected by SEBI's grievance systems such as SCORES.",
     ["sebi_nov2024"]),
    ("29 January 2025",
     "Entities solely engaged in education could use price data only with a three-month lag.",
     ["sebi_jan2025"]),
    ("8 May 2026 (in force from 1 July 2026)",
     "SEBI replaced the one-day and three-month lags with a single 30-day lag for price data shared or used for "
     "education and investor awareness, still with no monetary incentive for participants.",
     ["sebi_may2026", "sebi_may2026_b"]),
]

FAQS = [
    ("Is paper trading allowed in India?",
     "SEBI's concern is platforms built on real-time share prices: its 4 November 2024 caution said platforms offering "
     "virtual trading, paper trading or fantasy games on real-time share price data violate the Securities Contracts "
     "(Regulation) Act, 1956 and the SEBI Act, 1992. Since 1 July 2026, price data shared or used for education must "
     "lag by at least 30 days. Check each app's own terms; this is not legal advice."),
    ("Do Indian brokers offer paper trading on live prices?",
     "Two large brokers say they do not. Zerodha's support pages say it does not offer a demo account for paper "
     "trading, and its Kite demo uses dummy "
     "data. Dhan's API help pages say paper trading with virtual funds and live market data is not permitted under "
     "the applicable regulatory framework."),
    ("Why are prices on some paper trading apps 30 days old?",
     "SEBI's circular of 8 May 2026, in force from 1 July 2026, set a single 30-day lag for price data shared or used "
     "for education and investor awareness, replacing the earlier one-day and three-month lags. Neostox, for "
     "example, says on its homepage that its prices are delayed by 30 days."),
    ("Can I paper trade F&O and commodities?",
     "Yes. Neostox, Sensibull, AlgoTest and Nifty Paper Trade list futures or options, and FrontPage and Nifty Paper "
     "Trade mention MCX commodities. SEBI's price data rules cover equity, derivatives and commodity exchanges alike."),
]

TITLE = "Paper Trading Apps in India 2026: Prices, Costs and SEBI Rules"


def _long(d):
    return "%d %s %d" % (d.day, d.strftime("%B"), d.year)


def _src_links(keys, esc):
    return " ".join('<a href="%s" rel="noopener nofollow" target="_blank">[%d]</a>'
                    % (esc(SOURCES[k][1]), list(SOURCES).index(k) + 1) for k in keys)


def render(esc, head, foot, breadcrumb, site_url):
    canonical = site_url + URL_PATH
    checked = _long(LAST_CHECKED)
    desc = ("Which paper trading apps in India use live, delayed or dummy prices, what they cost, and SEBI's "
            "30-day price data rule for stocks, F&O and commodities.")

    crumb_html, crumb_jsonld = breadcrumb([("BrokerLens", "/"), ("Paper trading apps in India", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Article", "headline": TITLE, "description": desc, "url": canonical,
         "mainEntityOfPage": canonical, "inLanguage": "en-IN",
         "datePublished": FIRST_PUBLISHED.isoformat(), "dateModified": LAST_CHECKED.isoformat(),
         "author": {"@type": "Organization", "name": "BrokerLens", "url": site_url},
         "publisher": {"@type": "Organization", "name": "BrokerLens",
                       "logo": {"@type": "ImageObject", "url": site_url + "/apple-touch-icon.png"}}},
        crumb_jsonld,
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQS]},
    ]}

    key_points = [
        "Several large platforms do not offer paper trading on live Indian prices: Zerodha's demo uses dummy data, "
        "Dhan says paper trading with live data is not permitted, and TradingView does not support Indian exchange "
        "symbols in its Paper Trading.",
        "Since 1 July 2026, SEBI requires price data shared or used for education to be at least 30 days old. "
        "Neostox says its prices are delayed by 30 days.",
        "Some apps say they use live prices. Whatever you pick, check where its prices come from, how old they are "
        "and what it charges.",
        "Practice that ignores brokerage and statutory charges overstates what you would really make.",
    ]

    rows = []
    for p in PLATFORMS:
        rows.append("<tr><td><strong>%s</strong></td><td>%s</td><td>%s</td><td>%s</td><td>%s %s</td></tr>" % (
            esc(p["name"]), esc(p["prices"]), esc(p["segments"]), esc(p["cost"]), esc(p["notes"]),
            _src_links(p["sources"], esc)))

    rules_html = "".join(
        '<li style="margin-bottom:10px"><strong>%s.</strong> %s %s</li>' % (esc(when), esc(what), _src_links(keys, esc))
        for when, what, keys in RULES)

    segments_html = (
        '<h3 style="font-size:17px;margin:18px 0 6px 0">Stocks (cash market)</h3>'
        '<p style="max-width:75ch">If you want to learn a broker&#39;s order screens, a broker demo such as Zerodha&#39;s '
        'Kite demo (dummy data) shows the layout. To practise building a portfolio of shares, a simulator with delayed '
        'prices works: decisions to buy and hold for months do not depend on minute by minute moves. Before you invest '
        'real money, price what your trades will actually cost: brokerage, STT, exchange charges, stamp duty, GST and '
        'DP charges on sells. The <a href="/trade-costs/">trade cost calculator</a> and the '
        '<a href="/calculator/">brokerage calculator</a> do this for each broker.</p>'
        '<h3 style="font-size:17px;margin:18px 0 6px 0">Futures and options (F&amp;O)</h3>'
        '<p style="max-width:75ch">Many of the tools above focus on F&amp;O: Neostox, Sensibull&#39;s Virtual '
        'Portfolios, AlgoTest and Nifty Paper Trade all list futures or options. Practising on delayed data teaches '
        'lot sizes, margins, expiry and order types, but it cannot show how fast option prices move in a live session. '
        'SEBI&#39;s study published on 23 September 2024 found that about 93%% of individual equity F&amp;O traders '
        'lost money between FY22 and FY24 %s. Practise long enough to live through losing stretches, not only '
        'winning ones.</p>'
        '<h3 style="font-size:17px;margin:18px 0 6px 0">Commodities (MCX)</h3>'
        '<p style="max-width:75ch">Commodity exchanges are SEBI-regulated too, so the same price data rules apply. '
        'Fewer apps cover commodities: FrontPage&#39;s App Store listing and Nifty Paper Trade&#39;s website mention '
        'MCX contracts. Commodity contracts have their own lot sizes, margins, trading hours and expiry dates, so check '
        'that a practice app models them before relying on its results.</p>'
    ) % _src_links(["sebi_fo_study"], esc)

    checklist = [
        "Where the prices come from and how old they are. If an app does not say, ask before you rely on it.",
        "Prizes or paid contests: SEBI's rules allow price data for education only without monetary incentives "
        "for participants.",
        "Who runs the app, before you share a broker login or your trading data. SEBI's November 2024 caution said "
        "users who share confidential trading data with unauthorised platforms are not protected by its grievance "
        "systems such as SCORES.",
        "Whether practice trades are charged realistic brokerage and statutory charges.",
        "A starting balance close to what you would actually invest, so the habits you build carry over.",
    ]

    faq_html = "".join('<h3 style="font-size:16px;margin:18px 0 4px 0">%s</h3><p class="small" style="margin:0;'
                       'max-width:75ch">%s</p>' % (esc(q), esc(a)) for q, a in FAQS)
    sources_html = "".join('<li><a href="%s" rel="noopener nofollow" target="_blank">%s</a></li>' % (esc(url), esc(label))
                           for label, url in SOURCES.values())

    body = (
        head % {"title": esc(TITLE), "description": esc(desc), "canonical": esc(canonical),
                "jsonld": json.dumps(jsonld, ensure_ascii=False)}
        + crumb_html
        + '<h1 style="margin-top:0">Paper trading apps in India (2026)</h1>'
        + '<p class="xs muted" style="margin:0 0 12px 0">Last checked: %s</p>' % esc(checked)
        + '<p style="max-width:75ch">Paper trading, also called virtual or demo trading, lets you place practice '
          'orders with virtual money. In India the real choice is about prices: some apps use dummy data, some use '
          'prices delayed by 30 days, and some say they use live prices. This guide sets out what each well-known '
          'platform says about itself and the SEBI rules they all work under.</p>'
        + '<div class="card" style="margin:16px 0;padding:16px 18px;border-left:3px solid var(--accent)">'
          '<div style="font-weight:700;margin-bottom:6px">Key points</div><ul class="small" style="padding-left:18px;'
          'margin:0">%s</ul></div>' % "".join("<li>%s</li>" % esc(k) for k in key_points)
        + '<h2 style="margin-top:28px">The rules: SEBI and exchange price data</h2>'
        + '<ul class="small" style="padding-left:18px;max-width:75ch">%s</ul>' % rules_html
        + '<p class="small" style="max-width:75ch">These rules are about price data from SEBI-regulated exchanges, which '
          'include equity, derivatives and commodity exchanges, so they apply to practice apps for stocks, F&amp;O and '
          'commodities alike. This is a plain summary, not legal advice: read SEBI&#39;s circulars and each app&#39;s own '
          'terms.</p>'
        + '<h2 style="margin-top:28px">What each platform offers</h2>'
        + '<p class="small muted" style="max-width:75ch">As each platform described itself on %s. Figures and features '
          'change, so confirm on the platform&#39;s own site. Numbers in brackets link to the source.</p>' % esc(checked)
        + '<div class="table-scroll"><table class="data"><thead><tr><th>Platform</th><th>Prices you trade on</th>'
          '<th>Segments</th><th>Cost</th><th>Notes</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(rows)
        + '<h2 style="margin-top:28px">How to choose, by segment</h2>' + segments_html
        + '<h2 style="margin-top:28px">What to check before you sign up</h2>'
        + '<ul class="small" style="padding-left:18px;max-width:75ch">%s</ul>' % "".join(
            "<li>%s</li>" % esc(c) for c in checklist)
        + '<p class="small" style="max-width:75ch">When you are ready to open a real account, the '
          '<a href="/brokers/">broker comparison</a> sets out each broker&#39;s published charges side by side.</p>'
        + '<h2 style="margin-top:28px">Questions</h2>' + faq_html
        + '<h2 style="margin-top:28px">Sources</h2>'
        + '<ol class="small" style="padding-left:18px;max-width:75ch">%s</ol>' % sources_html
        + '<p class="xs faint" style="margin-top:20px;max-width:75ch">BrokerLens does not rank or recommend any of these '
          'apps. Details are as each platform described itself on %s and may have changed since. Nothing here is '
          'investment or legal advice.</p>' % esc(checked)
    )
    body += foot % {"source_note": "Platform details are from each platform's own website, help pages or app store "
                                   "listing, checked on %s. SEBI dates are from SEBI's circulars and press releases "
                                   "and reporting of them." % checked}
    return body


def write(site_dir, esc, head, foot, breadcrumb, write_text, site_url):
    """Write the page. Returns True when written."""
    body = render(esc, head, foot, breadcrumb, site_url)
    out = os.path.join(site_dir, URL_PATH.strip("/"))
    os.makedirs(out, exist_ok=True)
    write_text(os.path.join(out, "index.html"), body)
    return True
