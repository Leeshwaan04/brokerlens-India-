"""Stock pages for companies listed on BSE but not on NSE.

Every /stock/ page used to come from NSE's listed-securities file, so about
1,400 main-board companies that trade only on BSE (National Securities
Depository, SpiceJet, CIAN Agro and the like) had no page at all, although
"<company> share price target" searches for small companies are what this
site ranks for. This module gives the liquid ones the same page an NSE stock
gets, built only from BSE's own published data: its scrip list (name, code,
group, face value, ISIN, market capitalisation) and its daily bhavcopy
(prices). See pipeline/sources/bse.py's bse_only_history().

Which companies get a page is kept in data/manual/bse_only_equities.json,
which only grows. A company joins once it passes the liquidity rule in
sources/bse.py; it keeps its page (and its URL) after that even on a day BSE's
files cannot be reached, which is what the IPO archive had to be added for
after NSE's feed shrank and 399 pages became 404s. A company that later lists
on NSE leaves this list, because its NSE page takes over.
"""
from __future__ import annotations

import datetime
import json
import os

from .common import ROOT, SITE_DATA, log, now_iso, read_json, trim_to_last_break, write_json
from .sources.bse import LIQUID_MIN_AVG_VALUE_INR, LIQUID_MIN_SESSION_SHARE, isin_issuer_key

ARCHIVE_PATH = os.path.join(ROOT, "data", "manual", "bse_only_equities.json")
HUB_PATH = "/stocks/bse/"
_STABLE_FIELDS = ("symbol", "name", "isin", "group", "face_value", "bse_url")

# What each group means, in BSE's own classification. Shown on every page,
# because for a BSE-only company the group is the most practical fact a
# buyer needs (trade-for-trade settlement rules out intraday trading).
GROUP_NOTES = {
    "A": "Group A holds BSE's most actively traded companies, chosen on trading activity and other "
         "quantitative and qualitative measures.",
    "B": "Group B holds listed equities that BSE has not placed in group A, T or Z.",
    "T": "Group T is BSE's trade-for-trade segment: every trade must be settled by delivery of the shares, "
         "so a buy and a sell on the same day are not netted off and intraday trading is not possible.",
    "X": "Group X holds companies whose shares are listed only on BSE.",
    "XT": "Group XT holds companies listed only on BSE that trade on a trade-for-trade basis: every trade must "
          "be settled by delivery of the shares, so intraday trading is not possible.",
    "Z": "Group Z holds companies that BSE has found not to comply with its listing requirements. Check the "
         "company's filings on BSE before trading.",
}


def _rule_text():
    return ("traded on at least %d%% of the sessions on file, with an average daily traded value of at least "
            "Rs %d lakh" % (round(LIQUID_MIN_SESSION_SHARE * 100), LIQUID_MIN_AVG_VALUE_INR // 100000))


def load_universe(bse_only, nse_companies, slug_fn, today=None):
    """Merge today's BSE-only data into the committed list and return it.

    bse_only is ingest["bse"]["bse_only"] (may be None); nse_companies is NSE's
    listed-company list. Returns (scrips, fresh): scrips is the list of
    companies to build pages for, each {code, slug, added, *_STABLE_FIELDS};
    fresh maps scrip code to today's ingest record (candles, market cap)."""
    today = today or datetime.date.today().isoformat()
    archive = read_json(ARCHIVE_PATH, {}) or {}
    scrips = {k: dict(v) for k, v in (archive.get("scrips") or {}).items()}
    fresh = ((bse_only or {}).get("scrips")) or {}
    nse_slugs = {slug_fn(c.get("symbol")) for c in (nse_companies or [])} - {""}
    nse_keys = {isin_issuer_key(c.get("isin")) for c in (nse_companies or [])} - {None}
    changed = False

    # A company that has since listed on NSE now has an NSE page; the BSE one retires.
    # Only judged against a full NSE list, never a partial one.
    if len(nse_keys) >= 1500:
        for code in sorted(c for c, s in scrips.items() if isin_issuer_key(s.get("isin")) in nse_keys):
            log("bse-only: %s (%s) is now listed on NSE; its BSE-only page retires" % (
                scrips[code].get("name"), code), "ok")
            del scrips[code]
            changed = True

    taken = set(nse_slugs) | {s["slug"] for s in scrips.values()}
    added = skipped = 0
    for code in sorted(fresh):
        f = fresh[code]
        if not f.get("master"):
            continue   # BSE's scrip list was unreachable: the bhavcopy alone cuts names at 30 characters
        facts = {k: f[k] for k in _STABLE_FIELDS if f.get(k) not in (None, "")}
        if code in scrips:
            merged = dict(scrips[code], **facts)   # newer facts; slug and added date never change
            if merged != scrips[code]:
                scrips[code] = merged
                changed = True
            continue
        if not f.get("liquid") or len(nse_keys) < 1500 or isin_issuer_key(f.get("isin")) in nse_keys:
            continue
        slug = slug_fn(f.get("symbol"))
        if not slug or slug in taken:
            skipped += 1
            log("bse-only: %s (%s) skipped, its URL /stock/%s/ is already taken" % (f.get("name"), code, slug), "warn")
            continue
        taken.add(slug)
        scrips[code] = dict(facts, code=code, slug=slug, added=today)
        added += 1
        changed = True

    if changed:
        write_json(ARCHIVE_PATH, {
            "updated": today,
            "rule": "A BSE main-board company not listed on NSE joins when it is %s. Entries are never "
                    "dropped for low trading; one leaves only when the company lists on NSE." % _rule_text(),
            "scrips": dict(sorted(scrips.items())),
        })
    log("bse-only: %d companies on file (%d added today, %d skipped for a taken URL)"
        % (len(scrips), added, skipped), "ok")
    return sorted(scrips.values(), key=lambda s: (s.get("name") or "").lower()), fresh


def _fmt_cr(n):
    return "{:,.0f}".format(n) if n >= 100 else "{:,.2f}".format(n)


def write_pages(scrips, fresh, corporate_actions, news_articles, nse_slugs):
    """One /stock/<slug>/ page per BSE-only company. Returns the slugs written."""
    from . import publish as P
    from .price_target_section import (
        stock_title, stock_description, price_target_section_html, stock_target_faqs)

    esc = P._esc
    news_matcher = P._build_news_stock_indexer(news_articles or [])
    actions_by_code = {}
    for a in (corporate_actions or []):
        code = str(a.get("scrip_code") or "").strip()
        if code:
            actions_by_code.setdefault(code, []).append(a)

    hist_dir = os.path.join(SITE_DATA, "equity-history")
    os.makedirs(hist_dir, exist_ok=True)
    by_size = sorted(scrips, key=lambda s: -(((fresh.get(s["code"]) or {}).get("mktcap_cr")) or 0))
    rank = {s["code"]: i for i, s in enumerate(by_size)}

    written = []
    for s in scrips:
        slug, code = s["slug"], s["code"]
        if slug in nse_slugs:
            log("bse-only: /stock/%s/ now belongs to an NSE stock; %s not written" % (slug, s.get("name")), "warn")
            continue
        f = fresh.get(code) or {}
        name = s.get("name") or s.get("symbol") or code
        symbol = s.get("symbol") or code
        group = (f.get("group") or s.get("group") or "").upper()
        mktcap = f.get("mktcap_cr")
        history, break_date = trim_to_last_break(f.get("candles") or [])
        if history:
            write_json(os.path.join(hist_dir, "%s.json" % slug),
                       {"symbol": symbol, "exchange": "BSE", "generated_at": now_iso(), "candles": history},
                       compact=True)
        canonical = "%s/stock/%s/" % (P.SITE_URL, slug)
        title = stock_title(name, symbol)
        description = esc(stock_description(name, symbol, "BSE")[:300])
        price_row = history[-1] if history else None
        perf_html, perf = P._stock_perf(history, break_date, exchange="BSE")

        def fact(v):
            return esc(v) if v not in (None, "") else "Not disclosed"
        listing_rows = [
            ("BSE ticker", fact(symbol)),
            ("BSE scrip code", fact(code)),
            ("ISIN", fact(s.get("isin"))),
            ("BSE group", fact(group)),
            ("Face value", fact(("Rs %g" % s["face_value"]) if s.get("face_value") else None)),
            ("Market cap", fact(("Rs %s crore" % _fmt_cr(mktcap)) if mktcap else None)),
            ("Listed on NSE", "No"),
        ]
        listing_html = (
            '<div class="card"><div class="card-title">Listing details</div>'
            '<dl class="kv" style="margin-top:10px">'
            + "".join("<dt>%s</dt><dd>%s</dd>" % row for row in listing_rows)
            + '</dl></div>'
        )
        group_note = GROUP_NOTES.get(group)
        bse_link = s.get("bse_url") if (s.get("bse_url") or "").startswith("https://www.bseindia.com/") else None
        only_html = (
            '<div class="card" style="margin-top:20px;border-left:4px solid var(--accent)">'
            '<div class="card-title">Listed only on BSE</div>'
            '<p class="small" style="margin-top:6px;max-width:78ch">%s is listed on BSE and not on NSE, so its shares '
            'trade only on BSE, through a broker with a BSE cash-market membership. %s</p>%s</div>'
            % (esc(name), esc("BSE has placed it in group %s. %s" % (group, group_note)) if group_note else "",
               ('<p class="xs faint" style="margin-top:8px">Company announcements and filings: '
                '<a href="%s" rel="noopener" target="_blank">%s on bseindia.com</a></p>' % (esc(bse_link), esc(name)))
               if bse_link else "")
        )

        actions = actions_by_code.get(code) or []
        actions_html = ""
        if actions:
            actions_html = (
                '<div class="section-title"><h2>Upcoming corporate actions</h2></div>'
                '<div class="table-scroll"><table class="data"><thead><tr>'
                '<th>Purpose</th><th>Ex-date</th><th>Record date</th></tr></thead><tbody>'
                + "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    esc(a.get("purpose") or "-"), esc(a.get("ex_date") or "-"), esc(a.get("record_date") or "-"))
                    for a in actions)
                + '</tbody></table></div>'
                '<p class="xs faint" style="margin-top:4px">Source: BSE corporate-actions disclosure.</p>'
            )

        # Neighbours by market capitalisation: a real ordering, and the internal links
        # that let a crawler reach every BSE-only page from any one of them.
        i = rank[code]
        near = [x for x in by_size[max(0, i - 4):i + 5] if x["code"] != code and x["slug"] not in nse_slugs][:8]
        near_html = ""
        if near:
            near_html = (
                '<div class="section-title"><h2>Other BSE-only stocks of a similar size</h2></div>'
                '<p class="small" style="max-width:70ch">'
                + ", ".join('<a href="/stock/%s/">%s</a>' % (esc(x["slug"]), esc(x.get("name") or x["slug"])) for x in near)
                + '. <a href="%s">All BSE-only stocks &rarr;</a></p>' % HUB_PATH
            )

        trade_cta_html = (
            '<div class="card" style="margin-top:20px;background:var(--accent-soft);border-style:solid">'
            '<div class="card-title">Trade %s</div>'
            '<p class="small muted" style="margin:4px 0 10px 0">%s is tradable through any SEBI-registered broker '
            'with a BSE cash-market membership. Compare broker charges, STT, and breakeven point movements:</p>'
            '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px">'
            '<a class="badge" href="/trade-costs/" style="text-decoration:none;padding:5px 9px">Stock Trade Cost Calculator &rarr;</a>'
            '<a class="badge" href="/compare/" style="text-decoration:none;padding:5px 9px">Compare Top Brokers &rarr;</a>'
            '</div>'
            '<div style="margin-top:14px;background:var(--bg-raised);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:var(--radius-lg);padding:16px 18px;box-shadow:var(--shadow-sm)">'
            '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">'
            '<div style="font-weight:700;font-size:14px;color:var(--text)">Open Demat Account to Trade %s</div>'
            '<span class="badge badge-verified" style="font-size:11px">Zero Delivery Brokerage</span>'
            '</div>'
            '<p class="small muted" style="margin:6px 0 12px 0;line-height:1.5">Ready to invest in %s? Open a paperless Demat account with zero equity delivery brokerage, flat Rs 11 F&amp;O orders, and zero account opening fee with Indiabulls Securities.</p>'
            '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">'
            '<a class="btn btn-primary btn-sm" href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" style="font-weight:600">Open Free Demat Account &rarr;</a>'
            '<span class="xs faint">SEBI Reg. INZ000036136 &middot; 20+ Years Trusted &middot; Sponsored</span>'
            '</div></div></div>'
        ) % (esc(symbol), esc(name), esc(symbol), esc(name))

        facts_line = ""
        if perf:
            facts_line = (
                "What the data shows: %s last closed at %s on %s. Over the %d sessions on file it traded between %s and %s "
                "and was %.1f%% %s its high on the last close." % (
                    name, P._px_html(perf["last"]), P._iso_to_long_date(perf["last_date"]), perf["n"],
                    P._px_html(perf["lo"]), P._px_html(perf["hi"]), abs(perf["from_high"]),
                    "below" if perf["from_high"] < 0 else "at"))
        faqs = [
            ("What is the BSE code of %s?" % name,
             "%s trades on BSE under scrip code %s and the ticker %s." % (name, code, symbol)),
            ("Is %s listed on NSE?" % name,
             "No. %s is listed on BSE only: neither NSE's main-board list nor its SME list carries an equity share of "
             "this company, so it can be bought and sold only on BSE." % name),
            ("What is the ISIN of %s?" % name,
             ("%s's ISIN is %s." % (name, s["isin"])) if s.get("isin")
             else "The ISIN is not disclosed in BSE's scrip list."),
        ]
        if group_note:
            faqs.append(("Which BSE group is %s in?" % name, "%s is in BSE's group %s. %s" % (name, group, group_note)))
        if s.get("face_value"):
            faqs.append(("What is the face value of %s shares?" % name,
                         "The face value of %s shares is Rs %g, as listed in BSE's scrip list." % (name, s["face_value"])))
        if mktcap:
            faqs.append(("What is the market capitalisation of %s?" % name,
                         "BSE's scrip list gives %s a market capitalisation of about Rs %s crore. It moves with the "
                         "share price every trading day." % (name, _fmt_cr(mktcap))))
        faqs.extend(stock_target_faqs(name, symbol, facts_line, exchange="BSE"))
        if perf:
            wins = dict(perf["wins"])
            faqs.append((
                "How has %s performed recently?" % name,
                "From %s to %s, %s moved %+.1f%% (%d sessions on file). %s Past performance does not indicate future results." % (
                    P._iso_to_long_date(perf["first_date"]), P._iso_to_long_date(perf["last_date"]), name, perf["since"],
                    perf["n"], ("Over the last month it moved %+.1f%%." % wins["1 month"]) if "1 month" in wins else "")))
        faqs.append(("What was %s's last closing price?" % name,
                     "%s closed at %s on %s, from BSE's own daily bhavcopy." % (
                         name, P._px_html(price_row["close"]), P._iso_to_long_date(price_row["date"]))
                     if price_row else
                     "A recent closing price for %s was not available in this site's latest data refresh." % name))
        faq_html = "".join('<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (esc(q), esc(a))
                           for q, a in faqs)

        corp = {"@type": "Corporation", "name": name, "tickerSymbol": symbol, "url": canonical}
        if s.get("isin"):
            corp["identifier"] = s["isin"]
        crumb_html, crumb_jsonld = P._breadcrumb([
            ("BrokerLens", "/"), ("Browse stocks", "/stocks/"), ("BSE-only stocks", HUB_PATH), (name, None)])
        jsonld = {"@context": "https://schema.org", "@graph": [
            corp,
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]},
            crumb_jsonld,
        ]}
        body = P._REGISTRY_PAGE_HEAD % {"title": esc(title), "description": description,
                                        "canonical": esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False)}
        if history:
            body = body.replace("</head>", P._stamp_asset_versions(
                '<script src="/assets/js/vendor/lightweight-charts.standalone.production.js" defer></script>'
                '<script type="module" src="/assets/js/stock-chart.js" defer></script></head>'))
        body = body.replace("</head>", P._stamp_asset_versions('<script src="/assets/js/calculators.js" defer></script></head>'))
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % esc(name)
            + '<p class="muted">BSE: %s &middot; Scrip code %s</p>' % (esc(symbol), esc(code))
            + (
                '<div class="grid g-main" style="margin-top:16px">'
                '<div class="card"><div class="card-title">Price history</div>'
                '<div data-stock-chart data-symbol="%s"></div>%s%s%s</div>'
                '<div class="stack">%s%s%s%s</div></div>'
                % (esc(slug), P._stock_ohlc_html(history), trade_cta_html, P.ibslBanner_html("card", "stock"),
                   P._stock_price_html(history), listing_html, P.affiliateBanner_html(), P.jiraafBanner_html())
                if history else
                listing_html + trade_cta_html
            )
            + only_html
            + '<p class="xs faint" style="margin-top:16px">Source: BSE\'s list of active equity scrips%s.</p>'
              % (" and BSE's daily bhavcopy for price history" if history else
                 "; price history was not available for this company in the latest data refresh")
            + perf_html
            + price_target_section_html(name, symbol, history, P._px_html, P._iso_to_long_date, esc, exchange="BSE")
            + actions_html
            + P._stock_news_section_html(news_matcher(symbol, name, slug, None, False), esc)
            + near_html
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + faq_html + '</div>'
        )
        body += P._REGISTRY_PAGE_FOOT % {"source_note": P._source_note(
            "This page is generated directly from BSE's own list of active equity scrips and its daily bhavcopy.")}
        dest = os.path.join(ROOT, "site", "stock", slug)
        os.makedirs(dest, exist_ok=True)
        P._write_text(os.path.join(dest, "index.html"), body)
        written.append(slug)
    log("stock pages: %d BSE-only equity pages written" % len(written), "ok")
    return written


def write_hub(scrips, fresh, written):
    """/stocks/bse/: every BSE-only company with a page, largest first."""
    from . import publish as P
    esc = P._esc
    live = set(written)
    rows = [s for s in scrips if s["slug"] in live]
    if not rows:
        return False
    rows.sort(key=lambda s: -(((fresh.get(s["code"]) or {}).get("mktcap_cr")) or 0))
    asof = max((((fresh.get(s["code"]) or {}).get("candles") or [{}])[-1].get("date") or "") for s in rows) or None

    def close_of(s):
        c = (fresh.get(s["code"]) or {}).get("candles") or []
        return P._px_html(c[-1]["close"]) if c else "-"
    table = "".join(
        '<tr><td><a href="/stock/%s/">%s</a></td><td>%s</td><td>%s</td><td>%s</td>'
        '<td class="right num">%s</td><td class="right num">%s</td></tr>' % (
            esc(s["slug"]), esc(s.get("name") or s["slug"]), esc(s.get("symbol") or ""), esc(s["code"]),
            esc((fresh.get(s["code"]) or {}).get("group") or s.get("group") or ""), close_of(s),
            _fmt_cr((fresh.get(s["code"]) or {})["mktcap_cr"]) if (fresh.get(s["code"]) or {}).get("mktcap_cr") else "-")
        for s in rows)
    canonical = P.SITE_URL + HUB_PATH
    title = "Stocks Listed Only on BSE, Not on NSE (%d Companies) | BrokerLens" % len(rows)
    description = ("%d companies listed on BSE but not on NSE, with BSE code, group, last close and market cap. "
                   "Each links to a page with its price history." % len(rows))
    crumb_html, crumb_jsonld = P._breadcrumb([("BrokerLens", "/"), ("Browse stocks", "/stocks/"), ("BSE-only stocks", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "ItemList", "name": title, "url": canonical, "numberOfItems": len(rows),
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": "%s/stock/%s/" % (P.SITE_URL, s["slug"]),
                              "name": s.get("name") or s["slug"]} for i, s in enumerate(rows)]},
        crumb_jsonld]}
    body = P._REGISTRY_PAGE_HEAD % {"title": esc(title), "description": esc(description),
                                    "canonical": esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False)}
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Stocks listed only on BSE</h1>'
        + '<div style="max-width:78ch">'
          '<p class="muted">These companies are listed on BSE and not on NSE, so their shares trade only on BSE. '
          'A company appears here once it is %s, which leaves out the many BSE-only shares that rarely change hands. '
          'Once listed here a company keeps its page; it moves to an NSE page if it later lists on NSE.</p>'
          '<p class="xs faint" style="margin-top:8px">Sorted by market capitalisation from BSE\'s scrip list%s.</p>'
          '<h2 style="margin-top:20px;font-size:16px">What the BSE groups mean</h2>'
          '<dl class="kv" style="margin-top:8px">%s</dl></div>'
          % (esc(_rule_text()), (", last close as of %s" % esc(P._iso_to_long_date(asof))) if asof else "",
             "".join("<dt>Group %s</dt><dd>%s</dd>" % (esc(g), esc(GROUP_NOTES[g]))
                     for g in ("A", "B", "T", "X", "XT", "Z") if any(
                         ((fresh.get(s["code"]) or {}).get("group") or s.get("group")) == g for s in rows)))
        + '<div class="table-scroll" style="margin-top:16px"><table class="data"><thead><tr>'
          '<th>Company</th><th>BSE ticker</th><th>Scrip code</th><th>Group</th>'
          '<th class="right">Last close</th><th class="right">Market cap (Rs crore)</th></tr></thead><tbody>'
        + table + '</tbody></table></div>'
    )
    body += P._REGISTRY_PAGE_FOOT % {"source_note": P._source_note(
        "This page lists companies from BSE's own list of active equity scrips that NSE does not list.")}
    dest = os.path.join(ROOT, "site", "stocks", "bse")
    os.makedirs(dest, exist_ok=True)
    P._write_text(os.path.join(dest, "index.html"), body)
    log("BSE-only stocks hub: %d companies listed" % len(rows), "ok")
    return True


def sitemap_entries(scrips, fresh, written, site_url, today):
    live = set(written)
    out = ["<url><loc>%s%s</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>" % (site_url, HUB_PATH, today)] if live else []
    for s in scrips:
        if s["slug"] not in live:
            continue
        c = (fresh.get(s["code"]) or {}).get("candles") or []
        out.append("<url><loc>%s/stock/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
                   % (site_url, s["slug"], c[-1]["date"] if c else today))
    return out


def search_rows(scrips, written):
    live = set(written)
    return [[s.get("name") or s["slug"], "/stock/%s/" % s["slug"], "stock", s.get("symbol") or ""]
            for s in scrips if s["slug"] in live]
