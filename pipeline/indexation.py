"""Crawl and index hygiene helpers (stdlib only).

Kept in one small module so the large page-generator files only need one-line
hooks. Nothing here writes pages; it answers "should this URL be indexable and
in the sitemap?" and supplies the discovery links that were missing.

Contents
  - SIP permutation policy: which /calculators/sip/<amount>-per-month-for-<n>-years/
    pages stay indexable (the amounts and years people actually search).
  - Branch page verification: a city page for a broker is indexable only where
    the data on file shows that broker registered or headquartered in that city.
  - First-wave ETF picks for the sitemap.
  - Footer discovery links (crawlable plain anchors) shared by the page shells.
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NOINDEX_META = '<meta name="robots" content="noindex,follow">'

# ---------------------------------------------------------------- SIP policy

# Amounts and horizons that match real search phrasing ("5000 per month for 10
# years"). Every other permutation stays live but is noindex,follow and is left
# out of the sitemap so crawl budget goes to the pages that can rank.
SIP_INDEX_AMOUNTS = (500, 1000, 2000, 3000, 5000, 10000, 15000, 20000, 25000, 50000)
SIP_INDEX_YEARS = (1, 3, 5, 10, 15, 20, 25, 30)


def sip_indexable(amount, years):
    return int(amount) in SIP_INDEX_AMOUNTS and int(years) in SIP_INDEX_YEARS


# ------------------------------------------------------- branch verification

# Register and master-file spellings that name the same city as a CITIES key in
# broker_branch_engine. Exact names only: Navi Mumbai and Thane are separate
# cities there, never folded into Mumbai.
_CITY_ALIASES = {
    "bangalore": "bengaluru", "bengaluru": "bengaluru", "bangalore urban": "bengaluru",
    "bombay": "mumbai", "mumbai": "mumbai",
    "new delhi": "delhi", "delhi": "delhi",
    "calcutta": "kolkata", "kolkata": "kolkata",
    "madras": "chennai", "chennai": "chennai",
    "gurgaon": "gurugram", "gurugram": "gurugram",
    "allahabad": "prayagraj", "prayagraj": "prayagraj",
    "baroda": "vadodara", "vadodara": "vadodara",
    "cochin": "kochi", "kochi": "kochi",
    "trivandrum": "thiruvananthapuram", "thiruvananthapuram": "thiruvananthapuram",
    "mysore": "mysuru", "mysuru": "mysuru",
    "vizag": "visakhapatnam", "visakhapatnam": "visakhapatnam",
    "navi mumbai": "navi-mumbai", "thane": "thane",
    "calicut": "kozhikode", "kozhikode": "kozhikode",
    "trichy": "tiruchirappalli", "tiruchirappalli": "tiruchirappalli",
    "hubli": "hubballi", "hubballi": "hubballi",
    "mangaluru": "mangalore", "mangalore": "mangalore",
}


def city_key(raw, known_keys=None):
    """Map a free-text city from the SEBI register or the broker master file to a
    branch-engine city key, or None. Matching is exact (after lower-casing and
    trimming punctuation); an unknown spelling is never guessed at."""
    text = re.sub(r"[^a-z ]+", " ", str(raw or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    key = _CITY_ALIASES.get(text)
    if key is None:
        slug = text.replace(" ", "-")
        key = slug if (known_keys is not None and slug in known_keys) else None
    if key is not None and known_keys is not None and key not in known_keys:
        return None
    return key


def load_broker_profile(b_id, site_dir=None):
    """The broker profile written earlier in the build (site/data/brokers/<id>.json),
    or None when it is absent."""
    path = os.path.join(site_dir or os.path.join(ROOT, "site"), "data", "brokers", "%s.json" % b_id)
    try:
        with open(path, encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("profile") or None
    except (OSError, ValueError):
        return None


def verified_city_keys(profile, known_keys=None):
    """City keys where the data on file places this broker: the city of any SEBI
    register entity matched to it, the register city on the profile, and the head
    office city from the curated master file. Returns {key: basis_label}.
    A broker with no profile on file verifies nowhere."""
    out = {}
    if not profile:
        return out
    for ent in profile.get("sebi_entities") or []:
        k = city_key(ent.get("city"), known_keys)
        if k:
            out.setdefault(k, "sebi_register")
    k = city_key(profile.get("sebi_city"), known_keys)
    if k:
        out.setdefault(k, "sebi_register")
    k = city_key(profile.get("hq"), known_keys)
    if k:
        out.setdefault(k, "head_office_on_file")
    return out


def address_mentions_city(address, key, city_name, known_keys=None):
    """True when a curated street address names the page's city, so the address
    is only ever printed on a page for the city it is actually in."""
    text = re.sub(r"[^a-z ]+", " ", str(address or "").lower())
    text = re.sub(r"\s+", " ", " %s " % text)
    names = {city_name.lower(), key.replace("-", " ")}
    names |= {a for a, v in _CITY_ALIASES.items() if v == key}
    for n in names:
        if " %s " % n in text:
            # "Navi Mumbai" and "Thane West, Mumbai" must not count for Mumbai
            # unless the bare city is named on its own.
            if key == "mumbai" and " navi mumbai " in text and text.count(" mumbai ") <= text.count(" navi mumbai "):
                continue
            return True
    return False


# ------------------------------------------------------------ sitemap wave 1

def top_etf_slugs(etfs, equity_history, slug_fn, limit=40):
    """Slugs of the most-traded ETFs (by average daily volume in the history on
    file) for the first sitemap wave. ETFs with no volume history are never
    picked; ties break on slug so the choice is stable between builds."""
    scored = []
    for e in etfs or []:
        sym = (e.get("symbol") or "").strip()
        slug = slug_fn(sym)
        if not slug:
            continue
        hist = (equity_history or {}).get(sym.upper()) or []
        vols = [r["volume"] for r in hist if isinstance(r.get("volume"), (int, float))]
        if vols:
            scored.append((-sum(vols) / len(vols), slug))
    scored.sort()
    return [s for _, s in scored[:limit]]


# ------------------------------------------------------- discovery link data

# (href, anchor text). Plain anchors with real hrefs, never data-link only, so a
# crawler that does not run the SPA router still follows them.
FOOTER_DISCOVERY_LINKS = (
    ("/ipo/upcoming/", "Upcoming IPOs"),
    ("/ipo/subscription/", "IPO subscription status"),
    ("/trade-costs/", "Trade cost calculator"),
    ("/index/nifty-50/", "Nifty 50 constituents"),
    ("/etf/niftybees/", "Nifty 50 ETF: NIFTYBEES"),
)


def footer_discovery_inline(skip=()):
    """Inline anchors for the compact one-paragraph footer."""
    return " &middot; ".join(
        '<a href="%s">%s</a>' % (h, t) for h, t in FOOTER_DISCOVERY_LINKS if h not in skip
    )


def add_home_footer_links(page_html):
    """site/index.html is the hand-maintained SPA shell, so its footer cannot take the
    shared template. Add the discovery links to its footer lists (idempotent: a link
    already present is not added twice). Returns the page unchanged when the footer
    layout is not the expected one."""
    cut = page_html.find("<footer")
    if cut < 0:
        return page_html
    head, foot = page_html[:cut], page_html[cut:]

    def after(foot, anchor, hrefs):
        li = "".join(
            '\n          <li><a href="%s">%s</a></li>' % (h, t)
            for h, t in FOOTER_DISCOVERY_LINKS if h in hrefs and 'href="%s"' % h not in foot)
        return foot.replace(anchor, anchor + li, 1) if li and anchor in foot else foot

    foot = after(foot, '<li><a href="/ipo/">IPO tracker</a></li>',
                 ("/ipo/upcoming/", "/ipo/subscription/", "/trade-costs/"))
    foot = after(foot, '<li><a href="/stocks/">Browse stocks A-Z</a></li>', ("/index/nifty-50/",))
    foot = after(foot, '<li><a href="/etfs/">Browse ETFs</a></li>', ("/etf/niftybees/",))
    return head + foot


# ------------------------------------------------------------ index allowlist

# The sitemap is the only set of pages Google may index. Every other built page
# gets noindex,follow at the end of the build. "Left out of the sitemap" used to be
# the whole gate, and it was not one: with no robots tag, internally linked pages
# were indexed anyway (33.5K indexed against 4,823 submitted, mostly trade-cost
# templates), and impressions fell 97% overnight on 2 Nov 2026. Promoting a family
# into the sitemap (SITEMAP_WAVE) is now the one switch that makes it indexable.
_ROBOTS_META_RE = re.compile(r'<meta\s+name=["\']robots["\'][^>]*>', re.I)
_NOINDEX_RE = re.compile(r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*noindex', re.I)
_CANONICAL_RE = re.compile(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']', re.I)
_SKIP_DIRS = ("assets", "data", "sitemaps")


def sitemap_paths(site_dir):
    """URL paths (with a trailing slash) in every child sitemap the index lists."""
    index = os.path.join(site_dir, "sitemap.xml")
    try:
        children = re.findall(r"<loc>([^<]+)</loc>", open(index, encoding="utf-8").read())
    except OSError:
        return set()
    paths = set()
    for child in children:
        local = os.path.join(site_dir, re.sub(r"^https?://[^/]+/", "", child))
        try:
            locs = re.findall(r"<loc>([^<]+)</loc>", open(local, encoding="utf-8").read())
        except OSError:
            continue
        for loc in locs:
            path = re.sub(r"^https?://[^/]+", "", loc) or "/"
            paths.add(path if path.endswith("/") else path + "/")
    return paths


def enforce_index_allowlist(site_dir, allowed=None):
    """Give noindex,follow to every built page whose URL is not in a sitemap.

    Returns (pages_checked, pages_changed). A page that already says noindex is
    left alone; an existing index robots tag is replaced, otherwise the tag is
    inserted right after <head>. Pages stay crawlable, so links still pass.

    A page whose canonical names another URL is also left alone: the canonical
    already keeps it out of the index in favour of that URL, and adding noindex
    on top is the mixed signal Google can resolve by carrying the noindex over to
    the canonical target. That was 481 secondary SEBI registrations pointing at
    their company's main registry page (about 4,300 impressions a month)."""
    allowed = sitemap_paths(site_dir) if allowed is None else allowed
    if not allowed:
        return 0, 0  # no sitemap written: never noindex a whole site by accident
    checked = changed = 0
    for root, dirs, files in os.walk(site_dir):
        if root == site_dir:
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if "index.html" not in files:
            continue
        rel = os.path.relpath(root, site_dir).replace(os.sep, "/")
        path = "/" if rel == "." else "/" + rel + "/"
        checked += 1
        if path in allowed:
            continue
        f = os.path.join(root, "index.html")
        with open(f, encoding="utf-8", errors="surrogateescape") as fh:
            page = fh.read()
        head_end = page.find("</head>")
        head = page[:head_end] if head_end != -1 else page[:8000]
        if _NOINDEX_RE.search(head):
            continue
        canon = _CANONICAL_RE.search(head)
        if canon:
            target = re.sub(r"^https?://[^/]+", "", canon.group(1)).split("?", 1)[0].split("#", 1)[0] or "/"
            if (target if target.endswith("/") else target + "/") != path:
                continue
        if _ROBOTS_META_RE.search(head):
            page = _ROBOTS_META_RE.sub(NOINDEX_META, page, count=1)
        else:
            page = re.sub(r"(<head[^>]*>)", r"\1\n" + NOINDEX_META, page, count=1, flags=re.I)
        with open(f, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(page)
        changed += 1
    return checked, changed
