"""Honest replacement for the retired /stock/:symbol/share-price-target-:year pages.

Those pages ranked for queries like "<company> share price target 2030" but
published year-by-year projections, which is speculation. This module gives the
stock page itself the answer to that query without any forecast:

  * an H2 "What is a share price target for <Name>?" that explains the term,
    says plainly that BrokerLens publishes no targets, and shows only exchange
    data already on file (last close, range) with its real window length;
  * a static "What-if price calculator" (arithmetic on the visitor's own
    assumption, wired by assets/js/calculators.js, kind 'price-whatif'), with
    one-click picks for the years people search a target for, which set the
    number of years and nothing else;
  * three FAQ entries and the title / meta wording.

Nothing here invents a figure: every number comes from the NSE history passed
in, and anything not on file is simply left out. Formatting helpers are passed
in by publish.py (px, long_date, esc) so this module has no import cycle.
Stdlib only. No em or en dashes anywhere in the copy.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

TITLE_SUFFIX = " | BrokerLens"
_TITLE_MAX = 70   # about what a results page shows; beyond it the brand suffix goes first


def short_company_name(name, symbol=""):
    """Display name without a trailing 'Limited' or 'Ltd', the same rule as
    ipo_facts._short_name (copied, not imported, so this module stays free of
    imports). Falls back to the full name or the symbol when nothing is left."""
    full = (name or symbol or "").strip()
    short = re.sub(r"\s+(limited|ltd\.?)\s*$", "", full, flags=re.I).strip()
    return short or full


def stock_title(name, symbol):
    """'<Name> (<SYM>): Share Price Target 2026-2050, What-If Calculator | BrokerLens' with
    'Limited' or 'Ltd' stripped from the name. "Share price target <years>" matches the query
    this page actually ranks for (the FAQ below answers that exact question honestly, with no
    target asserted) - putting the same phrase in the title too, instead of leaving it only in
    on-page FAQ text, makes that match a title-tag signal Google can act on directly rather
    than something it has to infer or rewrite. The brand suffix is dropped first, then - for a
    long company name - the title is allowed to run past the usual ~70-char display budget
    rather than fall back to a title with no target-year phrase at all: Google still indexes
    and matches on the full title text even where it visually truncates the SERP display.
    Plain text; caller escapes."""
    head = "%s (%s)" % (short_company_name(name, symbol), symbol)
    # Real GSC query data: "2030" dominates (6,345 impr/28d), "2026"/"2027" are next (1,740 /
    # 1,261), but there is a real, non-trivial tail at "2040" (390) and "2050" (174) too -
    # spanning the title to 2050 catches that tail without changing anything about the page's
    # content (it never asserts a number for any year asked about, near or far).
    tail = ": Share Price Target 2026-2050, What-If Calculator"
    for suffix in (TITLE_SUFFIX, ""):
        title = head + tail + suffix
        if len(title) <= _TITLE_MAX:
            return title
    return head + tail


def stock_description(name, symbol, exchange="NSE"):
    """Plain text meta description (caller escapes and caps the length).

    Leads with the "share price target <years>" query match and what the page
    concretely offers, rather than opening (or, as before, closing) on a bare
    negation - the honest "no forecasts" disclosure still runs prominently in
    the page's own H2 body copy, so dropping it from this snippet-only field
    doesn't weaken that compliance posture, it just stops a meta description
    Google may not even render past its own truncation from reading, in
    effect, as a reason not to click."""
    return (
        "%s (%s: %s) share price target 2026-2050: see the real last close and %s trading "
        "range, and run your own what-if price calculator with any growth assumption you choose."
        % (name, exchange, symbol, exchange)
    )


def window_facts(history):
    """Real, labelled high/low window from the daily candles on file.

    Mirrors stock_compare_engine: a range is called 52-week only when at least
    252 sessions are on file (and then only the latest 252 are used); below
    that the true session count is stated. Returns None when there is nothing
    usable, so the caller omits the block rather than guessing."""
    rows = [r for r in (history or []) if isinstance(r, dict) and r.get("date")]
    if not rows:
        return None
    n_all = len(rows)
    window = rows[-252:] if n_all >= 252 else rows
    highs = [r["high"] for r in window if isinstance(r.get("high"), (int, float)) and r["high"] > 0]
    lows = [r["low"] for r in window if isinstance(r.get("low"), (int, float)) and r["low"] > 0]
    last = rows[-1]
    close = last.get("close") if isinstance(last.get("close"), (int, float)) and last["close"] > 0 else None
    if close is None and not (highs and lows):
        return None
    n = len(window)
    return {
        "close": close, "close_date": last["date"],
        "hi": max(highs) if highs else None, "lo": min(lows) if lows else None,
        "n": n, "is_52w": n_all >= 252,
        "first_date": window[0]["date"], "last_date": window[-1]["date"],
    }


# The years people search a target for. Real GSC data for the retired per-year URLs, 28 days
# to 1 Nov 2026: 2030 drew 14,601 impressions, 2026 7,531, 2027 5,780, 2050 4,177, 2040 4,036,
# 2035 3,396 and 2028 2,130. Those URLs now 308 to the stock page, so when Google recrawls them
# this page inherits their rankings; it has to actually name the year that was searched.
# Demand clusters on the next two years and on round milestones.
_MILESTONE_YEARS = (2030, 2035, 2040, 2050)


def target_years(today=None):
    """(this_year, future years offered as one-click picks), from the build date.

    Only years the calculator's 1-to-30 range can reach are offered, so the set
    rolls forward on its own as the daily build's date moves."""
    y0 = (today or datetime.now(timezone.utc)).year
    picks = sorted({y0 + 1, y0 + 2, *_MILESTONE_YEARS})
    return y0, [y for y in picks if y0 < y <= y0 + 30]


def _year_list(years):
    """'2026, 2027 or 2030' from [2026, 2027, 2030]."""
    names = [str(y) for y in years]
    return names[0] if len(names) == 1 else "%s or %s" % (", ".join(names[:-1]), names[-1])


def _tile(label, value_html, sub=""):
    return ('<div class="mega-seg"><div class="mega-seg-label">%s</div>'
            '<div style="margin-top:2px;font-weight:600">%s</div>%s</div>'
            % (label, value_html, ('<div class="xs faint" style="margin-top:2px">%s</div>' % sub) if sub else ""))


def price_target_section_html(name, symbol, history, px, long_date, esc, today=None, exchange="NSE"):
    """The explanatory section plus the what-if calculator, as one HTML block.

    px(n) -> formatted rupee price html; long_date(iso) -> '18 Sep 2026';
    esc(text) -> HTML-escaped text; today defaults to the build date."""
    facts = window_facts(history)
    n_esc = esc(name)
    y0, picks = target_years(today)
    intro = (
        '<div class="section-title"><h2>What is a share price target for %s?</h2></div>'
        '<div style="max-width:78ch">'
        '<p class="small">A share price target is a view on where a share could trade at a future date. It is usually '
        'issued by an analyst or a brokerage, and it rests on assumptions about earnings, growth and market conditions. '
        'It is not a fact, it is not guaranteed, and it is often revised.</p>'
        '<p class="small" style="margin-top:8px">BrokerLens does not publish price targets, forecasts or analyst ratings '
        'for %s or any other company. Any target you read elsewhere, including one you work out yourself below, is an '
        'assumption. Nothing on this page is investment advice.</p></div>' % (n_esc, n_esc)
    )

    data_html = ""
    if facts:
        tiles = []
        if facts["close"] is not None:
            tiles.append(_tile("Last close", px(facts["close"]), "as of %s" % esc(long_date(facts["close_date"]))))
        span = "last 52 weeks" if facts["is_52w"] else "last %d sessions" % facts["n"]
        if facts["hi"] is not None:
            tiles.append(_tile("High, %s" % span, px(facts["hi"])))
        if facts["lo"] is not None:
            tiles.append(_tile("Low, %s" % span, px(facts["lo"])))
        note = "Exchange data from %s daily history, %s to %s (%d trading sessions)." % (
            exchange, esc(long_date(facts["first_date"])), esc(long_date(facts["last_date"])), facts["n"])
        if not facts["is_52w"]:
            note += " BrokerLens holds fewer than 252 sessions for this symbol, so no 52-week figure is shown."
        data_html = (
            '<div class="grid g3" style="margin-top:14px">%s</div>'
            '<p class="xs faint" style="margin-top:8px;max-width:78ch">%s</p>' % ("".join(tiles), note)
        )

    start = ""
    if facts and facts["close"] is not None:
        start = "%.2f" % facts["close"]
    start_note = (
        "Prefilled with the last close on file; change it to any price you like."
        if start else "No recent close is on file for this symbol, so enter a starting price yourself."
    )
    year_note = (
        '<p class="small" style="margin-top:14px;max-width:78ch">Looking for a share price target for %s in %s? '
        'Nobody can know where the share will trade in any of those years, and BrokerLens does not publish a number '
        'for any of them. Pick a year in the calculator below and enter your own yearly growth assumption: it shows '
        'the arithmetic from %s, nothing more.</p>'
        % (n_esc, _year_list([y0] + picks), "the last close on file" if start else "a starting price you enter")
    )
    year_picks = "".join(
        '<button type="button" class="btn btn-outline xs" data-preset-years="%d" data-year="%d" '
        'aria-label="Years until %d" style="padding:2px 8px;font-size:11px">%d</button>' % (y - y0, y, y, y)
        for y in picks
    )
    calc = year_note + (
        '<div class="card" data-calc="price-whatif" style="margin-top:16px;padding:20px;max-width:560px">'
        '<div class="card-title">What-if price calculator</div>'
        '<p class="xs muted" style="margin-top:4px">Work out what a price would become if it grew at a rate you choose. '
        'You supply the growth assumption; BrokerLens does not.</p>'
        '<div class="field" style="margin-top:12px"><label for="pw-price">Starting price per share (Rs)</label>'
        '<input id="pw-price" type="number" inputmode="decimal" min="0.01" step="0.01" value="%s" '
        'placeholder="Enter a price in rupees"></div>'
        '<div class="field"><label for="pw-growth">Assumed growth per year (%%), your own assumption</label>'
        '<input id="pw-growth" type="number" inputmode="decimal" min="-90" max="100" step="0.1" value="" '
        'placeholder="Type your own number, for example 8">'
        '<div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">'
        '<span class="xs muted" style="align-self:center">Example assumptions:</span>'
        '<button type="button" class="btn btn-outline xs" data-preset-growth="10" style="padding:2px 8px;font-size:11px">+10%% CAGR</button>'
        '<button type="button" class="btn btn-outline xs" data-preset-growth="15" style="padding:2px 8px;font-size:11px">+15%% CAGR</button>'
        '<button type="button" class="btn btn-outline xs" data-preset-growth="20" style="padding:2px 8px;font-size:11px">+20%% CAGR</button>'
        '</div></div>'
        '<div class="field"><label for="pw-years">Years (1 to 30)</label>'
        '<input id="pw-years" type="number" inputmode="numeric" min="1" max="30" step="1" value="5">'
        '<div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">'
        '<span class="xs muted" style="align-self:center">Or pick a year:</span>%s</div></div>'
        '<p class="xs faint" style="margin-top:6px">%s The growth box is left empty on purpose: the number in the placeholder '
        'is only an example of the format, not an estimate for %s.</p>'
        '<button type="button" id="calc-btn" class="btn" style="margin-top:8px">Calculate</button>'
        '<div id="calc-result" class="stack" style="margin-top:16px" aria-live="polite" hidden></div>'
        '<p class="xs faint" style="margin-top:12px">This is arithmetic on your assumption, not a forecast or a '
        'recommendation.</p>'
        '<div class="xs faint" style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border)">'
        'Related tools: <a href="/calculators/cagr-calculator/">CAGR Calculator</a> &middot; '
        '<a href="/calculators/sip-calculator/">SIP Calculator</a> &middot; '
        '<a href="/calculators/capital-gains-tax-calculator/">Capital Gains Tax</a> &middot; '
        '<a href="/trade-costs/">Trade Cost Calculator</a></div>'
        '</div>' % (start, year_picks, esc(start_note), n_esc)
    )
    return intro + data_html + calc


def stock_target_faqs(name, symbol, facts_line="", exchange="NSE"):
    """Three (question, answer) pairs. The first keeps the wording the page has
    always used for this query (a QA check pins it); facts_line is the
    existing 'what the data shows' sentence, appended only when there is data."""
    first = (
        "BrokerLens does not publish price targets or forecasts, and nothing here is investment advice. A target is an "
        "assumption about the future, usually issued by a SEBI-registered research analyst or brokerage, and it can be "
        "wrong or revised. To test an assumption of your own, use the what-if price calculator on this page: you enter "
        "the starting price, a yearly growth rate and the number of years." + ((" " + facts_line) if facts_line else "")
    )
    return [
        ("What is the share price target of %s for 2026, 2030, 2040 or 2050?" % name, first),
        ("How does the what-if price calculator for %s work?" % name,
         "It multiplies the starting price by (1 + growth rate) once for each year. For example, a starting price of 100 "
         "and a growth rate of 10 percent a year gives 110 after one year and 121 after two. The growth rate is yours to "
         "choose and the box is empty on purpose. The result is arithmetic on that assumption, not a forecast or a "
         "recommendation, and it ignores dividends, taxes, charges and the chance of a fall."),
        ("Where can I find analyst price targets for %s?" % name,
         "Price targets are published by the research analysts and brokerages that issue them, in their own reports. "
         "Check that the analyst is registered with SEBI, read the assumptions behind the number, and compare it with "
         "the company's own disclosures on the %s. BrokerLens does not collect or rate targets."
         % ("BSE website" if exchange == "BSE" else "NSE and BSE websites")),
    ]
