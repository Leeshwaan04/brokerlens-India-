"""The site header's navigation, defined once.

Both page shells in publish.py (the SPA shell _APP_SHELL_HEAD and the static
page head _REGISTRY_PAGE_HEAD) used to carry their own hand-copied nav, and
the two drifted. They now both take their nav from here.

Structure (decided 27 Nov 2026): a visitor arrives to do one of a few things, so
the header is organised by task, not by what was built first:

    Brokers v   choose, compare and check a broker
    Markets v   stocks, movers, IPOs, funds, crypto, holidays
    IPO         (direct: the highest-intent item)
    Tools v     calculators and comparisons
    Learn v     news, reports, and how BrokerLens works
    [Practise free]   the paper-trading app, as the one clear action

Rules this file keeps:
  * every link a visitor could reach from the old header is still linked from
    every page (site-wide internal linking must not shrink): panels are in the
    HTML, only hidden until opened;
  * no link points at a page that does not exist (tests/qa_e2e.py checks each
    one against the built site);
  * a "Live" or "Coming soon" badge is only for markets, never decoration.
"""

from __future__ import annotations

import re
from html import escape

PAPER_URL = "https://paper.brokerlens.in/?utm_source=brokerlens&utm_medium=nav&utm_campaign=header"

# Routes the single-page shell navigates client-side (data-link). Anything else
# is a normal page load, which is always safe.
_SPA_ROUTES = {
    "/compare/", "/leaderboards/", "/registry/", "/algo/", "/news/", "/brokers/",
    "/coming-soon/us", "/coming-soon/gcc",
}

# (key, button label, panel id, columns); a column is (heading, badge, [(label, href, note)]).
GROUPS = [
    ("brokers", "Brokers", "mega-brokers", [
        ("Choose", None, [
            ("Find my broker", "/find-broker/", "Answer a few questions, see your matches"),
            ("Compare brokers", "/compare/", "Fees and features side by side"),
            ("All brokers", "/brokers/", "Every broker we track in depth"),
        ]),
        ("Check", None, [
            ("SEBI registry", "/registry/", "Is this broker registered?"),
            ("Brokers by segment", "/brokers-by/segment/", "Equity, F&O, currency, commodity"),
            ("Algo trading platforms", "/algo/", "Platforms and API access"),
        ]),
        ("Costs", None, [
            ("Brokerage and trade costs", "/trade-costs/", "What a trade really costs"),
        ]),
    ]),
    ("markets", "Markets", "mega-markets", [
        ("India", "Live", [
            ("Stocks A to Z", "/stocks/", "Every NSE-listed stock"),
            ("Market movers", "/leaderboards/", "Gainers, losers, broker stats"),
            ("IPO tracker", "/ipo/", "Open, upcoming and listed"),
            ("ETFs", "/etfs/", "NSE-listed ETFs"),
            ("Mutual funds", "/funds-by/", "Browse by fund house"),
            ("Market holidays", "/stock-market-holidays/", "Trading days and closures"),
        ]),
        ("Crypto", "Live", [
            ("Crypto prices", "/crypto/", "Coins and market data"),
        ]),
        ("More markets", None, [
            ("US", "/coming-soon/us", "Coming soon"),
            ("GCC", "/coming-soon/gcc", "Coming soon"),
        ]),
    ]),
    ("tools", "Tools", "mega-tools", [
        ("Calculators", None, [
            ("Brokerage and trade costs", "/trade-costs/", "Per-trade and yearly cost"),
            ("Financial calculators", "/calculators/", "SIP, PPF, EMI, tax and more"),
        ]),
        ("Compare", None, [
            ("Compare stocks", "/compare/stocks/", "Head-to-head, side by side"),
            ("Compare brokers", "/compare/", "Fees and features"),
        ]),
    ]),
    ("learn", "Learn", "mega-learn", [
        ("Read", None, [
            ("News and blogs", "/news/", "Market news and research notes"),
            ("State of Indian broking 2026", "/reports/state-of-indian-broking-2026/", "Our annual report"),
        ]),
        ("How BrokerLens works", None, [
            ("Methodology", "/methodology/", "How we rate and rank"),
            ("Editorial policy", "/editorial-policy/", "What we publish and why"),
            ("Data sources", "/sources/", "Where every number comes from"),
            ("About", "/about/", "Who we are"),
        ]),
    ]),
]

# Shown in the nav bar itself (not in a panel): the direct IPO link.
DIRECT_LINKS = [("IPO", "/ipo/")]


def all_internal_hrefs() -> list[str]:
    """Every internal path the nav links to, for tests and link audits."""
    out = [h for _, _, _, cols in GROUPS for _, _, items in cols for _, h, _ in items]
    out += [h for _, h in DIRECT_LINKS]
    return sorted({h for h in out if h.startswith("/")})


def _a(label: str, href: str, spa: bool, extra: str = "", nav_key: str = "") -> str:
    data_link = " data-link" if spa and href in _SPA_ROUTES else ""
    nav = f' data-nav="{escape(nav_key, quote=True)}"' if nav_key else ""
    return f'<a href="{escape(href, quote=True)}"{data_link}{nav}{extra}>{label}</a>'


def render_nav(spa: bool) -> str:
    """The <nav> element: group buttons, the direct IPO link, and the Practise button."""
    parts = []
    for key, label, panel_id, _cols in GROUPS:
        parts.append(
            f'<button class="mega-toggle" id="{key}-toggle" aria-expanded="false" '
            f'aria-controls="{panel_id}">{escape(label)} <span aria-hidden="true">&#9662;</span></button>'
        )
        if key == "markets":
            for dl_label, dl_href in DIRECT_LINKS:
                parts.append(_a(escape(dl_label), dl_href, spa, nav_key=f"direct/{dl_href.strip('/')}"))
    parts.append(
        f'<a href="{PAPER_URL}" class="nav-paper-cta" target="_blank" rel="noopener" data-nav="cta/practise">Practise free</a>'
    )
    return '<nav class="nav-links" id="navlinks" aria-label="Main">\n    ' + "\n    ".join(parts) + "\n  </nav>"


def render_timings_button() -> str:
    """A clock button for the session-timings panel, kept with the search and theme buttons."""
    return (
        '<button class="icon-btn" id="timings-toggle" title="Market timings" aria-label="Market timings" '
        'aria-expanded="false" aria-controls="mega-timings">'
        '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
        '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.6"/>'
        '<path d="M8 4.5V8l2.5 1.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>'
    )


def render_panels(spa: bool) -> str:
    """The dropdown panels. The timings panel is filled in by nav-widgets.js."""
    out = [
        '<div class="mega" id="mega-timings" hidden>\n  <div class="wrap">\n'
        '    <div id="mega-timings-body" class="mega-grid"><div class="small faint" style="padding:16px 0">Loading timings&hellip;</div></div>\n'
        "  </div>\n</div>"
    ]
    for key, _label, panel_id, cols in GROUPS:
        col_html = []
        for heading, badge, items in cols:
            badge_html = ""
            if badge:
                tone = "badge-up" if badge == "Live" else "badge-warn"
                badge_html = f' <span class="badge {tone}">{escape(badge)}</span>'
            lis = []
            for label, href, note in items:
                coming = note == "Coming soon"
                note_html = f'<span class="mega-note">{escape(note)}</span>' if note and not coming else ""
                badge2 = ' <span class="badge badge-warn">Coming soon</span>' if coming else ""
                lis.append(
                    "<li>" + _a(f"<span>{escape(label)}</span>{badge2}{note_html}", href, spa,
                               nav_key=f"{key}/{href.strip('/')}") + "</li>"
                )
            col_html.append(
                f'<div class="mega-col mega-links"><h4><span>{escape(heading)}</span>{badge_html}</h4>'
                f'<ul>{"".join(lis)}</ul></div>'
            )
        out.append(
            f'<div class="mega" id="{panel_id}" hidden>\n  <div class="wrap">\n'
            f'    <div class="mega-grid">{"".join(col_html)}</div>\n  </div>\n</div>'
        )
    return "\n".join(out)


def render_flat_nav() -> str:
    """The same six items as plain links (each group's main page), for pages that
    do not load the menu script (the programmatic trade-cost pages). Same labels,
    same destinations, no dropdowns."""
    hubs = [("Brokers", "/brokers/"), ("Compare", "/compare/"), ("Markets", "/stocks/"),
            ("IPO", "/ipo/"), ("Tools", "/calculators/"), ("Learn", "/news/")]
    links = "\n    ".join(f'<a href="{h}">{escape(t)}</a>' for t, h in hubs)
    return (
        '<nav class="nav-links" id="navlinks" aria-label="Main">\n    ' + links + "\n    "
        f'<a href="{PAPER_URL}" class="nav-paper-cta" target="_blank" rel="noopener" data-nav="cta/practise">Practise free</a>\n  </nav>'
    )


# ---------------------------------------------------------------- upgrading committed pages
# Pages that are committed rather than rebuilt (the hand-kept site/index.html,
# older news articles) carry a copy of the header. Every build re-renders it
# from this module, keyed on the page's structure rather than on what it held
# before, so a later change to the nav (a label, the button, an ARIA fix)
# reaches those pages too instead of freezing them at their first upgrade.
# The three parts (nav, timings button, panels) are replaced together, only
# when all are found, so a page is never left half-updated; re-running changes
# nothing. Pages without the timings panel (the plain-link variant, pages with
# their own minimal header) are left alone.
_NAV_RE = re.compile(r'<nav class="nav-links" id="navlinks"[^>]*>.*?</nav>', re.S)
_TIMINGS_BTN_RE = re.compile(r'<button class="icon-btn" id="timings-toggle".*?</button>', re.S)
_SEARCH_RE = re.compile(r'<button class="icon-btn" id="search-toggle"')
_PANELS_RE = re.compile(r'<div class="mega" id="mega-timings" hidden>.*?(?=</header>)', re.S)
_HEADER_RE = re.compile(r'<nav class="nav-links" id="navlinks".*?</header>', re.S)


def has_current_or_old_full_header(html: str) -> bool:
    return bool(_NAV_RE.search(html)) and 'id="mega-timings"' in html


def still_on_old_header(html: str) -> bool:
    """True for a page with the previous (pre-27 Nov 2026) header, for logging."""
    return 'aria-controls="mega-markets">Brokers' in html and 'id="brokers-toggle"' not in html


def upgrade_header_html(html: str) -> str:
    if not has_current_or_old_full_header(html):
        return html
    region = _HEADER_RE.search(html)
    # The SPA shell routes some links client-side (data-link); keep that for pages that had it.
    spa = bool(region and " data-link" in region.group(0))
    out = _TIMINGS_BTN_RE.sub("", html, count=1)
    out, a = _NAV_RE.subn(lambda m: render_nav(spa), out, count=1)
    out, b = _SEARCH_RE.subn(lambda m: render_timings_button() + m.group(0), out, count=1)
    out, c = _PANELS_RE.subn(lambda m: render_panels(spa) + "\n", out, count=1)
    return out if (a, b, c) == (1, 1, 1) else html
