"""/stock-market-holidays/: NSE's trading holiday calendar as a page.

Built from data/manual/nse_holidays.json (pipeline.run holidays, NSE's own
calendar). Nothing here is hand-typed: the dates, names and the Muhurat day
all come from that file, and "next holiday" is worked out at build time.
The Muhurat session's timings come from a separate NSE circular, so the
page names the day and points to NSE rather than asserting a time.
Stdlib only. No em or en dashes anywhere in the copy.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "manual", "nse_holidays.json")
URL_PATH = "/stock-market-holidays/"
NSE_HOLIDAYS_URL = "https://www.nseindia.com/resources/exchange-communication-holidays"


def _long(iso):
    d = date.fromisoformat(iso)
    return "%s %d %s %d" % (d.strftime("%A"), d.day, d.strftime("%B"), d.year)


def page_facts(data, today):
    """Everything the page says, derived from the NSE file. None if unusable."""
    cm = ((data or {}).get("segments") or {}).get("CM") or []
    if not cm:
        return None
    fo = ((data or {}).get("segments") or {}).get("FO") or []
    year = int(cm[0]["date"][:4])
    # "Next holiday" means the next weekday the market is shut. A listed holiday on a
    # Saturday or Sunday closes nothing extra (8 Nov 2026 even hosts the Muhurat session).
    upcoming = [h for h in cm if h["date"] >= today.isoformat() and date.fromisoformat(h["date"]).weekday() < 5]
    return {
        "year": year,
        "holidays": cm,
        "count": len(cm),
        "weekend": sum(1 for h in cm if date.fromisoformat(h["date"]).weekday() >= 5),
        "next": upcoming[0] if upcoming else None,
        "muhurat": next((h for h in cm if h.get("muhurat")), None),
        "fo_same": [h["date"] for h in fo] == [h["date"] for h in cm],
    }


def render(data, today, esc, head, foot, breadcrumb, site_url):
    f = page_facts(data, today)
    if not f:
        return None
    year, n, nxt, muh = f["year"], f["count"], f["next"], f["muhurat"]
    title = "NSE Holidays %d: Stock Market Holiday List & Muhurat Trading" % year
    desc = ("NSE lists %d trading holidays in %d. Full holiday list for equity and F&O, the next "
            "market holiday%s, from NSE's own calendar."
            % (n, year, (", and the Diwali Muhurat trading day (%s)" % _long(muh["date"])) if muh else ""))
    as_of = "%d %s %d" % (today.day, today.strftime("%B"), today.year)
    if nxt:
        next_text = "As of %s, the next NSE trading holiday is <strong>%s</strong> (%s)." % (
            esc(as_of), esc(_long(nxt["date"])), esc(nxt["name"]))
    else:
        next_text = "As of %s, there are no more NSE trading holidays in %d." % (esc(as_of), year)

    faqs = []
    if nxt:
        faqs.append(("When is the next stock market holiday?",
                     "%s, %s. NSE's equity and F&O markets are closed that day." % (_long(nxt["date"]), nxt["name"])))
    if muh:
        faqs.append(("When is Muhurat trading in %d?" % year,
                     "On %s (%s). NSE holds a special Muhurat trading session that day; its timings are set by "
                     "NSE circular, so check NSE before placing orders." % (_long(muh["date"]), muh["name"])))
    faqs.append(("How many trading holidays does NSE have in %d?" % year,
                 "%d days in its holiday calendar, %d of which fall on a Saturday or Sunday." % (n, f["weekend"])))

    rows = []
    for h in f["holidays"]:
        d = date.fromisoformat(h["date"])
        past = h["date"] < today.isoformat()
        is_next = nxt is not None and h["date"] == nxt["date"]
        notes = []
        if d.weekday() >= 5:
            notes.append("falls on a weekend")
        if h.get("muhurat"):
            notes.append("Muhurat trading session")
        style = ' style="font-weight:700"' if is_next else (' class="faint"' if past else "")
        rows.append('<tr%s><td>%d %s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            style, d.day, d.strftime("%b %Y"), d.strftime("%A"), esc(h["name"]),
            esc(", ".join(notes)) + (" (next)" if is_next else "")))

    crumb_html, crumb_jsonld = breadcrumb([("BrokerLens", "/"), ("Stock market holidays", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": site_url + URL_PATH, "description": desc},
        crumb_jsonld,
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]},
    ]}
    muhurat_html = ""
    if muh:
        muhurat_html = (
            '<div class="card" style="margin:16px 0;padding:16px 18px;border-left:3px solid var(--accent)">'
            '<div style="font-weight:700">Diwali Muhurat trading: %s</div>'
            '<p class="small" style="margin:6px 0 0 0;max-width:75ch">NSE marks %s (%s) for a special Muhurat '
            'trading session, held although the exchange is otherwise closed that day. The session timings are set '
            'by NSE circular; check <a href="%s" rel="noopener" target="_blank">NSE&#39;s holiday and circulars page</a> '
            'before placing orders.</p></div>'
            % (esc(_long(muh["date"])), esc(_long(muh["date"])), esc(muh["name"]), NSE_HOLIDAYS_URL))
    fo_note = ("The equity derivatives (F&amp;O) segment is closed on the same %d days." % n) if f["fo_same"] else (
        "The equity derivatives (F&amp;O) segment has its own list on NSE&#39;s calendar.")
    faq_html = "".join('<h3 style="font-size:16px;margin:18px 0 4px 0">%s</h3><p class="small" style="margin:0;max-width:75ch">%s</p>'
                       % (esc(q), esc(a)) for q, a in faqs)
    body = (
        head % {"title": esc(title), "description": esc(desc), "canonical": esc(site_url + URL_PATH),
                "jsonld": json.dumps(jsonld, ensure_ascii=False)}
        + crumb_html
        + '<h1 style="margin-top:0">Stock market holidays %d (NSE)</h1>' % year
        + '<p style="max-width:75ch">%s NSE&#39;s %d calendar lists %d trading holidays, %d of which fall on a '
          'Saturday or Sunday; the market is also closed every weekend. %s</p>' % (next_text, year, n, f["weekend"], fo_note)
        + muhurat_html
        + '<div class="table-scroll"><table class="data"><thead><tr><th>Date</th><th>Day</th><th>Holiday</th>'
          '<th>Note</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(rows)
        + '<h2 style="margin-top:28px">Questions</h2>' + faq_html
        + '<p class="xs faint" style="margin-top:20px;max-width:75ch">Source: NSE trading holiday calendar for the equity '
          'and equity derivatives segments. Exchanges can change a holiday by circular; verify with NSE before relying '
          'on a date. Session times for each exchange are in the Market timings menu.</p>'
    )
    body += foot % {"source_note": "Holiday dates are from the National Stock Exchange (NSE) trading holiday calendar."}
    return body


def write(site_dir, esc, head, foot, breadcrumb, write_text, site_url, today=None):
    """Write the page if the NSE file is usable. Returns True when written."""
    try:
        with open(DATA_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    today = today or datetime.now(timezone.utc).date()
    body = render(data, today, esc, head, foot, breadcrumb, site_url)
    if not body:
        return False
    out = os.path.join(site_dir, URL_PATH.strip("/"))
    os.makedirs(out, exist_ok=True)
    write_text(os.path.join(out, "index.html"), body)
    return True
