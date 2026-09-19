"""Assembles ingested + manual data into the static JSON payloads the site reads.

Output contract (site/data/):
  overview.json        market pulse, aggregates, leaderboards, compact broker index
  brokers/<id>.json    full profile, lazily fetched on route change
  sources.json         data lineage - every source, when it last ran, what it fed
  search.json          full-site index (every broker, stock, ETF, fund, SEBI
                       entity, index, calculator, report and core page) for
                       instant client-side search - no server, no live API
  sitemap.xml, feed.xml

Design constraint carried over from mtf.trading: the browser must never call a
live API. Everything is precomputed, CDN-cacheable and survives a source going
down.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.request
from datetime import datetime, timezone

from . import feeds, metrics
from .sources.nse import INDEX_FILES
from .common import (
    CONFIG,
    DATA,
    ROOT,
    MANUAL,
    SITE_DATA,
    log,
    now_iso,
    read_json,
    slugify,
    write_json,
)
from .identity import Resolver, norm as inorm

SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")

# Single source of truth for the site's contact address, so /contact, the
# footer, the privacy policy and the terms of service can never drift apart.
CONTACT_EMAIL = "letmeknow@brokerlens.in"

# PUBLISH_MODE=production drops every dataset flagged provenance:"sample" instead
# of publishing it behind a banner. Set it for any build that reaches a public
# origin. Local development stays in the default mode so the UI has data to
# exercise.
PRODUCTION = os.environ.get("PUBLISH_MODE", "").lower() == "production"

# A sitemap and RSS feed of unresolvable URLs is worse than none: search engines
# reject it and the failure is silent. The old default was "https://example.invalid"
# and it shipped in the committed artefacts, so the placeholder is now refused.
_PLACEHOLDER_HOSTS = ("example.invalid", "example.com", "localhost", "127.0.0.1")


def _stamp_asset_versions(html):
    """Append a content-hash query string to every /assets/* href or src so a
    changed CSS/JS file gets a new URL, not just new bytes at the old one.

    /assets/* is served with `Cache-Control: public, max-age=31536000,
    immutable` (see vercel.json) and no per-deploy filename hashing - a
    returning visitor's browser honours that literally and never re-checks
    the URL, so every CSS/JS-only deploy was invisible to anyone who had
    already loaded the site, indefinitely, until a hard refresh (caught live:
    a banner redesign shipped correctly to the server but rendered unstyled
    in a browser that had cached the previous app.css). Re-applying this to
    an already-versioned URL (its own prior output, or a stale one from
    before a rebuild) is safe - the old ?v= is stripped before rehashing."""
    def repl(m):
        attr, rel = m.group(1), m.group(2).split("?", 1)[0]
        path = os.path.join(ROOT, "site", "assets", rel)
        try:
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:10]
        except OSError:
            return m.group(0)
        return '%s="/assets/%s?v=%s"' % (attr, rel, digest)
    return re.sub(r'(href|src)="/assets/([^"]+)"', repl, html)


def _require_site_url():
    if not SITE_URL or any(h in SITE_URL for h in _PLACEHOLDER_HOSTS):
        raise ValueError(
            "SITE_URL is unset or a placeholder (got %r). Set it to the public origin "
            "before publishing, e.g. SITE_URL=https://brokerlens.in python3 -m pipeline.run all. "
            "Refusing to write a sitemap and feed that point nowhere." % (SITE_URL or None)
        )

# Raw ingest state is internal: it must NOT live under site/, which is
# world-readable once deployed.
INGEST_PATH = os.path.join(DATA, "_ingest.json")


def _profile(b):
    return {
        "id": b["id"],
        "brand": b.get("brand"),
        "slug": b["id"],
        "legal_name": b.get("legal_name"),
        "legal_name_verified": False,
        "sebi_reg_no": None,
        "sebi_exchanges": [],
        "sebi_categories": [],
        "sebi_validity": None,
        "sebi_city": None,
        "dp_registrations": [],
        "sebi_entities": [],
        "type": b.get("type"),
        "hq": b.get("hq"),
        "founded": b.get("founded"),
        "website": b.get("website"),
        "apps": b.get("apps") or [],
        "segments": b.get("segments") or [],
        "listed_company": bool(b.get("listed")),
        "note": b.get("note"),
        "provenance": {
            "brand": "curated",
            "legal_name": "curated_pending_sebi",
            "hq": "curated",
            "founded": "curated",
            "website": "curated",
        },
    }


def _merge_registry(sebi_registry_by_cat):
    """One record per SEBI registration number, across every category pulled."""
    merged = {}
    for cat, rows in (sebi_registry_by_cat or {}).items():
        for r in rows or []:
            key = r.get("sebi_reg_no") or (r.get("legal_name") or "").lower()
            if not key:
                continue
            cur = merged.setdefault(key, dict(r, categories=[], exchanges=list(r.get("exchanges") or [])))
            if cat not in cur["categories"]:
                cur["categories"].append(cat)
            for e in r.get("exchanges") or []:
                if e not in cur["exchanges"]:
                    cur["exchanges"].append(e)
            # prefer the record with the most contact detail
            for f in ("email", "telephone", "address", "city", "validity", "trade_name"):
                if not cur.get(f) and r.get(f):
                    cur[f] = r[f]
    return list(merged.values())


BROKING_CATS = ("stock_broker", "commodity_broker")
DP_CATS = ("dp_cdsl", "dp_nsdl")


def _apply_sebi(profiles, resolver, registry, defaulters):
    """Fold the SEBI registry into curated profiles.

    A broker holds several DISTINCT registrations: a broking licence (INZ...)
    and, separately, a depository-participant licence (IN-DP-...). They must not
    overwrite each other - publishing a DP number as the broking licence would
    be a factual error. One broker can therefore match several registry records;
    each populates its own field.
    """
    matched, unmatched = set(), []
    for rec in registry or []:
        bid, method, score = resolver.resolve(rec["legal_name"])
        if not bid or bid not in profiles:
            unmatched.append(dict(rec, match_reason=method, match_score=score))
            continue
        p = profiles[bid]
        cats = rec.get("categories") or []
        reg = rec.get("sebi_reg_no")
        is_dp = any(c in DP_CATS for c in cats)
        is_broking = any(c in BROKING_CATS for c in cats)

        # A consumer brand often spans several legal entities: "Zerodha Broking
        # Limited" holds the equity membership while "Zerodha Commodities Private
        # Limited" holds the commodity one. Record every registration found, and
        # only promote one to the headline legal_name when its name actually
        # matches the curated legal entity - otherwise the profile would claim
        # the wrong company.
        if reg and not any(e["reg_no"] == reg for e in p["sebi_entities"]):
            p["sebi_entities"].append({
                "legal_name": rec["legal_name"],
                "reg_no": reg,
                "categories": cats,
                "exchanges": rec.get("exchanges") or [],
                "validity": rec.get("validity"),
                "city": rec.get("city"),
            })

        if is_broking and reg and inorm(rec["legal_name"]) == inorm(p["legal_name"]):
            p["sebi_reg_no"] = reg
            p["legal_name_verified"] = True
            p["sebi_validity"] = rec.get("validity")
            p["provenance"]["legal_name"] = "sebi_registry"
            p["provenance"]["sebi_reg_no"] = "sebi_registry"

        if is_dp and reg:
            depo = "CDSL" if "dp_cdsl" in cats else "NSDL"
            if not any(d["reg_no"] == reg for d in p["dp_registrations"]):
                p["dp_registrations"].append({
                    "depository": depo, "reg_no": reg, "entity": rec["legal_name"],
                })
            p["provenance"]["dp_registrations"] = "sebi_registry"

        for e in rec.get("exchanges") or []:
            p.setdefault("sebi_exchanges", [])
            if e not in p["sebi_exchanges"]:
                p["sebi_exchanges"].append(e)
        for c in cats:
            p.setdefault("sebi_categories", [])
            if c not in p["sebi_categories"]:
                p["sebi_categories"].append(c)
        if rec.get("city") and not p.get("sebi_city"):
            p["sebi_city"] = rec["city"]
        p.setdefault("_match", {"method": method, "score": score})
        matched.add(bid)

    # Defaulter attribution is ADVERSE, so it demands an exact normalised match.
    # A fuzzy hit here does not produce a data-quality wrinkle: it publishes
    # "this named, regulated firm is a SEBI defaulter" on a public page. The
    # cost of a miss is a gap; the cost of a false positive is a defamation
    # claim. Registration numbers are matched too, since they are unambiguous.
    reg_to_bid = {}
    for bid, p in profiles.items():
        for e in p.get("sebi_entities") or []:
            if e.get("reg_no"):
                reg_to_bid[str(e["reg_no"]).strip().upper()] = bid
        if p.get("sebi_reg_no"):
            reg_to_bid[str(p["sebi_reg_no"]).strip().upper()] = bid

    flags = {}
    for d in defaulters or []:
        bid = None
        reg = str(d.get("reg_no") or "").strip().upper()
        if reg and reg in reg_to_bid:
            bid = reg_to_bid[reg]
        else:
            bid, _, _ = resolver.resolve(d.get("name", ""), strict=True)
        if bid:
            flags.setdefault(bid, []).append(d.get("name"))
    return len(matched), unmatched, flags


def build():
    master = read_json(os.path.join(CONFIG, "brokers_master.json"), {})
    sources_cfg = read_json(os.path.join(CONFIG, "sources.json"), {})
    brokers_cfg = master.get("brokers", [])
    resolver = Resolver(brokers_cfg)

    ingest = read_json(INGEST_PATH, {}) or {}
    nse_d = ingest.get("nse") or {}
    bse_d = ingest.get("bse") or {}
    sebi_d = ingest.get("sebi") or {}
    crypto_coins = (ingest.get("crypto") or {}).get("coins") or []
    ipo_records = _ipo_merge(nse_d.get("ipo") or {})
    amfi_d = ingest.get("amfi") or {}

    clients_raw = read_json(os.path.join(MANUAL, "active_clients.json"), {}) or {}
    complaints_raw = read_json(os.path.join(MANUAL, "complaints.json"), {}) or {}
    charges_raw = read_json(os.path.join(MANUAL, "charges.json"), {}) or {}
    listings_raw = read_json(os.path.join(MANUAL, "listings.json"), {}) or {}

    # Provenance must be declared, not inferred. Previously anything whose flag
    # was not literally "sample" fell through to "nse" / "sebi_annexure_b", so a
    # hand-typed file, or one whose flag was renamed to "manual" or "estimate",
    # published as a regulator-mandated disclosure with a green provenance dot.
    # An unrecognised value now fails the build rather than being dressed up.
    PROVENANCE_BY_DATASET = {
        "active_clients": {"sample", "nse_ucc", "manual", "estimate"},
        "complaints": {"sample", "sebi_annexure_b", "manual", "estimate"},
        "charges": {"sample", "broker_supplied", "manual", "estimate"},
    }
    declared, sample_flags = {}, {}
    for name, raw in (("active_clients", clients_raw), ("complaints", complaints_raw),
                      ("charges", charges_raw)):
        if not raw:
            declared[name] = None
            sample_flags[name] = False
            continue
        prov = raw.get("provenance")
        if prov not in PROVENANCE_BY_DATASET[name]:
            raise ValueError(
                "data/manual/%s.json declares provenance %r; expected one of %s. "
                "Refusing to publish: an undeclared provenance would be labelled "
                "as regulator-sourced." % (name, prov, sorted(PROVENANCE_BY_DATASET[name]))
            )
        declared[name] = prov
        sample_flags[name] = prov == "sample"

    # PRODUCTION MODE: sample data never reaches a public origin.
    #
    # The banner is not enough. Placeholder figures look plausible, they are
    # attached to real named firms, and a screenshot carries none of the
    # disclaimer. In production a sample dataset is DROPPED, so the fields
    # publish empty and the UI shows an honest "not published yet" state rather
    # than an invented number.
    if PRODUCTION:
        dropped = [n for n, is_sample in sample_flags.items() if is_sample]
        if dropped:
            log("production mode: dropping sample dataset(s): %s" % ", ".join(dropped), "warn")
        if "active_clients" in dropped:
            clients_raw = {}
        if "complaints" in dropped:
            complaints_raw = {}
        if "charges" in dropped:
            charges_raw = {}
        for n in dropped:
            declared[n] = None
            sample_flags[n] = False

    profiles = {b["id"]: _profile(b) for b in brokers_cfg}
    registry = _merge_registry(sebi_d.get("registry"))
    matched, untracked, defaulter_flags = _apply_sebi(
        profiles, resolver, registry, sebi_d.get("defaulters")
    )
    log("sebi identity: %d/%d tracked profiles verified; %d further registered entities"
        % (matched, len(profiles), len(untracked)),
        "ok" if matched else "warn")

    # market totals per month, from whatever client data we have
    market_totals = {}
    for bid, series in (clients_raw.get("brokers") or {}).items():
        for m, v in series:
            market_totals[m] = market_totals.get(m, 0) + (v or 0)

    circulars = nse_d.get("circulars") or {}
    # The regulatory picture is only "checked" if both adverse sources actually
    # returned data this run. A failed SEBI pull must not read as a clean record.
    regulatory_checked = bool(sebi_d.get("defaulters")) and "circulars" in nse_d
    bse_members = {}
    mt = bse_d.get("member_turnover") or {}
    for row in (mt.get("members") or []):
        bid, method, _ = resolver.resolve(row.get("member_name", ""))
        if bid:
            prev = bse_members.get(bid, {"gross": 0})
            bse_members[bid] = {"gross": prev["gross"] + (row.get("gross") or 0),
                                "date": mt.get("date")}

    built = []
    for b in brokers_cfg:
        bid = b["id"]
        p = profiles[bid]
        series = (clients_raw.get("brokers") or {}).get(bid) or []
        cm = metrics.client_metrics(series, market_totals)
        comp = metrics.complaint_metrics(
            (complaints_raw.get("brokers") or {}).get(bid) or [], cm.get("active_clients")
        )
        ch = (charges_raw.get("brokers") or {}).get(bid)
        cost = metrics.cost_of_basket(ch)
        listing = dict(master.get("listing_defaults") or {})
        listing.update((listings_raw.get("brokers") or {}).get(bid) or {})

        built.append({
            "id": bid,
            "profile": p,
            "clients": cm,
            "complaints": comp,
            "charges": ch,
            "cost": cost,
            "listing": listing,
            "bse_activity": bse_members.get(bid),
            "regulatory_flags": {
                # `checked` records that the regulatory scan actually ran against
                # real source data. Without it, "no flags found" was indistinguishable
                # from "we never looked", and the reliability score treated the
                # latter as a clean record worth full marks.
                "checked": regulatory_checked,
                "defaulter": bid in defaulter_flags,
                "defaulter_names": defaulter_flags.get(bid, []),
                "circulars": circulars.get(bid, []),
            },
            # Each field carries the provenance its source file DECLARED, never a
            # default. `None` means we hold no data, which the UI renders as a gap.
            "provenance": {
                "active_clients": declared["active_clients"] if cm.get("active_clients") is not None else None,
                "complaints": declared["complaints"] if comp.get("available") else None,
                "charges": declared["charges"] if ch else None,
                "identity": "sebi_registry" if p["legal_name_verified"] else "curated",
            },
        })

    for b in built:
        b["reliability"] = metrics.reliability_score(b, built)

    # ranks
    ranked = sorted(built, key=lambda x: (x["clients"].get("active_clients") or -1), reverse=True)
    for i, b in enumerate(ranked, 1):
        b["rank"] = i if b["clients"].get("active_clients") else None

    aggregates = metrics.market_aggregates(built, market_totals)
    boards = metrics.leaderboards(built)
    tags = _derive_tags(built, boards)
    for b in built:
        b["tags"] = tags.get(b["id"], [])

    # ---- write per-broker profiles
    os.makedirs(os.path.join(SITE_DATA, "brokers"), exist_ok=True)
    for b in built:
        peers = _peers(b, built)
        payload = dict(b, peers=peers, generated_at=now_iso())
        write_json(os.path.join(SITE_DATA, "brokers", "%s.json" % b["id"]), payload, compact=True)

    # ---- compact index for directory/search/compare
    index = [{
        "id": b["id"],
        "brand": b["profile"]["brand"],
        "type": b["profile"]["type"],
        "hq": b["profile"]["hq"],
        "founded": b["profile"]["founded"],
        "segments": b["profile"]["segments"],
        "verified": b["profile"]["legal_name_verified"],
        "sebi_reg_no": b["profile"]["sebi_reg_no"],
        "rank": b.get("rank"),
        "clients": b["clients"].get("active_clients"),
        "clients_yoy": b["clients"].get("yoy_pct"),
        "share": b["clients"].get("market_share_pct"),
        "spark": [v for _, v in (b["clients"].get("series") or [])][-12:],
        "complaints_per_10k": b["complaints"].get("per_10k_clients_12m"),
        "resolution": b["complaints"].get("resolution_rate_pct"),
        # A bare score next to other brokers implies like-for-like comparison, so
        # the index carries it only when enough inputs back it. A score built on
        # tenure and "no adverse findings" alone reads as a quality signal it is
        # not. The full profile still shows the breakdown with its confidence.
        "reliability": ((b.get("reliability") or {}).get("score")
                        if (b.get("reliability") or {}).get("rankable") else None),
        "reliability_confidence": (b.get("reliability") or {}).get("confidence"),
        "cost": (b.get("cost") or {}).get("monthly_total"),
        "tier": b["listing"].get("tier"),
        "claimed": bool(b["listing"].get("claimed")),
        "flagged": bool(b["regulatory_flags"]["defaulter"]) or bool(b["regulatory_flags"]["circulars"]),
        "tags": b["tags"],
    } for b in built]

    overview = {
        "metadata": {
            "generated_at": now_iso(),
            "site": "Indian Stock Broker Marketplace",
            "broker_count": len(built),
            "verified_count": sum(1 for b in built if b["profile"]["legal_name_verified"]),
            "claimed_count": sum(1 for b in built if b["listing"].get("claimed")),
            "entity_linked_count": sum(1 for b in built if b["profile"]["sebi_entities"]),
            "sample_data": sample_flags,
            "production": PRODUCTION,
            # What the site does and does not yet hold, so the UI can say so
            # plainly instead of rendering an empty chart that reads as broken.
            "data_status": {
                "active_clients": bool(clients_raw.get("brokers")),
                "complaints": bool(complaints_raw.get("brokers")),
                "charges": bool(charges_raw.get("brokers")),
                "registry": bool(registry),
                "market": bool((nse_d.get("pulse") or {}).get("indices")),
            },
            "data_months": clients_raw.get("months") or [],
        },
        "market": {
            "nse": (nse_d.get("pulse") or {}),
            "fii_dii": (nse_d.get("fii_dii") or [])[:2],
            "turnover": nse_d.get("turnover") or [],
            "bse_delivery": bse_d.get("delivery") or [],
            "corporate_actions": (bse_d.get("corporate_actions") or [])[:12],
            "universe": {"nse_symbols": ((nse_d.get("universe") or {}).get("symbol_count"))},
        },
        "aggregates": aggregates,
        "leaderboards": boards,
        "brokers": index,
        "registry_count": len(registry),
        "defaulter_count": len(sebi_d.get("defaulters") or []),
        "untracked_count": len(untracked),
    }
    size = write_json(os.path.join(SITE_DATA, "overview.json"), overview, compact=True)
    log("overview.json %.1f KB, %d tracked brokers" % (size / 1024, len(index)), "ok")

    # The long tail: every SEBI-registered entity we do not yet track in depth.
    # Regulator-sourced only - name, registration, exchanges, city, validity.
    # This is what takes coverage from ~50 brands to the whole market, and it
    # doubles as the outreach list for broker acquisition.
    reg_rows = [{
        "name": r.get("legal_name"),
        "trade_name": r.get("trade_name") if r.get("trade_name") != r.get("legal_name") else None,
        "reg": r.get("sebi_reg_no"),
        "city": r.get("city"),
        "exchanges": r.get("exchanges") or [],
        "categories": r.get("categories") or [],
        "validity": r.get("validity"),
        "slug": slugify(r.get("legal_name") or ""),
    } for r in untracked]

    # A broking + DP registration for the same firm produces the same name and
    # therefore the same slug, which silently overwrote one entity's page with
    # another's. Disambiguate with the registration number so every entity
    # keeps a stable, unique URL.
    seen_slugs = {}
    for row in reg_rows:
        base = row["slug"] or "entity"
        n = seen_slugs.get(base, 0)
        seen_slugs[base] = n + 1
        if n:
            suffix = re.sub(r"[^a-z0-9]", "", (row.get("reg") or "").lower())[-6:] or str(n)
            row["slug"] = "%s-%s" % (base, suffix)

    reg_size = write_json(os.path.join(SITE_DATA, "registry.json"),
                          {"generated_at": now_iso(), "source": "SEBI recognised intermediaries",
                           "count": len(reg_rows), "entities": reg_rows}, compact=True)
    log("registry.json %.1f KB, %d untracked registered entities"
        % (reg_size / 1024, len(reg_rows)), "ok")

    sources_data = _write_sources(sources_cfg, ingest, sample_flags)
    algo_data = _write_algo(brokers_cfg)
    _write_timings()
    _write_registry_pages(reg_rows)
    _write_broker_pages(built)
    hub_groups = _write_broker_hub_pages(built)
    equity_companies = ((nse_d.get("universe") or {}).get("companies")) or []
    index_universe = nse_d.get("indices") or {}
    equity_history = nse_d.get("equity_history") or {}
    build_equity_history(equity_history)
    _write_stock_pages(equity_companies, read_json(os.path.join(CONFIG, "broker_stocks.json"), {}).get("stocks"),
                        index_universe, equity_history, bse_d.get("corporate_actions") or [])
    _write_index_pages(index_universe, equity_companies)
    etf_universe = nse_d.get("etfs") or []
    _write_etf_pages(etf_universe, index_universe)
    mf_schemes = amfi_d.get("schemes") or []
    _funds, fund_slugs = _write_mutual_fund_pages(mf_schemes)
    report_slugs = _write_reports(built, reg_rows, equity_companies, index_universe, etf_universe,
                                   _funds, len(sebi_d.get("defaulters") or []))
    calc_slugs = _write_calculator_pages()
    _write_calculator_hub()
    _write_methodology_page()
    _write_coming_soon_pages()
    _write_about_page()
    _write_contact_page()
    _write_privacy_page()
    _write_terms_page()
    _write_sources_page(sources_data)
    _write_algo_page(algo_data)
    _write_leaderboards_page(overview, nse_d.get("live") or {}, crypto_coins)
    registry_letters = _write_registry_directory(reg_rows)
    _write_registry_landing_page(reg_rows, overview, registry_letters)
    _write_compare_page(overview)
    _write_brokers_page(overview)
    _write_calculator_tool_page(built)
    _prerender_home(overview)
    stock_letters = _write_stock_directory(equity_companies)
    amc_slugs = _write_fund_amc_pages(fund_slugs)
    _write_etf_directory(etf_universe)
    crypto_slugs = _write_crypto_pages(crypto_coins)
    _write_crypto_hub(crypto_coins)
    _write_ipo_pages(ipo_records)
    _write_ipo_hub(ipo_records)
    _write_ipo_archive(ipo_records)
    _write_sitemap(built, reg_rows, hub_groups, equity_companies, index_universe, etf_universe,
                    fund_slugs, report_slugs, calc_slugs, stock_letters, amc_slugs, crypto_slugs, ipo_records,
                    registry_letters)
    _write_search_index(built, reg_rows, hub_groups, equity_companies, index_universe, etf_universe,
                         fund_slugs, report_slugs, amc_slugs, crypto_coins, ipo_records)
    _write_feed(built, aggregates)
    build_ticker()
    build_crypto_ticker()
    build_crypto_history()
    build_market_movers()
    _restamp_js_imports()
    _restamp_index_html_assets()
    return overview


def _restamp_index_html_assets():
    """site/index.html (the SPA shell) is hand-maintained, not generated by
    this module, so it needs its own asset-cache-busting pass - see
    _stamp_asset_versions()'s docstring for why this matters."""
    path = os.path.join(ROOT, "site", "index.html")
    try:
        html = open(path, encoding="utf-8").read()
    except OSError:
        return
    stamped = _stamp_asset_versions(html)
    if stamped != html:
        _write_text(path, stamped)


def _restamp_js_imports():
    """_stamp_asset_versions() only rewrites href/src attributes in HTML - it
    never touches a JS file's own `import ... from './other.js'` specifiers.
    Combined with the immutable, one-year Cache-Control on /assets/* (see
    vercel.json), that left every cross-module import invisible to cache
    busting: app.js's own <script src> got a fresh ?v= each deploy, forcing a
    refetch of app.js, but its `import * as pages from './pages.js'` line
    pointed at the same URL forever, so a browser that had already cached the
    old pages.js kept running it - caught live as a wording fix (Affiliate ->
    Sponsored) that shipped to the server but kept rendering the old text for
    anyone who had visited before. Every module reachable this way (store.js
    behind nav-widgets.js/search.js/crypto-live.js/app.js/pages.js) had the
    same exposure.

    Processed leaves-first (files with no local imports get hashed first) so
    a file's own hash reflects its already-rewritten import lines, mirroring
    _stamp_asset_versions()'s content-hash approach but for import specifiers
    instead of HTML attributes. A stale query value on the very first run
    after this lands is harmless - Vercel serves static files by path, not by
    query string, and the next build's hash matches exactly since it reads
    back what this pass just wrote.
    """
    js_dir = os.path.join(ROOT, "site", "assets", "js")
    try:
        names = sorted(f for f in os.listdir(js_dir) if f.endswith(".js"))
    except OSError:
        return
    # Matches both `... from './x.js'` and the bare side-effect form
    # `import './x.js';` (app.js pulls in nav-widgets.js/search.js this way,
    # with no separate <script src> anywhere for the SPA shell to have
    # already cache-busted) - either keyword directly followed by the quote.
    import_re = re.compile(r"""((?:from|import)\s+['"]\./)([\w.-]+\.js)(?:\?v=[0-9a-f]+)?(['"])""")
    raw = {name: open(os.path.join(js_dir, name), encoding="utf-8").read() for name in names}
    deps = {
        name: {m.group(2) for m in import_re.finditer(content) if m.group(2) in raw}
        for name, content in raw.items()
    }

    order, done = [], set()

    def visit(name, stack):
        if name in done or name in stack:
            return
        stack.add(name)
        for dep in deps.get(name, ()):
            visit(dep, stack)
        stack.discard(name)
        done.add(name)
        order.append(name)

    for name in names:
        visit(name, set())

    hashes = {}
    for name in order:
        content = raw[name]

        def repl(m):
            target = m.group(2)
            h = hashes.get(target)
            return "%s%s?v=%s%s" % (m.group(1), target, h, m.group(3)) if h else m.group(0)

        new_content = import_re.sub(repl, content)
        if new_content != content:
            _write_text(os.path.join(js_dir, name), new_content)
        hashes[name] = hashlib.sha256(new_content.encode("utf-8")).hexdigest()[:10]


def _peers(b, built):
    """Nearest comparable brokers - same type, closest client count."""
    n = b["clients"].get("active_clients") or 0
    same = [x for x in built if x["id"] != b["id"] and x["profile"]["type"] == b["profile"]["type"]]
    same.sort(key=lambda x: abs((x["clients"].get("active_clients") or 0) - n))
    return [{"id": x["id"], "brand": x["profile"]["brand"],
             "clients": x["clients"].get("active_clients"),
             "reliability": (x.get("reliability") or {}).get("score"),
             "cost": (x.get("cost") or {}).get("monthly_total")} for x in same[:5]]


def _derive_tags(built, boards):
    """Factual badges derived from the leaderboards, not editorial opinion."""
    tags = {}
    board_tag = {
        "most_clients": ("Top 5 by clients", 5),
        "fastest_growing": ("Fastest growing", 5),
        "fewest_complaints": ("Low complaint rate", 5),
        "best_resolution": ("High resolution rate", 5),
        "cheapest_basket": ("Low cost", 5),
        "cheapest_fno": ("Low cost F&O", 5),
    }
    for bd in boards:
        label_n = board_tag.get(bd["key"])
        if not label_n:
            continue
        label, n = label_n
        for row in bd["rows"][:n]:
            tags.setdefault(row["id"], []).append(label)
    for b in built:
        if len(b["profile"]["segments"]) >= 4:
            tags.setdefault(b["id"], []).append("All segments")
        if b["profile"]["listed_company"]:
            tags.setdefault(b["id"], []).append("Listed company")
        if b["regulatory_flags"]["defaulter"]:
            tags.setdefault(b["id"], []).append("SEBI defaulter list")
    return tags


def build_ticker():
    """Emit site/data/ticker.json: the payload the rolling header polls.

    Separate from overview.json and deliberately small so it can be refreshed
    every minute (or streamed) without republishing the site.
    """
    ingest = read_json(os.path.join(INGEST_PATH), {}) or {}
    built = feeds.build(ingest)
    _carry_forward_stale_feeds(built)

    payload = {
        "generated_at": now_iso(),
        "order": feeds.FEED_ORDER,
        "feeds": built,
    }
    size = write_json(os.path.join(SITE_DATA, "ticker.json"), payload, compact=True)
    counts = " ".join("%s=%d" % (k, len(v.get("instruments") or [])) for k, v in built.items())
    log("ticker.json %.1f KB (%s)" % (size / 1024, counts), "ok")
    return payload


def _carry_forward_stale_feeds(built):
    """If this run's fetch came back with zero instruments for a feed,
    reuse whatever the site is already live-serving for that feed instead of
    publishing an empty ticker.

    data/ (the fetched-raw cache) is gitignored and every Vercel build starts
    from a fresh checkout, so there is no local "last successful fetch" to
    fall back on - and MCX's top-gainers/full-watch endpoints return nothing
    when there is no active session (a real empty result, not a bug), so
    empty happens routinely on non-trading days. NSE/BSE rarely hit this
    because their own upstream APIs keep returning last-session data outside
    trading hours. Mirrors the same carry-forward the live Cloud Run stream
    now does in server/quotes.py's Hub.seed_from_disk().
    """
    empty = [fid for fid, f in built.items() if not f.get("instruments")]
    if not empty or not SITE_URL:
        return
    try:
        req = urllib.request.Request(
            "%s/data/ticker.json" % SITE_URL, headers={"User-Agent": "brokerlens-build-carryforward/1"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            body = resp.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError("live ticker.json exceeded the size cap")
        live_feeds = (json.loads(body) or {}).get("feeds") or {}
    except Exception as exc:
        log("ticker.json: could not fetch live snapshot to carry forward %s: %s" % (empty, exc), "warn")
        return
    for fid in empty:
        prev = live_feeds.get(fid) or {}
        if prev.get("instruments"):
            built[fid]["instruments"] = prev["instruments"]
            built[fid]["as_of"] = prev.get("as_of")
            built[fid]["note"] = "Carried forward from the last successful fetch; %s did not respond on this run." % fid
            log("ticker.json: %s empty this run, carried forward %d instruments from the live site"
                % (fid, len(prev["instruments"])), "warn")


def build_crypto_ticker():
    """Emit site/data/crypto-ticker.json - same small/frequently-refreshed
    contract as build_ticker(), for the 28-coin Phase 1 crypto universe.
    Refreshed on the same cheap `pipeline.run ticker` cadence as the
    NSE/BSE/MCX legs, never baked into the static crypto pages themselves -
    the exact pattern the rest of this site already uses for anything that
    changes faster than a rebuild. Sourced from Binance when reachable,
    CoinGecko otherwise (Binance 451s every automated build/refresh
    environment this runs in - see pipeline/sources/crypto.py)."""
    ingest = read_json(os.path.join(INGEST_PATH), {}) or {}
    coins = ingest.get("crypto", {}).get("coins") or []
    payload = {
        "generated_at": now_iso(),
        "coins": [
            {"symbol": c["symbol"], "price_usd": c.get("price_usd"),
             "change_pct_24h": c.get("change_pct_24h"), "high_24h": c.get("high_24h"),
             "low_24h": c.get("low_24h"), "volume_24h_usd": c.get("volume_24h_usd"),
             "market_cap_rank": c.get("market_cap_rank")}
            for c in coins if c.get("price_usd") is not None
        ],
    }
    size = write_json(os.path.join(SITE_DATA, "crypto-ticker.json"), payload, compact=True)
    log("crypto-ticker.json %.1f KB (%d coins)" % (size / 1024, len(payload["coins"])), "ok")
    return payload


def build_crypto_history():
    """One small JSON file per coin (site/data/crypto-history/<symbol>.json),
    up to a year of real daily closing prices for that coin's chart - a
    separate file per symbol, fetched lazily only when that coin's own page
    is actually viewed, the same separation-of-concerns as ticker.json vs.
    the static pages themselves. A coin whose history fetch failed or is
    still rate-limited this run simply has no file yet; the chart says so
    rather than showing a guess."""
    ingest = read_json(os.path.join(INGEST_PATH), {}) or {}
    history = ingest.get("crypto", {}).get("history") or {}
    dest_dir = os.path.join(SITE_DATA, "crypto-history")
    os.makedirs(dest_dir, exist_ok=True)
    written = 0
    for symbol, points in history.items():
        if not points:
            continue
        payload = {"symbol": symbol, "generated_at": now_iso(), "candles": points}
        write_json(os.path.join(dest_dir, "%s.json" % symbol.lower()), payload, compact=True)
        written += 1
    log("crypto-history: %d coin files written" % written, "ok")


def build_equity_history(equity_history):
    """One small JSON file per NSE-listed stock (site/data/equity-history/
    <symbol-slug>.json), real daily OHLCV from NSE's own bhavcopy - see
    pipeline/sources/nse.py's equity_history(). Same lazy-per-page-fetch
    shape as build_crypto_history(), and the same honesty rule: a symbol
    with no file yet (delisted, newly listed, or this run's fetch simply
    didn't reach it) shows "not enough history yet" rather than a guess."""
    dest_dir = os.path.join(SITE_DATA, "equity-history")
    os.makedirs(dest_dir, exist_ok=True)
    written = 0
    for symbol, points in (equity_history or {}).items():
        if not points:
            continue
        slug = _stock_slug(symbol)
        if not slug:
            continue
        payload = {"symbol": symbol, "generated_at": now_iso(), "candles": points}
        write_json(os.path.join(dest_dir, "%s.json" % slug), payload, compact=True)
        written += 1
    log("equity-history: %d stock files written" % written, "ok")


def build_market_movers():
    """site/data/market-movers.json - NSE's own gainers/losers/most-active
    rows, the same real data _write_leaderboards_page() bakes into the
    server-rendered /leaderboards page, published as its own small file so
    pages.js's client-side leaderboards() can render the identical boards
    after hydration instead of replacing them with the old broker-only
    view. Crypto's equivalent boards need no separate file - crypto-ticker.json
    already has every coin's price, 24h change and market-cap rank, which is
    all client-side sorting needs."""
    ingest = read_json(os.path.join(INGEST_PATH), {}) or {}
    nse_live = (ingest.get("nse") or {}).get("live") or {}

    def rows(key):
        return [r for r in (nse_live.get(key) or []) if r.get("symbol") and r.get("last") is not None][:10]

    payload = {
        "generated_at": now_iso(),
        "gainers": rows("gainers"),
        "losers": rows("losers"),
        "most_active": rows("quotes"),
    }
    size = write_json(os.path.join(SITE_DATA, "market-movers.json"), payload, compact=True)
    log("market-movers.json %.1f KB (gainers=%d losers=%d most_active=%d)"
        % (size / 1024, len(payload["gainers"]), len(payload["losers"]), len(payload["most_active"])), "ok")
    return payload


def _write_sources(cfg, ingest, sample_flags):
    rows = []
    status = ingest.get("_status") or {}
    for sid, s in (cfg.get("sources") or {}).items():
        rows.append({
            "id": sid, "publisher": s.get("publisher"), "title": s.get("title"),
            "url": s.get("url"), "cadence": s.get("cadence"),
            "verified": s.get("verified"), "notes": s.get("notes"),
            "last_run": status.get(sid, {}).get("last_run"),
            "last_status": status.get(sid, {}).get("status"),
        })
    payload = {"generated_at": now_iso(), "sources": rows,
               "licensing": cfg.get("licensing"), "sample_data": sample_flags}
    write_json(os.path.join(SITE_DATA, "sources.json"), payload)
    return payload


def _write_algo(brokers_cfg):
    """Emit site/data/algo.json: the curated algo-platform directory.

    Entirely curated (config/algo_platforms.json), so every record is published
    with provenance:'curated' and the page must say so. `works_with` broker ids
    are validated against brokers_master and enriched with the brand name so the
    front end can cross-link to /broker/:id without a second lookup.
    """
    cfg = read_json(os.path.join(CONFIG, "algo_platforms.json"), {}) or {}
    brands = {b["id"]: b.get("brand") for b in brokers_cfg}
    platforms = []
    for p in cfg.get("platforms") or []:
        links, dropped = [], []
        for bid in p.get("works_with") or []:
            (links if bid in brands else dropped).append(bid)
        if dropped:
            log("algo: %s references unknown broker id(s): %s"
                % (p.get("id"), ", ".join(dropped)), "warn")
        platforms.append(dict(p, works_with=[
            {"id": bid, "brand": brands[bid]} for bid in links
        ], provenance="curated"))

    payload = {
        "generated_at": now_iso(),
        "last_reviewed": cfg.get("last_reviewed"),
        "provenance": "curated",
        "categories": cfg.get("categories") or {},
        "count": len(platforms),
        "platforms": platforms,
    }
    size = write_json(os.path.join(SITE_DATA, "algo.json"), payload, compact=True)
    log("algo.json %.1f KB, %d platforms" % (size / 1024, len(platforms)), "ok")
    return payload


def _write_timings():
    """Emit site/data/timings.json: curated session timings for the nav mega menu."""
    cfg = read_json(os.path.join(CONFIG, "market_timings.json"), {}) or {}
    payload = {
        "generated_at": now_iso(),
        "last_reviewed": cfg.get("last_reviewed"),
        "provenance": "curated",
        "timezone": cfg.get("timezone") or "Asia/Kolkata",
        "notes": cfg.get("notes") or [],
        "holiday_links": cfg.get("holiday_links") or [],
        "exchanges": cfg.get("exchanges") or [],
    }
    size = write_json(os.path.join(SITE_DATA, "timings.json"), payload, compact=True)
    log("timings.json %.1f KB, %d exchanges" % (size / 1024, len(payload["exchanges"])), "ok")


CATEGORY_LABELS = {
    "stock_broker": "Stock broker",
    "commodity_broker": "Commodity broker",
    "dp_cdsl": "Depository participant (CDSL)",
    "dp_nsdl": "Depository participant (NSDL)",
}

_REGISTRY_PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="/assets/js/theme-init.js"></script>
<title>%(title)s</title>
<meta name="description" content="%(description)s">
<link rel="canonical" href="%(canonical)s">
<meta name="theme-color" content="#2f4a8f">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/assets/css/app.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BrokerLens">
<meta property="og:locale" content="en_IN">
<meta property="og:url" content="%(canonical)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(description)s">
<script type="application/ld+json">%(jsonld)s</script>
</head>
<body>
<header class="site"><div class="wrap nav">
  <a class="brand" href="/">
    <svg class="brand-logo" viewBox="0 0 512 512" width="26" height="26" role="img" aria-label="BrokerLens">
      <defs><clipPath id="bl-lens-reg"><circle cx="256" cy="256" r="143"/></clipPath></defs>
      <g fill="none" stroke="var(--accent)" stroke-width="30" stroke-linecap="round">
        <path d="M50 369 L84 359" opacity=".38"/><path d="M18 379 L30 375" opacity=".18"/>
        <path d="M438 161 L470 149" opacity=".38"/><path d="M486 143 L496 140" opacity=".18"/>
      </g>
      <circle cx="256" cy="256" r="166" fill="none" stroke="var(--accent)" stroke-width="46"/>
      <path d="M-24 392 L146 340 L212 288 L272 336 L360 190 L528 128" fill="none" stroke="var(--up)"
            stroke-width="46" stroke-linecap="round" stroke-linejoin="round" clip-path="url(#bl-lens-reg)"/>
    </svg>
    <span>BrokerLens</span>
  </a>
  <button class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="navlinks"
          aria-label="Menu"><span aria-hidden="true">&#9776;</span></button>
  <nav class="nav-links" id="navlinks">
    <button class="mega-toggle" id="markets-toggle" aria-expanded="false" aria-controls="mega-markets">Brokers <span aria-hidden="true">&#9662;</span></button>
    <a href="/compare">Compare</a>
    <a href="/leaderboards">Movers</a>
    <a href="/calculators/">Calculators</a>
    <a href="/registry">SEBI registry</a>
    <a href="/algo">Algo platforms</a>
    <a href="/ipo/">IPO</a>
    <a href="/reports/state-of-indian-broking-2026/">Reports</a>
    <button class="mega-toggle" id="timings-toggle" aria-expanded="false" aria-controls="mega-timings">Market timings <span aria-hidden="true">&#9662;</span></button>
  </nav>
  <button class="icon-btn" id="search-toggle" title="Search (Ctrl+K)" aria-label="Search" aria-haspopup="dialog" aria-controls="search-overlay"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
  <button class="icon-btn" id="theme-toggle" title="Switch theme" aria-label="Switch theme">&#9680;</button>
</div>
<div class="mega" id="mega-timings" hidden>
  <div class="wrap">
    <div id="mega-timings-body" class="mega-grid"><div class="small faint" style="padding:16px 0">Loading timings...</div></div>
  </div>
</div>
<div class="mega" id="mega-markets" hidden>
  <div class="wrap">
    <div class="markets-list">
      <a href="/brokers"><span>India</span><span class="badge badge-up">Live</span></a>
      <a href="/crypto/"><span>Crypto</span><span class="badge badge-up">Live</span></a>
      <a href="/coming-soon/us"><span>US</span><span class="badge badge-warn">Coming soon</span></a>
      <a href="/coming-soon/gcc"><span>GCC</span><span class="badge badge-warn">Coming soon</span></a>
    </div>
  </div>
</div>
</header>
<div class="search-overlay" id="search-overlay" hidden>
  <div class="search-modal" role="dialog" aria-modal="true" aria-label="Search BrokerLens">
    <div class="search-input-row">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
      <input type="text" id="search-input" placeholder="Search brokers, stocks, funds, calculators..." autocomplete="off" aria-label="Search BrokerLens">
      <kbd class="search-esc">Esc</kbd>
    </div>
    <div id="search-results" class="search-results"></div>
  </div>
</div>
<main class="wrap" style="padding-top:24px;padding-bottom:24px">
"""

_REGISTRY_PAGE_FOOT = f"""</main>
<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">%(source_note)s</p>
  <p class="small"><a href="/registry">Search the full SEBI registry →</a> ·
  <a href="/brokers">Brokers tracked in depth →</a> ·
  <a href="/brokers-by/type/">Brokers by type →</a> ·
  <a href="/brokers-by/segment/">Brokers by segment →</a> ·
  <a href="/brokers-by/city/">Brokers by city →</a> ·
  <a href="/stocks/">Browse stocks A-Z →</a> ·
  <a href="/funds-by/">Browse mutual funds by AMC →</a> ·
  <a href="/etfs/">Browse ETFs →</a> · <a href="/ipo/">IPO tracker →</a> · <a href="/">BrokerLens home →</a></p>
  <p class="small"><a href="/about">About</a> · <a href="/contact">Contact</a> ·
  <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> · <a href="/privacy-policy">Privacy policy</a> ·
  <a href="/terms-of-service">Terms of service</a></p>
</div></footer>
<script type="module" src="/assets/js/nav-widgets.js"></script>
<script type="module" src="/assets/js/search.js"></script>
</body>
</html>
"""
_REGISTRY_PAGE_HEAD = _stamp_asset_versions(_REGISTRY_PAGE_HEAD)
_REGISTRY_PAGE_FOOT = _stamp_asset_versions(_REGISTRY_PAGE_FOOT)

# Six routes (brokers, compare, leaderboards, registry, algo, calculator) are
# genuinely interactive tools, not just content - unlike every other static
# family in this file, they need to stay fully interactive (sort, filter,
# live search) for a visitor who lands on them directly, not just one who
# clicked in from an already-loaded SPA page. So this is a hybrid shell, not
# a plain static page: same real content-first approach as _REGISTRY_PAGE_HEAD
# for a crawler or first paint, but it also boots the full app.js/pages.js SPA
# (mirroring site/index.html's own shell exactly), which re-renders the same
# route with live data moments later. A direct hit gets real content
# immediately with no skeleton flash; an in-app navigation is untouched.
_APP_SHELL_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="/assets/js/theme-init.js"></script>
<title>%(title)s</title>
<meta name="description" content="%(description)s">
<link rel="canonical" href="%(canonical)s">
<meta name="theme-color" content="#2f4a8f">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/assets/css/app.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BrokerLens">
<meta property="og:locale" content="en_IN">
<meta property="og:url" content="%(canonical)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(description)s">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">%(jsonld)s</script>
</head>
<body>
<div class="ticker" aria-label="Live market prices">
  <div class="ticker-bar">
    <div class="exch-picker">
      <span class="mkt-dot" id="exch-dot" aria-hidden="true"></span>
      <select id="exch-select" aria-label="Choose ticker feed">
        <option value="NSE">NSE</option>
      </select>
      <span class="exch-status xs" id="exch-status"></span>
    </div>
    <div class="ticker-rail" id="ticker-rail"><div class="ticker-track" id="ticker-track"></div></div>
  </div>
</div>

<header class="site">
  <div class="wrap nav">
    <a class="brand" href="/" data-link>
      <svg class="brand-logo" viewBox="0 0 512 512" width="26" height="26" role="img" aria-label="BrokerLens">
        <defs><clipPath id="bl-lens-nav"><circle cx="256" cy="256" r="143"/></clipPath></defs>
        <g fill="none" stroke="var(--accent)" stroke-width="30" stroke-linecap="round">
          <path d="M50 369 L84 359" opacity=".38"/><path d="M18 379 L30 375" opacity=".18"/>
          <path d="M438 161 L470 149" opacity=".38"/><path d="M486 143 L496 140" opacity=".18"/>
        </g>
        <circle cx="256" cy="256" r="166" fill="none" stroke="var(--accent)" stroke-width="46"/>
        <path d="M-24 392 L146 340 L212 288 L272 336 L360 190 L528 128" fill="none" stroke="var(--up)"
              stroke-width="46" stroke-linecap="round" stroke-linejoin="round" clip-path="url(#bl-lens-nav)"/>
      </svg>
      <span>BrokerLens</span>
    </a>
    <button class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="navlinks"
            aria-label="Menu"><span aria-hidden="true">&#9776;</span></button>
    <nav class="nav-links" id="navlinks">
      <button class="mega-toggle" id="markets-toggle" aria-expanded="false" aria-controls="mega-markets">Brokers <span aria-hidden="true">&#9662;</span></button>
      <a href="/compare" data-link>Compare</a>
      <a href="/leaderboards" data-link>Movers</a>
      <a href="/calculators/">Calculators</a>
      <a href="/registry" data-link>SEBI registry</a>
      <a href="/algo" data-link>Algo platforms</a>
      <a href="/ipo/">IPO</a>
      <a href="/reports/state-of-indian-broking-2026/">Reports</a>
      <button class="mega-toggle" id="timings-toggle" aria-expanded="false" aria-controls="mega-timings">Market timings <span aria-hidden="true">&#9662;</span></button>
    </nav>
    <button class="icon-btn" id="search-toggle" title="Search (Ctrl+K)" aria-label="Search" aria-haspopup="dialog" aria-controls="search-overlay"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
    <button class="icon-btn" id="theme-toggle" title="Switch theme" aria-label="Switch theme">&#9680;</button>
  </div>
  <div class="mega" id="mega-timings" hidden>
    <div class="wrap">
      <div id="mega-timings-body" class="mega-grid"><div class="small faint" style="padding:16px 0">Loading timings&hellip;</div></div>
    </div>
  </div>
  <div class="mega" id="mega-markets" hidden>
    <div class="wrap">
      <div class="markets-list">
        <a href="/brokers" data-link><span>India</span><span class="badge badge-up">Live</span></a>
        <a href="/crypto/"><span>Crypto</span><span class="badge badge-up">Live</span></a>
        <a href="/coming-soon/us" data-link><span>US</span><span class="badge badge-warn">Coming soon</span></a>
        <a href="/coming-soon/gcc" data-link><span>GCC</span><span class="badge badge-warn">Coming soon</span></a>
      </div>
    </div>
  </div>
</header>
<div class="search-overlay" id="search-overlay" hidden>
  <div class="search-modal" role="dialog" aria-modal="true" aria-label="Search BrokerLens">
    <div class="search-input-row">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
      <input type="text" id="search-input" placeholder="Search brokers, stocks, funds, calculators..." autocomplete="off" aria-label="Search BrokerLens">
      <kbd class="search-esc">Esc</kbd>
    </div>
    <div id="search-results" class="search-results"></div>
  </div>
</div>

<main id="app" class="wrap" style="padding-top:24px;padding-bottom:24px">
"""

_APP_SHELL_FOOT = """</main>

<footer class="site">
  <div class="wrap">
    <div class="cols">
      <div>
        <div class="brand" style="margin-bottom:8px">
          <svg class="brand-logo" viewBox="0 0 512 512" width="26" height="26" aria-hidden="true">
            <defs><clipPath id="bl-lens-foot2"><circle cx="256" cy="256" r="143"/></clipPath></defs>
            <g fill="none" stroke="var(--accent)" stroke-width="30" stroke-linecap="round">
              <path d="M50 369 L84 359" opacity=".38"/><path d="M18 379 L30 375" opacity=".18"/>
              <path d="M438 161 L470 149" opacity=".38"/><path d="M486 143 L496 140" opacity=".18"/>
            </g>
            <circle cx="256" cy="256" r="166" fill="none" stroke="var(--accent)" stroke-width="46"/>
            <path d="M-24 392 L146 340 L212 288 L272 336 L360 190 L528 128" fill="none" stroke="var(--up)"
                  stroke-width="46" stroke-linecap="round" stroke-linejoin="round" clip-path="url(#bl-lens-foot2)"/>
          </svg> BrokerLens</div>
        <p class="small">Broker statistics assembled from primary NSE, BSE and SEBI disclosures. We publish facts and
        normalised ratios so you can compare brokers yourself.</p>
        <p class="small"><a href="mailto:%(contact_email)s">%(contact_email)s</a></p>
      </div>
      <div>
        <h5>Compare</h5>
        <ul>
          <li><a href="/brokers" data-link>All brokers</a></li>
          <li><a href="/brokers-by/type/">Brokers by type</a></li>
          <li><a href="/brokers-by/segment/">Brokers by segment</a></li>
          <li><a href="/brokers-by/city/">Brokers by city</a></li>
          <li><a href="/leaderboards" data-link>Movers</a></li>
          <li><a href="/calculator" data-link>Cost calculator</a></li>
          <li><a href="/registry" data-link>SEBI registry</a></li>
          <li><a href="/algo" data-link>Algo platforms</a></li>
          <li><a href="/ipo/">IPO tracker</a></li>
        </ul>
      </div>
      <div>
        <h5>Data</h5>
        <ul>
          <li><a href="/methodology" data-link>Methodology</a></li>
          <li><a href="/sources" data-link>Sources &amp; lineage</a></li>
          <li><a href="/reports/state-of-indian-broking-2026/">State of Indian Broking, 2026</a></li>
          <li><a href="/feed.xml">RSS feed</a></li>
          <li><a href="/sitemap.xml">Sitemap</a></li>
        </ul>
      </div>
      <div>
        <h5>Markets</h5>
        <ul>
          <li><a href="/stocks/">Browse stocks A-Z</a></li>
          <li><a href="/funds-by/">Browse mutual funds by AMC</a></li>
          <li><a href="/etfs/">Browse ETFs</a></li>
          <li><a href="/calculators/">Financial calculators</a></li>
        </ul>
      </div>
      <div>
        <h5>Company</h5>
        <ul>
          <li><a href="/about" data-link>About</a></li>
          <li><a href="/contact" data-link>Contact</a></li>
          <li><a href="/privacy-policy" data-link>Privacy policy</a></li>
          <li><a href="/terms-of-service" data-link>Terms of service</a></li>
        </ul>
      </div>
    </div>
    <div class="disclaimer">
      <strong>Not investment advice.</strong> BrokerLens is an information service. We are not a SEBI-registered
      investment adviser or research analyst and we do not recommend any broker, security or strategy. Figures are
      reproduced from exchange and regulator disclosures and may lag their source. Verify anything material with the
      broker and with SEBI before acting on it. Brokerage figures exclude statutory charges (STT, stamp duty, exchange
      transaction charges, SEBI turnover fees and GST), which are identical across brokers for the same trade.
    </div>
  </div>
</footer>

<script type="module" src="/assets/js/app.js"></script>
</body>
</html>
"""
_APP_SHELL_HEAD = _stamp_asset_versions(_APP_SHELL_HEAD)

_APP_SHELL_FOOT = _stamp_asset_versions(_APP_SHELL_FOOT) % {"contact_email": CONTACT_EMAIL}


def _source_note(claim):
    """Every static page's footer states, in plain language, exactly what it
    is (and isn't). The claim differs by page type - SEBI's register, NSE's
    listed-securities master and NSE's own index files are three different
    sources, and stating the wrong one on a page is a factual error, not a
    stylistic one - so this is never reused verbatim across page types."""
    return ("%s It is not curated, scored or ranked, and nothing on it is investment advice. "
            "BrokerLens is not a SEBI-registered investment adviser or research analyst." % claim)


_PROV_DOT_TITLE = {
    "primary": "Sourced from a primary exchange or regulator feed",
    "sample": "SAMPLE data (not a real figure, pending first ingest)",
    "curated": "Hand-curated or broker-supplied, not regulator-verified",
    "none": "Not available",
}


def _mark_color(id_):
    """Python port of store.js's markColor() - identical hash so a broker's
    initials-avatar colour matches exactly whether the page was server- or
    client-rendered."""
    h = 0
    for ch in str(id_):
        h = (h * 31 + ord(ch)) % 360
    return "hsl(%d 42%% 42%%)" % h


def _initials(name):
    """Python port of store.js's initials()."""
    words = [w for w in re.split(r"[\s.]+", str(name or "?")) if w]
    return "".join(w[0].upper() for w in words[:2])


def _mark_html(id_, name, size=26):
    """Python port of pages.js's mark() - the colored initials-avatar square
    shown next to a broker/platform name."""
    return (
        '<span style="width:%dpx;height:%dpx;border-radius:6px;flex:none;display:grid;place-items:center;'
        'background:%s;color:#fff;font-size:%dpx;font-weight:700">%s</span>'
    ) % (size, size, _mark_color(id_), round(size * 0.42), _esc(_initials(name)))


def _indian_grouping(n):
    """en-IN digit grouping (lakh/crore: 2s after the first 3), matching
    what n.toLocaleString('en-IN') produces in every JS number formatter
    this file's Python renderers need to match exactly."""
    s = str(int(round(abs(n))))
    if len(s) <= 3:
        return s
    last3, rest = s[-3:], s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts) + "," + last3


def _count_html(n):
    """Python port of store.js's count()."""
    if n is None:
        return "-"
    a = abs(n)
    if a >= 1e7:
        return "%.2f Cr" % (n / 1e7)
    if a >= 1e5:
        return "%.2f L" % (n / 1e5)
    sign = "-" if n < 0 else ""
    return sign + _indian_grouping(n)


def _full_html(n):
    """Python port of store.js's full()."""
    return "-" if n is None else _indian_grouping(n) if n >= 0 else "-" + _indian_grouping(n)


def _pct_html(n, sign=True, decimals=2):
    """Python port of store.js's pct()."""
    if n is None:
        return "-"
    s = "+" if n > 0 and sign else ""
    return "%s%.*f%%" % (s, decimals, n)


def _inr_html(n, decimals=None):
    """Python port of store.js's inr()."""
    if n is None:
        return "-"
    a, sign = abs(n), ("-" if n < 0 else "")
    if a >= 1e7:
        return "%s&#8377;%.*f Cr" % (sign, decimals if decimals is not None else 2, a / 1e7)
    if a >= 1e5:
        return "%s&#8377;%.*f L" % (sign, decimals if decimals is not None else 2, a / 1e5)
    if a >= 1e3:
        return "%s&#8377;%s" % (sign, _indian_grouping(a))
    return "%s&#8377;%.*f" % (sign, decimals if decimals is not None else 0, a)


def _cls_class(n):
    """Python port of store.js's cls() - the up/down CSS class."""
    return "" if n is None else "up" if n > 0 else "down" if n < 0 else ""


def _fmt_board_html(bd, v):
    """Python port of pages.js's fmtBoard()."""
    if v is None:
        return "-"
    unit = bd.get("unit")
    if unit == "clients":
        return _count_html(v)
    if unit == "%":
        return _pct_html(v)
    if unit == "bps":
        return "%s%.0f" % ("+" if v > 0 else "", v)
    if unit == "INR/month":
        return _inr_html(v, decimals=0)
    if unit == "/100":
        return "%.1f" % v
    return "%.2f" % v


def _safe_url(url):
    """Python port of store.js's safeUrl() (the allowlist check only - the
    escaping itself still goes through _esc() at the call site, matching
    every other href in this file). Only http(s) survives; javascript:,
    data:, protocol-relative and anything else is refused."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw)
    if cleaned.startswith("//") or not re.match(r"^https?://", cleaned, re.I):
        return ""
    return cleaned


def _broker_badge_html(b):
    """Python port of pages.js's badge() - `b` is one row from overview.json's
    `brokers` list (the same shape passed to dirRow()/dirRowSimple())."""
    out = []
    if b.get("tier") == "featured":
        out.append('<span class="badge badge-featured">Featured</span>')
    elif b.get("claimed"):
        out.append('<span class="badge badge-verified">Claimed</span>')
    if b.get("verified"):
        out.append('<span class="badge badge-verified" title="Legal entity and SEBI registration matched to '
                    'the SEBI register">SEBI &#10003;</span>')
    if b.get("flagged"):
        out.append('<span class="badge badge-warn" title="Named in an exchange circular or on the SEBI '
                    'defaulter list">&#9873; Flagged</span>')
    return " ".join(out)


def _prov_dot_html(kind):
    """Python port of store.js's provDot() - same three-tier trust indicator
    (primary/curated/sample/none) rendered identically on both the SPA and
    these static pages, so a visitor sees one consistent visual language
    regardless of which rendering path served the page."""
    k = ("primary" if kind in ("nse", "sebi_registry", "sebi_annexure_b", "primary")
         else "sample" if kind == "sample"
         else "none" if kind is None
         else "curated")
    return '<span class="dot-src %s" title="%s"></span>' % (k, _PROV_DOT_TITLE[k])


def _breadcrumb(trail):
    """One shared breadcrumb builder for both the visible trail and its
    BreadcrumbList JSON-LD, so the two can never drift apart the way two
    hand-written copies eventually would. `trail` is [(label, url|None), ...]
    with the current page last (url=None, not a link to itself).

    Also a real, previously-missing internal-link path: before this, a
    visitor (or crawler) landing on a leaf page like a stock or fund had no
    way back to its parent directory except the site-wide footer links.
    """
    parts = []
    for label, url in trail:
        if url:
            parts.append('<a href="%s">%s</a>' % (_esc(url), _esc(label)))
        else:
            parts.append('<span aria-current="page">%s</span>' % _esc(label))
    html = ('<nav class="breadcrumb" aria-label="Breadcrumb">'
            + '<span class="sep"> &rsaquo; </span>'.join(parts) + '</nav>')
    jsonld = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            dict({"@type": "ListItem", "position": i + 1, "name": label},
                 **({"item": SITE_URL + url} if url else {}))
            for i, (label, url) in enumerate(trail)
        ],
    }
    return html, jsonld


def _write_registry_pages(reg_rows):
    """One static, server-rendered page per SEBI-registered entity.

    Everything else on this site is a client-rendered SPA: a crawler that
    cannot execute JS - including every current AI answer engine - sees an
    empty <main id="app"> for every route. These pages are deliberately plain
    static HTML with no script tag at all, so the ~1,700 entities that are not
    one of the 48 tracked in depth are actually indexable, and so the highest-
    volume, lowest-competition search intent this site can serve ("is
    <legal name> SEBI registered") has an answer that exists outside
    JavaScript. Links off this page are plain <a> (no data-link): there is no
    app.js here to intercept the click, so a normal browser navigation to the
    SPA is exactly what should happen.
    """
    base = os.path.join(SITE_DATA, "..", "sebi-registry")
    written = 0
    keep = {r["slug"] for r in reg_rows if r.get("slug")}
    pruned = _prune_stale_dirs(base, keep)
    for r in reg_rows:
        slug = r.get("slug")
        if not slug:
            continue
        name = r.get("name") or "Unnamed entity"
        cats = [CATEGORY_LABELS.get(c, c) for c in (r.get("categories") or [])]
        canonical = "%s/sebi-registry/%s/" % (SITE_URL, slug)

        title = "%s: SEBI Registration | BrokerLens" % name
        description = ("%s: SEBI registration number, category, exchange memberships and validity, "
                       "sourced from SEBI's recognised-intermediary register." % name)[:300]

        org_jsonld = {
            "@type": "Organization",
            "name": name,
            "url": canonical,
        }
        if r.get("trade_name"):
            org_jsonld["alternateName"] = r["trade_name"]
        if r.get("reg"):
            org_jsonld["identifier"] = r["reg"]
        if r.get("city"):
            org_jsonld["address"] = {"@type": "PostalAddress", "addressLocality": r["city"], "addressCountry": "IN"}
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("SEBI registry", "/registry"), (name, None),
        ])
        jsonld = {"@context": "https://schema.org", "@graph": [org_jsonld, crumb_jsonld]}

        def fact(raw):
            # _esc() stringifies before escaping, so _esc(None) == "None" (a
            # truthy string) - the missing-value check must happen first.
            return _esc(raw) if raw else "Not disclosed"

        facts = [
            ("SEBI registration number", fact(r.get("reg"))),
            ("Category", fact(", ".join(cats))),
            ("Exchange / register memberships", fact(", ".join(r.get("exchanges") or []))),
            ("City", fact(r.get("city"))),
            ("Validity", fact(r.get("validity"))),
        ]
        facts_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div>'
            '<div style="margin-top:2px">%s</div></div>' % (label, value)
            for label, value in facts
        )

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": _esc(description),
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + (('<p class="muted">Trading as %s</p>' % _esc(r["trade_name"])) if r.get("trade_name") else "")
            + '<p class="muted" style="max-width:70ch">This entity is registered with SEBI but is not one of the '
              'brokers BrokerLens tracks in depth, so no client, complaint or cost data is shown here - only what '
              'the regulator itself discloses.</p>'
            + '<div class="card" style="margin-top:16px;padding:16px">' + facts_html + '</div>'
            + '<p class="xs faint" style="margin-top:12px">Source: SEBI recognised-intermediary register.</p>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page is generated directly from SEBI's recognised-intermediary register.")}

        dest_dir = os.path.join(base, slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    log("registry pages: %d static entity pages written%s" % (
        written, (", %d stale pruned" % pruned) if pruned else ""), "ok")


TYPE_LABEL = {"discount": "Discount", "full_service": "Full service", "bank_backed": "Bank-backed"}
SEGMENT_LABEL = {
    "equity_cash": "Equity delivery", "equity_fno": "Equity F&O",
    "currency": "Currency", "commodity": "Commodity",
}
BROKER_HUB_DIM_NOUN = {
    "type": "Stock brokers by type",
    "segment": "Brokers by registered segment",
    "city": "Stock brokers by head-office city",
}
BROKER_HUB_DIM_INTRO = {
    "type": "Every broker type BrokerLens tracks: bank-backed, discount and full-service.",
    "segment": "Every trading segment BrokerLens tracks broker registrations for: equity cash, equity F&O, currency and commodity.",
    "city": "Every head-office city with a BrokerLens-tracked broker.",
}


def _broker_facts_html(b):
    """The server-rendered <main> content for one broker's static page.

    Deliberately mirrors pages.js's broker() renderer in substance (same
    facts, same production-mode honesty about what isn't published yet) but
    stays plain HTML with no canvas/chart markup - charts need JS and have no
    server-rendered equivalent. Once app.js boots client-side, its own
    broker() render replaces this with the full interactive version; this is
    what a crawler, an answer engine, or a visitor with JS disabled actually
    sees, and it is also what paints first (better LCP) for everyone else.
    """
    p, c, k = b["profile"], b.get("clients") or {}, b.get("complaints") or {}
    rel, cost, flags = b.get("reliability") or {}, b.get("cost") or {}, b.get("regulatory_flags") or {}

    def fact(raw):
        return _esc(raw) if raw else None

    identity_rows = [
        ("Legal name", fact(p.get("legal_name"))),
        ("SEBI registration", fact(p.get("sebi_reg_no")) or ("Not yet matched to the SEBI register" if not p.get("legal_name_verified") else None)),
        ("Type", fact(TYPE_LABEL.get(p.get("type"), p.get("type")))),
        ("Segments", fact(", ".join(SEGMENT_LABEL.get(s, s) for s in (p.get("segments") or [])))),
        ("Head office", fact(p.get("hq"))),
        ("Founded", fact(p.get("founded"))),
    ]
    identity_html = "".join(
        '<div class="mega-seg"><div class="mega-seg-label">%s</div><div style="margin-top:2px">%s</div></div>'
        % (label, value) for label, value in identity_rows if value
    )

    rel_html = (
        '<div class="card" style="padding:16px"><div class="stat-label">Reliability score</div>'
        '<div class="stat-value">%.1f<span class="muted" style="font-size:var(--fs-base)">/100</span></div>'
        '<div class="xs faint" style="margin-top:6px">confidence: %s</div></div>'
        % (rel["score"], _esc(rel.get("confidence") or "none"))
        if rel.get("score") is not None else
        '<div class="pending"><strong>Reliability score not available</strong>'
        'Not enough regulator-sourced inputs exist yet to compute one.</div>'
    )

    client_html = (
        '<div class="mega-seg"><div class="mega-seg-label">Active clients</div>'
        '<div style="margin-top:2px">%s as of %s</div></div>'
        % (_esc(format(c["active_clients"], ",")), _esc(c.get("as_of") or ""))
        if c.get("active_clients") is not None else
        '<div class="pending"><strong>Active clients not published yet</strong>'
        'NSE publishes member-wise active-client counts monthly; this figure is populated once that '
        'ingestion is live, never estimated.</div>'
    )

    complaint_html = (
        '<div class="mega-seg"><div class="mega-seg-label">Complaints per 10,000 clients (12 months)</div>'
        '<div style="margin-top:2px">%.2f</div></div>' % k["per_10k_clients_12m"]
        if k.get("per_10k_clients_12m") is not None else
        '<div class="pending"><strong>Complaint record not published yet</strong>'
        'Sourced from each broker\'s SEBI Annexure-B disclosure once crawled; shown only when a full '
        '12-month window is confirmed.</div>'
    )

    cost_html = (
        '<div class="mega-seg"><div class="mega-seg-label">Monthly cost, standard basket</div>'
        '<div style="margin-top:2px">%s</div></div>' % _esc("Rs %.2f" % cost["monthly_total"])
        if cost.get("monthly_total") is not None else
        '<div class="pending"><strong>Charges not verified yet</strong>'
        'Shown only once traced to the broker\'s own disclosed rate card.</div>'
    )

    flag_html = ""
    if flags.get("defaulter"):
        flag_html = (
            '<div class="banner" style="margin-top:16px"><span>&#9873;</span><div>'
            '<strong>This entity appears on SEBI\'s defaulter / expelled broker list.</strong> '
            'Matched names: %s. Verify directly with SEBI before proceeding.</div></div>'
            % _esc("; ".join(flags.get("defaulter_names") or []))
        )

    website = p.get("website") or ""
    website_html = (
        '<a class="btn btn-sm" href="%s" rel="nofollow noopener external" target="_blank">Website &#8599;</a>'
        % _esc(website) if website.startswith(("http://", "https://")) else ""
    )

    return (
        '<h1 style="margin-top:16px">%s</h1>' % _esc(p.get("brand") or b["id"])
        + '<p class="muted small">%s</p>' % _esc(p.get("legal_name") or "")
        + flag_html
        + '<div class="row-wrap" style="margin-top:10px">%s'
          '<a class="btn btn-sm" href="/compare?b=%s">Compare</a></div>'
          % (website_html, _esc(b["id"]))
        + '<div class="grid g4" style="margin-top:16px">' + client_html + complaint_html + cost_html + rel_html + '</div>'
        + '<div class="section-title" style="margin-top:20px"><h2>Registration and identity</h2></div>'
        + '<div class="grid g3">' + identity_html + '</div>'
        + '<p class="xs faint" style="margin-top:16px">Source: SEBI recognised-intermediary register and, where '
          'noted above, NSE/BSE/SEBI primary disclosures. <a href="/methodology">Methodology</a> &middot; '
          '<a href="/sources">Sources &amp; lineage</a> &middot; <a href="/brokers">All brokers</a></p>'
    )


def _write_broker_pages(built):
    """Static, server-rendered pages at the SAME /broker/:id URL the SPA already
    uses - not a sibling path like the registry pages needed.

    That's safe here in a way it wasn't for /registry: /broker/:id has no bare
    /broker route to protect (every valid request under this prefix names a
    real, existing id), so writing site/broker/<id>/index.html cannot shadow
    any route the way site/registry/ once did. The file also keeps the exact
    same <script src="/assets/js/app.js"> as the shell, so a JS-capable visitor
    gets this static content first (fast LCP, real content for crawlers) and
    then transparently upgrades to the full interactive profile (charts,
    theme-aware redraws) via the same client route that already renders it for
    in-app navigation - this is progressive enhancement, not a fork to keep in
    sync by hand.

    Built from the shared _APP_SHELL_HEAD/_APP_SHELL_FOOT templates (same as
    every other hybrid page: /compare, /brokers, /leaderboards, ...), not by
    string-replacing into a live copy of site/index.html. That used to be a
    same-file skeleton swap, but _prerender_home() permanently bakes real
    content into site/index.html's <main>, so once that ran, this function's
    expected-skeleton match could never succeed again on any later build -
    all 48 broker pages silently stopped regenerating and every one of them
    served the homepage's title/canonical/JSON-LD to crawlers instead of its
    own. The shared templates are immutable module-level strings, not a file
    another writer can mutate first.
    """
    written = 0
    for b in built:
        bid, brand = b["id"], b["profile"].get("brand") or b["id"]
        canonical = "%s/broker/%s/" % (SITE_URL, bid)
        title = "%s: active clients, complaints and charges | BrokerLens" % brand
        description = (
            "%s: active client count, market share, SEBI complaint record, regulatory registrations "
            "and cost, from primary NSE, BSE and SEBI disclosures." % brand
        )[:300]
        crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Brokers", "/brokers"), (brand, None)])
        entity_jsonld = {"@type": "FinancialService", "name": brand, "url": canonical}
        if b["profile"].get("legal_name"):
            entity_jsonld["legalName"] = b["profile"]["legal_name"]
        if b["profile"].get("sebi_reg_no"):
            entity_jsonld["identifier"] = b["profile"]["sebi_reg_no"]
        if b["profile"].get("hq"):
            entity_jsonld["address"] = {"@type": "PostalAddress", "addressLocality": b["profile"]["hq"], "addressCountry": "IN"}
        entity_jsonld["areaServed"] = "IN"
        jsonld = {"@context": "https://schema.org", "@graph": [entity_jsonld, crumb_jsonld]}

        page = _APP_SHELL_HEAD % {
            "title": _esc(title), "description": _esc(description),
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        page += crumb_html
        page += _broker_facts_html(b)
        page += _APP_SHELL_FOOT

        dest_dir = os.path.join(ROOT, "site", "broker", bid)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), page)
        written += 1

    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "broker"), {b["id"] for b in built})
    log("broker pages: %d static profile pages written%s" % (
        written, (", %d stale pruned" % pruned) if pruned else ""), "ok")


def _write_broker_hub_pages(built):
    """Category hub pages: brokers grouped by type, segment and HQ city.

    Standalone static pages, not a shell-hydration pair like the broker
    profiles - the /brokers directory's type/segment filter chips are pure
    client-side state with no URL reflection at all (confirmed: dirState only
    reads `q` from the query string), so there is no existing client route for
    "/brokers filtered by type=discount" to hydrate into. These are genuinely
    new URLs.

    Path prefix is /brokers-by/..., deliberately NOT /brokers/... - creating a
    real site/brokers/ directory would shadow the SPA's own /brokers route on
    disk exactly the way site/registry/ once shadowed /registry. Every prefix
    chosen for a static-page tree in this file must be checked against the
    live SPA route list before use; this one isn't in it.
    """
    by_type, by_segment, by_city = {}, {}, {}
    for b in built:
        p = b["profile"]
        if p.get("type"):
            by_type.setdefault(p["type"], []).append(b)
        for seg in p.get("segments") or []:
            by_segment.setdefault(seg, []).append(b)
        if p.get("hq"):
            by_city.setdefault(p["hq"], []).append(b)

    groups = (
        [("type", key, TYPE_LABEL.get(key, key), rows) for key, rows in by_type.items()]
        + [("segment", key, SEGMENT_LABEL.get(key, key), rows) for key, rows in by_segment.items()]
        + [("city", key, key, rows) for key, rows in by_city.items()]
    )

    written = 0
    for dim, key, label, rows in groups:
        slug = slugify(key.replace("_", "-"))
        if not slug:
            continue
        canonical = "%s/brokers-by/%s/%s/" % (SITE_URL, dim, slug)
        noun = {"type": "Stock brokers", "segment": "Brokers registered for", "city": "Stock brokers headquartered in"}[dim]
        title = ("%s %s | BrokerLens" % (noun, label)) if dim != "type" else ("%s: %s | BrokerLens" % (noun, label))
        h1 = {
            "type": "%s stock brokers in India" % label,
            "segment": "Brokers registered for %s" % label,
            "city": "Stock brokers headquartered in %s" % label,
        }[dim]
        description = _esc(
            "%s, matched to their SEBI registration where confirmed. %d brokers tracked in depth on BrokerLens."
            % (h1, len(rows))
        )[:300]

        rows_sorted = sorted(rows, key=lambda b: b["profile"].get("brand") or b["id"])
        list_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-head"><a href="/broker/%s/">%s</a></div>'
            '<div class="xs faint" style="margin-top:2px">%s%s</div></div>'
            % (
                _esc(b["id"]), _esc(b["profile"].get("brand") or b["id"]),
                _esc(b["profile"].get("hq") or ""),
                " &middot; SEBI verified" if b["profile"].get("legal_name_verified") else "",
            )
            for b in rows_sorted
        )

        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), (BROKER_HUB_DIM_NOUN[dim], "/brokers-by/%s/" % dim), (label, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "ItemList", "name": h1, "url": canonical,
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1, "url": "%s/broker/%s/" % (SITE_URL, b["id"]),
                         "name": b["profile"].get("brand") or b["id"]}
                        for i, b in enumerate(rows_sorted)
                    ],
                },
                crumb_jsonld,
            ],
        }

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(h1)
            + '<p class="muted" style="max-width:70ch">%d broker%s tracked in depth on BrokerLens match this. '
              'Client, complaint and cost figures on each profile follow the same production-mode rules as the '
              'rest of the site: shown only once traced to a primary source.</p>'
              % (len(rows_sorted), "" if len(rows_sorted) == 1 else "s")
            + '<div class="grid g3" style="margin-top:16px">' + list_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">'
              '<a href="/brokers">Full broker directory (search and filter) &rarr;</a></p>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page groups the brokers BrokerLens tracks in depth by type, segment or head-office city.")}

        dest_dir = os.path.join(ROOT, "site", "brokers-by", dim, slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    # Every leaf page above lives under /brokers-by/<dim>/<slug>/, but nothing
    # ever wrote /brokers-by/<dim>/ itself - that bare path has no static file
    # on disk, so the SPA catch-all rewrite quietly serves the homepage there
    # instead, which Search Console flags as a soft 404 (real symptom: GSC
    # inspection of /brokers-by/type came back "URL is not available to
    # Google - Soft 404"). Writing a real index page per dimension gives that
    # URL genuine, distinct content and a place for the leaf pages to link
    # back to.
    index_written = 0
    for dim in ("type", "segment", "city"):
        items = sorted(
            (
                (slugify(key.replace("_", "-")), label, len(rows))
                for d, key, label, rows in groups
                if d == dim and slugify(key.replace("_", "-"))
            ),
            key=lambda t: (-t[2], t[1]),
        )
        if not items:
            continue
        canonical = "%s/brokers-by/%s/" % (SITE_URL, dim)
        title = "%s | BrokerLens" % BROKER_HUB_DIM_NOUN[dim]
        description = _esc("%s %d group%s tracked on BrokerLens." % (
            BROKER_HUB_DIM_INTRO[dim], len(items), "" if len(items) == 1 else "s"))[:300]
        crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), (BROKER_HUB_DIM_NOUN[dim], None)])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "ItemList", "name": BROKER_HUB_DIM_NOUN[dim], "url": canonical,
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1,
                         "url": "%s/brokers-by/%s/%s/" % (SITE_URL, dim, slug), "name": label}
                        for i, (slug, label, _count) in enumerate(items)
                    ],
                },
                crumb_jsonld,
            ],
        }
        list_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-head"><a href="/brokers-by/%s/%s/">%s</a></div>'
            '<div class="xs faint" style="margin-top:2px">%d broker%s</div></div>'
            % (dim, slug, _esc(label), count, "" if count == 1 else "s")
            for slug, label, count in items
        )
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(BROKER_HUB_DIM_NOUN[dim])
            + '<p class="muted" style="max-width:70ch">%s</p>' % _esc(BROKER_HUB_DIM_INTRO[dim])
            + '<div class="grid g3" style="margin-top:16px">' + list_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">'
              '<a href="/brokers">Full broker directory (search and filter) &rarr;</a></p>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page groups the brokers BrokerLens tracks in depth by type, segment or head-office city.")}
        dest_dir = os.path.join(ROOT, "site", "brokers-by", dim)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        index_written += 1

    pruned = 0
    hub_base = os.path.join(ROOT, "site", "brokers-by")
    for dim in ("type", "segment", "city"):
        keep = {slugify(key.replace("_", "-")) for d, key, _, _ in groups if d == dim}
        pruned += _prune_stale_dirs(os.path.join(hub_base, dim), keep)
    log("broker hub pages: %d written (type/segment/city), %d dimension index pages%s" % (
        written, index_written, (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return groups


_MONTH_ABBR = {"JAN": "January", "FEB": "February", "MAR": "March", "APR": "April",
               "MAY": "May", "JUN": "June", "JUL": "July", "AUG": "August",
               "SEP": "September", "OCT": "October", "NOV": "November", "DEC": "December"}


def _long_date(nse_date):
    """'06-OCT-2008' -> '6 October 2008'. Falls back to the raw string on
    anything unexpected rather than dropping a real, verifiable fact."""
    try:
        d, mon, y = nse_date.split("-")
        return "%d %s %s" % (int(d), _MONTH_ABBR.get(mon.upper(), mon.title()), y)
    except (ValueError, AttributeError):
        return nse_date


def _stock_slug(symbol):
    """Same transform used for every /stock/:symbol/ directory name - shared
    so an index page's constituent links always land on the real stock page
    for the same company instead of a slightly different slug."""
    return re.sub(r"[^a-z0-9]+", "-", (symbol or "").lower()).strip("-")


def _stock_price_html(history):
    """Last close + day change from real bhavcopy history (see nse.py's
    equity_history()) as a hero stat tile - the page's single most-wanted
    number gets the same visual weight the homepage gives its own headline
    figures, not one more box in a flat grid of static reference facts.
    Both points are actually published by NSE, never a live tick. Returns ""
    if fewer than 2 points exist yet."""
    if not history or len(history) < 2:
        return ""
    last, prev = history[-1], history[-2]
    if last.get("close") is None or prev.get("close") is None or not prev["close"]:
        return ""
    chg_pct = (last["close"] - prev["close"]) / prev["close"] * 100
    return (
        '<div class="card stat">'
        '<div class="stat-label">Last close</div>'
        '<div class="stat-value sm">%s <span class="%s" style="font-family:var(--font);font-size:var(--fs-base)">%s</span></div>'
        '<div class="stat-sub">as of %s</div></div>'
    ) % (_inr_html(last["close"]), _cls_class(chg_pct), _pct_html(chg_pct), _iso_to_long_date(last["date"]))


def _listing_details_html(symbol, c, sector):
    """Static reference facts (ISIN, series, face value, market lot) as a
    compact key-value list, not a grid of boxy tiles - these matter far less
    than the price/chart above them, and a flat 3-column grid of 7 items
    always left one cell empty (7 doesn't divide by 3)."""
    def fact(raw):
        return _esc(raw) if raw else "Not disclosed"
    rows = [
        ("NSE symbol", fact(symbol)),
        ("ISIN", fact(c.get("isin"))),
        ("Series", fact(c.get("series"))),
        ("Sector", fact(sector)),
        ("Listed since", fact(_long_date(c.get("listing_date")) if c.get("listing_date") else None)),
        ("Face value", fact(("Rs %s" % c["face_value"]) if c.get("face_value") else None)),
        ("Market lot", fact(c.get("market_lot"))),
    ]
    return (
        '<div class="card"><div class="card-title">Listing details</div>'
        '<dl class="kv" style="margin-top:10px">'
        + "".join("<dt>%s</dt><dd>%s</dd>" % (label, value) for label, value in rows)
        + '</dl></div>'
    )


def _iso_to_long_date(iso_date):
    """'2026-09-18' -> '18 Sep 2026'. Never falls back to a guessed format -
    an unparseable string is returned as-is so it's visibly wrong, not
    silently mangled."""
    try:
        y, m, d = iso_date.split("-")
        return "%d %s %s" % (int(d), _MONTH_NAMES[int(m) - 1], y)
    except (ValueError, IndexError, AttributeError):
        return iso_date


# Sectoral index slugs (see nse.py's INDEX_FILES): the subset that names an
# actual industry rather than a broad-market cap band (Nifty 50/100/500) or a
# strategy/thematic cut (Commodities, CPSE, Infrastructure, Consumption) that
# cuts across sectors - kept separate so "Sector" means one real thing.
_SECTOR_INDEX_SLUGS = {
    "nifty-bank", "nifty-auto", "nifty-it", "nifty-pharma", "nifty-fmcg", "nifty-metal",
    "nifty-realty", "nifty-energy", "nifty-psu-bank", "nifty-media", "nifty-consumer-durables",
    "nifty-healthcare", "nifty-oil-gas",
}


def _write_stock_pages(companies, brokers_cfg, indices=None, equity_history=None, corporate_actions=None):
    """One static page per NSE-listed equity - Phase 1 of docs/SCALE_TO_60K_PLAN.md,
    completed: sector, a real price snapshot and corporate actions were named
    in that plan as in-scope "from data this pipeline already pulls" but
    hadn't actually shipped until now.

    The data (NSE's own EQUITY_L.csv, index constituent files, bhavcopy) was
    already being fetched on every run; only the page-generation step is new
    for most of this. Unlike the sample-gated broker metrics, every field
    here is always real and always available - there is no "not published
    yet" state for a company's own listing facts, though price/chart/
    corporate-action fields degrade honestly to nothing when that day's
    fetch didn't reach this symbol.

    Path is /stock/:symbol/, checked against the live SPA route list before
    use (nothing named "stock" exists there) - same discipline that avoided
    two prior collisions (site/registry/, site/brokers/).
    """
    by_symbol = {s["symbol"].upper(): s for s in (brokers_cfg or [])}
    # A peer link must only ever point at a symbol this same run is actually
    # about to write a /stock/ page for - an index file can lag EQUITY_L.csv
    # by a day (a recent delisting, a symbol change), and a dead link is
    # worse than a peer list one entry shorter.
    valid_symbols = {(c.get("symbol") or "").strip().upper() for c in companies} - {""}
    membership, industry_by_symbol, sector_members = {}, {}, {}
    for slug, idx in (indices or {}).items():
        for con in idx["constituents"]:
            sym = (con.get("symbol") or "").upper()
            if not sym:
                continue
            membership.setdefault(sym, []).append((slug, idx["label"]))
            if con.get("industry") and sym not in industry_by_symbol:
                industry_by_symbol[sym] = con["industry"]
            if slug in _SECTOR_INDEX_SLUGS and sym in valid_symbols:
                sector_members.setdefault(slug, []).append((sym, con.get("name") or sym))

    # BSE's corporate-actions feed uses BSE's own symbol/short-name, which
    # doesn't always match NSE's ticker for the same company - only an exact
    # match is trusted (same discipline as the identity Resolver's strict
    # mode elsewhere in this file); anything that doesn't match exactly is a
    # real gap on that stock's page, never a fuzzy guess.
    actions_by_symbol = {}
    for a in (corporate_actions or []):
        sym = (a.get("symbol") or "").strip().upper()
        if sym:
            actions_by_symbol.setdefault(sym, []).append(a)

    def stock_faqs(name, symbol, c, member_of, match, price_row):
        """Every question is answered from a fact already on this page -
        varying genuinely with real data (an absent ISIN, index membership,
        a broker link) rather than a fixed list reworded per symbol, which
        is what a mechanically-padded FAQ count across 2,571 pages would
        actually look like to a quality rater."""
        faqs = [
            ("What is the NSE symbol for %s?" % name, "%s trades on NSE under the symbol %s." % (name, symbol)),
            ("What is the ISIN of %s?" % name,
             ("%s's ISIN is %s." % (name, c["isin"])) if c.get("isin")
             else "This company's ISIN is not disclosed in NSE's listed-securities master file."),
            ("When was %s listed on NSE?" % name,
             ("%s has been listed on NSE since %s." % (name, _long_date(c["listing_date"])))
             if c.get("listing_date") else "The listing date is not disclosed in NSE's listed-securities master file."),
            ("What is the face value of %s shares?" % name,
             ("The face value of %s shares is Rs %s." % (name, c["face_value"])) if c.get("face_value")
             else "Face value is not disclosed in NSE's listed-securities master file."),
            ("What is the market lot for %s?" % name,
             ("The market lot for %s is %s share(s) per lot." % (name, c["market_lot"])) if c.get("market_lot")
             else "Market lot is not disclosed in NSE's listed-securities master file."),
        ]
        if member_of:
            faqs.append(("Which NSE indices include %s?" % name,
                         "%s is a constituent of: %s." % (name, ", ".join(l for _s, l in member_of))))
        else:
            faqs.append(("Is %s part of Nifty 50?" % name,
                         "%s is not currently a constituent of Nifty 50 or any other NSE index BrokerLens "
                         "tracks a published list for." % name))
        if match and match.get("broker_id"):
            faqs.append(("Is %s a listed stock broker?" % name,
                         "Yes, %s is the listed parent of a BrokerLens-tracked broker; see its broker profile "
                         "for regulatory and cost details." % name))
        faqs.append(("What was %s's last closing price?" % name,
                     "%s closed at %s on %s, from NSE's own daily bhavcopy." % (name, _inr_html(price_row["close"]), price_row["date"])
                     if price_row else
                     "A recent closing price for %s was not available in this site's latest data refresh." % name))
        return faqs

    written = 0
    for c in companies:
        symbol = (c.get("symbol") or "").strip()
        if not symbol:
            continue
        slug = _stock_slug(symbol)
        if not slug:
            continue
        name = c.get("name") or symbol
        canonical = "%s/stock/%s/" % (SITE_URL, slug)
        title = "%s (%s): NSE Listing Details | BrokerLens" % (_esc(name), _esc(symbol))
        description = _esc(
            "%s (NSE: %s): last close, sector, listing facts and price history, sourced directly from "
            "NSE's own listed-securities register and daily bhavcopy." % (name, symbol)
        )[:300]

        corp_jsonld = {"@type": "Corporation", "name": name, "tickerSymbol": symbol, "url": canonical}
        if c.get("isin"):
            corp_jsonld["identifier"] = c["isin"]

        history = (equity_history or {}).get(symbol.upper()) or []
        price_row = history[-1] if history else None
        sector = industry_by_symbol.get(symbol.upper())
        listing_html = _listing_details_html(symbol, c, sector)

        broker_link = ""
        match = by_symbol.get(symbol.upper())
        if match and match.get("broker_id"):
            rel = "the listed parent of" if match.get("relation") == "parent" else ""
            broker_link = (
                '<div class="pending" style="border-style:solid;background:var(--accent-soft)">'
                '<strong>This company %s a BrokerLens-tracked broker.</strong> '
                '<a href="/broker/%s/">View %s\'s broker profile &rarr;</a></div>'
                % (rel or "is", _esc(match["broker_id"]), _esc(match.get("label") or match["broker_id"]))
            )

        member_of = sorted(membership.get(symbol.upper(), []), key=lambda x: x[1])
        index_html = ""
        if member_of:
            index_html = (
                '<p class="xs faint" style="margin-top:12px">Constituent of: '
                + ", ".join('<a href="/index/%s/">%s</a>' % (_esc(s), _esc(l)) for s, l in member_of)
                + '</p>'
            )

        # Real, upcoming corporate actions for this exact symbol - see the
        # exact-match-only note above actions_by_symbol's construction.
        actions = actions_by_symbol.get(symbol.upper()) or []
        actions_html = ""
        if actions:
            actions_html = (
                '<div class="section-title"><h2>Upcoming corporate actions</h2></div>'
                '<div class="table-scroll"><table class="data"><thead><tr>'
                '<th>Purpose</th><th>Ex-date</th><th>Record date</th></tr></thead><tbody>'
                + "".join(
                    "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                    % (_esc(a.get("purpose") or "-"), _esc(a.get("ex_date") or "-"), _esc(a.get("record_date") or "-"))
                    for a in actions
                )
                + '</tbody></table></div>'
                '<p class="xs faint" style="margin-top:4px">Source: BSE corporate-actions disclosure.</p>'
            )

        # Other constituents of the same sector index - a real comparison
        # set, not a random sample, capped so this never reads as padding.
        peers_html = ""
        my_sectors = [slug for slug, _l in member_of if slug in _SECTOR_INDEX_SLUGS]
        if my_sectors:
            peers = [(s, n) for s, n in sector_members.get(my_sectors[0], []) if s != symbol.upper()][:10]
            if peers:
                sector_label = dict(member_of)[my_sectors[0]]
                peers_html = (
                    '<div class="section-title"><h2>Other %s stocks</h2></div>'
                    '<p class="small" style="max-width:70ch">'
                    + ", ".join('<a href="/stock/%s/">%s</a>' % (_esc(_stock_slug(s)), _esc(n)) for s, n in peers)
                    + '</p>'
                ) % _esc(sector_label)

        trade_cta_html = (
            '<div class="card" style="margin-top:20px;background:var(--accent-soft);border-style:solid">'
            '<div class="card-title">Trade %s</div>'
            '<p class="small muted" style="margin-top:4px">%s is tradable through any SEBI-registered broker '
            'with an NSE cash-market membership. <a href="/compare">Compare brokers side by side</a> '
            'or see the <a href="/brokers">full broker directory</a> before opening an account.</p>'
            '</div>'
        ) % (_esc(symbol), _esc(name))

        faqs = stock_faqs(name, symbol, c, member_of, match, price_row)
        faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in faqs
        )
        letter = name[0].upper() if name else ""
        letter = letter if letter.isalpha() else "0-9"
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Browse stocks", "/stocks/"),
            (letter, "/stocks/%s/" % slugify(letter)), (name, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                corp_jsonld,
                {"@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]},
                crumb_jsonld,
            ],
        }

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        if history:
            body = body.replace("</head>", _stamp_asset_versions(
                '<script src="/assets/js/vendor/lightweight-charts.standalone.production.js"></script>'
                '<script type="module" src="/assets/js/stock-chart.js" defer></script></head>'))
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + '<p class="muted">NSE: %s</p>' % _esc(symbol)
            + broker_link
            + (
                '<div class="grid g-main" style="margin-top:16px">'
                '<div class="card"><div class="card-title">Price history</div>'
                '<div data-stock-chart data-symbol="%s"></div></div>'
                '<div class="stack">%s%s%s%s</div></div>'
                % (_esc(slug), _stock_price_html(history), listing_html,
                   affiliateBanner_html(), fivepaisaBanner_html())
                if history else
                listing_html + '<div class="grid g2" style="margin-top:16px">%s%s</div>'
                % (affiliateBanner_html(), fivepaisaBanner_html())
              )
            + '<p class="xs faint" style="margin-top:16px">Source: NSE listed-securities master file (EQUITY_L)%s.</p>'
              % (" and NSE's daily bhavcopy for price history" if history else "; price history was not available "
                 "for this symbol in the latest data refresh")
            + index_html
            + trade_cta_html
            + actions_html
            + peers_html
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + faq_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page is generated directly from NSE's own listed-securities master file (EQUITY_L).")}

        dest_dir = os.path.join(ROOT, "site", "stock", slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    keep = {_stock_slug(c.get("symbol")) for c in companies if _stock_slug(c.get("symbol"))}
    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "stock"), keep)
    log("stock pages: %d NSE-listed equity pages written%s" % (
        written, (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return written


def _write_index_pages(indices, companies):
    """One static page per NSE index (Nifty 50, Nifty Bank, sectoral indices),
    listing every constituent with a cross-link to its /stock/:symbol/ page.

    Path is /index/:slug/, checked against the live SPA route list before use
    (nothing named "index" or "indices" exists there) - same discipline as
    every other static-page prefix on this site. Constituents only link to a
    /stock/ page when that symbol is confirmed to exist in the current NSE
    equity universe, so a stale or misspelled index-file symbol can never
    produce a dead link.
    """
    known = {_stock_slug(c.get("symbol")) for c in (companies or []) if c.get("symbol")}
    written = 0
    for slug, idx in indices.items():
        label = idx["label"]
        constituents = idx["constituents"]
        canonical = "%s/index/%s/" % (SITE_URL, slug)
        title = "%s: Constituent Stocks List | BrokerLens" % label
        description = _esc(
            "Every constituent of the %s index, sourced directly from NSE's own published index list, "
            "with each company's ISIN and a link to its NSE listing details." % label
        )[:300]

        rows_sorted = sorted(constituents, key=lambda c: c.get("name") or c.get("symbol") or "")
        jsonld = {
            "@context": "https://schema.org", "@type": "ItemList", "name": label, "url": canonical,
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1,
                 "url": "%s/stock/%s/" % (SITE_URL, _stock_slug(c["symbol"])), "name": c.get("name") or c["symbol"]}
                for i, c in enumerate(rows_sorted) if c.get("symbol") and _stock_slug(c["symbol"]) in known
            ],
        }

        def fact(raw):
            return _esc(raw) if raw else "Not disclosed"

        list_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-head">%s</div>'
            '<div class="xs faint" style="margin-top:2px">%s%s</div></div>'
            % (
                ('<a href="/stock/%s/">%s</a>' % (_esc(_stock_slug(c["symbol"])), _esc(c.get("name") or c["symbol"]))
                 if _stock_slug(c.get("symbol") or "") in known else fact(c.get("name"))),
                _esc(c.get("symbol") or ""),
                (" &middot; %s" % _esc(c["industry"])) if c.get("industry") else "",
            )
            for c in rows_sorted
        )

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            '<h1 style="margin-top:0">%s</h1>' % _esc(label)
            + '<p class="muted">%d constituent%s</p>' % (len(rows_sorted), "" if len(rows_sorted) == 1 else "s")
            + '<div class="grid g3" style="margin-top:16px">' + list_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page is generated directly from NSE's own published index-constituent list.")}

        dest_dir = os.path.join(ROOT, "site", "index", slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "index"), set(indices.keys()))
    log("index pages: %d NSE index constituent pages written%s" % (
        written, (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return written


def _write_etf_pages(etfs, indices):
    """One static page per NSE-listed ETF - a separate instrument universe
    from EQUITY_L.csv (confirmed zero symbol overlap), so this needed its own
    fetch and its own URL prefix rather than reusing /stock/.

    An ETF is a fund, not a company, so its JSON-LD type is FinancialProduct
    rather than the Corporation type used for stock pages - getting this
    wrong would be a real factual error, the same class of mistake the
    per-page-type source note already exists to prevent.

    Path is /etf/:symbol/, checked against the live SPA route list before use
    (nothing named "etf" exists there).
    """
    by_label = {lbl.lower(): slug for slug, (_f, lbl) in INDEX_FILES.items()}
    written = 0
    for e in etfs or []:
        symbol = (e.get("symbol") or "").strip()
        if not symbol:
            continue
        slug = _stock_slug(symbol)
        if not slug:
            continue
        name = e.get("name") or symbol
        canonical = "%s/etf/%s/" % (SITE_URL, slug)
        title = "%s (%s): ETF Listing Details | BrokerLens" % (_esc(name), _esc(symbol))
        description = _esc(
            "%s (NSE: %s): the ETF's underlying benchmark, ISIN, listing date and market lot, "
            "sourced directly from NSE's own listed-ETF register." % (name, symbol)
        )[:300]

        etf_jsonld = {"@type": "FinancialProduct", "name": name, "url": canonical}
        if e.get("isin"):
            etf_jsonld["identifier"] = e["isin"]
        if e.get("underlying_key"):
            etf_jsonld["category"] = e["underlying_key"]

        def fact(raw):
            return _esc(raw) if raw else "Not disclosed"

        facts_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div><div style="margin-top:2px">%s</div></div>'
            % (label, value) for label, value in [
                ("NSE symbol", fact(symbol)),
                ("Tracks", fact(e.get("underlying_key") or e.get("underlying_asset"))),
                ("Category", fact(e.get("category"))),
                ("ISIN", fact(e.get("isin"))),
                ("Listed on NSE since", fact(_long_date(e["listing_date"]) if e.get("listing_date") else None)),
                ("Face value", fact(("Rs %s" % e["face_value"]) if e.get("face_value") else None)),
                ("Market lot", fact(e.get("market_lot"))),
            ]
        )

        index_slug = by_label.get((e.get("underlying_key") or "").strip().lower())
        index_html = ""
        if index_slug:
            index_html = (
                '<p class="xs faint" style="margin-top:12px">Tracks the same benchmark as: '
                '<a href="/index/%s/">%s constituent list</a></p>' % (_esc(index_slug), _esc(INDEX_FILES[index_slug][1]))
            )

        etf_faqs = [
            ("What is the NSE symbol for %s?" % name, "%s trades on NSE under the symbol %s." % (name, symbol)),
            ("What does %s track?" % name,
             ("%s tracks %s." % (name, e.get("underlying_key") or e.get("underlying_asset")))
             if (e.get("underlying_key") or e.get("underlying_asset"))
             else "The underlying benchmark for this ETF is not disclosed in NSE's listed-ETF register."),
            ("What is the ISIN of %s?" % name,
             ("%s's ISIN is %s." % (name, e["isin"])) if e.get("isin")
             else "This ETF's ISIN is not disclosed in NSE's listed-ETF register."),
            ("When was %s listed on NSE?" % name,
             ("%s has been listed on NSE since %s." % (name, _long_date(e["listing_date"])))
             if e.get("listing_date") else "The listing date is not disclosed in NSE's listed-ETF register."),
            ("What is the market lot for %s?" % name,
             ("The market lot for %s is %s unit(s) per lot." % (name, e["market_lot"])) if e.get("market_lot")
             else "Market lot is not disclosed in NSE's listed-ETF register."),
            ("Is %s an equity, debt or gold ETF?" % name,
             ("%s is categorised as %s." % (name, e["category"])) if e.get("category")
             else "This ETF's category is not disclosed in NSE's listed-ETF register."),
            ("Does this page show %s's live price or NAV?" % name,
             "No. This page carries NSE's own listing facts only; live price and trading data are not "
             "carried here."),
        ]
        etf_faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in etf_faqs
        )
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Browse ETFs", "/etfs/"), (name, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                etf_jsonld,
                {"@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in etf_faqs
                ]},
                crumb_jsonld,
            ],
        }

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + '<p class="muted">NSE: %s</p>' % _esc(symbol)
            + '<div class="grid g3" style="margin-top:16px">' + facts_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">Source: NSE listed-ETF register. '
              'Live price and trading data are not carried on this page.</p>'
            + index_html
            + '<div class="grid g2" style="margin-top:20px">%s%s</div>'
              % (affiliateBanner_html(), fivepaisaBanner_html())
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + etf_faq_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page is generated directly from NSE's own listed-ETF register.")}

        dest_dir = os.path.join(ROOT, "site", "etf", slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    keep = {_stock_slug(e.get("symbol")) for e in (etfs or []) if e.get("symbol")}
    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "etf"), keep)
    log("etf pages: %d NSE-listed ETF pages written%s" % (
        written, (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return written


def _group_mutual_funds(schemes):
    """One page per real scheme, not per NAV row - AMFI's file carries every
    Plan x Option combination as its own row (confirmed live: 14,300+ rows
    collapse to ~3,400 real schemes), and shipping one page per row would be
    exactly the thin, combinatorial page pattern this project's own scale
    plan rules out. Grouped by (AMC, scheme name); every variant is kept and
    shown on the one page for its scheme, the same way an index page shows
    every constituent rather than getting a page each."""
    groups = {}
    order = []
    for s in schemes or []:
        amc, name = s.get("amc"), s.get("name")
        if not amc or not name:
            continue
        key = (amc, name)
        if key not in groups:
            groups[key] = {"amc": amc, "name": name, "categories": [], "variants": []}
            order.append(key)
        g = groups[key]
        if s.get("category") and s["category"] not in g["categories"]:
            g["categories"].append(s["category"])
        g["variants"].append(s)
    return [groups[k] for k in order]


def _write_mutual_fund_pages(schemes):
    """One static page per mutual fund scheme, sourced from AMFI's own daily
    NAV master file - the biggest single lever in docs/SCALE_TO_60K_PLAN.md.

    Path is /fund/:slug/, checked against the live SPA route list before use
    (nothing named "fund" exists there). Slugs are derived from (AMC, scheme
    name); a defensive numeric suffix handles any future collision even
    though today's data produces none, once AMFI's own whitespace and
    trailing-punctuation inconsistencies are normalised (see amfi.py).
    """
    funds = _group_mutual_funds(schemes)
    used_slugs = {}
    written = 0
    for fund in funds:
        amc, name = fund["amc"], fund["name"]
        base_slug = slugify("%s %s" % (amc, name))
        if not base_slug:
            continue
        slug = base_slug
        n = 2
        while slug in used_slugs and used_slugs[slug] != (amc, name):
            slug = "%s-%d" % (base_slug, n)
            n += 1
        used_slugs[slug] = (amc, name)

        canonical = "%s/fund/%s/" % (SITE_URL, slug)
        title = "%s: Mutual Fund Scheme Details | BrokerLens" % _esc(name)
        description = _esc(
            "%s from %s: NAV, ISIN and plan/option details for every variant of this scheme, "
            "sourced directly from AMFI's own daily NAV master file." % (name, amc)
        )[:300]

        fund_jsonld = {"@type": "FinancialProduct", "name": name,
                       "url": canonical, "provider": {"@type": "Organization", "name": amc}}
        if fund["categories"]:
            fund_jsonld["category"] = fund["categories"][0]

        variants_sorted = sorted(
            fund["variants"], key=lambda v: (v.get("plan") or "", v.get("option") or ""))
        rows_html = "".join(
            "<tr><td>%s</td><td>%s</td><td class=\"right num\">%s</td><td class=\"small\">%s</td>"
            "<td class=\"small num\">%s</td><td class=\"small num\">%s</td></tr>"
            % (
                _esc(v.get("plan") or "Not disclosed"), _esc(v.get("option") or "Not disclosed"),
                ("%.4f" % v["nav"]) if isinstance(v.get("nav"), (int, float)) else "Not disclosed",
                _esc(v.get("nav_date") or "Not disclosed"),
                _esc(v.get("isin_growth") or "-"), _esc(v.get("isin_div_reinvest") or "-"),
            )
            for v in variants_sorted
        )

        has_direct = any((v.get("plan") or "").lower().startswith("direct") for v in variants_sorted)
        has_regular = any((v.get("plan") or "").lower().startswith("regular") for v in variants_sorted)
        has_growth = any("growth" in (v.get("option") or "").lower() for v in variants_sorted)
        has_idcw = any("idcw" in (v.get("option") or "").lower() for v in variants_sorted)
        growth_variant = next((v for v in variants_sorted if "growth" in (v.get("option") or "").lower()
                                and (v.get("plan") or "").lower().startswith("direct")), variants_sorted[0])

        fund_faqs = [
            ("Which AMC manages %s?" % name, "%s is managed by %s." % (name, amc)),
            ("What is the latest NAV of %s?" % name,
             ("As of %s, the %s / %s variant of %s had a NAV of Rs %.4f." % (
                 growth_variant.get("nav_date") or "the last update", growth_variant.get("plan") or "",
                 growth_variant.get("option") or "", name, growth_variant["nav"]))
             if isinstance(growth_variant.get("nav"), (int, float))
             else "NAV for this scheme's variants is shown in the table above."),
            ("Does %s have both Direct and Regular plans?" % name,
             "Yes, both Direct and Regular plans are available." if (has_direct and has_regular)
             else ("Only a Direct plan is listed for this scheme." if has_direct
                   else ("Only a Regular plan is listed for this scheme." if has_regular
                         else "Plan availability is shown in the table above."))),
            ("Does %s offer a Growth option, an IDCW option, or both?" % name,
             "Both Growth and IDCW options are available." if (has_growth and has_idcw)
             else ("Only a Growth option is listed for this scheme." if has_growth
                   else ("Only an IDCW option is listed for this scheme." if has_idcw
                         else "Option availability is shown in the table above."))),
            ("What category is %s?" % name,
             ("%s is categorised as %s." % (name, " / ".join(fund["categories"]))) if fund["categories"]
             else "This scheme's category is not disclosed in AMFI's daily NAV master file."),
            ("How many plan/option variants does %s have?" % name,
             "%d variant(s) of %s currently publish a NAV, shown in the table above." % (len(variants_sorted), name)),
            ("Does this page show historical returns or portfolio holdings for %s?" % name,
             "No. This page carries AMFI's own current NAV, ISIN and plan/option data only; historical "
             "returns and portfolio holdings are not carried here."),
        ]
        faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in fund_faqs
        )
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Mutual funds by AMC", "/funds-by/"),
            (amc, "/funds-by/%s/" % slugify(amc)), (name, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                fund_jsonld,
                {"@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in fund_faqs
                ]},
                crumb_jsonld,
            ],
        }

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + '<p class="muted">%s</p>' % _esc(amc)
            + (('<p class="xs faint">%s</p>' % _esc(" / ".join(fund["categories"])))
               if fund["categories"] else "")
            + '<div class="table-scroll" style="margin-top:16px">'
              '<table class="data"><thead><tr>'
              '<th>Plan</th><th>Option</th><th class="right">NAV (Rs)</th><th>As of</th>'
              '<th>ISIN (growth/payout)</th><th>ISIN (reinvestment)</th>'
              '</tr></thead><tbody>' + rows_html + '</tbody></table></div>'
            + '<p class="xs faint" style="margin-top:16px">Source: AMFI daily NAV master file. '
              'Historical NAV, returns and portfolio holdings are not carried on this page.</p>'
            + '<div class="grid g2" style="margin-top:20px">%s%s</div>'
              % (affiliateBanner_html(), fivepaisaBanner_html())
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + faq_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page is generated directly from AMFI's (Association of Mutual Funds in India) "
            "own published daily NAV master file.")}

        dest_dir = os.path.join(ROOT, "site", "fund", slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "fund"), set(used_slugs.keys()))
    log("mutual fund pages: %d written across %d AMCs%s" % (
        written, len(set(f["amc"] for f in funds)),
        (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return funds, used_slugs


_REPORT_SLUG = "state-of-indian-broking-2026"
# Fixed at this report's real first publish date - datePublished must not
# change on every rebuild (it did: this used to be datetime.now() at build
# time, so both the JSON-LD and the page's own "Published <date>" line
# silently relabelled themselves as "published today" on every single
# deploy). Update only if genuinely re-issuing the report under this slug;
# ordinary data refreshes belong in dateModified below, which is meant to
# change.
_REPORT_PUBLISHED = "2026-09-16"


def _write_reports(built, reg_rows, companies, indices, etfs, funds, defaulter_count):
    """A single, hand-written, data-driven report page - not a per-entity
    template like everything else this file generates. The point is
    citability: every figure here is one this pipeline already computed for
    its own pages, just aggregated and stated plainly, so it is exactly as
    defensible as the rest of the site and nothing here is estimated.

    Path is /reports/<slug>/, checked against the live SPA route list before
    use (nothing named "reports" exists there).
    """
    by_cat = {}
    for r in reg_rows:
        for c in (r.get("categories") or []):
            by_cat[c] = by_cat.get(c, 0) + 1

    amc_scheme_counts = {}
    for f in funds:
        amc_scheme_counts[f["amc"]] = amc_scheme_counts.get(f["amc"], 0) + 1
    top_amcs = sorted(amc_scheme_counts.items(), key=lambda kv: -kv[1])[:5]

    total_registered = len(built) + len(reg_rows)
    per_household_name = round(len(reg_rows) / len(built)) if built else 0

    canonical = "%s/reports/%s/" % (SITE_URL, _REPORT_SLUG)
    title = "State of Indian Broking & Investing 2026 | BrokerLens"
    description = _esc(
        "How many SEBI-registered brokers, NSE-listed companies, ETFs and mutual fund schemes actually "
        "exist in India, counted directly from primary regulator and exchange data."
    )[:300]

    jsonld = {
        "@context": "https://schema.org", "@type": "Article", "headline": "State of Indian Broking & Investing 2026",
        "url": canonical, "datePublished": _REPORT_PUBLISHED,
        "dateModified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "author": {"@type": "Organization", "name": "BrokerLens", "url": SITE_URL},
        "publisher": {"@type": "Organization", "name": "BrokerLens", "url": SITE_URL,
                      "logo": {"@type": "ImageObject", "url": "%s/apple-touch-icon.png" % SITE_URL}},
    }

    def stat(n, label):
        return '<div class="mega-seg"><div class="stat-value" style="font-size:28px">%s</div><div class="mega-seg-label">%s</div></div>' % (n, _esc(label))

    stats_html = "".join([
        stat(f"{total_registered:,}", "SEBI-registered broking/DP entities, total"),
        stat(f"{len(reg_rows):,}", "registered but not a household name"),
        stat(f"{defaulter_count:,}", "entities on SEBI's defaulter list"),
        stat(f"{len(companies):,}", "companies listed on NSE"),
        stat(f"{len(etfs):,}", "ETFs listed on NSE"),
        stat(f"{len(indices):,}", "NSE indices with a published constituent list"),
        stat(f"{len(funds):,}", "distinct mutual fund schemes quoting daily NAV"),
        stat(f"{len(amc_scheme_counts):,}", "AMCs running those schemes"),
    ])

    amc_rows = "".join(
        '<tr><td>%s</td><td class="right num">%s</td></tr>' % (_esc(amc), f"{count:,}")
        for amc, count in top_amcs
    )

    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": description,
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    published_dt = datetime.strptime(_REPORT_PUBLISHED, "%Y-%m-%d")
    body += (
        '<p class="xs faint">Published %s &middot; figures last refreshed %s</p>'
        % (published_dt.strftime("%-d %B %Y"), datetime.now(timezone.utc).strftime("%-d %B %Y"))
        + '<h1 style="margin-top:4px">State of Indian Broking &amp; Investing, 2026</h1>'
        + '<p class="muted" style="max-width:68ch">Every figure below is counted directly from SEBI, NSE and '
          'AMFI\'s own published registers, the same primary sources this pipeline pulls for every other page '
          'on the site. Nothing here is a survey estimate or a rounded guess.</p>'
        + '<div class="grid g3" style="margin-top:20px">' + stats_html + '</div>'

        + '<h2 style="margin-top:32px">The broking universe is much bigger than the brands you know</h2>'
        + '<p style="max-width:68ch">%s consumer-facing brokers are what most Indian investors could name if asked. '
          "SEBI's own recognised-intermediary register lists %s more: roughly %d further registered entities for "
          'every household name, spanning commodity brokers, and depository participants registered with CDSL and NSDL. '
          "Separately, %s entities appear on SEBI's own defaulter/expelled-broker list; that list draws on a different, "
          'longer historical record and is not a subset of the entities counted above.</p>'
          % (len(built), f"{len(reg_rows):,}", per_household_name, f"{defaulter_count:,}")
        + '<div class="table-scroll" style="margin-top:12px"><table class="data"><thead><tr>'
          '<th>Registration category</th><th class="right">Entities</th></tr></thead><tbody>'
          + "".join('<tr><td>%s</td><td class="right num">%s</td></tr>'
                    % (_esc(CATEGORY_LABELS.get(c, c)), f"{n:,}") for c, n in sorted(by_cat.items(), key=lambda kv: -kv[1]))
          + '</tbody></table></div>'

        + '<h2 style="margin-top:32px">The mutual fund industry, counted at the scheme level</h2>'
        + '<p style="max-width:68ch">AMFI\'s daily NAV file lists %s distinct schemes (Direct/Regular and Growth/IDCW '
          'variants collapsed into one page per real fund, not counted separately) run by %s Asset Management '
          'Companies. The five largest by scheme count:</p>'
          % (f"{len(funds):,}", len(amc_scheme_counts))
        + '<div class="table-scroll" style="margin-top:12px"><table class="data"><thead><tr>'
          '<th>AMC</th><th class="right">Distinct schemes</th></tr></thead><tbody>' + amc_rows + '</tbody></table></div>'

        + '<h2 style="margin-top:32px">Listed markets</h2>'
        + '<p style="max-width:68ch">NSE currently lists %s companies and %s exchange-traded funds. This site '
          'tracks %s of NSE\'s own published index-constituent lists, from Nifty 50 down to sector indices '
          'like Nifty PSU Bank and Nifty Realty.</p>'
          % (f"{len(companies):,}", f"{len(etfs):,}", len(indices))

        + '<p class="xs faint" style="margin-top:24px">Methodology: every count on this page is derived from the '
          'same SEBI, NSE and AMFI source files BrokerLens ingests for its registry, stock, ETF and mutual fund '
          'pages, snapshotted at publish time. See <a href="/methodology">methodology</a> and '
          '<a href="/sources">sources</a> for exactly how each figure is computed and how often it refreshes.</p>'
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page aggregates counts already computed from SEBI's recognised-intermediary register, "
        "NSE's own listed-securities and index files, and AMFI's daily NAV master file.")}

    dest_dir = os.path.join(ROOT, "site", "reports", _REPORT_SLUG)
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("reports: 1 written (%s)" % _REPORT_SLUG, "ok")
    return [_REPORT_SLUG]


# Every formula below was verified against hand-computed reference values
# before being written into calculators.js (see the session's own worked
# examples). Path is /calculators/:slug/, deliberately NOT nested under
# /calculator/ - that bare route already exists as the SPA's brokerage
# calculator, and nesting under it would shadow it on disk exactly like
# site/registry/ once shadowed the SPA's /registry route.
CALCULATORS = [
    {
        "slug": "sip-calculator", "calc": "sip", "h1": "SIP Calculator",
        "title": "SIP Calculator: Estimate Mutual Fund SIP Returns | BrokerLens",
        "description": "Work out what a monthly SIP could grow to at a given return rate, using the standard "
                        "future-value-of-annuity formula every SIP calculator is built on.",
        "intro": "A Systematic Investment Plan (SIP) invests a fixed amount every month. This estimates the "
                  "maturity value using the standard future-value-of-an-annuity formula, assuming the return "
                  "rate holds steady every month, which real markets never do exactly.",
        "formula": "FV = P &times; [((1+r)<sup>n</sup> - 1) / r] &times; (1+r), where P is the monthly amount, "
                   "r is the monthly return rate, and n is the number of months.",
        "fields": [
            ("sip-monthly", "Monthly investment (Rs)", "5000", "500"),
            ("sip-rate", "Expected annual return (%)", "12", "0.5"),
            ("sip-years", "Investment period (years)", "10", "1"),
        ],
        "how_to": "Enter the amount you plan to invest every month, an assumed annual return rate, and how many "
                  "years you'll keep investing. The calculator applies the formula below and shows the invested "
                  "amount, estimated returns, and total maturity value.",
        "limits": "This assumes the return rate is exactly constant every single month, which no real market "
                   "does. It doesn't subtract a fund's expense ratio, doesn't model a step-up SIP (increasing the "
                   "monthly amount over time), and doesn't account for capital gains tax on withdrawal.",
        "faqs": [
            ("What is a SIP?", "A Systematic Investment Plan invests a fixed amount at a fixed interval, usually "
             "monthly, into a mutual fund scheme, regardless of the unit price on that date."),
            ("How is a SIP different from a lumpsum investment?", "A SIP spreads purchases across many dates, "
             "buying more units when prices are low and fewer when prices are high, rather than committing the "
             "full amount at a single price point the way a lumpsum investment does."),
            ("Does this calculator account for expense ratio?", "No. It computes growth at the return rate you "
             "enter. A mutual fund's actual expense ratio reduces its NAV growth, so real returns are typically "
             "lower than this estimate unless your assumed rate already reflects post-expense returns."),
            ("What return rate should I assume?", "This calculator doesn't recommend one. Historical mutual fund "
             "returns vary widely by fund, category and period; use a rate you can source, such as a specific "
             "fund's own disclosed trailing returns, not a guess."),
            ("Does a SIP guarantee returns?", "No. Every SIP is subject to market risk. The formula here assumes "
             "a constant monthly return, which real markets never deliver exactly."),
            ("Can I increase my SIP amount over time?", "This calculator assumes a fixed monthly amount for the "
             "whole period. A step-up SIP, where the amount rises periodically, compounds faster than this "
             "estimate shows."),
            ("What happens if I miss a SIP instalment?", "This calculator assumes no missed instalments. Missing "
             "months reduces the total invested amount and the resulting maturity value proportionally."),
            ("Is a SIP only for equity mutual funds?", "No. SIPs can run into debt funds, hybrid funds and index "
             "funds too. The same formula applies regardless of the underlying asset class; only the realistic "
             "return assumption changes."),
            ("Does this calculator include tax on withdrawal?", "No. Capital gains tax applies when you redeem, "
             "not during the investment period. Use BrokerLens's capital gains tax calculator for that separately."),
            ("Where does the monthly return rate come from?", "This calculator divides your entered annual rate "
             "by 12 as a simplification. A real fund's actual compounding behaviour may differ slightly."),
            ("Can I use this for a one-time lumpsum investment instead?", "No, use the separate lumpsum "
             "calculator, which applies compound growth to a single deposit instead of a monthly annuity formula."),
            ("Why does the total value grow faster in later years?", "Compounding: returns earned in early years "
             "themselves start earning returns, so growth accelerates over time even with a constant monthly "
             "contribution."),
        ],
    },
    {
        "slug": "lumpsum-calculator", "calc": "lumpsum", "h1": "Lumpsum Investment Calculator",
        "title": "Lumpsum Calculator: Estimate One-Time Investment Growth | BrokerLens",
        "description": "Work out what a one-time lumpsum investment could grow to at a given annual return rate, "
                        "using standard compound growth.",
        "intro": "A lumpsum calculator answers a simpler question than a SIP calculator: what does one investment "
                  "made today become after compounding at a steady annual rate?",
        "formula": "FV = P &times; (1+r)<sup>t</sup>, where P is the amount invested, r is the annual return rate, "
                   "and t is the number of years.",
        "fields": [
            ("ls-principal", "Investment amount (Rs)", "100000", "1000"),
            ("ls-rate", "Expected annual return (%)", "12", "0.5"),
            ("ls-years", "Investment period (years)", "10", "1"),
        ],
        "how_to": "Enter the amount you're investing as a single deposit, an assumed annual return rate, and the "
                  "number of years you'll hold it. The calculator applies compound growth and shows the invested "
                  "amount, estimated returns, and total value at the end of the period.",
        "limits": "This assumes one deposit and a perfectly constant annual return, with no withdrawals, top-ups, "
                   "entry or exit loads, or tax along the way. Real investments rarely grow at a smooth, constant "
                   "rate.",
        "faqs": [
            ("What is a lumpsum investment?", "A single deposit made at one point in time, left to grow at a "
             "compounding rate, as opposed to periodic monthly SIP contributions."),
            ("How is this different from a fixed deposit?", "The mechanics, a single deposit compounding over "
             "time, are similar, but a bank fixed deposit's rate is contractually guaranteed, while a mutual fund "
             "or equity lumpsum's return is market-linked and not guaranteed."),
            ("Does this account for entry or exit load?", "No. Some funds charge an exit load if redeemed within "
             "a specified period; this calculator only computes gross growth at your assumed rate."),
            ("Is a lumpsum better than a SIP?", "Neither is universally better. A lumpsum invested right before a "
             "market fall underperforms a SIP that averages in over time, while a lumpsum invested right before a "
             "rally outperforms it. Timing risk is the key difference."),
            ("What return rate should I use?", "Use a rate you can source for the specific instrument you're "
             "evaluating. Don't use a generic market-average assumption as a promise of future performance."),
            ("Does this calculator show inflation-adjusted returns?", "No, all figures are nominal. To estimate "
             "real returns, subtract your assumed inflation rate from the return rate before entering it."),
            ("Can I model a lumpsum plus later top-ups?", "Not with this calculator; it computes a single deposit "
             "only. Combine its result with the SIP calculator's output for additional planned contributions."),
            ("Does this include taxes?", "No. Capital gains tax applies on redemption and depends on holding "
             "period and instrument type; see the capital gains tax calculator for that separately."),
            ("What's the difference between CAGR and the return rate entered here?", "They're the same concept "
             "for a single deposit compounding at a constant rate. The CAGR calculator instead works backward "
             "from a known start and end value to find that rate."),
            ("Why does compounding matter more over longer periods?", "Returns generated in early years "
             "themselves earn returns in later years, so the growth curve steepens with time even at a constant "
             "rate."),
        ],
    },
    {
        "slug": "emi-calculator", "calc": "emi", "h1": "EMI Calculator",
        "title": "EMI Calculator: Monthly Loan Instalment | BrokerLens",
        "description": "Work out the monthly EMI, total interest and total payment for a loan, using the standard "
                        "reducing-balance EMI formula.",
        "intro": "Every standard reducing-balance loan (home, personal, vehicle) uses the same EMI formula, "
                  "regardless of lender. This computes the fixed monthly instalment for a given principal, "
                  "interest rate and tenure.",
        "formula": "EMI = P &times; r &times; (1+r)<sup>n</sup> / ((1+r)<sup>n</sup> - 1), where P is the loan "
                   "amount, r is the monthly interest rate, and n is the number of monthly instalments.",
        "fields": [
            ("emi-principal", "Loan amount (Rs)", "1000000", "10000"),
            ("emi-rate", "Annual interest rate (%)", "9", "0.1"),
            ("emi-years", "Loan tenure (years)", "20", "1"),
        ],
        "how_to": "Enter the loan amount, the annual interest rate your lender quotes, and the loan tenure in "
                  "years. The calculator applies the standard reducing-balance formula and shows your fixed "
                  "monthly instalment, total interest paid, and total repayment over the full tenure.",
        "limits": "This assumes a fixed interest rate for the entire tenure, no prepayment, and no processing "
                   "fees or insurance premiums, which most real loans add on top of principal and interest.",
        "faqs": [
            ("What is EMI?", "Equated Monthly Instalment: a fixed amount paid every month toward a loan, "
             "covering both interest and principal, until the loan is fully repaid."),
            ("Does the EMI amount stay the same for the whole loan?", "Under a fixed-rate reducing-balance loan, "
             "which this calculator assumes, yes. A floating-rate loan's EMI or tenure can change if the lender's "
             "rate changes."),
            ("Why does most of my early EMI go toward interest?", "Interest is charged on the outstanding "
             "balance, which is highest at the start, so early instalments are interest-heavy. The principal "
             "share grows as the balance shrinks."),
            ("Does this include processing fees or insurance?", "No, only principal and interest at the stated "
             "rate. Lenders often add a one-time processing fee and may require insurance, which this calculator "
             "doesn't include."),
            ("What happens if I prepay part of the loan?", "This calculator assumes no prepayment. Prepaying "
             "reduces the outstanding principal, which either shortens the tenure or lowers future EMIs depending "
             "on what your lender allows."),
            ("Can I use this for a floating-rate loan?", "You can approximate one snapshot in time, but a "
             "floating rate can change, which would change the real EMI or tenure versus this fixed-rate "
             "estimate."),
            ("Is a longer tenure always cheaper per month?", "Yes, but at the cost of paying more total interest "
             "over the life of the loan. Compare the total-interest figure alongside the monthly EMI, not the "
             "EMI alone."),
            ("Does this work the same for a home loan, personal loan and vehicle loan?", "Yes, the "
             "reducing-balance EMI formula is identical across loan types; only the typical interest rate and "
             "tenure ranges differ."),
            ("What's the difference between flat rate and reducing balance interest?", "This calculator assumes "
             "reducing balance, the standard for most loans in India. A flat-rate loan charges interest on the "
             "full original principal for the whole tenure, which works out to a materially higher effective "
             "rate for the same stated percentage."),
        ],
    },
    {
        "slug": "cagr-calculator", "calc": "cagr", "h1": "CAGR Calculator",
        "title": "CAGR Calculator: Compound Annual Growth Rate | BrokerLens",
        "description": "Work out the compound annual growth rate (CAGR) between a starting and ending value over "
                        "a given number of years.",
        "intro": "CAGR smooths an investment's actual (bumpy) year-to-year path into a single, comparable annual "
                  "growth rate, as if it had grown at exactly that steady rate every year.",
        "formula": "CAGR = ((End value / Start value)<sup>(1/years)</sup> - 1) &times; 100.",
        "fields": [
            ("cagr-start", "Starting value (Rs)", "100000", "1000"),
            ("cagr-end", "Ending value (Rs)", "250000", "1000"),
            ("cagr-years", "Number of years", "5", "1"),
        ],
        "how_to": "Enter the value you started with, the value you ended with, and the number of years between "
                  "them. The calculator works backward to find the single, constant annual rate that reconciles "
                  "the two.",
        "limits": "CAGR smooths out every year in between into one number; it says nothing about how bumpy the "
                   "path was, and a fund that fell sharply then recovered can show the same CAGR as one that grew "
                   "steadily the whole time.",
        "faqs": [
            ("What does CAGR stand for?", "Compound Annual Growth Rate: the constant annual rate an investment "
             "would need to grow at, uniformly, to go from its starting value to its ending value over the "
             "stated period."),
            ("How is CAGR different from average annual return?", "A simple average of yearly returns can "
             "overstate real growth because it ignores compounding and the order of gains and losses. CAGR is "
             "the single smoothed rate that actually reconciles the start and end values."),
            ("Does CAGR account for volatility along the way?", "No. Two investments with the same start value, "
             "end value and duration have the same CAGR even if one had wild swings and the other grew "
             "steadily."),
            ("Can CAGR be negative?", "Yes, if the ending value is lower than the starting value, CAGR is "
             "negative, representing an average annual decline."),
            ("Is CAGR the same as XIRR?", "No. CAGR assumes a single lumpsum invested once. XIRR (extended "
             "internal rate of return) handles multiple cash flows at different dates, such as SIP instalments, "
             "which CAGR cannot."),
            ("What counts as a good CAGR?", "This calculator doesn't judge that; it depends entirely on the "
             "asset class, risk taken and time period being compared. Compare like for like, such as only "
             "against similar funds over the same period."),
            ("Does CAGR include dividends or only price appreciation?", "That depends entirely on what ending "
             "value you enter. Including reinvested dividends in your ending value reflects total return; "
             "excluding them reflects only price return."),
            ("Can I use CAGR to compare two investments with different durations?", "Yes, that's exactly what "
             "CAGR is designed for, since it's already annualised, unlike a simple total-return percentage which "
             "isn't directly comparable across different time periods."),
        ],
    },
    {
        "slug": "compound-interest-calculator", "calc": "compound", "h1": "Compound Interest Calculator",
        "title": "Compound Interest Calculator | BrokerLens",
        "description": "Work out the maturity value of a principal amount compounding at a given rate and "
                        "frequency over a given period.",
        "intro": "Unlike the lumpsum investment calculator above, this lets the compounding frequency vary "
                  "(annual, half-yearly, quarterly, monthly) since bank deposits and bonds often compound more "
                  "often than once a year.",
        "formula": "A = P &times; (1 + r/n)<sup>(n&times;t)</sup>, where P is the principal, r is the annual rate, "
                   "n is the number of times interest compounds per year, and t is the number of years.",
        "fields": [
            ("ci-principal", "Principal (Rs)", "50000", "1000"),
            ("ci-rate", "Annual interest rate (%)", "8", "0.1"),
            ("ci-freq", "Compounding frequency per year", "4", "1"),
            ("ci-years", "Period (years)", "5", "1"),
        ],
        "how_to": "Enter the principal, the annual interest rate, how many times per year it compounds (1 for "
                  "annual, 4 for quarterly, 12 for monthly), and the period in years. The calculator shows the "
                  "interest earned and the final maturity value.",
        "limits": "This assumes the rate and compounding frequency stay fixed for the whole period and doesn't "
                   "account for TDS on interest, which banks deduct at source above a threshold.",
        "faqs": [
            ("What's the difference between this and the lumpsum calculator?", "This lets you set a compounding "
             "frequency (annual, half-yearly, quarterly, monthly); the lumpsum calculator assumes annual "
             "compounding only. Otherwise the underlying math is the same."),
            ("Does more frequent compounding always mean more money?", "Yes, all else equal, more frequent "
             "compounding produces a usually small additional gain, since interest starts earning its own "
             "interest sooner."),
            ("What compounding frequency do Indian bank fixed deposits use?", "This varies by bank and product; "
             "check your specific FD's terms rather than assuming a frequency."),
            ("Does this account for TDS on interest?", "No. Banks deduct tax at source on FD interest above a "
             "threshold; this calculator shows gross growth before any tax."),
            ("Is this the same formula banks use for recurring deposits?", "No, a recurring deposit involves "
             "periodic contributions like a SIP, not a single principal. Use the SIP calculator to approximate a "
             "recurring deposit instead."),
            ("Can the interest rate change during the period?", "This calculator assumes a constant rate for the "
             "whole period; a real product's rate could change, or could be fixed by contract, depending on what "
             "you're modelling."),
            ("Why is quarterly compounding more common in India than continuous compounding?", "Continuous "
             "compounding is a mathematical limit rarely used in real products. Indian banks and post-office "
             "schemes typically compound quarterly or annually by convention, not out of mathematical "
             "necessity."),
        ],
    },
    {
        "slug": "capital-gains-tax-calculator", "calc": "capital-gains", "h1": "Capital Gains Tax Calculator",
        "title": "Capital Gains Tax Calculator: Equity LTCG & STCG | BrokerLens",
        "description": "Estimate long-term or short-term capital gains tax on listed equity shares or equity "
                        "mutual funds at current FY 2025-26 rates.",
        "intro": "For listed equity shares and equity-oriented mutual funds, India taxes gains differently by how "
                  "long the asset was held: over 365 days is long-term (LTCG), 365 days or under is short-term "
                  "(STCG). This uses the FY 2025-26 rates confirmed at publish time and excludes cess and "
                  "surcharge, which depend on total income.",
        "formula": "LTCG: 12.5% on gains above a Rs 1,25,000 annual exemption. STCG: 20% flat on the full gain. "
                   "Neither rate changed in Budget 2025 or Budget 2026.",
        "fields": [
            ("cg-buy", "Purchase value (Rs)", "100000", "1000"),
            ("cg-sell", "Sale value (Rs)", "300000", "1000"),
            ("cg-days", "Holding period (days)", "400", "1"),
        ],
        "how_to": "Enter what you paid, what you sold for, and how many days you held the position. The "
                  "calculator classifies the holding as long-term or short-term at the 365-day mark and applies "
                  "the matching rate.",
        "limits": "This shows base tax only, excluding cess and surcharge, and does not model set-off of losses "
                   "against other gains, carry-forward of losses, or any instrument other than listed equity "
                   "shares and equity-oriented mutual funds. It is not tax advice.",
        "faqs": [
            ("What counts as long-term for equity?", "Holding a listed equity share or equity mutual fund unit "
             "for more than 365 days (over one year) at the time of sale."),
            ("What is the LTCG exemption?", "The first Rs 1,25,000 of long-term capital gains from listed "
             "equity or equity mutual funds in a financial year is tax-free; only the amount above that is "
             "taxed at 12.5%."),
            ("Is the exemption per transaction or per year?", "Per financial year, aggregated across all your "
             "long-term equity gains, not per individual sale."),
            ("Does STCG have any exemption?", "No, short-term capital gains on listed equity are taxed at a "
             "flat 20% from the first rupee of gain, with no exemption threshold."),
            ("Do these rates include cess?", "No. A 4% health and education cess applies on top of the tax "
             "amount, and a surcharge may apply at higher income levels; this calculator shows the base tax "
             "only."),
            ("Does this apply to debt mutual funds too?", "No. Debt fund taxation rules differ; this calculator "
             "is for listed equity shares and equity-oriented mutual funds only."),
            ("What if I have a capital loss instead of a gain?", "This calculator shows zero tax on a loss. "
             "Capital losses can typically be set off against capital gains and carried forward under income "
             "tax rules; consult a tax professional for your specific situation."),
            ("Can I offset STCG against LTCG losses or vice versa?", "Set-off rules between short-term and "
             "long-term capital gains and losses have specific conditions under the Income Tax Act. This "
             "calculator does not model set-off; it only computes a single sale's tax in isolation."),
            ("Is the holding period counted from the purchase date or the settlement date?", "Generally from "
             "the date of purchase, or allotment for an IPO or mutual fund unit, to the date of sale. Check the "
             "exact rule for your instrument if you're near the 365-day boundary."),
            ("Will these rates change in a future Budget?", "Possibly. Tax rates are set by the Union Budget "
             "and can change. This calculator uses the rates confirmed current as of publish time and states "
             "that date; always verify against the current Income Tax Act before filing."),
            ("Does this apply to unlisted shares or property?", "No. Unlisted equity, property, gold and other "
             "asset classes have entirely different capital gains tax rules and rates; this calculator is "
             "specific to listed equity shares and equity mutual funds."),
        ],
    },
    {
        "slug": "simple-interest-calculator", "calc": "simple-interest", "h1": "Simple Interest Calculator",
        "title": "Simple Interest Calculator | BrokerLens",
        "description": "Work out simple interest and the total repayable amount on a principal, rate and time period.",
        "intro": "Simple interest is charged only on the original principal for the whole period, unlike compound "
                  "interest where earlier interest itself starts earning interest. It's the basis for some loans "
                  "and short-term deposits.",
        "formula": "SI = (P &times; R &times; T) / 100, where P is the principal, R is the annual rate (%), and T "
                   "is the time in years.",
        "fields": [
            ("si-principal", "Principal (Rs)", "100000", "1000"),
            ("si-rate", "Annual interest rate (%)", "8", "0.1"),
            ("si-years", "Time period (years)", "5", "1"),
        ],
        "how_to": "Enter the principal, the annual simple interest rate, and the time period in years. The "
                  "calculator shows the interest and the total amount repayable.",
        "limits": "This assumes interest is charged only on the original principal for the entire period; if your "
                   "product actually compounds (most bank deposits and loans do), use the compound interest "
                   "calculator instead.",
        "faqs": [
            ("What's the difference between simple and compound interest?", "Simple interest is charged only on "
             "the original principal for the whole period. Compound interest is charged on the principal plus "
             "any interest already added, so it grows faster over time."),
            ("Where is simple interest actually used?", "Some short-term loans, certain bonds, and specific "
             "penalty or overdue-payment calculations use simple interest. Most savings products (FDs, RDs, "
             "savings accounts) compound instead."),
            ("Does a longer time period always mean more interest?", "Yes, simple interest grows linearly with "
             "time: doubling the period exactly doubles the interest, unlike compound interest which accelerates."),
            ("Can I use this for a loan?", "Only if your specific loan is genuinely a simple-interest loan. Most "
             "consumer loans in India (home, personal, vehicle) use reducing-balance EMI instead; use the EMI "
             "calculator for those."),
        ],
    },
    {
        "slug": "step-up-sip-calculator", "calc": "stepup-sip", "h1": "Step-up SIP Calculator",
        "title": "Step-up SIP Calculator: Annual Increase SIP Returns | BrokerLens",
        "description": "Work out what a SIP grows to when the monthly investment increases by a fixed percentage "
                        "every year, instead of staying flat.",
        "intro": "A step-up (or top-up) SIP increases your monthly investment by a fixed percentage every year, "
                  "typically matching salary increments, so you invest more as your income grows rather than a "
                  "flat amount for the whole period.",
        "formula": "Simulated month by month: each month the balance grows at the monthly return rate and the "
                   "current instalment is added; the instalment itself increases by the step-up percentage at "
                   "the start of every new year.",
        "fields": [
            ("ssip-monthly", "Starting monthly investment (Rs)", "5000", "500"),
            ("ssip-stepup", "Annual step-up (%)", "10", "1"),
            ("ssip-rate", "Expected annual return (%)", "12", "0.5"),
            ("ssip-years", "Investment period (years)", "10", "1"),
        ],
        "how_to": "Enter your starting monthly investment, the percentage you'll increase it by each year, an "
                  "assumed annual return rate, and the investment period. The calculator simulates the SIP "
                  "month by month with the increasing instalment.",
        "limits": "This assumes the step-up happens exactly once a year, every year, without fail, and that the "
                   "return rate is constant. It doesn't account for a fund's expense ratio or tax on withdrawal.",
        "faqs": [
            ("How is this different from the regular SIP calculator?", "The regular SIP calculator assumes a "
             "fixed monthly amount for the whole period. This one increases the monthly amount by a set "
             "percentage every year, which usually results in a larger corpus for the same starting amount."),
            ("What step-up percentage should I use?", "A common approach is to match your expected annual salary "
             "increment, but this calculator doesn't recommend a specific figure; use one you can realistically "
             "sustain."),
            ("Does the step-up compound on itself?", "Yes. Each year's instalment is the previous year's "
             "instalment multiplied by (1 + step-up rate), so the step-up itself compounds over a long period."),
            ("Can I model a step-up that happens less often than annually?", "Not with this calculator; it "
             "assumes exactly one step-up per year. A less frequent step-up would produce a smaller corpus than "
             "shown here."),
            ("Is a step-up SIP always better than a flat SIP?", "It generally builds a larger corpus for the "
             "same starting amount since later years contribute more, but it also requires committing to larger "
             "outflows over time, which is a real affordability question, not just a math one."),
        ],
    },
    {
        "slug": "swp-calculator", "calc": "swp", "h1": "SWP Calculator",
        "title": "SWP Calculator: Systematic Withdrawal Plan | BrokerLens",
        "description": "Work out how long a corpus lasts under a fixed monthly withdrawal, or what remains after "
                        "a given period, assuming a steady return rate.",
        "intro": "A Systematic Withdrawal Plan withdraws a fixed amount every month from an existing corpus, "
                  "which continues to earn returns on whatever remains. This is the mirror image of a SIP, "
                  "usually used to draw a regular income from accumulated savings.",
        "formula": "Simulated month by month: each month the remaining balance grows at the monthly return rate, "
                   "then the withdrawal is subtracted.",
        "fields": [
            ("swp-corpus", "Starting corpus (Rs)", "1000000", "10000"),
            ("swp-withdrawal", "Monthly withdrawal (Rs)", "8000", "500"),
            ("swp-rate", "Expected annual return (%)", "8", "0.5"),
            ("swp-years", "Period to check (years)", "15", "1"),
        ],
        "how_to": "Enter your starting corpus, how much you plan to withdraw every month, an assumed annual "
                  "return rate, and how many years you want to check. The calculator shows whether the corpus "
                  "outlasts that period, and if so, how much remains.",
        "limits": "This assumes a constant monthly return and a fixed withdrawal amount with no adjustment for "
                   "inflation over time; a withdrawal that doesn't rise with inflation buys less each year in "
                   "real terms even if the corpus itself survives.",
        "faqs": [
            ("How is SWP different from a fixed monthly income product?", "SWP draws down an investment corpus "
             "that keeps growing (or shrinking) with market returns; a fixed-income product like an annuity "
             "typically guarantees the payout amount instead."),
            ("What happens if my withdrawal exceeds the return the corpus earns?", "The corpus shrinks over "
             "time and will eventually deplete; this calculator shows exactly when, to the month, if that "
             "happens within the period you check."),
            ("Does this account for tax on each withdrawal?", "No. Depending on the underlying investment, part "
             "of each SWP withdrawal may be treated as capital gains for tax purposes; this calculator shows "
             "gross cash flow only."),
            ("Should my withdrawal amount increase with inflation?", "Many real SWP plans do increase the "
             "withdrawal over time to maintain purchasing power; this calculator assumes a fixed withdrawal "
             "amount for the whole period you check."),
            ("Can I use this to plan retirement income?", "It can approximate one part of that question (will a "
             "given corpus support a given withdrawal), but see the dedicated retirement corpus calculator for "
             "working out how large a corpus you'd need in the first place."),
        ],
    },
    {
        "slug": "inflation-calculator", "calc": "inflation", "h1": "Inflation Calculator",
        "title": "Inflation Calculator: Future Cost of Living | BrokerLens",
        "description": "Work out what something costing a given amount today will cost in the future at an "
                        "assumed inflation rate.",
        "intro": "Inflation erodes purchasing power over time: the same rupee buys less in the future. This "
                  "shows what a cost today grows to at an assumed annual inflation rate.",
        "formula": "Future cost = Cost today &times; (1 + inflation rate)<sup>years</sup>.",
        "fields": [
            ("infl-cost", "Cost today (Rs)", "50000", "1000"),
            ("infl-rate", "Assumed annual inflation (%)", "6", "0.5"),
            ("infl-years", "Number of years", "10", "1"),
        ],
        "how_to": "Enter today's cost of whatever you're planning for, an assumed annual inflation rate, and the "
                  "number of years ahead. The calculator shows the equivalent future cost.",
        "limits": "This assumes a single constant inflation rate for the entire period; real inflation varies "
                   "year to year and differs by category (education and healthcare inflation in India have "
                   "historically run above the general Consumer Price Index rate).",
        "faqs": [
            ("What inflation rate should I use?", "This calculator doesn't recommend one. India's general CPI "
             "inflation has historically varied significantly year to year; use a rate you can source rather "
             "than a guess, and consider that specific categories (education, healthcare) often run higher."),
            ("Is this the same as calculating investment returns?", "No, this only shows how much a cost grows "
             "due to inflation. To check whether your savings will keep pace, compare the future cost shown "
             "here against a separate SIP or lumpsum calculator's projected corpus."),
            ("Does inflation affect all expenses equally?", "No. This calculator applies one flat rate to a "
             "single cost; real household budgets have categories that inflate at different rates."),
            ("Why does the extra cost from inflation grow faster in later years?", "Inflation compounds: each "
             "year's price increase is applied on top of the already-inflated price from the year before, not "
             "on the original amount."),
        ],
    },
    {
        "slug": "retirement-calculator", "calc": "retirement", "h1": "Retirement Corpus Calculator",
        "title": "Retirement Calculator: How Much Corpus You Need | BrokerLens",
        "description": "Work out the retirement corpus needed to sustain a given monthly expense, adjusted for "
                        "inflation, over a given number of years in retirement.",
        "intro": "This answers a specific question: given what you spend monthly today, how large does your "
                  "retirement corpus need to be at the day you retire, so that inflation-adjusted withdrawals "
                  "last through your expected years in retirement?",
        "formula": "Future monthly expense = today's expense &times; (1 + inflation)<sup>years to retirement</sup>. "
                   "Corpus = future monthly expense &times; the present value of an annuity, using a real "
                   "(inflation-adjusted) monthly return rate over the retirement period.",
        "fields": [
            ("ret-expense", "Current monthly expense (Rs)", "50000", "1000"),
            ("ret-years-to", "Years until retirement", "25", "1"),
            ("ret-inflation", "Assumed inflation (%)", "6", "0.5"),
            ("ret-years-in", "Years to plan for in retirement", "20", "1"),
            ("ret-return", "Expected return during retirement (%)", "10", "0.5"),
        ],
        "how_to": "Enter your current monthly expense, years until you retire, an assumed inflation rate, how "
                  "many years you're planning for after retirement, and an assumed return rate on your corpus "
                  "during retirement. The calculator shows the inflated monthly expense at retirement and the "
                  "corpus needed to sustain it.",
        "limits": "This assumes constant inflation and constant returns for decades, which real markets never "
                   "deliver, and doesn't account for other retirement income (pension, rental income, Social "
                   "Security-equivalent schemes) that would reduce how much corpus you personally need.",
        "faqs": [
            ("Why does the calculator use a 'real' return rate instead of the return rate I entered?", "Because "
             "your expenses are also rising with inflation every year in retirement, what matters for how long "
             "the corpus lasts is the return rate after subtracting inflation, not the raw return rate."),
            ("Does this include a pension, EPF or NPS payout?", "No. This calculates the total corpus needed "
             "assuming it's the only source of retirement income; if you'll also receive a pension or annuity, "
             "you need a smaller self-funded corpus than shown here."),
            ("What return rate should I assume during retirement?", "This calculator doesn't recommend one; "
             "typically retirement portfolios shift toward safer, lower-return assets than pre-retirement "
             "investing, so consider using a lower rate than an equity-heavy accumulation-phase assumption."),
            ("Why does a small change in the assumed inflation or return rate move the answer so much?", "Over "
             "20-30 year horizons, small differences in rate compound into large differences in outcome; this "
             "is a well-known sensitivity of all long-horizon retirement projections, not a quirk of this "
             "calculator specifically."),
            ("Should I recalculate this periodically?", "Yes. Your actual expenses, inflation, and returns will "
             "differ from any assumption made years in advance; treat this as a periodically-revisited estimate, "
             "not a one-time answer."),
        ],
    },
    {
        "slug": "ppf-calculator", "calc": "ppf", "h1": "PPF Calculator",
        "title": "PPF Calculator: Public Provident Fund Maturity Value | BrokerLens",
        "description": "Work out the maturity value of a Public Provident Fund account at the current "
                        "government-set interest rate.",
        "intro": "The Public Provident Fund is a government-backed long-term savings scheme with a 15-year "
                  "lock-in, annual compounding, and an interest rate set (and revised quarterly) by the Ministry "
                  "of Finance. This assumes the same deposit is made every year for the period you enter.",
        "formula": "Balance compounds annually: each year, that year's deposit is added, then the full balance "
                   "grows at the current PPF rate. Current rate: 7.1% per annum (Jul-Sep 2026 quarter).",
        "fields": [
            ("ppf-deposit", "Annual deposit (Rs, max 1,50,000)", "150000", "1000"),
            ("ppf-years", "Number of years", "15", "1"),
        ],
        "how_to": "Enter your planned annual deposit (the government caps this at Rs 1,50,000 per financial "
                  "year) and the number of years. The calculator compounds annually at the current PPF rate and "
                  "shows the maturity value.",
        "limits": "PPF's interest rate is revised every quarter by the Ministry of Finance; this calculator uses "
                   "7.1%, the confirmed rate for Jul-Sep 2026, for every year of the period, which will not "
                   "match reality if the rate changes in a future quarter. It also assumes the same deposit "
                   "amount and timing every year, and does not model partial withdrawals or loans against the "
                   "account, both of which real PPF accounts allow after certain years.",
        "faqs": [
            ("What is the current PPF interest rate?", "7.1% per annum for the Jul-Sep 2026 quarter, unchanged "
             "for nine consecutive quarters as of this rate's confirmation. It is revised quarterly by the "
             "Ministry of Finance, so check the current rate before relying on this for a plan spanning future "
             "quarters."),
            ("What is the maximum I can deposit into PPF each year?", "Rs 1,50,000 per financial year, across "
             "all your PPF accounts combined."),
            ("What is the PPF lock-in period?", "15 years from account opening, extendable in blocks of 5 years "
             "after maturity. Partial withdrawals are permitted from the 7th year under specific rules."),
            ("Is PPF interest taxable?", "No. PPF is an EEE (Exempt-Exempt-Exempt) instrument: the deposit, the "
             "interest earned, and the maturity amount are all exempt from income tax under current rules."),
            ("Does this calculator assume monthly or annual deposits?", "Annual, with interest compounding once "
             "a year on the balance including that year's deposit. Real PPF interest is actually computed on "
             "the lowest balance between the 5th and last day of each month, so a real account funded via "
             "monthly deposits will differ slightly from this simplified annual model."),
        ],
    },
    {
        "slug": "gst-calculator", "calc": "gst", "h1": "GST Calculator",
        "title": "GST Calculator: Add or Remove GST | BrokerLens",
        "description": "Work out the GST amount and total price, either adding GST to a base price or extracting "
                        "it from a GST-inclusive price, at current GST slab rates.",
        "intro": "India's GST structure was rationalised in September 2025 (\"GST 2.0\") from four slabs down to "
                  "essentially two main rates plus a de-merit rate: 5% (merit goods), 18% (standard), and 40% "
                  "(select sin/luxury goods), alongside a 0% (nil) rate for specified essentials. This works "
                  "either direction: adding GST to a base price, or extracting it from a price that already "
                  "includes GST.",
        "formula": "Exclusive (adding GST): GST = base &times; rate / 100, Total = base + GST. "
                   "Inclusive (extracting GST): base = total / (1 + rate/100), GST = total - base.",
        "fields": [
            ("gst-amount", "Amount (Rs)", "1000", "10"),
        ],
        "extra_fields_html": (
            '<div class="field"><label for="gst-rate">GST rate</label>'
            '<select id="gst-rate"><option value="5">5%</option><option value="18" selected>18%</option>'
            '<option value="40">40%</option><option value="0">0% (nil-rated)</option></select></div>'
            '<div class="field"><label>Amount entered is</label>'
            '<label style="display:flex;align-items:center;gap:6px;font-weight:400;margin-top:4px">'
            '<input type="radio" name="gst-mode" value="exclusive" checked style="width:auto"> Exclusive of GST (add GST)</label>'
            '<label style="display:flex;align-items:center;gap:6px;font-weight:400;margin-top:4px">'
            '<input type="radio" name="gst-mode" value="inclusive" style="width:auto"> Inclusive of GST (extract GST)</label></div>'
        ),
        "how_to": "Enter an amount, choose the applicable GST rate, and choose whether that amount already "
                  "includes GST or not. The calculator shows the base amount, the GST amount, and the total.",
        "limits": "This applies one flat rate to one amount; it doesn't handle mixed-rate invoices (where "
                   "different line items attract different GST rates), input tax credit, or the compensation "
                   "cess that applies to specific goods like tobacco and vehicles on top of the 40% slab.",
        "faqs": [
            ("What are the current GST slabs?", "Since September 22, 2025, India's GST structure is 0% (nil, "
             "for specified essentials like individual life/health insurance and select life-saving drugs), 5% "
             "(merit goods), 18% (standard rate), and 40% (de-merit rate for select sin and luxury goods). The "
             "earlier 12% and 28% slabs no longer exist for most items."),
            ("What changed in the September 2025 GST reform?", "The GST Council collapsed the previous "
             "four-slab structure (5/12/18/28%) into essentially two main slabs (5% and 18%) plus a 40% "
             "de-merit rate, moving most 12%-slab items to 5% and most 28%-slab items to 18%."),
            ("What's the difference between GST-inclusive and GST-exclusive amounts?", "An exclusive amount is "
             "the base price before GST is added; GST is added on top to get the total. An inclusive amount "
             "already has GST baked in; the base price and GST amount are extracted from it."),
            ("Does this calculator account for input tax credit?", "No. Input tax credit is a business-level "
             "adjustment against GST already paid on purchases; this calculator computes GST on a single "
             "amount only."),
            ("Does this include compensation cess?", "No. Certain goods (tobacco, pan masala, some vehicles) "
             "attract an additional compensation cess on top of the 40% GST slab, which this calculator doesn't "
             "model."),
            ("Will these rates change again?", "Possibly; GST Council meetings can revise rates. This "
             "calculator uses the slabs confirmed current as of publish time; verify against the current GST "
             "Council notification before relying on this for a formal filing or invoice."),
        ],
    },
]


def _write_calculator_pages():
    written = []
    for c in CALCULATORS:
        canonical = "%s/calculators/%s/" % (SITE_URL, c["slug"])
        faqs = c.get("faqs") or []
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Calculators", "/calculators/"), (c["h1"], None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebApplication", "name": c["h1"], "url": canonical,
                    "applicationCategory": "FinanceApplication", "operatingSystem": "Any (runs in browser)",
                    "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"},
                },
                {
                    "@type": "FAQPage",
                    "mainEntity": [
                        {"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}}
                        for q, a in faqs
                    ],
                },
                crumb_jsonld,
            ],
        }
        fields_html = "".join(
            '<div class="field"><label for="%s">%s</label>'
            '<input id="%s" type="number" min="0" step="%s" value="%s"></div>'
            % (fid, _esc(label), fid, step, default)
            for fid, label, default, step in c["fields"]
        ) + c.get("extra_fields_html", "")
        faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in faqs
        )
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(c["title"]), "description": _esc(c["description"])[:300],
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(c["h1"])
            + '<p class="muted" style="max-width:68ch">%s</p>' % c["intro"]
            + '<p class="xs faint" style="max-width:68ch;margin-top:8px">%s</p>' % c["formula"]
            + '<div data-calc="%s" class="card" style="margin-top:20px;padding:20px;max-width:480px">' % c["calc"]
            + fields_html
            + '<button type="button" id="calc-btn" class="btn" style="margin-top:8px">Calculate</button>'
            + '<div id="calc-result" class="grid g3" style="margin-top:16px" hidden></div>'
            + '</div>'

            + '<h2 style="margin-top:32px;font-size:18px">How to use this calculator</h2>'
            + '<p style="max-width:68ch">%s</p>' % c["how_to"]

            + '<h2 style="margin-top:28px;font-size:18px">What this doesn\'t account for</h2>'
            + '<p style="max-width:68ch">%s</p>' % c["limits"]

            + ('<h2 style="margin-top:28px;font-size:18px">Frequently asked questions</h2>'
               '<div style="max-width:68ch">%s</div>' % faq_html if faq_html else '')

            + '<p class="xs faint" style="margin-top:20px">This is a generic financial calculation, not investment, '
              'loan or tax advice specific to you. BrokerLens is not a SEBI-registered investment adviser.</p>'
        )
        body = body.replace("</head>", _stamp_asset_versions(
            '<script src="/assets/js/calculators.js" defer></script></head>'))
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page runs a standard, published financial formula entirely in your browser; it is not "
            "generated from any BrokerLens-ingested regulator or exchange dataset.")}

        dest_dir = os.path.join(ROOT, "site", "calculators", c["slug"])
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written.append(c["slug"])

    log("calculator pages: %d written" % len(written), "ok")
    return written


def _write_stock_directory(companies):
    """A-Z browse pages for every NSE-listed equity.

    Index-membership links already reach a stock page for anything in a
    tracked index, but that is a few hundred of ~2,568 listed names - most
    NSE-listed companies are not in Nifty 50 or any other index this site
    tracks, and had NO inbound link anywhere on the site before this, only
    a sitemap.xml entry. A sitemap is a hint, not a crawl-priority signal on
    its own; Google prioritises pages it can actually reach by following a
    link, especially on a low-authority new domain. This closes that gap.
    """
    groups = {}
    for c in companies or []:
        name = (c.get("name") or c.get("symbol") or "").strip()
        symbol = (c.get("symbol") or "").strip()
        slug = _stock_slug(symbol)
        if not name or not slug:
            continue
        letter = name[0].upper()
        letter = letter if letter.isalpha() else "0-9"
        groups.setdefault(letter, []).append((name, symbol, slug))

    letters = sorted(groups.keys(), key=lambda l: (l == "0-9", l))
    nav_html = "".join(
        '<a class="chip" href="/stocks/%s/">%s</a>' % (_esc(slugify(l)), _esc(l)) for l in letters
    )

    written = 0
    for letter in letters:
        rows = sorted(groups[letter], key=lambda r: r[0])
        letter_slug = slugify(letter)
        canonical = "%s/stocks/%s/" % (SITE_URL, letter_slug)
        title = "NSE-Listed Stocks Starting With %s | BrokerLens" % letter
        description = _esc(
            "%d NSE-listed companies whose name starts with %s, each linking to its own listing page "
            "(ISIN, listing date, face value, market lot)." % (len(rows), letter)
        )[:300]
        list_html = "".join(
            '<a href="/stock/%s/">%s <span class="xs faint">(%s)</span></a>'
            % (_esc(slug), _esc(name), _esc(symbol))
            for name, symbol, slug in rows
        )
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Browse stocks", "/stocks/"), (letter, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "ItemList", "name": title, "url": canonical,
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1, "url": "%s/stock/%s/" % (SITE_URL, slug), "name": name}
                        for i, (name, symbol, slug) in enumerate(rows)
                    ],
                },
                crumb_jsonld,
            ],
        }
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">Stocks starting with %s</h1>' % _esc(letter)
            + '<p class="muted" style="max-width:70ch">%d NSE-listed compan%s. Each link goes to that '
              'company\'s own listing page.</p>' % (len(rows), "y" if len(rows) == 1 else "ies")
            + '<div class="row-wrap" style="margin:16px 0">' + nav_html + '</div>'
            + '<div class="link-columns">' + list_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page lists NSE's own listed-securities master file, grouped alphabetically by company name.")}
        dest_dir = os.path.join(ROOT, "site", "stocks", letter_slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    total = sum(len(v) for v in groups.values())
    canonical = "%s/stocks/" % SITE_URL
    title = "Browse NSE-Listed Stocks A-Z | BrokerLens"
    description = ("Every NSE-listed equity BrokerLens has a listing page for (%d companies), "
                    "browsable alphabetically." % total)
    counts_html = "".join(
        '<a class="card" href="/stocks/%s/" style="display:block;text-align:center"><h3>%s</h3>'
        '<p class="xs faint" style="margin-top:4px">%d stocks</p></a>'
        % (_esc(slugify(l)), _esc(l), len(groups[l]))
        for l in letters
    )
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Browse stocks", None)])
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps({"@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "name": title, "url": canonical}, crumb_jsonld]}, ensure_ascii=False),
    }
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Browse NSE-listed stocks</h1>'
        '<p class="muted" style="max-width:70ch">%d companies across %d letters, sourced from NSE\'s own '
        'listed-securities master file.</p>' % (total, len(letters))
        + '<div class="grid g4" style="margin-top:16px">' + counts_html + '</div>'
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page indexes NSE's own listed-securities master file alphabetically by company name.")}
    dest_dir = os.path.join(ROOT, "site", "stocks")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)

    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "stocks"), {slugify(l) for l in letters})
    log("stock directory: %d letter pages written, %d stocks linked%s" % (
        written, total, (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return letters


def _write_fund_amc_pages(fund_slugs):
    """One hub page per AMC (/funds-by/<amc-slug>/), linking every scheme
    that AMC publishes on AMFI's daily NAV master file. Before this, none of
    the 3,365 fund pages had an inbound link anywhere on the site except a
    sitemap.xml entry - the same orphaned-page problem the stock directory
    above fixes for equities, for the single largest page family this
    pipeline writes.
    """
    by_amc = {}
    for slug, (amc, name) in (fund_slugs or {}).items():
        by_amc.setdefault(amc, []).append((name, slug))

    amc_slugs = {}
    for amc in sorted(by_amc):
        base = slugify(amc)
        if not base:
            continue
        slug, n = base, 2
        while slug in amc_slugs.values():
            slug = "%s-%d" % (base, n)
            n += 1
        amc_slugs[amc] = slug

    written = 0
    for amc, rows in by_amc.items():
        amc_slug = amc_slugs.get(amc)
        if not amc_slug:
            continue
        rows_sorted = sorted(rows, key=lambda r: r[0])
        canonical = "%s/funds-by/%s/" % (SITE_URL, amc_slug)
        title = "%s Mutual Fund Schemes | BrokerLens" % amc
        description = _esc(
            "Every %s mutual fund scheme on AMFI's daily NAV master file (%d schemes), with NAV, ISIN and "
            "plan/option details on each scheme's own page." % (amc, len(rows_sorted))
        )[:300]
        list_html = "".join(
            '<a href="/fund/%s/">%s</a>' % (_esc(slug), _esc(name)) for name, slug in rows_sorted
        )
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Mutual funds by AMC", "/funds-by/"), (amc, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "ItemList", "name": title, "url": canonical,
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1, "url": "%s/fund/%s/" % (SITE_URL, slug), "name": name}
                        for i, (name, slug) in enumerate(rows_sorted)
                    ],
                },
                crumb_jsonld,
            ],
        }
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s mutual fund schemes</h1>' % _esc(amc)
            + '<p class="muted" style="max-width:70ch">%d scheme%s from %s, sourced from AMFI\'s own daily '
              'NAV master file.</p>' % (len(rows_sorted), "" if len(rows_sorted) == 1 else "s", _esc(amc))
            + '<div class="link-columns" style="margin-top:16px">' + list_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page groups AMFI's own daily NAV master file by fund house (AMC).")}
        dest_dir = os.path.join(ROOT, "site", "funds-by", amc_slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    total = sum(len(v) for v in by_amc.values())
    canonical = "%s/funds-by/" % SITE_URL
    title = "Browse Mutual Funds by AMC | BrokerLens"
    description = "Every AMC (fund house) on AMFI's daily NAV master file, each linking to its own scheme list."
    amc_cards = "".join(
        '<a class="card" href="/funds-by/%s/" style="display:block"><h3 style="font-size:15px">%s</h3>'
        '<p class="xs faint" style="margin-top:4px">%d schemes</p></a>'
        % (_esc(amc_slugs[amc]), _esc(amc), len(rows))
        for amc, rows in sorted(by_amc.items()) if amc in amc_slugs
    )
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Mutual funds by AMC", None)])
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps({"@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "name": title, "url": canonical}, crumb_jsonld]}, ensure_ascii=False),
    }
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Browse mutual funds by AMC</h1>'
        '<p class="muted" style="max-width:70ch">%d fund houses across %d schemes, sourced from AMFI\'s own '
        'daily NAV master file.</p>' % (len(amc_slugs), total)
        + '<div class="grid g3" style="margin-top:16px">' + amc_cards + '</div>'
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page indexes AMFI's own daily NAV master file by fund house (AMC).")}
    dest_dir = os.path.join(ROOT, "site", "funds-by")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)

    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "funds-by"), set(amc_slugs.values()))
    log("fund AMC directory: %d AMC pages written, %d schemes linked%s" % (
        written, total, (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return amc_slugs


def _write_etf_directory(etfs):
    """A single browse page listing every NSE-listed ETF. Unlike stocks
    (~2.5k) or funds (~3.4k), 350 items fits comfortably on one page without
    needing letter buckets, and gives every ETF page an on-site inbound link
    beyond the handful that also appear on an /index/ constituent page."""
    rows = []
    for e in etfs or []:
        symbol = (e.get("symbol") or "").strip()
        slug = _stock_slug(symbol)
        name = e.get("name") or symbol
        if slug:
            rows.append((name, symbol, slug))
    rows.sort(key=lambda r: r[0])

    canonical = "%s/etfs/" % SITE_URL
    title = "Browse NSE-Listed ETFs | BrokerLens"
    description = _esc(
        "Every NSE-listed ETF BrokerLens has a listing page for (%d funds), each linking to its underlying "
        "benchmark, ISIN, listing date and market lot." % len(rows)
    )[:300]
    list_html = "".join(
        '<a href="/etf/%s/">%s <span class="xs faint">(%s)</span></a>' % (_esc(slug), _esc(name), _esc(symbol))
        for name, symbol, slug in rows
    )
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Browse ETFs", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList", "name": title, "url": canonical,
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "url": "%s/etf/%s/" % (SITE_URL, slug), "name": name}
                    for i, (name, symbol, slug) in enumerate(rows)
                ],
            },
            crumb_jsonld,
        ],
    }
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": description,
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Browse NSE-listed ETFs</h1>'
        '<p class="muted" style="max-width:70ch">%d ETFs, sourced from NSE\'s own listed-ETF register.</p>'
        % len(rows)
        + '<div class="link-columns" style="margin-top:16px">' + list_html + '</div>'
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page lists NSE's own listed-ETF register in full.")}
    dest_dir = os.path.join(ROOT, "site", "etfs")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("ETF directory: 1 page written, %d ETFs linked" % len(rows), "ok")


def _fmt_usd(n, decimals=2):
    if n is None:
        return "Not disclosed"
    return "$%s" % format(round(n, decimals), ",")


def _fmt_supply(n):
    if n is None:
        return "Not disclosed"
    return "%s coins" % format(int(n), ",")


_ZERODHA_LOGO_DATA_URI = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGJhc2VQcm9maWxlPSJ0aW55IiB3aWR0aD"
    "0iNjA5IiBoZWlnaHQ9IjgwIiB4bWxuczp2PSJodHRwczovL3ZlY3RhLmlvL25hbm8iPjxwYXRoIGQ9Ik02Ni4yNTIgMjEuNDY5YzQuNDA0IDUuNz"
    "EgOC4wNTYgMTIuMTI0IDEwLjg4NiAxOS4wNFYzLjkzMUg0Ni4wNzdjNy40NzIgNC4wMzcgMTQuMzE3IDkuOTQzIDIwLjE3NSAxNy41Mzh6TTIxLj"
    "Q3MyA3LjgyOGMtNS43NTQgMC0xMS4yODkgMS4yMy0xNi40NzMgMy41MDZ2NjQuNzM1aDY4Ljk2M2MtLjUzNC0zNy43NTQtMjMuODc1LTY4LjI0MS"
    "01Mi40OS02OC4yNDEiIGZpbGwtcnVsZT0iZXZlbm9kZCIgZmlsbD0iIzM4N2VkMSIvPjxwYXRoIGZpbGw9IiMzODdlZDEiIGQ9Ik0xMTguMzQ5ID"
    "Y0LjkxOGwzOC41MzMtNDYuNjVIMTE5LjU2VjguMDk4aDUyLjI1djguNDlsLTM4LjUzMyA0Ni42NTFoMzguNTMzdjEwLjE2OWgtNTMuNDYxdi04Lj"
    "Q5em02Ny44MjgtNTYuODJoNDguMzMxdjEwLjM1NkgxOTcuNTZ2MTYuNzk0aDMyLjc1MXYxMC4zNTdIMTk3LjU2djE3LjQ0NmgzNy40MTN2MTAuMz"
    "U2aC00OC43OTZWOC4wOTh6bTYyLjUxMiAwaDI5LjExYzQuMTA1IDAgNy43NDQuNTc2IDEwLjkxNyAxLjcyNnM1LjgxNCAyLjc1MiA3LjkzIDQuOD"
    "A1YzEuNzQxIDEuODA1IDMuMDggMy44ODggNC4wMTMgNi4yNTFzMS4zOTggNC45NzcgMS4zOTggNy44Mzd2LjE4N2MwIDIuNjc1LS4zODggNS4wOD"
    "UtMS4xNjUgNy4yMzFzLTEuODUzIDQuMDQ0LTMuMjIgNS42OTEtMy4wMDEgMy4wNDktNC44OTggNC4xOTgtMy45OTcgMi4wMzgtNi4yOTcgMi42NT"
    "lsMTcuNjMzIDI0LjcyNWgtMTMuNTI5bC0xNi4wOTctMjIuNzY1aC0uMTg2LTE0LjIyN3YyMi43NjVoLTExLjM4M1Y4LjA5OHptMjguMjMxIDMyLj"
    "M3NWM0LjExNSAwIDcuMzkzLS45ODIgOS44MjQtMi45NTFzMy42NTItNC42MzkgMy42NTItOC4wMTJ2LS4xODdjMC0zLjU2LTEuMTg4LTYuMjYzLT"
    "MuNTU5LTguMTA2cy01LjcwOS0yLjc2NC0xMC4wMTQtMi43NjRoLTE2Ljc1MnYyMi4wMTloMTYuODQ5em03MC4zODkgMzQuMDU1Yy01LjAzOSAwLT"
    "kuNjQxLS44ODYtMTMuODA3LTIuNjU4cy03Ljc0NC00LjE4Mi0xMC43My03LjIzMi01LjMxOC02LjYwNy02Ljk5Ni0xMC42ODItMi41MjEtOC40MT"
    "MtMi41MjEtMTMuMDE2di0uMTg3YzAtNC42MDMuODQtOC45NDEgMi41MjEtMTMuMDE2czQuMDQxLTcuNjUxIDcuMDktMTAuNzMgNi42NTQtNS41Mi"
    "AxMC44MjQtNy4zMjQgOC43NjgtMi43MDYgMTMuODA3LTIuNzA2IDkuNjQxLjg4NiAxMy44MDkgMi42NTkgNy43NDQgNC4xODQgMTAuNzMgNy4yMz"
    "EgNS4zMTYgNi42MDkgNi45OTYgMTAuNjgzIDIuNTIxIDguNDEzIDIuNTIxIDEzLjAxNXYuMTg3YzAgNC42MDQtLjg0IDguOTQzLTIuNTIxIDEzLj"
    "AxNXMtNC4wNDMgNy42NTEtNy4wOSAxMC43My02LjY1NiA1LjUyMS0xMC44MjQgNy4zMjQtOC43NyAyLjcwNy0xMy44MDkgMi43MDd6bS4xODctMT"
    "AuNTQzYzMuMjIxIDAgNi4xNzgtLjYwNiA4Ljg3MS0xLjgxOXM1LjAwMi0yLjg2IDYuOTIyLTQuOTQ0IDMuNDIyLTQuNTI2IDQuNTA2LTcuMzI1ID"
    "EuNjI1LTUuNzg1IDEuNjI1LTguOTU2di0uMTg3YzAtMy4xNzItLjU0MS02LjE3My0xLjYyNS05LjAwNHMtMi42MDQtNS4yODYtNC41NTMtNy4zNy"
    "00LjI4OS0zLjc0Ny03LjAxNi00Ljk5Mi01LjY5Ny0xLjg2Ni04LjkxOC0xLjg2Ni02LjE3OC42MDYtOC44NzEgMS44MTktNS4wMDIgMi44NjItNi"
    "45MjIgNC45NDUtMy40MjIgNC41MjUtNC41MDggNy4zMjQtMS42MjUgNS43ODUtMS42MjUgOC45NTd2LjE4N2MwIDMuMTcyLjU0MSA2LjE3MyAxLj"
    "YyNSA5LjAwMnMyLjYwNCA1LjI4OSA0LjU1NSA3LjM3MiA0LjI4OSAzLjc0OCA3LjAxNCA0Ljk5MSA1LjY5OSAxLjg2NiA4LjkyIDEuODY2em00Ny"
    "45NTUtNTUuODg3aDI0LjM1NGM1LjEgMCA5Ljc3OS44MjUgMTQuMDQzIDIuNDczczcuOTI4IDMuOTM0IDExLjAwOCA2Ljg1NyA1LjQ1NyA2LjM2MS"
    "A3LjEzOSAxMC4zMTEgMi41MiA4LjIyNyAyLjUyIDEyLjgyOXYuMTg3YzAgNC42MDQtLjg0IDguODk2LTIuNTIgMTIuODc1cy00LjA1OSA3LjQzNS"
    "03LjEzOSAxMC4zNTYtNi43NDggNS4yMjYtMTEuMDA4IDYuOTA0LTguOTQzIDIuNTE5LTE0LjA0MyAyLjUxOWgtMjQuMzU0VjguMDk4em0yNC4yNi"
    "A1NC45NTRjMy40MiAwIDYuNTMxLS41NDUgOS4zMy0xLjYzOXM1LjE4LTIuNjIyIDcuMTM3LTQuNTg5IDMuNDgyLTQuMzEyIDQuNTcyLTcuMDMgMS"
    "42MzUtNS42NjcgMS42MzUtOC44NTR2LS4xODdjMC0zLjE4Ni0uNTQ3LTYuMTUyLTEuNjM1LTguOXMtMi42MTMtNS4xMDYtNC41NzItNy4wNzQtNC"
    "4zMzgtMy41MTQtNy4xMzctNC42MzktNS45MS0xLjY4Ny05LjMzLTEuNjg3aC0xMi44Nzd2NDQuNTk4aDEyLjg3N3ptNDguNzAzLTU0Ljk1NGgxMS"
    "4zODN2MjcuMTUxaDMxLjM1MlY4LjA5OGgxMS4zODN2NjUuMzExaC0xMS4zODNWNDUuODg1aC0zMS4zNTJ2MjcuNTIzaC0xMS4zODNWOC4wOTh6bT"
    "k0LjA0OS0uNDY3SDU3My4xbDI4LjczNiA2NS43NzdoLTEyLjEyOWwtNi42MjUtMTUuNzY4aC0zMC44ODNsLTYuNzE5IDE1Ljc2OGgtMTEuNzU2bD"
    "I4LjczOS02NS43Nzd6bTE2LjQyMiAzOS44NDFsLTExLjI5MS0yNi4xMjUtMTEuMTk3IDI2LjEyNWgyMi40ODh6Ii8+PC9zdmc+"
)


_FIVEPAISA_LOGO_DATA_URI = (
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTE1IiBoZWlnaHQ9IjI4IiB2aWV3Qm94PSIwIDAgMTE1IDI4IiBmaWxsPSJub25lIiB4bWxucz0i"
    "aHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIj4NCjxwYXRoIGZpbGwtcnVsZT"
    "0iZXZlbm9kZCIgY2xpcC1ydWxlPSJldmVub2RkIiBkPSJNODIuMTY5OCAyLjA2MTQ5VjUuMTM4NzNIODUuNjc1MlYyLjA2MTQ5SDgyLjE2OThaTTgyLjMw"
    "MzYgNy4zMDYxOVYyMS40MzM3SDg1LjU2ODFWNy4zMDYxOUg4Mi4zMDM2Wk00NC4wNjA4IDIuNzAzNjlIMzIuODU2NEgzMi44NTUzTDMyLjMyMDIgMTEuOD"
    "gxOUwzNC4zMDAzIDEzLjE5MzFDMzQuNzgyIDEyLjk2MTkgMzUuMzA3NSAxMi43NjUgMzUuODc5MSAxMi42MDQ0QzM2LjQ0OTYgMTIuNDQzOCAzNy4wNzM2"
    "IDEyLjM2MzYgMzcuNzUyMiAxMi4zNjM2QzM4LjkyOTUgMTIuMzYzNiAzOS44NjkzIDEyLjY0NjEgNDAuNTc0NyAxMy4yMTAyQzQxLjI3OSAxMy43NzQzID"
    "QxLjYzMTEgMTQuNTA0MyA0MS42MzExIDE1LjUwNzJDNDEuNjMxMSAxNi41MTAxIDQxLjI5MTggMTcuMzA3NSA0MC42MTQzIDE3Ljg5ODNDMzkuOTM1NyAx"
    "OC40ODkyIDM5LjAzNTUgMTguNzg0NiAzNy45MTE2IDE4Ljc4NDZDMzcuMDM4MiAxOC43ODQ2IDM2LjIwMzQgMTguNTg0NCAzNS40MTAyIDE4LjE4M0MzNC"
    "42MTcxIDE3Ljc4MTcgMzMuODQ1NCAxNy4yMzM3IDMzLjA5NjIgMTYuNTM3OUwzMS4wNjI1IDE4LjkxODRDMzEuOTU0MSAxOS43NjcyIDMyLjk2MjQgMjAu"
    "NDUyMiAzNC4wODYyIDIwLjk3MzRDMzUuMjEwMSAyMS40OTQ3IDM2LjQ5NDUgMjEuNzU1OSAzNy45Mzk1IDIxLjc1NTlDMzguOTczNCAyMS43NTU5IDM5Lj"
    "kxOTYgMjEuNjAzOSA0MC43NzcgMjEuMzAxQzQxLjYzNDMgMjAuOTk4MSA0Mi4zNjk2IDIwLjU2OTkgNDIuOTgwOCAyMC4wMTY2QzQzLjU5MiAxOS40NjQz"
    "IDQ0LjA2NCAxOC43OTUzIDQ0LjM5NjkgMTguMDA5N0M0NC43Mjk4IDE3LjIyNTEgNDQuODk1NyAxNi4zODU5IDQ0Ljg5NTcgMTUuMzg3M0M0NC44OTU3ID"
    "E0LjM4ODcgNDQuNzI5OCAxMy41MTk1IDQ0LjM5NjkgMTIuNzc4OUM0NC4wNjQgMTIuMDM5MyA0My42MDA1IDExLjQyMzggNDMuMDA3NiAxMC45MzI1QzQy"
    "LjQxMzUgMTAuNDQyMyA0MS43MTk5IDEwLjA3NjIgNDAuOTI0NyA5LjgzNTQxQzQwLjEyOTQgOS41OTM1MiAzOS4yNzc0IDkuNDczNjQgMzguMzY3NiA5Lj"
    "Q3MzY0QzM3Ljc0MzYgOS40NzM2NCAzNy4yMDQxIDkuNTIzOTQgMzYuNzQ5MyA5LjYyMTM0QzM2LjI5NDQgOS43MTg3NSAzNS44NDM3IDkuODQ4MjYgMzUu"
    "Mzk4NSAxMC4wMDg4TDM1LjY5MjggNS42MjAzOUg0NC4wNjA4VjIuNzAzNjlaTTYxLjA3MjQgMTkuODE0MkM2MS42ODc5IDE5LjE4MTcgNjIuMTc4MSAxOC"
    "40MSA2Mi41NDQyIDE3LjUwMDJINjIuNTQ1MkM2Mi45MTAyIDE2LjU5MDQgNjMuMDkzMyAxNS41NDY4IDYzLjA5MzMgMTQuMzY5NEM2My4wOTMzIDEzLjE5"
    "MiA2Mi45MDU5IDEyLjE0ODQgNjIuNTMyNCAxMS4yMzg2QzYyLjE1ODggMTAuMzI4OCA2MS42NjQzIDkuNTU4MTkgNjEuMDUxIDguOTI0NTRDNjAuNDM2Ny"
    "A4LjI5MTk3IDU5LjczODggNy44MTQ2IDU4Ljk1NTMgNy40OTM0OUM1OC4xNzI5IDcuMTcyMzkgNTcuMzYyNiA3LjAxMTg0IDU2LjUyNjcgNy4wMTE4NEM1"
    "NS4zODc4IDcuMDExODQgNTQuNDM1MiA3LjI2NTUxIDUzLjY2OTkgNy43NzM5MkM1Mi45MDQ2IDguMjgyMzQgNTIuMjYzNSA4LjkxMDYzIDUxLjc0NzYgOS"
    "42NTk4N1Y3LjMwNTExSDQ4LjQ4M1YyNS43MTRINTEuNzQ3Nkw1MS43MjA4IDE5LjIzODRDNTIuMjE5NiAxOS44OTg4IDUyLjg1MzIgMjAuNDc4OSA1My42"
    "MjA3IDIwLjk3NzdDNTQuMzg4MSAyMS40NzY1IDU1LjM1MDQgMjEuNzI3IDU2LjUxMDYgMjEuNzI3QzU3LjM0ODcgMjEuNzI3IDU4LjE2NDMgMjEuNTY2NC"
    "A1OC45NTg1IDIxLjI0NTNDNTkuNzUyNyAyMC45MjQyIDYwLjQ1NyAyMC40NDc5IDYxLjA3MjQgMTkuODE0MlpNNTguNjM4NSAxMS4wNTI0QzU5LjAwMzUg"
    "MTEuNDQ0MSA1OS4yOTM1IDExLjkyMTUgNTkuNTA3NiAxMi40ODM0QzU5LjcyMTcgMTMuMDQ1NCA1OS44Mjg3IDEzLjY3MzcgNTkuODI4NyAxNC4zNjk0Qz"
    "U5LjgyODcgMTUuMDY1MSA1OS43MjE3IDE1LjY5MzQgNTkuNTA3NiAxNi4yNTUzQzU5LjI5MzUgMTYuODE3MyA1OS4wMDM1IDE3LjI5NDcgNTguNjM4NSAx"
    "Ny42ODY0QzU4LjI3MjQgMTguMDc5MiA1Ny44NDQzIDE4LjM4MjEgNTcuMzU0MSAxOC41OTYyQzU2Ljg2MzggMTguODEwMyA1Ni4zNDI2IDE4LjkxNzMgNT"
    "UuNzg5MiAxOC45MTczQzU1LjIzNTggMTguOTE3MyA1NC43MDkyIDE4LjgxMDMgNTQuMjEwNCAxOC41OTYyQzUzLjcxMDYgMTguMzgyMSA1My4yNzM5IDE4"
    "LjA3NDkgNTIuODk5MyAxNy42NzM2QzUyLjUyNDYgMTcuMjcyMiA1Mi4yMjYgMTYuNzk1OSA1Mi4wMDM0IDE2LjI0MjVDNTEuNzgwOCAxNS42OTAyIDUxLj"
    "Y2OTQgMTUuMDY1MSA1MS42Njk0IDE0LjM2OTRDNTEuNjY5NCAxMy42NzM3IDUxLjc3OTcgMTMuMDQ5NyA1Mi4wMDM0IDEyLjQ5NjNDNTIuMjI2IDExLjk0"
    "NCA1Mi41MjQ2IDExLjQ2NjYgNTIuODk5MyAxMS4wNjUyQzUzLjI3MzkgMTAuNjYzOSA1My43MTA2IDEwLjM1NjcgNTQuMjEwNCAxMC4xNDI2QzU0LjcwOT"
    "IgOS45Mjg1MyA1NS4yMzY5IDkuODIxNSA1NS43ODkyIDkuODIxNUM1Ni4zNDE1IDkuODIxNSA1Ni44NjI4IDkuOTI4NTMgNTcuMzU0MSAxMC4xNDI2QzU3"
    "Ljg0NDMgMTAuMzU2NyA1OC4yNzI0IDEwLjY2MDYgNTguNjM4NSAxMS4wNTI0Wk03NS4wNTI5IDIxLjQzMzdWMTkuNjk0NEM3NC41NzEzIDIwLjI2NTkgNz"
    "MuOTU1OCAyMC43NDc2IDczLjIwNjYgMjEuMTM5NEM3Mi40NTc0IDIxLjUzMTEgNzEuNTQ3NiAyMS43MjggNzAuNDc3MiAyMS43MjhDNjkuNzk4NiAyMS43"
    "MjggNjkuMTU2NCAyMS42MzM5IDY4LjU1MDYgMjEuNDQ3NkM2Ny45NDM3IDIxLjI2MDMgNjcuNDEzOSAyMC45ODQyIDY2Ljk1OSAyMC42MTgxQzY2LjUwND"
    "EgMjAuMjUzMSA2Ni4xMzggMTkuNzk4MiA2NS44NjE5IDE5LjI1MzRDNjUuNTg0NyAxOC43MDk3IDY1LjQ0NjYgMTguMDgwMyA2NS40NDY2IDE3LjM2NzVW"
    "MTcuMzEzOUM2NS40NDY2IDE2LjU0NzYgNjUuNTg4OSAxNS44Nzg2IDY1Ljg3NDcgMTUuMzA3QzY2LjE1OTQgMTQuNzM2NSA2Ni41NTY1IDE0LjI2MzQgNj"
    "cuMDY0OSAxMy44ODg4QzY3LjU3MzQgMTMuNTE0MiA2OC4xNzkyIDEzLjIzMzggNjguODg0NSAxMy4wNDY1QzY5LjU4ODggMTIuODU5MiA3MC4zNTIgMTIu"
    "NzY2IDcxLjE3MTkgMTIuNzY2QzcxLjk5MTggMTIuNzY2IDcyLjc1NDkgMTIuODE5NSA3My4zNTIyIDEyLjkyNjZDNzMuOTQ5NCAxMy4wMzM2IDc0LjUyNT"
    "MgMTMuMTc3IDc1LjA3NzYgMTMuMzU0N1YxMy4wMDY5Qzc1LjA3NzYgMTIuMDI2NCA3NC43Nzg5IDExLjI3NzIgNzQuMTgwNiAxMC43NTkxQzczLjU4MjMg"
    "MTAuMjQyMiA3Mi43MjI4IDkuOTgzMTMgNzEuNTk4OSA5Ljk4MzEzQzcwLjc5NjIgOS45ODMxMyA3MC4wODIzIDEwLjA2MzQgNjkuNDU4MyAxMC4yMjRDNj"
    "guODMzMiAxMC4zODQ1IDY4LjIwMDYgMTAuNTk4NiA2Ny41NTg0IDEwLjg2NjJMNjYuNjc1NCA4LjI3MDU3QzY3LjQ1OTkgNy45MTQxNSA2OC4yNjI3IDcu"
    "NjI4MzYgNjkuMDgzNiA3LjQxNDI5QzY5LjkwMzUgNy4yMDAyMyA3MC44OTM2IDcuMDkzMTkgNzIuMDUzOCA3LjA5MzE5Qzc0LjE1ODEgNy4wOTMxOSA3NS"
    "43MTk4IDcuNjE1NTIgNzYuNzM2NiA4LjY1ODA0Qzc3Ljc1MzQgOS43MDA1NiA3OC4yNjE5IDExLjE2OTEgNzguMjYxOSAxMy4wNTkzVjIxLjQzNDhINzUu"
    "MDUwOEw3NS4wNTI5IDIxLjQzMzdaTTc1LjEzMzIgMTUuNDM5OEM3NC43MjIyIDE1LjI3OTIgNzQuMjM2MyAxNS4xNDU0IDczLjY3NTQgMTUuMDM4NEM3My"
    "4xMTM1IDE0LjkzMTMgNzIuNTIwNSAxNC44Nzc4IDcxLjg5NjUgMTQuODc3OEM3MC44Nzk3IDE0Ljg3NzggNzAuMDg1NSAxNS4wNzQ4IDY5LjUxNSAxNS40"
    "NjY1QzY4Ljk0MzQgMTUuODU5MyA2OC42NTg3IDE2LjQyMTMgNjguNjU4NyAxNy4xNTIzVjE3LjIwNThDNjguNjU4NyAxNy44ODQ0IDY4LjkyMiAxOC40MD"
    "E0IDY5LjQ0NzUgMTguNzU3OEM2OS45NzMxIDE5LjExNTMgNzAuNjIwNiAxOS4yOTMgNzEuMzg3IDE5LjI5M0M3MS45MjIyIDE5LjI5MyA3Mi40MTY3IDE5"
    "LjIyMjQgNzIuODcxNiAxOS4wNzg5QzczLjMyNjUgMTguOTM2NiA3My43MjM2IDE4LjczNTQgNzQuMDYxOCAxOC40Nzc0Qzc0LjQgMTguMjE5NCA3NC42Nj"
    "MzIDE3LjkwNjkgNzQuODUxNyAxNy41NDA4Qzc1LjAzOSAxNy4xNzU5IDc1LjEzMjIgMTYuNzY5MSA3NS4xMzIyIDE2LjMyMzlWMTUuNDQwOEw3NS4xMzMy"
    "IDE1LjQzOThaTTk5LjQ1NDYgMTkuMjEyN0M5OS4xODcgMTkuNzY2MSA5OC44MTY3IDIwLjIyNTMgOTguMzQ0NyAyMC41OTAzQzk3Ljg3MTYgMjAuOTU2My"
    "A5Ny4zMTUgMjEuMjMyNSA5Ni42NzI4IDIxLjQxOThDOTYuMDMwNiAyMS42MDcxIDk1LjM0MzQgMjEuNzAwMiA5NC42MTI0IDIxLjcwMDJDOTMuNTk1NSAy"
    "MS43MDAyIDkyLjU2NTkgMjEuNTIxNSA5MS41MjIzIDIxLjE2NUM5MC40Nzg3IDIwLjgwODYgODkuNTExMSAyMC4yODIgODguNjE5NSAxOS41ODYzTDkwLj"
    "A2NDUgMTcuMzkyMUM5MC44MzA4IDE3Ljk2MzYgOTEuNjEyMiAxOC4zOTUgOTIuNDA1MyAxOC42ODkzQzkzLjE5ODQgMTguOTgzNyA5My45NjE2IDE5LjEz"
    "MDMgOTQuNjkyNiAxOS4xMzAzQzk1LjQyMzcgMTkuMTMwMyA5NS45Mjc4IDE4Ljk5MjIgOTYuMzExIDE4LjcxNUM5Ni42OTQyIDE4LjQzODkgOTYuODg1OC"
    "AxOC4wNjg1IDk2Ljg4NTggMTcuNjA1MVYxNy41NTE1Qzk2Ljg4NTggMTcuMjg0IDk2LjgwMTIgMTcuMDUyOCA5Ni42MzEgMTYuODU1OEM5Ni40NjE5IDE2"
    "LjY1OTkgOTYuMjI5NyAxNi40ODU1IDk1LjkzNTMgMTYuMzMzNUM5NS42NDEgMTYuMTgyNiA5NS4zMDE3IDE2LjA0ODggOTQuOTE4NSAxNS45MzIxQzk0Lj"
    "Y3NDMgMTUuODU4NiA5NC40MjUzIDE1Ljc4MyA5NC4xNzExIDE1LjcwNThMOTQuMTcwMiAxNS43MDU1TDkzLjcyODMgMTUuNTcxNEM5My4yMTAyIDE1LjQx"
    "MDggOTIuNjg5IDE1LjIzMzIgOTIuMTYzNCAxNS4wMzYyQzkxLjYzNjggMTQuODQwNCA5MS4xNjQ4IDE0LjU4NTYgOTAuNzQ1MiAxNC4yNzQxQzkwLjMyNT"
    "YgMTMuOTYyNyA4OS45ODMxIDEzLjU3ODQgODkuNzE1NSAxMy4xMjM1Qzg5LjQ0NzkgMTIuNjY4NiA4OS4zMTQxIDEyLjEwMjQgODkuMzE0MSAxMS40MjQ5"
    "VjExLjM3MTRDODkuMzE0MSAxMC43MTIgODkuNDQzNyAxMC4xMTM3IDg5LjcwMTYgOS41Nzg1M0M4OS45NTk2IDkuMDQzMzYgOTAuMzE3MSA4LjU4ODQ2ID"
    "kwLjc3MiA4LjIxMzg0QzkxLjIyNjkgNy44MzkyMiA5MS43NjIgNy41NTQ1IDkyLjM3NzUgNy4zNTc1NkM5Mi45OTI5IDcuMTYxNjkgOTMuNjQ5MSA3LjA2"
    "MzIyIDk0LjM0MzcgNy4wNjMyMkM5NS4yMzUzIDcuMDYzMjIgOTYuMTM2NSA3LjIwNjY0IDk3LjA0NjMgNy40OTEzNUM5Ny45NTYxIDcuNzc3MTQgOTguNz"
    "g1NyA4LjE2OTk1IDk5LjUzNDkgOC42Njg3NEw5OC4yNTA1IDEwLjk3Qzk3LjU3MTkgMTAuNTYgOTYuODg1OCAxMC4yMzQ3IDk2LjE5MDEgOS45OTM4M0M5"
    "NS40OTQzIDkuNzUzIDk0Ljg1MjEgOS42MzIwNSA5NC4yNjM0IDkuNjMyMDVDOTMuNjM5NCA5LjYzMjA1IDkzLjE1MzUgOS43NjU4NCA5Mi44MDU2IDEwLj"
    "AzMzRDOTIuNDU3OCAxMC4zMDEgOTIuMjgzMyAxMC42NDAzIDkyLjI4MzMgMTEuMDUwM1YxMS4xMDM4QzkyLjI4MzMgMTEuMzU0MiA5Mi4zNzIxIDExLjU3"
    "MjYgOTIuNTUwOSAxMS43NTg4QzkyLjcyODYgMTEuOTQ2MSA5Mi45NjYyIDEyLjExNjMgOTMuMjU5NSAxMi4yNjcyQzkzLjU1MzggMTIuNDE5MiA5My44OT"
    "IgMTIuNTYxNiA5NC4yNzYzIDEyLjY5NTRDOTQuNjU5NSAxMi44MjkyIDk1LjA1NjYgMTIuOTU4NyA5NS40NjY1IDEzLjA4MjhDOTUuOTgzNSAxMy4yNDM0"
    "IDk2LjUwMDUgMTMuNDMwNyA5Ny4wMTg1IDEzLjY0NDhDOTcuNTM1NSAxMy44NTg4IDk4LjAwNDMgMTQuMTIyMiA5OC40MjI4IDE0LjQzNDdDOTguODQxMy"
    "AxNC43NDcyIDk5LjE4NDkgMTUuMTI2MSA5OS40NTI1IDE1LjU3MTRDOTkuNzIwMSAxNi4wMTc3IDk5Ljg1MzkgMTYuNTYxNSA5OS44NTM5IDE3LjIwMzdW"
    "MTcuMjU3MkM5OS44NTM5IDE4LjAwNjQgOTkuNzIwMSAxOC42NTgzIDk5LjQ1MjUgMTkuMjEwNkw5OS40NTQ2IDE5LjIxMjdaTTExMS43OSAxOS42OTQ0Vj"
    "IxLjQzMzdMMTExLjc4OSAyMS40MzQ4SDExNVYxMy4wNTkzQzExNSAxMS4xNjkxIDExNC40OTEgOS43MDE2MyAxMTMuNDc1IDguNjU4MDRDMTEyLjQ1OCA3"
    "LjYxNTUyIDExMC44OTYgNy4wOTMxOSAxMDguNzkyIDcuMDkzMTlDMTA3LjYzMiA3LjA5MzE5IDEwNi42NDEgNy4yMDAyMyAxMDUuODIyIDcuNDE0MjlDMT"
    "A1LjAwMSA3LjYyODM2IDEwNC4xOTggNy45MTQxNSAxMDMuNDEzIDguMjcwNTdMMTA0LjI5NiAxMC44NjYyQzEwNC45MzkgMTAuNTk4NiAxMDUuNTcxIDEw"
    "LjM4NDUgMTA2LjE5NiAxMC4yMjRDMTA2LjgyIDEwLjA2MzQgMTA3LjUzNCA5Ljk4MzEzIDEwOC4zMzcgOS45ODMxM0MxMDkuNDYxIDkuOTgzMTMgMTEwLj"
    "MyIDEwLjI0MjIgMTEwLjkxOSAxMC43NTkxQzExMS41MTcgMTEuMjc3MiAxMTEuODE2IDEyLjAyNjQgMTExLjgxNiAxMy4wMDY5VjEzLjM1NDdDMTExLjI2"
    "MyAxMy4xNzcgMTEwLjY4NyAxMy4wMzM2IDExMC4wOSAxMi45MjY2QzEwOS40OTMgMTIuODE5NSAxMDguNzMgMTIuNzY2IDEwNy45MSAxMi43NjZDMTA3Lj"
    "A5IDEyLjc2NiAxMDYuMzI3IDEyLjg1OTIgMTA1LjYyMyAxMy4wNDY1QzEwNC45MTcgMTMuMjMzOCAxMDQuMzEgMTMuNTE0MiAxMDMuODAzIDEzLjg4ODhD"
    "MTAzLjI5NiAxNC4yNjM0IDEwMi44OTcgMTQuNzM2NSAxMDIuNjEzIDE1LjMwN0MxMDIuMzI3IDE1Ljg3ODYgMTAyLjE4NSAxNi41NDc2IDEwMi4xODUgMT"
    "cuMzEzOVYxNy4zNjc1QzEwMi4xODUgMTguMDgwMyAxMDIuMzIzIDE4LjcwOTcgMTAyLjU5OSAxOS4yNTM0QzEwMi44NzUgMTkuNzk4MiAxMDMuMjQxIDIw"
    "LjI1MzEgMTAzLjY5NiAyMC42MTgxQzEwNC4xNTEgMjAuOTg0MiAxMDQuNjgxIDIxLjI2MDMgMTA1LjI4NyAyMS40NDc2QzEwNS44OTMgMjEuNjMzOSAxMD"
    "YuNTM2IDIxLjcyOCAxMDcuMjE0IDIxLjcyOEMxMDguMjg0IDIxLjcyOCAxMDkuMTk0IDIxLjUzMTEgMTA5Ljk0NCAyMS4xMzk0QzExMC42OTMgMjAuNzQ3"
    "NiAxMTEuMzA4IDIwLjI2NTkgMTExLjc5IDE5LjY5NDRaTTExMC40MTIgMTUuMDM4NEMxMTAuOTczIDE1LjE0NTQgMTExLjQ1OSAxNS4yNzkyIDExMS44Ny"
    "AxNS40Mzk4TDExMS44NzEgMTUuNDQwOFYxNi4zMjM5QzExMS44NzEgMTYuNzY5MSAxMTEuNzc4IDE3LjE3NTkgMTExLjU5MSAxNy41NDA4QzExMS40MDIg"
    "MTcuOTA2OSAxMTEuMTM5IDE4LjIxOTQgMTEwLjgwMSAxOC40Nzc0QzExMC40NjMgMTguNzM1NCAxMTAuMDY2IDE4LjkzNjYgMTA5LjYxMSAxOS4wNzg5Qz"
    "EwOS4xNTUgMTkuMjIyNCAxMDguNjYgMTkuMjkzIDEwOC4xMjUgMTkuMjkzQzEwNy4zNTkgMTkuMjkzIDEwNi43MTEgMTkuMTE1MyAxMDYuMTg2IDE4Ljc1"
    "NzhDMTA1LjY1OSAxOC40MDE0IDEwNS4zOTYgMTcuODg0NCAxMDUuMzk2IDE3LjIwNThWMTcuMTUyM0MxMDUuMzk2IDE2LjQyMTMgMTA1LjY4IDE1Ljg1OT"
    "MgMTA2LjI1MiAxNS40NjY1QzEwNi44MjIgMTUuMDc0OCAxMDcuNjE3IDE0Ljg3NzggMTA4LjYzMyAxNC44Nzc4QzEwOS4yNTcgMTQuODc3OCAxMDkuODUg"
    "MTQuOTMxMyAxMTAuNDEyIDE1LjAzODRaIiBmaWxsPSJibGFjayIvPg0KPHBhdGggZD0iTTAuMDM5ODU0OCAwTDAgMjhIMjcuOTU5MUwyOCAwSDAuMDM5OD"
    "U0OFoiIGZpbGw9IiNDMDFGNDEiLz4NCjxyZWN0IHdpZHRoPSIyOCIgaGVpZ2h0PSIyOCIgZmlsbD0idXJsKCNwYXR0ZXJuMCkiLz4NCjxkZWZzPg0KPHBh"
    "dHRlcm4gaWQ9InBhdHRlcm4wIiBwYXR0ZXJuQ29udGVudFVuaXRzPSJvYmplY3RCb3VuZGluZ0JveCIgd2lkdGg9IjEiIGhlaWdodD0iMSI+DQo8dXNlIH"
    "hsaW5rOmhyZWY9IiNpbWFnZTBfMjY5NF8xNzQxOCIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTAuMDA1OTUyMzgpIHNjYWxlKDAuMDExOTA0OCkiLz4NCjwv"
    "cGF0dGVybj4NCjxpbWFnZSBpZD0iaW1hZ2UwXzI2OTRfMTc0MTgiIHdpZHRoPSI4NSIgaGVpZ2h0PSI4NCIgeGxpbms6aHJlZj0iZGF0YTppbWFnZS9wbm"
    "c7YmFzZTY0LGlWQk9SdzBLR2dvQUFBQU5TVWhFVWdBQUFGVUFBQUJVQ0FZQUFBRHpxWHYvQUFBQUNYQklXWE1BQUNFNEFBQWhPQUZGbGpGZ0FBQUFBWE5T"
    "UjBJQXJzNGM2UUFBQUFSblFVMUJBQUN4and2OFlRVUFBQ1hKU1VSQlZIZ0I3WHhwa0Z6WGRkNTVXeS9Ucys4eldBWVk3QXRCQ2pSSm1mTENPSXJzS2xteH"
    "JDU01GYWVRdUZLV3k1S3R5Rlk1NVpUTENWVmhMRVd1Y2xTeHliS2k4cC9ZK1NNblRxbXNoRjZTU0tJaVVlSWlVZ0lKRUlOOW1YMm1lNlo3Wm5wN1M4NTN6"
    "cjJ2MzhBTFNSRUFLUnNYNk9xZTEvMjJjOC95bmUrYys0anVqcnZqN3JnNzdvNjc0KzY0Tys2T3UrUHUrRnN4SExyRjR4dGYrTUpZTzFmOG9YeFAxL0Zjc1"
    "Rqa2t6T1VFQTNIamZaQVRJa1g4dkJ5L2xvY3hVdXRkcnRjMzlxYTNhaXVuVzdPenovejZDLy9jcG4rQm93M0xkVG5ubnJxVURBdzlJK0x4Znc3K1dnbmcy"
    "SitMUEE4U2hJV1plSlJPd3lKQlNpL3hUYTg0bGovZGh5SDJzUy9hYmVwMGFnblliTjVyZFZ1L1orMXBhWC9QZmZzeWg5OTlMYy8ycVR2d2ZGZENmWFpMLz"
    "c1ZEdsODZDTzV2UDhldjVBL0xrTGs3VUhncStENGN4eEZGSVZFSWI5alExYVk4am1KS1dKaFE2alludkRMY1Z5SytZcFlzTlRZMnFxRjlmcm55d3VMdi92"
    "QmYzSHFlZm9lR205SXFHZGZQUDFJNGlUL09wL1B2OXNQV0FJc0xkZDEwKzhoTFB3ZHh3bHRibTFTdFZxblJuMkxXR1FpTUNmUk0vTCtWT3JxSWovSVVTTk"
    "1pRDBDZWE2SEkxQ1RQK000bUF6UlpCYndSbVgxNmJYcTJyODZkZXJVTitsN1lMeW1VRC8vK2M5N2g2ZW5QMURNRjMvVnorVk9lcXlWY1JJUnY2bUo4eUZt"
    "NXhlbzNtanczekZkblZ1aFJxc3RBdk9EZ0JwcnkzVHlvWWZwN0xtTEJLRkZMTFRxK2hydDJUbEtVYUttMzEwcVViRlFvSjZlWHNLQlZjZ3V0Vm5Wb2NFUk"
    "M3alZhbEYxZGZsUEc4dnJQMy9xRjMvMk1yMk54MThwMUplZmZlSEhJaWY1WU5CVi9Fa09OajNRSkdnT1hsRWMwbzI1RzdTd1hLWnlyVTc1UXBGOVlvTk9I"
    "anRBTTFjWHhKd2RhQ3dMdzQ4YTFEOHlRYXVWTmRGV1RNVEMzSFY2NUFjZW9tdnpaZHFzMThubFkwTERsM2o3Tys0N3djSW02aXFXeEVWQTZMcGZMQlpRcj"
    "I4bHRkWHl2MW1ybFQvemtZOThaSVBlaHNQTi92SGlWNzcrOEV2UFAvL0pGNTkvWVRiSyswKzVoZndwRms2UEE5bnovOW41ZWJwdzZTTE5MOHpSM2oxVGRP"
    "SytrOVRUMjBmNVhKNjhKS1Rob1NIakRod1JiTE5ScDlHUllXcXlsckZrUkVnNFRzZ20zZFhkSjlxTlNjSkFRR3Z6N3lZbWQ5RGlTb1d1WHI5T2EydHJCSm"
    "RNQ1Z3S0pqT2hYSzdvOUk5Ty9MdXhrUjFQUC9ua2s5UDBOaHpPUzEvOTZzRXdLUDVVRk1lUDhoVWZjNG0xeTNQSjkzMjVZWmUxWlA3R0RkSE93WUYrR2hz"
    "ZFVVM2s3M0tzb1Z1TkpzVmhtd3E1UUxiVjJ5RUwvaHF0cnBZcFpLRSsvTkJESEl3Y2V2WGlWYXB1YkxCcHQ2a3I1OUxlL1FmbzNNeWxUR0FMYVdLNGo1eW"
    "dTSXZMcTJKQ09FL2dlM0xzM3A0QitaMDFyamlPMkkxVUtxMzE5Vjg1OWJPbmZvL2VSc1A1MmpQUE1lSkpISmdnZktDYjZJMnNsbGZaOUpweTAyT2pvOVJm"
    "NmhaQkk5cEFlRW1pZ1FTYWFkL2I3VkRNVkw5UFZMdENqZmhCTGtjYmJPcVY5UXIxOWZYUlpqT2lzek1YNVhjUTA4TDhMUDNFZTMrTW5udnBGZGJvUk5FQU"
    "gzT2pWcVhtWm8yT0hUdkdHaDh4d2lpSXhtTS8rT2VvM2FxdlZSWS8xZnVuVC8zN1IvL3dEeU42R3d5M0hVVU9HUjFnZjBWWHJseWhLMWN2c3dCZDJyMTdO"
    "KzNkdTVlNk9GS3JYeU14UmJ4Y2lkWWt3a1FnYVhOdzhqelhtTE1qL2cvV2JyRnBrMDJkMVZFRWl0OFA5bmJSUFlmMzA4VG9FSzB1TDlFb1c4SGljaVg5dm"
    "JnUmZyOSs1UkxkYy93NHJhNXYwTnBHalgxM0RXb3FBcFh6T0c2eDFEUDgyTm9qNy81TmVwc001MC8rN0V2SmFubUZpdmtDbTFtT1JzZkdXVGlKQ0VnMGt3"
    "ZUhLTlpnRlNDck5Mc0hGcWdERGRUSjBOK3hWaUphSjJxMkpNTHhSSUF3Y0NRQXdLQnRGcXpGckNKNC9rMkROWGh3Y0lBV3ltVzZmUFdHUkg0Y0dYQ3N2RG"
    "hISngvOGZscFlYTllKWkdGMkZRS0daVjJ5djc0aWhtQWhiU3d2L0tlZis0V2YrNWYwRmc4WHdXRFh6dDAwT2o1T0E4TWpFbEFFVXpxcWdkYTBBYVh3Z28r"
    "RkFGM1hiUGNONEJlVFZGL25pTzQ3cWRZNTVuTVlSMmxnVWppbVdSVnc2M3ExUmtPc3hUdkd4OWd5aXVJU2JyREZIRGg0Z0JhWFZramdHTy92YzRKUmJ6SD"
    "Z1SDZaN0tUaXg1N25VM0ZnNUtPZmZlS3p2MFp2OFhCMzdOd2wyaWVDZEIzeFp5RUFlUnVhbVNkWVdSS3BEeE9CaU1BNmZoT2FJeG1SbUd6SHgxb2h4QVpu"
    "aW1ZYUlkdFhsREM0aCt2Z1Y4amZWeGgySlpLR05lbmE1Um1hWUFHWGVnZEUwekVIT0NvMDh1cVZpelF5UEV6RHcvM3MvMGt5czhSa2EyNnA5L0VubnZqY0"
    "tYb0xoOXRxTmVXaXlHUTlNTDJBdFEvbW4wajB6WW1nWE04VndiaWl4VWdsMnlJODN3LytndmFwYWNzaFUrRjd2dUpjQ05nS21VemtUMkFkT0FjZnE5alZ5"
    "eTVvRnozODhDTzAvK0JSdmg3ZitHcVNTV2tDYlREMDJqazFSWmV2emJJN2lka2RPVHo1a1h6djRIcHl1Yy85enFkKzZ4aTlSY08xQXNGRklaTUpXVmd5OD"
    "BSR0NLR0FlUEdKY1d6eWQ4YUxqQlR3R1JCSnlSTksvU1QyazJUQlZid3F2akJqN3VwS2ZIRVJXVzFPRXAwQUFINThacjJYOXhwcjhPVUxNN1N5dUVDWHpy"
    "OUtqenp5ZCtqOHBhdHlqWnYxQnR0TnpNZFRLOEh4aUZPL3NLZjAzNTk0NG9sdWVndUdIOGZxSTZFTkFOZVlkVnlZRXlHeU92STMvZ0hHdU1aRkpJa0tBY0"
    "tSbVRINXZ5ZXNWRnNucUIySnZVTERSVFBGZUtGeEtqUUpNSTZ2L3BheVJFc0h0OGJHdmV6YU5VWGo0eE5VWGwybHlZa2RWS2x0R2ordGJxZkY1Nm96N0Nv"
    "VVNuSXZPSUtYTHgxcXJLOThramY4SXQzaDRhcDU2ZzI3ZkpNUWtNV09ZcHF4M3FRMVpYM1h6OURzMkFnWUJBZ21BL3NERGVBbEpFbGlUOFZNVmd6TnhUbH"
    "l2TDh2NWkrSGhQQllpSkZocXhMam8zRnVETWNFejRHQklYWVBKVnBjV0V5eEtsNVhMbCtpTFVZSzQrTkRJbWd5Z2RQdDZ2NkYvL2pwVDUra096eDgzQWh1"
    "UHBaM1Y3QWxocGdSYTJ2a0oyS21Qc3pWQVh3SnllZUxSaFIybFZVeGZqTVdvV0RnRFdDLzNtaUwyVVBEVzhaOTZFU1JtcmVqYmtjOWd5TkN4TjkyMGhTcT"
    "Z1UVo2YkxtUnRUVDNVUFhybDBXd2VLN0k0Y1AwdUhEUitqbFYyY294L2k2aXZRWE83TS9qbkxkdjh0N1BraDNjQWlpVDR6Znc5MUM0MndVbDRodXN5YlhN"
    "U3BxVkJVajBlQkdCdkJiL3h5d3YvVlpvNTQvTTBNdm5MbEE1NjdNMHNibXBwTFZobHVGY2NCM2R4Z2RQWWJ2ZStiUWlWb0FxTUJZUDBPSXNVRWV1M2Z2cG"
    "Y2K0FZR0J3eU5qOU9McE01eUFoSlJuZHF6RWtNeHFlK1E0RDN6eThVLy9BN3FEd3pYc25VWlAxa0lJVVVFNWlYQ044YWVZMVpxV2hWSDRMUGpWK0ZXZ2dS"
    "eVRKVjkrNWdYbVJ0dlVaSTFmcWxicDVZdVhhZWJhZFNxdnI0dEdSeFpxYVpxV1l0d29pbEloNnprMDZvdVc4dDh0ZnJYaGwvbThoZTVlSm1aNjZPTGxxK2"
    "1FdGpoVkxoWHlaUHdLVzVOUHNlZi9DdDNCNGRvYk1lNVNNcDRJcG13WXBSVEFtNHYyUklzOWt5VFlhTjB5VVo3Smo1NSsrcjlmZVlZYXphWUt6V2diUHE5"
    "d0ZIL2x3aVg2OXJrWldtYkNKWkxzeXZqa3NJTUNvTUdLQmhKakZLTGVoSEJuT1Z4b3V0WDJjcVhNeUdCUnZwdTdjWjB1czQvdEx1YTFsQU0wa2dzZWV2d1"
    "RqNytQN3REd2NWS0ovQUx3SThwNWdURDFBT01PQjQ5Y1JuanFFM2s3K3kwSlpMd3RFR2lWaUE4THVycnBTMDgvSzhTS3BmbGprNVpLNllTalByUy94cTVn"
    "dlZZam4vY1pIaHlrd1g2bUQ0TTh3VHNBSFlSR0dORE1XQVFjeXY1aEVxVmxHUEg1eHBwNit3YzUrN3BJRnhodUhidm5Idkd2aXl4a0lBU2dFUWN4SThoOW"
    "1DL29qK2tPRE9lTFQzMDVRYW9KM09rNGtaZy9nSHJBdmlubks2U3lFUjArRitnU2ZpK0xRM1BNcC9vczBLODk4eUpWYXh2aWw5dWtVUnpDYVJzc3E0RW9O"
    "SFJmWWxqOVdBUXoyRDhncnk2dUFFRERFSkNpREU4ZzdIOFNwWnFjU0pDS0ROL1FtY0R4VWVadkd5MER0WnBzRVd1S3QvbXp1N0U1L2V1UC8vcHRyeHFJSX"
    "hTdE16bTc0eWx1RmUwME40V0JkOS9tLy9DZnhsMGd5bnVGTHZycTExNmdjcmtpeVVPajJhQVdtNzlxbkdvVVBpdUwzL0dkYlpQaVFraExxeXQwNXZ3NTVs"
    "MHYwQnI3M2NUQUVPcytGTDZaZ0pWeFdWSXNsSnFXYXZmczdIeks5L1owbCtRNkpZRkJ2Y3VsdjA5M1lMZzJZRVFTWVEwdU5RRUlHcW1GdkRqRnJ0WVZ5TT"
    "c4WGE3WVExLzdCbXNvRXlMNHJyeXlTQ09sSEEzbFhkcXNyQkRYOWVXbUlGanJPeU5UWVZVaVdobW1LTlFKWE9lZ2RwR0psRE16OEx0YzcwSmFLc2xEa3Bh"
    "Nm8weDJKKzRsVHRKYVZzaWY1K2RtWlJLV2xwYXBtQXZTVEM5eW5mZlNIUmpPSDMzaHp4S1VRNUQ1UUVqUXZJQWp1TWUrclpCelRNNnVBaXg0V29aV1lzV2"
    "hVdCtRYUdodFkxTnVybHhlb25lZHZKZEIrb0Q2VWQ1MitzeFpPbi8xT250dlBnZVNBbFBZZzVaYWR0OU9tZ1EvY2t5UU1nUUphMkkvbDJ4S1BkMWlSUkMr"
    "Wm1SR2t3MFNnY0FkUjkxUmpZbndKU2E5Z1F3T01zdTF0THF1RnRGdU1ua1E3L2lOMy9pMWVicU53MGZFbGhTVWxPNVRmTWQvKzU3aEFCSXRyWkRpUnlnWn"
    "lpMDluTjA4emJDcHdzUXhCTEsydWt6dmZNZFJHaG9hU2pVWjJuam8wQkhhdC84d25lZmMvZnpsSzlUQWtaaWt3WmZ0TUVxekpZRnBKcGhwK2drZU5oSkVz"
    "Ymk2UmJUcWNOVzFoL3JaNzdxZXdqY2xaVHA5Qk8xbVc3WUh6QTFQVGswYkl0MDE3a0lMNVk0Yi9rUGUrTnQwRzRjYkdtTFptcnhsa1VLNU9aUFoyT0ljUX"
    "ljWWJUZHI0dE5mZjU3VzE2cWlYZVhWSmJyL252MjBZM0lpUFhCc0pvZE0wWEEvMTZSKzlFZitMaDNmUDAxZXpINTNhOU5NVWtoZ3lsQ0N0bnlDWTVnd2RU"
    "MVMrUk1ocjYydlNuVUNmSUM0akNnMHNDMFdGMkNGVGNaRmdleFpaai9mVlN5dzFiUWxnakFqOWg2NnpjTk40amcxUjJ0Q3lpUjE2RHpWaUZqZ0V6S1lyei"
    "83SFk3eW14SWdWcFlYNmRqMFRwcm02dXJOblNqa21KdE1ySytPdVZxNm05NzE4QS9SY2RiZ0lFRUZ0Ym1OWTRXbWFwT0dsWSt6RGJkQytLQWR4YythVEFz"
    "Q0RzMzF4MGJqTWVDL204MFdsVXBkQXRVaTVtbGJVZXU5SC9yNHg0ZnBOZzdmNXUweDUvbEpvRUpCcWRobndzUExlUjBoOFUzMkQ0L1QvM3YyUmFxVTE5Uj"
    "MxZGJvK0w2ZGRPTFlrUlFtMllsSU1seXAwTnF4aFVQd2cwUVR6RFlOajR5eUgxNmxjK2ZPVUkwcnJ4NzdkdjVXU1BLRTJpbi9hbjBsUm14NGdNamcxeVNo"
    "RkFrZzJPTGFKUk1VRjJRQ1ZEdVV5Y0IyTHdpY3ZpaitJTjFHRitEYVRFWTAxR3dFa0EvaG94Q1pJUnorZTR4Tit4dmZmb1hLakVNajF1THFacFYyalEvUW"
    "lhTkhVdmNoS1U1R3FCTFJEY3ZsQ2hUelV1MEZkb1V3U2x5bHZmZmUrK21lb3ljNDBZQUE2dnk3S0QyT0lCRER3Vm9rUW9sdGRFdlNJSWVFQTNRaGZoOGI2"
    "NHNUMXVpa3habmNDbzJOREtXLzQ0bCtsRzdqY09GM0ZGWXBqc1FyTW1tbFNwaG9hdmNPZXY3Rmw3bHNYUkh6Mm1EWU16SFFUUS9lL3c3dFJER3dTRGdEU2"
    "pxd3krazBueVVtMzQ4ejdrSFlma3dnbjYvQW9QL29rUk4wNU9CeHRoS084bWpBSURMSHBOVDhVNzdXWUdBdDAyaEtqWXB1cTJVckVsNTZrMDEyTWNJRlcv"
    "enQwTHMrZmh0ZGdKdk5XS3pHdXBaRlowSHRaWUYraXdXNnNscVJUS2xhcWRCSWQ1N2UrY0Q5NUJqV1Zjb3Q1Sm5QSmtGQXoxVktabW5ER2N6ZTRtTHg0eE"
    "NDcEs1dUtyaUFYY0RlQTBkbzk5UStFVzRTYXBablhZRk9Yb2NERU00aVZxc2dWNjhIeDI2MUdoU20yWlpxdkhWUENCaXU2MytRYnRQd3dmYjR4bWUxTFc5"
    "SmdmQ1lodzRjcE5Pdm5LZWw1Yko4dDhFbVAxQU02UHNmK0Q3S3MyYXRNZUN2YlRXb3ZMYk9uemRwaS8xaXRib2g3VHdRSU1nWE1WKysrZjYrWHVycjZhVV"
    "NNMHR4eWlPb3Y1T1NTcVNhSEJyQm9jRnRmTWNVTS9xYlZHRzRGa1A0UEZINHZXcG9rdUpaclJhRWFWbkg4RjdtczdvS29JQmhMb012TGE4cTgrVTQvNGh1"
    "azE5MWZ1OFAvbHVTQjlqbkM3WnBLQktBZTQ0ZUVFcnQrdlU1N1l0aU9OWGQ1VE1oZkZoNm5hN05MZEQ2ZWxYemM4dDNabUNVdmZIWXVCYnJEN3U3aTdSbj"
    "V4UUQrbjdOOFNFT0ZsVEk1ZzRZQjg0Z05Qazlnb3Z0R1dqd2hHMVcxMFFMKzRaRzB1aXZyZ1Q3TkZPWGxRMXM5bThJZUdSb2tCYVdsOVVOeEdGclR6NDM4"
    "dEZQZktKS3QzajRFaTBsWlpUaXVWekFrVVBUZE8zNkxNM05MWnI2ZjF2YUdzc2JFWDNsR3krWXNrZGkwdHZJa0NXUlVQNnhORStvdGtUbWI1dFdTaHNQMT"
    "VLK2MvWTcxTXRhdTIvUEFZNzRBY01jMWo2T1gyM0oweE1qMUNnbFRTeG4yOU0vSk9jVFladDBXblZSNjJIV1JhUWowWXpMRXU0Qm53c0QyL2grYzllM3Ru"
    "NksvL3pQZEl1SEQ0Wk9idHhocldId2ZHRC9IcHBqVXVJcWE2aHFuSnBWSzdRZ25HKytzWVVlSmlhRGN6UTVPVUs5akFPRFhFSExNUVpMYmpKVHRNWHZWNj"
    "VlWmFUQUUrZmxOS2c0YXVxVnRRcTk5UEszT0FoT1V4Y3pYQnFBMm1uekJxNUpLRVRLV0FFRVlzcnAwclFoMVFwVDhVMGlLZms0WmpMVFlCa3BtWU5KV2Vi"
    "QzRmam9LTTB6TFJnSlYrdjlrOXNoVk9kM1B2ZjdDWVNCTWdRYWJ3R1VaMmV2TVZIU0xmNUxrZ08rNkxWcW1mTHNIM2RPanRIT2lYSGFOVGx1c2gvVFZNRT"
    "R0OFZBT3pUUnVRSGhSOHBBVmF2cnpIV2VwK3Z6Y3d6UGJHVWhUak9mOGJGSmRndTlLVkZ0NlVGTEdVYVdYeFV0eEg3Nk94VzZxY1ltSFI4cVpSNlRQZHpz"
    "RWlaR1I4Uy9Da0hFMlVCdklULzgyR09QM2RJK1YxOFlmZzRsd24reTlpVmJUSmt4ZTQ4bXRlNitQZzRVRzlUTlRNb1BQSGhTaUJKa1ZjWEFsd1kyV3cySV"
    "RmUlZpSVRJenhjY28vOUtCWWdHdDBPSGoxSWZtKytaY3k4TEJyYjlBSGlmbjc5QlkyTTdLSjh2aW5scm9TOUpZVmhhcnhLMlN3bHcyeEVqd0Y5dFg2RVZt"
    "WFVHVVpTNVBpMXVBbFlGcGw5QmhPeTQrV3AxOHdQOGsvOUN0M0M0bHRPRWxnZ2dCMllzZHRIeFl5ZG9xSytmVGh3L1FmZmU5MzFVZ0lsR2liRHpNTGNtOD"
    "ZXZDVnbmJPOXhwUEF2VFRwUW9yWGtORGc3VHZjZnVFN1JodXdXMXFPZ3laRnZrODdjTTB4OTFTaXpHSjh2Rkd1SWwydGJrRnFlSmhFMDZRSnJiWk1HNkUw"
    "T0xDNGsrUGpKaVNqVzgzWE4vbW03eGNDM0Ryc1NGbWd2TUdCclN6MHhVTHA5VFh4Ymp3bHlCU25yaE9SVWpHQ1Z0ZDVZb0x0RTZWZ3dwaVVSS01xdFplMH"
    "dCbmp4eG4wUjZ6OHRnUng0cnpNV0doaXlCWDRhUXd3anZUZjFzRXBYRWRQcGxhMmRXd0ZBS0lJVVVjOE42SERkdHhGOW5WczAyTklQV1pCWCs0UTkvK01P"
    "M3RKUEZ4WTIzVEpHdTAyd1d5MDFMc01ETkFlcEFpK0xFUlBqUUNFeVg2YmlJZG1LV0xNaUVhL3h3SjJGazZsSmh5dm9MRHlxUnZFRDdwNmIwQXFpVGd1Sz"
    "h0VnJGdEJBSkMyTUNKZHdCanE5dVFTSFM5djR0bXlDNEJoWmloT1orSk9kM1Rib3J5WW1XaHdRKzV0bnBGSXMvUTdkd3VLSVJiV1dwMUFXRTBvV1hscEJG"
    "Z3gxRFhDQy9ibS9MWm1LemdnUWpNczBRclRZMEJod25USnpUME1pUmtuSUxWb0FrZ21rL1JIMDNzU2xvU09seW9RVE1VdDJBK2lpbDlpVDRHSFZMZXdDTU"
    "5vb1FUZVhYc213WXR2M1Rwc09veGVHOXdzbktDUE8rTXNHTTBkMWM0WmFXV1Z6bEhkVkhvbjhVQnR4aTdXZ2JRaVZKVk9zRXFLZmRnZHFmS2wyQzZGd1Ja"
    "WEVsVGJSOStaRXh4WllwWDJOUElOZ0dGK0FBdGVZNHMzbnc1RWtwT0tKWHdEVTNybXVubEY5TnV3aE45NHRVVUoxTzk3WTFlVVVMNW82U2pEQ2RUbytzWE"
    "tFNVI0T1BYU29XVGE4dCtxNXlQL2pFTFhRQmJtU0xhTUNra1hieDZiVWxwbGNWR1JPTWxLdXRibzV2ekdkdGM5Zzl4QUw0YmVOS1cyNlN0QmFWZEpna0Vv"
    "d2JDc0VkbW9BQzdkK3ExMlZsQ3dSdnE3V2VhUzVHeVNhTzIyb1pjU2R3Q1RuZERsUGtZQWZ3cWJ6akdLYXVsZ1lxVnpVWjM3bHA3NElHUjNVQlB0WTY1Sz"
    "hVU3YrTWJ0RndRMVB2RWQ4cXdTRVVWa2VZZUZzcU5rTEJ1eU9KVnlDVDRJcmI0eFFXTjB5Q3N3VXVSV0cwcmZhRWlXc2JUbFBYb1RibGZZVXJCMU83ZGty"
    "UXN5UU1JQStDSTBlLzFDZG11b3hTN2JPQ3cxREJkWVJzQTVRdnBmZGM2ajlkSzF4K3gwcVpDVTRFY3B4bG9ZdkZLK2JmVDdkb3VNSTV4bTNSSHBpcVVuK2"
    "02aGthVnNpMG50dGdJNzdMTloxL2NCSFFjajVZQTVwSVpEUThOR3hSVy8wMDc5YzAvaHNEMzkzZ3pHM1g1R1RhSlNndjFsSUl1Y2pZTms2Wk05Tnc3R1hh"
    "NUZPdERzeG5QOU54cU1GSWVobXRwcHI5OEE2WGcydUJRQjJHaVhuZXQxQXNzUXQ0N0phNEFEOFdMV29hMnEwZzBSNERGd25Od2dWQUVKamRYSUlJN1p2Zz"
    "VFbHgwT0diQ01FTm1CSXpHaG1VTU83MFM5bkpJbEwvaUVEVWFqY29xaWV5V2tXRW9xM1NaQnNLOHF5dEc1dU9wcjZPbWpnb1NVdUllNmE3MjNXOGJSeHVH"
    "cmprSnRUVVpZMkN0MzBOTFFTT1krYU1QK2VmNXVlSzY2ZDQ4NVAwSm9jdkpvb1dTYlEydGtQMXJiRzJQN3JkM2RRQXBBRmJDcGdWYTRUUGR2aEJFNXZRWH"
    "RPdktuMVQ1aDBUMUdnMVV3MkhXd0dIQ3V3Si95cHRRRUlvKzdvQ3hsRmZMdmlWSjI5ZEJHYTNpMmpZWjJiTTNCUVZ4VWM2blVCbnIwMWNWS1E5WHJBNkNG"
    "WmpxaWNhdkxtMVJVT2NKV0lSaDhNVlhxY1l2TzlXQ0ZWYktaTU82NFRzeE5KMVV1VnNOa1h6SURoMDFHSGRhTnQwUWNldXRwbmpoa0tERGtKVGw0ZDVvZW"
    "dHUVc1dDFmbTFKZGdYeDBSRjFQcExMSWdUczNTdGFlYTBmWk9QMmMwOGhHc3daWUd6SkVVSzZpYXdvaVhITDd3RFBhVG1iUnVPeFlmcXZsakRrR2VYZ2o2"
    "eEloKy9pd1ZZY05rRmJEYW9xOVFsTGdkdXBOVFQ5OGh2L2RJdkZlbE5EbDlTUDFCdVlXeHFPbkdLQjBVN1RENlBpNHg4NDJmUnZwUGtsYk4wbEJWQ3hnU3"
    "RyZk4zOExOMVp0NGJiT1lnckNYeVI2cTVFTElWcUZ4QTRLZEN4RmwxaWJyaXpvQW5qRXY0N0JvOE9IOUpGTVNNSFczeFJIT0ZFQ2NaN2N5aUFra3NUQnB0"
    "TlZoVzRsQW5jWUF3YlVMQXhmZkNldi9nUCtXdlBrZHZZdmdGUDFCR0tLZk5EZEJZZ1BmRThKRHRnSU5QUGpMOVZyRm9HdE5WS2ZXR1NONkVKaHVCdGRDVH"
    "lvSkVGUUN3cWRuYzBPMWdzQ0xGbFBiR2JZWVQ0QVdmYVZaWll6SnhrOFZDa1pyMVRXMllTL1Mzc2VGV2JZTWNobklJblI0dmRDekMzN3NvQXJ0YTRySHBz"
    "SFVWMXYvVzJQVDdlbnZaZXVvVWxFcTB2RGozdmpjclZMZWJxNWxGSmxBQVk0SUFGNjFwWWJPMXlUNW5qV29iRmRyWVdKZDhXcEJBWkpyT1RPbFpTaE9DRE"
    "VJUkdwS0lqWTFORWVnV1owNDFoaTR3L1piZzFKYWtuYkVoVWpSYWV6eEhPVEZmeC9qWHdHQk5kQjdhYUMzYk9WcExTNUpyVE50VFV3ZUJrb1BaODNhWWVE"
    "ZXpYVXlwRUNvYWdZRlVOc21BUU9YdnZDNWxBb1llR09pVjQrRzcvcUdSZDc5WkYrQjM4ZXpBWEYyK1lRdFZVckROTHl4bGhGT0hOdVVjYUZRUFF5ZXVVSE"
    "xxbVdjMEFLMkF0cUxUYjJ1clNac3NSQWgyRTRMZDJoQXl4SGEvMk9WQWxrZlYzaXBmb0EyWkZUQTJXa3MwTHlSVUNQUGlUejF5T21iTTE5TTJWVk5OUXp1"
    "QnlmUDB5UmhaTTVjc0RNSTByc3IrN1FaT0dnYzhrMEIwZFpXSzZ5TmpiOG9GdUhqc1JsZDNpYlcxS0x4bkw1dENGMUk0dTVDWFozS1RpMjgxRlBSWSsyQy"
    "tXMnpLclRDUjFTeFI1TW5xNW1ZanBpMW1nUERhNUJlSWFVQXkyKzhFNGVFY0tFWGpoYWRSNEZ4K0dseFVJMTBUbVNIN1BQL2RGZVNweUZBdno4NVYxaElF"
    "R25qMGVvc1NnS3dtQm1aL0c3QUNFN0J3YnJnUUNYRFNkeHNZVWdXTDRZcnM5NXRjM3VtUjcvRjBEQTdJUDhIRXRVdmY1ZkJ4Y1FGbkw0aWlpUHhTQ2tHTE"
    "pGOHNXc3pGZEhuYlJsU1RpME1WRmI5RkMwMmNGT1Q3V20xVGVrclh1VVFDZ2RZNTJpZHRYVlh0bVF3RzVvVjl2YUJ6bzhOY2lFTlBxelpaVUFxSkV0TS9n"
    "UCs0amtJaG42YlNFcWgwNVp6Y1FHZDVVcExtLzdaaHpSTWM2Z25FazE0cjEwdmI4QzNqcUYyR01mVU9kYk53NjNJZFF5T2o3MjFVYS9mdzE5K203Mkw0aF"
    "dLaDA0UEVNeGV4WnZRV1MwSTZ3QTlXYTFYMnJYV0tHaWlMVkVVYklGUTM2UmN6QjhiREF4T1dsbFpZb3l0aWxoQU90QjYvQzR3R1padUZwU3VidGZIZzlG"
    "N2E0QW1CNEZMaXd5eG93MjlzYlVrZ2t3bW9HaUNkTk5qZ0gveHN5bExaVmt4TC9NQmwrRTRhL2JIZGxVWmgyK3ZhYVVxR2I0YlFSOGNuNkpXbHBZL3gxej"
    "lEMzhWdy92aC8vWGxpWjllYXE5WjNFb0ZJZ0U4YkxOUXErOHNhQ3hWQlptSnNqTzdsaXV2SThCQVg3ODdRK2N2WE9EaHRFWGpyVWxkSmdvRGdSMC94cEpj"
    "SlFsWVF1TEVmL3NHSDZabHY2dE9SdEYyOXMyaERncUtwUm5SMzk2aVFxSk0xMmVXY21oeW9ueVhSVURMdm5SSzFyUmdvdFpqeTFib3FHempiWkJlVEU2T3"
    "NIS3R5am9XRnVmWGxTM09ISC92Tnh4Ym9EUTRmUHNvV3pEeURBVFVoSUNyazgrTEVVVjdwSCtRVXREVWs1UWgwTzE5YldLUXRGdmkxR3pjRXBFK01qN0FB"
    "QStFbmxSSHExTENVYWUvMGt3SmZlbzRyK05XUzA4aVdUQXVzQ0tRWUZHbU4zVWxnam1jbndoWU1iZFhVcmdxMEpXckhDTkUyYStneXpZUVNRMnA3VG1lTk"
    "dDd29yUjQ0bWgxR2hnRWJIQjdwVzYrVWY1NTMrYmYwQm9mejVhOStQZEduU0NpWXhrMWo1dHRTK3ZETXVxcUk3THdMcWN4QXY4bEJDMy9Cc2N1Q0NZbnlr"
    "VEV4a05leWprVnZEcEhYMHliaTJHUnZnNFA5dkcrSkxyR1dXMmNvM0d4c2x4b1JhODBpVFV4TW1rVUpaSVR2R0lLNlU0YXhDK2l5UzkvbFdwTWs5YUYyOW"
    "JkZG15VnJiSTNhZW5adExYb0xPRFd2ckszSmJ4Ym1aeThORC9hZGZQVFJSOWZwRFF3L3g5cmhCdHBvRzVtMVVFZ0NVRXVDaGtqUHFya0lOSnhwWkdaL3h5"
    "ZWZPVC9ESmpPcExvT1JZUngxRmw1c1crZHZLd055REY5NDE3SFJZVnBsVTVQa2cwd0pHUnJsNmxOOVVLS3habTE1VUtneUJCcklNZUswZWNJM2hVY24wY2"
    "wzelJQZGJDS2hBbk1OZFdnc1E1N1dGa3ZXUldtWjNhNTIxTDR3ZGp2VE55NWUvUkgrNDMvUUd4Z0N6bXlQS2tBMzhuYlAwZlZNcUhveVFDVThzMC85Rkc0"
    "QTdKUkw1Y29hQjVrTnVVbms0RkVMRFdJZDdiRVVYZHBYbWlrMXUzeE1NTzlYMlEvTG1sY1RvTHhFaVhIUDFicTljTGR1WjFtbHZWWnRwbEZ5eEhkOXlaeG"
    "tPVkl1bDlKL2dJcDlmYjNVemRZQWZpR1g4K201RjE2U3pJN1BrQ0lCV1F0cmxpN0J1dEF3QjZqV3FqZG9kSGlFeW9zTC8vd05DOVZtTnJZc1lZT0tGUVNh"
    "RitCN3BIWGMxWWNkZ0ZoQnN5NStoOGkvWThjRUN3cFVZWWVZZGpNbWxmMWJpQXZHcUsxbU8yMUJwMHpFdHI5SGdNTGtGdktCYUxZMHRjRnE5SGsxTXZrND"
    "FxRUQwOUlFQWtIbmtVVHdRUUVGOGZBeENHaHhaU21kMkZaamk1T1hnbW52TkFIVDFVWEVnSHFZNEFaVGw3Q2l0VkR2cFc5dzZOMmYrZFJuZG4vc1Z6OTI3"
    "WFVMMVpwUWxra1h2akx6R2NMMlRkRU12MTlqRFVVYWl1Z0piQWVpSlBBb2Rmelc1SzJBc3N1RU1FYVpjYjl5WlZZWWQvdklKUTlMMXhPdHo2TXhFMHNqOS"
    "t6WnphWWZTLzR1KzNzbWVyTmtDL21jdUN2UWQ2dVYxYi8wNWlCNHdFQndFWk03ZHRBQTQrSnpaMmJrbVRFMnl4TnlPK2ZLbW9EWWRCQ0MzL0RGYWhNYUd4"
    "dnZLcThzb2UzeVA5RHJIS0krMmFZRGF6NmQzbjh2eFp2NERqUWVNaXpnMGNTMGc3YzRSYzJ5UTA0bXd0cmpaU011L200eml4WDRycXgwVVdEdXBzOEk4RV"
    "hyRzRiVzgxT0dYeC84aFJ5Zkp5ckJBOFpjem9SS2tvQ2NQMytlWm0vTXFpTHc2Ny8rL2gvUS8vemlGK24wdDcvRFZsVW0rd0Njd0NRZmVObW1DNzFYRWo4"
    "ZXNIbkVuTExEYmNnNk1UNXZvVkQ4VVBMWWwvelhLMVQvWmkyeUdGQUpqV0NicG1FN2hMb2g2NmJzWW9XUU02aE5UbTN6bEcxaHRHbHVLSFd0emhPRHhzZk"
    "hhVzV1anMzWUxIWnpyWDlVR3RxWDU2bUdzcEFqeStMYkRoUTc4Zkkzbit2VlYxK2xQM25xS1htRzF2VDBQcjBIZnYyOUgzMlBXSVFkY0JIV3VtenUzN0ZT"
    "RmFwV2grMERISEVndlplSnlSMTdQMU45N2dSLy9OYnJrQ21laDlEeGQvWW1yQUN6UGxiclRTM3Avb05EbC8wODE3U0thM3ByTlN0ci9zTERHaFNBNzVFV1"
    "E5T3pESDNxNHhLbEU5ZXJaWm8weTRjc1JMSVRZN2ZaUkFJQmlTRlBlajZjbzlsc2JtK3A1REhJREQrRWlxWVFnZU91RWkrd2lqZ1ZyQW9WSlI0UVRlTGEy"
    "SVgwOUhZNVhsZncwNjlYcUs0MVN5dmNteHNSN0UyRWhsaHBOTUhxbzF5Q2tyWSsyTERlWklHSHN2Z3JQWEEyNEZuVEh1Tk1iSDUrUHQyVzFlQ2NJVVl3OE"
    "t3c0JEUDdHOHZtMjJFbkJKYUVwWkxick1rSUU0OVlRckRDZ0tEQm1XSWcrbnMremh2TEswbndXRkluZFZGakV6dG9xYnpCbWVLTVNWc2R1Yllnbi8vQVp6"
    "LzBvZUQxQ05YUGFwYlYwR3pFRnYrSDhvaU5xSzBvcmFqYUd3MGpKYmFiYmQzbUpsRXFXT3NPYlA2L3pzU0xSUnRad2RxbFBaZzhDQ0hKQVBtMGtjM3BUSn"
    "E5M2ozTUg1dzllNWI2bUdVYUhoNldvQ1NVSW53d0MyT2NKeEorY1c1eFVmYXJtdk5yTURaZE5uRm41ZUZ6TDU1bXBkSGFHUnJ5N0c5SHhzYW1OazZjT01p"
    "SGVPVzFoT3B1YStReUx5c1FIQXgwSDE0UXFPM29FM0J0bmwraTFWalRKeVZNVXBJR2wwN0xlaUkrN3dhbnRQWWlyV0RzeTJyczdPd2NUVTFOYmNPbFZxRF"
    "pSQ0lOUEN5NGc0Y095Uk9DWDNycEpjYk9OWXBNNVJiSG1GOVlrTWVHVmlvVldsNWFrcUJtNzlOYWlPMDdRQ055amZlWExKTDNyYXpYMG52cDYrMXpuSHp4"
    "ZFQySXdVK2Y3cE10N1pxUklIUGk3NlFpeXJQV2JLTTFQRFJMZUpKME5RZ0dCSWl5Q1lKT2tIbTBFbzRORFZwWldSRnR2MWxRV2EyVDQ4VFJOaWlXSmMzdH"
    "ZyWWtnK05adjRwSjI3VnJGNTAvTjBQK3FrSXMxeFQ4TU9FWExseWd1ZGxaZXQrUC8zaDZuR3lRbG54L1lKQmVQbnVleGlkM1NjR3pXbDJqaVJGbDQ0ck01"
    "alhqRUEwWG4zb3RvYnJaaTdXZjdVMDFaWEZEcUUyMG5FbUZrYTVpRmxPVnhnYnpuS3EwaFZ5ZkJtU0ZoR09Da0FZTnVNQWFZODE1V3l0UFJwc3ZYcnhFVT"
    "d0M1U3WkYwcm9GSVowTnJMUCtGOXR4dzY2WnhIWDJ4VU1qd3pUQ1ViL09HVkZsWlpWV1dEdkwvSDV3L3dINnlmZS9YM3oxellqSFhoZnVaMnJIT0YyOWNJ"
    "WjZ1M3hOTEF4aEx6SEc5L2M4K2VTVEE2OGxWRDhib2JOd1JYczlEYmh2aDJMK0tsenRWTGFyclNPenhEeTl5S1NqZGJqeG5UdDMwc3VuejZZbWJ0MkxOZV"
    "Z0ZmhJUG0rRkp5QXJWM25UVzdMUGY5N0F2YlptbFN2Z05zR3FUY2ZPUm8wYzUyMXRsZm1HSjl1NmQ1ankrbE81ams1dWJ6NDlyMjdkdm12YnYzMGVWV3Ax"
    "T243MUVCL2Z0TXYyM2hCWGlZNVd0clRIK1dQbnJoT3BtZldoMkJxUFlWalY5eVRBZ1ZHbUVzRDJzUkNiTjFLNFIrL0FaK3lRSmNlNGpJelJ6N3BJOEpkZ0"
    "duSnRaSkR0bVpzN1RUczU2ck9DczltYk5NL3VkRlFpK2Jab28zODBrendNUFBVZ1BQUGdncmJLN2dXKys3Lzc3YVdGeFFiQ3gzVi91TDdQbTFVYitkRlVo"
    "SzlFQ2t6MndQS0FkbTdEQWgyOHVMZTJuMXhodWRwYnNTV3hqQkFwNmFIeXdwUWpiUlczWEplbkZ4ZWI1Z0dZVlgxdVhtR1BkZjZWU0ZmNDF6bUJHYXdYMm"
    "5OWVZJTk9CVU95d0ZwUjk0ZWJzZHpuV2FHZ28xbktoZklOZ2lrdENvSUpMNFBSU3RrSGdlL2J1cFR5YjhUZWZmWFpiVUxRKzJ5cUJsWUYyMXpTMXdIaFRz"
    "MTJ0WG4vTjVaZi9INkc4Z0ZaNTVvR0hBQUFBQUVsRlRrU3VRbUNDIi8+DQo8L2RlZnM+DQo8L3N2Zz4NCg=="
)


_BINANCE_LOGO_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAERlWElmTU0AKgAAAAgAAYdp"
    "AAQAAAABAAAAGgAAAAAAA6ABAAMAAAABAAEAAKACAAQAAAABAAAAIKADAAQAAAABAAAAIAAAAACshmLzAAACZElEQVRYCcVXu04DMRBMqCiA"
    "z6BMHaVAqSCBKoIyX4IUUCD8CSWIjldBgRCiTslnAEVKZpzdk8/23dk+CSw569sd74zXD0Sn06J9P/fm6JctUnS6uZNJjrlnMn+xvb+c5eTK"
    "EuCQK2+WiGQBFeTZIpIENJBniYgWEEmeLCJKQCJ5kohGAQ3kj8I2UlbHNh7MWgER5BMhvIPNElEpAOSnSHrlrEg/ufIJ7v6KDmA3YepEzIBd"
    "EOu2Dddhfb9g/GV967BETqcIYTV0SxRLyxzMFWyVFSAaK+vDPKHv8BvNI1+717+BSpB8DIHvNs4elyqABFNJYjCY+IHBAToTeeTADtD3DBg/"
    "TiU8cuZGnyqetqgAAnN8820PEfXg/xQCDE11BjAP6FwEV/kGaxqJMNiFbykuPSe3+D5EL26HEWCRK94ToQFa4JVct+YH7pIIB09BSq4hI6Ib"
    "IFdAUESAXPEUcYRVv6qDFvgQuUIWpTOg3r+0/74FpgIo2zlWfSEr90qPMvaklAYCPK/VGJ0n3dt/YjnHgPED/ArmGP1efOVDKE7uF6/IjUww"
    "bvj6GPAtIGnx+jGIGA8jCYp7Dh/3nK8iY6U3QGInwF8jZlpxDdVhWyHgVdPT7lXHwSv5SPzeW2DjOa4UECDXuUER1sqVXPHeFmmAtu4WDBHX"
    "lROrjQR3Qmh8NeSMb6EPOQi1ygoQjMRzGL6OoWYqIYG6v4TFgQslqRXACREiCHPLTh9bLTkBjQIIahBBSKg1knNSlAACE0VEkScJSBARTZ4s"
    "IEJEEnmWgBoRyeTZAgIissiZp1XjwURv9e/5L2XwMrWwIqehAAAAAElFTkSuQmCC"
)


def affiliateBanner_html():
    """Python port of pages.js's affiliateBanner() - the Zerodha sponsored
    banner, kept byte-for-byte in sync with the JS version (same logo, same
    copy, same .aff-banner-zerodha styling) so the SPA's own render of
    /brokers and / shows the identical banner a fresh visit already saw."""
    return (
        '<div class="aff-banner aff-banner-zerodha"><span class="aff-tag">Sponsored</span>'
        '<div class="aff-art aff-art-zerodha">'
        '<img src="%s" width="152" height="20" alt="Zerodha" style="display:block"></div>'
        '<div class="aff-body">'
        '<h4>Brokerage-free equity &amp; mutual fund investments</h4>'
        '<p class="xs muted">Trade with Zerodha\'s Kite platform and tools.</p>'
        '<ul class="aff-features">'
        '<li>Zero brokerage on equity delivery</li>'
        '<li>&#8377;20 flat for intraday, F&amp;O, currency and commodity*</li>'
        '<li>Free direct mutual fund investing</li>'
        '</ul>'
        '<a class="aff-cta" href="https://zerodha.com/open-account?c=ZE5729" target="_blank" '
        'rel="noopener sponsored">Open account &rarr;</a>'
        '<div class="aff-fine">*T&amp;C apply. Investment in securities market are subject to market risks; '
        'read all related documents carefully before investing. Full disclaimer at '
        '<a href="https://zerodha.com/pricing" target="_blank" rel="noopener">zerodha.com/pricing</a>. '
        'Member ID NSE (13906), BSE (6498), MCX (46025).</div></div></div>'
    ) % _ZERODHA_LOGO_DATA_URI


def fivepaisaBanner_html():
    """Python port of pages.js's fivepaisaBanner() - a second sponsored
    banner, same narrow-card/glow-pulse treatment as Zerodha's, stacked
    directly below it wherever affiliateBanner_html() already renders.
    Logo pulled from 5paisa's own live site (storage.googleapis.com/
    5paisa-prod-storage/app_logo/5paisalogonew.svg), not redrawn. Pricing
    facts (flat Rs 20/order, free account opening) and the SEBI
    registration number are 5paisa's own published figures - the latter is
    the same INZ000010231 this pipeline's own SEBI-registry match already
    carries for 5paisa's broker profile, not a fresh, unverified lookup."""
    return (
        '<div class="aff-banner aff-banner-5paisa"><span class="aff-tag">Sponsored</span>'
        '<div class="aff-art aff-art-5paisa">'
        '<img src="%s" width="120" height="29" alt="5paisa" style="display:block"></div>'
        '<div class="aff-body">'
        '<h4>Flat &#8377;20 per order, every segment</h4>'
        '<p class="xs muted">Trade stocks, derivatives and more on 5paisa\'s platform.</p>'
        '<ul class="aff-features">'
        '<li>&#8377;20 flat for delivery, intraday and F&amp;O</li>'
        '<li>Free account opening</li>'
        '<li>Listed on NSE and BSE</li>'
        '</ul>'
        '<a class="aff-cta" href="https://www.5paisa.com/demat-account?ReferralCode=53293333&amp;ReturnUrl=invest-open-account" '
        'target="_blank" rel="noopener sponsored">Open account &rarr;</a>'
        '<div class="aff-fine">*T&amp;C apply. Investment in securities market are subject to market risks; '
        'read all related documents carefully before investing. SEBI Registration: INZ000010231.</div>'
        '</div></div>'
    ) % _FIVEPAISA_LOGO_DATA_URI


def _crypto_banner_html():
    """The Binance CTA - only ever rendered on /crypto/ pages, never beside
    Indian broker content (explicit standing rule; see the pages.js
    affiliateBanner() comment for the equivalent Zerodha placement).

    Logo is Binance's own favicon mark, pulled directly from their static
    CDN (public.bnbstatic.com) - not a hand-drawn approximation, not a
    third-party logo mirror."""
    return (
        '<div class="aff-banner aff-banner-binance">'
        '<span class="aff-tag">Sponsored</span>'
        '<div class="aff-art aff-art-binance">'
        '<div class="aff-logo">'
        '<img src="%s" width="20" height="20" alt="" aria-hidden="true">Binance</div></div>' % _BINANCE_LOGO_DATA_URI
        + '<div class="aff-body">'
        "<h4>Trade crypto on the world's largest exchange</h4>"
        '<p class="xs muted">Sign up on Binance to buy, sell and trade Bitcoin, Ethereum and hundreds of '
        "other cryptocurrencies.</p>"
        '<ul class="aff-features">'
        "<li>Spot, futures and more in one account</li>"
        "<li>Deep liquidity, tight spreads</li>"
        "<li>Trusted by users worldwide</li>"
        "</ul>"
        '<a class="aff-cta" href="https://accounts.binance.com/en-IN/register?ref=191870492" '
        'target="_blank" rel="noopener sponsored">Know More &rarr;</a>'
        '<div class="aff-fine">Crypto assets are highly volatile and unregulated by SEBI. '
        "Not investment advice. You may lose your entire investment. 18+. T&amp;C apply.</div>"
        "</div></div>"
    )


_DELTA_LOGO_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAAAXNSR0IArs4c6QAAAERlWElmTU0AKgAAAAgAAYdpAAQAAAABAAAAGgAAAAAA"
    "A6ABAAMAAAABAAEAAKACAAQAAAABAAAAMKADAAQAAAABAAAAMAAAAADbN2wMAAAIg0lEQVRoBc2aW4hdVxnHv7X3PveZ6UyL15fGgTEiSJ98"
    "CjTTJtOapgW1Kn0QX0wqIhUUQTBpqGjxRVCKgpr0waaCSTRDrGicpJJUbB+iLyUFS6nMgIFQYopzOzNzzt7L37f2WSf73HJmzplps8g367LX"
    "5f//LmutvU+MDJjiY4GOvFes/Ij8nIj5o4hd0Ua7biW8KxBzJNbqjiaHYogVDGP3ICeA/QL5I8ZI2RSMJBu0fD+U9e+FQ0zff+iwBHQFi4wg"
    "n0dOWSu/ESOPUC4nsZUoshIfpdOxiKbtT9tBIItKiXwWSqcksS+SOyJiAqqJ1J+JxH5XjbZ9absJeGRK5HPIbyHxIvkBMaZs4kSSfAARI/bb"
    "Od93qHynCHhQoxSUyGmx9iT5AaRkYmKkEkty1EBmuBjZaQLgdakZI0SDt0jJEvEmEdEdrX5sMCLvFQFPRC3igh2LOCJERMltA0R/DYvEWyTy"
    "XhPoIGJT1/oMD0oBFoGH1I4EYjfpWu8XgSyRx6mcxhJqkYcdEVAlCdvvERzumYLv2zV/vwl4UN61zmADDXYsYkoSsP0mNaljkaSHRe4UAlki"
    "ziKNXethwrzEMSIJt5IYIrXnIt/X5XcaAQ9OLaJEzhAjL5CraxUFtMENDsSjGiMpkTuVAHhdUiJfQIiRlAhxXkSwiJXk6UA5bT3Zn219zJAj"
    "xhj/ReQ0NxIN9oeQ4r9LBa5dW0j2WTp/BOHSbNcYWpUpWzPnaZncwjRDd2XlRWPl/PVC7tebImB/ypr+oNQRCbdPIzMcQAeT/5krsmEepfVB"
    "pIzsWNKlDQfFUhTK38dH5NwHx6/dloD9BSOWkBKil+b02ryP/DCi+TsQ2RP/J7xpclbNqu3TyLYS8cAXAf4awM9+aFz+OVaR1dD8tysBp3G9"
    "LCpoFYPGrQOsAB9APMB52qftulmwi0xlG5YR+WpbP6pbTx64avxVB3wC4GWAE7xYguc3WjZV+0sWqSLqLlyyHHB1DStPUssCp3ormQKnJttB"
    "kJhl+s4y7gJP9yM6bi/iCVPsn7LAVeO/b2o8BR7qfaORtK+4XUVfXwHRSBVyBaCaVN/WerfkLMCDBfNNOP+Aa/JqKCZS9iQjoxDSebxrqTP2"
    "TFngqvFZgP/DuUpT4+1jbxj7E9q8u6RA1be9q/QC7idqIeAbrZ6Y+UTCekMjt4ioRe5HWiySBd5N407LfvLWHBdKnUiBKvBDyO003jq8R808"
    "m1rAvQvjjmx5S4CYtUYuYpGZxjrTtJX8ruKDM6vxrKv0WMrBf4xJv0aHB5AWzfQatNn28IcpkbWnjRRyodh6soRNznJDm+MVc9+7YfitK+OV"
    "+89+eMLorrLSCM7NAPcYUv3r/rGD6ZOTHxO7wRK4KiepvJsEUoxjuQexpUjq+YLkuR9AccsoIgLtJcb9lZHb5kIexe6Tu6Waq0qwgd6L3Cbj"
    "eBR3mrnbJodwp73LQVCWaiymWpW4HEp+LC8huQlwrk1yUQLaWb+o/QF5GdEY8NtmvyCma2ea+t2URIuRxLlYCkmB6e0ot8r9XI0Ps9PtpV7W"
    "bdq9gcHN8vJSW+bev1KXsBRKYbywaSIKv3MbtWybpuXg6kVkHnTTTOG20cmXJqWyWJFasYa62VaTZMTGdgawhyAwDdCyglXw1C1l9l1XdiT8"
    "M1VqVI4kP553uQl7WuSGI6AkNNkf80fvfWuIPklP1uy22h7k857A7l0fl8gSUgBqAN8PoCep7wVqFrgD64BDhmdpHV6egOauDIZcJSf5iZ5E"
    "Wk9i8x1AK+6f80dJ5EVP1nOYXbe//bT4bbaFyMuVMckFOUnqiX4+0X6HjTHTjCsDhU8nIFFXaS+rliDsngGaMWKD1PlxN0diY3HDuVdUiaQw"
    "URDNsxZRPfdM7jJ3k8dqFZ03tYgnopZ5R2qyJ7rv0zc/UV19CK0dBtB0N403tes1nnEdZ40+7biiC+7cSE4KdzeJdL/MAawluctdRJNqK6Ws"
    "mp5ZN+bgNz6668prpZFHg8Q+2A+4A5p1GyXRqHeQyLa3lRVDbtQRuf11uoUFFedadQq4w+zYhJy6656pfxWK54nXSdc3A6iXxpsk2kBpLDSf"
    "9S8vMv+fgyg4eVsXaifg6/Y5kfumPiV1Y3YFNrlE+73NZwDr0GbWPTYLXOfRf43+DYUo8DnmP26NfSUIgzV0ufWkN0/1JT79dyR3CDGrBmTX"
    "MoeUPlMr6vOeZT3M9F/aZ5F+Z5AvIV9h0TnIrekvQerZAyXdUXolBaW7idt9ANFRVmTqbhzLjqSWtX+m3REUoxq/QPOvqP+NMfq24nYhm7dy"
    "7alrgxNwEzFzVyJOedwzA/f9uTdYJlHXaJLwhHhpB+wFCB7n2Sv0SYFjjdoHanL9y9d1eZcGtoDTlp+lW56SuKVl+rSDbWjZtTfKS/T5C3p5"
    "PgiCy3ESV9XQUYFryUYsC08tdKw0MIGOmTobHEfVrgLPglUX07q6kcv100Eic07jYapxtazlVTVajuTtr7/dOXujZScJpEuoJTQgb4F1btc4"
    "nVXjcxA6wV36MmWn8dCEUivXZOGJTo23MxmYQFffb5/d1xsknCXS8hLjL0DqOOAv88uZ8/Ew5GfZ0XWZf2zej+ybD0yg78ztHRrAab4IEQ3O"
    "S1wPUuB8NoltLG8+8Wb7qL71oQiok2/SEvp5TLfDE6pxyqt68ib8QFYsFeX1g6/3Bdqrw8AE+u5C6YoK/CJyHLkEW6fxXC4nK+sr8tbjb6W9"
    "hvg7MIE+ml8Gk37c4r8gAByNIy6Y67W6XD14VavbkgYm0GN1Be40biw+HthVtO6+9Nm6lasHtg+4X39gAt6FsAThyYuP3k9Enqf9Em2r+HsK"
    "fM3KGwfeoLIzaWACDRcCvXkVaLPIn2hTImLqoOed7eq+7de4zp9N/wdsgi7o4BEkMgAAAABJRU5ErkJggg=="
)


def _delta_banner_html():
    """The Delta Exchange India CTA - stacked directly below the Binance
    banner, same /crypto/ pages only, same sponsored-and-separated rule.
    Copy (headline, feature list, discount code) is Delta Exchange's own
    official promo asset text, not written by BrokerLens. Logo is pulled
    directly from delta.exchange's own favicon, not a third-party mirror."""
    return (
        '<div class="aff-banner aff-banner-delta">'
        '<span class="aff-tag">Sponsored</span>'
        '<div class="aff-art aff-art-delta">'
        '<div class="aff-logo">'
        '<img src="%s" width="20" height="20" alt="" aria-hidden="true">Delta Exchange</div></div>' % _DELTA_LOGO_DATA_URI
        + '<div class="aff-body">'
        "<h4>Join India's largest crypto F&amp;O exchange</h4>"
        '<ul class="aff-features">'
        "<li>INR settlements</li>"
        "<li>Instant INR deposits and withdrawals</li>"
        "<li>FIU-IND registered</li>"
        "<li>Lowest fees</li>"
        "</ul>"
        '<a class="aff-cta" href="https://www.delta.exchange/?code=UAIYQN" '
        'target="_blank" rel="noopener sponsored">Get up to 10% fee discount &rarr;</a>'
        '<div class="aff-fine">Use code UAIYQN at signup. Crypto derivatives are highly volatile and '
        "unregulated by SEBI. Not investment advice. You may lose your entire investment. 18+. T&amp;C apply.</div>"
        "</div></div>"
    )


def _write_crypto_pages(coins):
    """One static page per Phase 1 crypto coin (/crypto/:symbol/).

    Facts (market-cap rank, supply, ATH/ATL) come from CoinGecko and are
    rebuilt on each publish, same cadence as a stock page's NSE facts. Price
    is never baked in here - it's fetched client-side from crypto-ticker.json
    (crypto-live.js), refreshed on the same cheap `pipeline.run ticker`
    cadence as NSE/BSE/MCX, so the browser never calls a third-party API
    directly. That refresh prefers Binance but falls back to CoinGecko,
    which is what actually runs in production (Binance 451s every automated
    environment this pipeline runs in).

    Universe is the 28 hand-verified coins in pipeline/sources/crypto.py -
    see that module's docstring for why this list only grows by hand.
    """
    written = 0
    slugs = set()
    for c in coins or []:
        symbol = c.get("symbol")
        name = c.get("name")
        if not symbol or not name:
            continue
        slug = symbol.lower()
        slugs.add(slug)
        canonical = "%s/crypto/%s/" % (SITE_URL, slug)
        title = "%s (%s) Price, Market Cap and Facts | BrokerLens" % (_esc(name), _esc(symbol))
        description = _esc(
            "%s (%s): market-cap rank, circulating supply and all-time high/low, plus a live reference "
            "price. Not investment advice." % (name, symbol)
        )[:300]

        rank = c.get("market_cap_rank")
        facts_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div><div style="margin-top:2px">%s</div></div>'
            % (label, value) for label, value in [
                ("Market cap rank", "#%d" % rank if rank else "Not disclosed"),
                ("Market cap", _fmt_usd(c.get("market_cap_usd"), 0)),
                ("Circulating supply", _fmt_supply(c.get("circulating_supply"))),
                ("Max supply", _fmt_supply(c.get("max_supply")) if c.get("max_supply") else "No max supply"),
                ("All-time high", "%s (%s)" % (_fmt_usd(c.get("ath_usd")), (c.get("ath_date") or "")[:10])
                 if c.get("ath_usd") else "Not disclosed"),
                ("All-time low", "%s (%s)" % (_fmt_usd(c.get("atl_usd")), (c.get("atl_date") or "")[:10])
                 if c.get("atl_usd") else "Not disclosed"),
            ]
        )

        faqs = [
            ("What is the current price of %s?" % name,
             "See the live price above, a reference price refreshed every few minutes. This page's other "
             "facts (market cap rank, supply, all-time high/low) are refreshed on each site update, not live."),
            ("What is %s's market cap rank?" % name,
             ("%s is ranked #%d by market capitalisation." % (name, rank)) if rank
             else "Market cap rank is not currently available."),
            ("What is the circulating supply of %s?" % name,
             ("%s coins are currently in circulation." % format(int(c["circulating_supply"]), ",")
              if c.get("circulating_supply") else "Circulating supply is not currently available.")),
            ("What was %s's all-time high?" % name,
             ("%s's all-time high was %s, reached on %s." % (name, _fmt_usd(c.get("ath_usd")), (c.get("ath_date") or "")[:10]))
             if c.get("ath_usd") else "All-time high data is not currently available."),
            ("Is %s regulated by SEBI?" % name,
             "No. Cryptocurrency is not regulated by SEBI in India; it falls under separate income-tax "
             "(virtual digital asset) rules and anti-money-laundering (FIU-IND) registration for exchanges. "
             "This page is informational only, not investment advice."),
            ("Can I buy %s through BrokerLens?" % name,
             "No. This page shows public facts and a live reference price only. Buying or selling %s "
             "requires an account on a crypto exchange." % name),
        ]
        faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in faqs
        )
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Crypto", "/crypto/"), (name, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]},
                crumb_jsonld,
            ],
        }

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body = body.replace("</head>", _stamp_asset_versions(
            '<script src="/assets/js/vendor/lightweight-charts.standalone.production.js"></script>'
            '<script type="module" src="/assets/js/crypto-live.js" defer></script>'
            '<script type="module" src="/assets/js/crypto-chart.js" defer></script></head>'))
        body += (
            crumb_html
            + '<h1 class="coin-name" style="margin-top:0">%s%s <span class="muted">(%s)</span></h1>' % (
                ('<img class="coin-icon" src="%s" width="28" height="28" alt="" loading="lazy" '
                 'style="width:28px;height:28px">' % _esc(c["image"])) if c.get("image") else "",
                _esc(name), _esc(symbol))
            + '<div id="crypto-price" data-symbol="%s" class="card" style="margin-top:12px;max-width:360px">'
              '<div class="small faint">Loading live price...</div></div>' % _esc(symbol)
            + '<div class="card coin-chart"><div class="card-title">Price history</div>'
              '<div data-crypto-chart data-symbol="%s"></div></div>' % _esc(symbol)
            + '<div class="grid g3" style="margin-top:16px">' + facts_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">Facts and reference price are aggregated from public '
              'market data, refreshed periodically. Cryptocurrency is not regulated by SEBI or any Indian '
              'financial regulator.</p>'
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + faq_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page's identity, supply and reference-price facts are aggregated from public "
            "cryptocurrency market data.")}

        dest_dir = os.path.join(ROOT, "site", "crypto", slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "crypto"), slugs)
    log("crypto pages: %d written%s" % (written, (", %d stale pruned" % pruned) if pruned else ""), "ok")
    return sorted(slugs)


_CRYPTO_HUB_FAQS = [
    ("Is this a crypto exchange?", "No. BrokerLens does not let you buy, sell or hold crypto. This page "
     "lists public facts (market cap, supply, all-time high/low) and a live reference price for each coin; "
     "trading happens on an exchange."),
    ("Where does the live price come from?", "Aggregated public cryptocurrency market data, refreshed every "
     "few minutes, independently of this page's other facts, which update on each site rebuild."),
    ("Why only 28 coins?", "Each one is hand-verified against real market-cap ranking and actual tradeable "
     "pairs, so there's no risk of a ticker symbol match being the wrong coin. This list grows only after "
     "the same manual verification, never by scanning symbols automatically."),
    ("Is cryptocurrency regulated in India?", "Not by SEBI. Crypto falls under separate income-tax (virtual "
     "digital asset) rules, and exchanges operating in India must register with FIU-IND under anti-money-"
     "laundering law. Nothing on this page is investment advice."),
]


_IPO_SEC_TYPES = {"EQ", "SME"}  # mainboard + SME - real stock IPOs, not the
# debt/rights/other public-issue codes that flow through the same NSE
# tracking system (see pipeline/sources/nse.py's ipo_past() docstring).


def _ipo_long_date(iso_date):
    """'2026-09-11' -> '11 September 2026'. pipeline/sources/nse.py's
    _ipo_date() normalises every IPO date to ISO (needed so _ipo_merge()'s
    sort-by-date below is a correct lexicographic sort), which is a
    different input shape than _long_date() above expects (NSE's own raw
    'DD-MON-YYYY') - a separate formatter rather than reusing that one."""
    if not iso_date:
        return None
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return iso_date


def _ipo_merge(ipo_data):
    """Merge NSE's three separately-shaped IPO feeds into one record per
    symbol, scoped to genuine equity IPOs.

    current/upcoming are already IPO-scoped by NSE itself (fetched via its
    own category=ipo / ipo-current-issue endpoints) and carry no
    security_type field at all, so they're trusted as-is; past is a broader
    "all public issues" historical log that does carry security_type, so
    that's where non-IPO types (debt, rights, ...) get filtered out.

    Priority when a symbol appears in more than one feed: past (real
    listing/closing facts) overrides current (real subscription data,
    bidding open now) overrides upcoming (forthcoming - price band and
    dates only, no bidding activity yet to have any subscription figures).
    """
    by_symbol = {}

    for r in ipo_data.get("upcoming") or []:
        by_symbol[r["symbol"]] = {
            "symbol": r["symbol"], "company": r.get("company"),
            "price_band": r.get("price_band"), "issue_size_shares": r.get("issue_size_shares"),
            "bidding_start": r.get("bidding_start"), "bidding_end": r.get("bidding_end"),
            "status": "Forthcoming" if r.get("status") == "Forthcoming" else "Active",
            "security_type": None,
        }

    for r in ipo_data.get("current") or []:
        row = by_symbol.setdefault(r["symbol"], {"symbol": r["symbol"], "security_type": None})
        row.update({
            "company": r.get("company") or row.get("company"),
            "price_band": r.get("price_band") or row.get("price_band"),
            "issue_size_shares": r.get("issue_size_shares") or row.get("issue_size_shares"),
            "bidding_start": r.get("bidding_start") or row.get("bidding_start"),
            "bidding_end": r.get("bidding_end") or row.get("bidding_end"),
            "shares_offered": r.get("shares_offered"),
            "shares_bid": r.get("shares_bid"),
            "times_subscribed": r.get("times_subscribed"),
            "status": "Active",
        })

    for r in ipo_data.get("past") or []:
        sec_type = r.get("security_type")
        if sec_type not in _IPO_SEC_TYPES:
            continue
        row = by_symbol.setdefault(r["symbol"], {"symbol": r["symbol"]})
        row.update({
            "company": r.get("company") or row.get("company"),
            "price_band": r.get("price_band") or row.get("price_band"),
            "issue_price": r.get("issue_price"),
            "security_type": sec_type,
            "bidding_start": r.get("bidding_start") or row.get("bidding_start"),
            "bidding_end": r.get("bidding_end") or row.get("bidding_end"),
            "listing_date": r.get("listing_date"),
            "status": "Listed" if r.get("listing_date") else "Closed",
        })

    # A symbol seen only via current/upcoming (never in past) has no
    # security_type at all - those two feeds are already IPO-scoped by NSE,
    # so that's fine; a symbol seen only via past that isn't EQ/SME was
    # already skipped above and never created a row.
    return sorted(
        by_symbol.values(),
        key=lambda r: r.get("listing_date") or r.get("bidding_start") or "",
        reverse=True,
    )


def _ipo_status_badge(status):
    cls = {"Active": "badge-up", "Forthcoming": "badge-warn", "Listed": "badge-verified"}.get(status, "")
    return '<span class="badge %s">%s</span>' % (cls, _esc(status)) if cls else _esc(status or "")


def _write_ipo_pages(records):
    """One static page per IPO (/ipo/:symbol/) - same "readable with zero
    JS, refreshed each publish" contract as a stock/fund/crypto page. No
    live-during-the-bidding-window ticker: subscription figures are as of
    the last site update, stated as such, same as every other periodically-
    refreshed fact on this site."""
    written = 0
    for r in records:
        symbol, company = r["symbol"], r.get("company") or r["symbol"]
        slug = symbol.lower()
        canonical = "%s/ipo/%s/" % (SITE_URL, slug)
        title = "%s IPO: Price Band, Dates and Subscription | BrokerLens" % _esc(company)
        description = _esc(
            "%s IPO: price band, issue size, bidding dates%s, from NSE's own public-issue disclosures." % (
                company, ", subscription and listing status" if r.get("status") != "Forthcoming" else "")
        )[:300]

        facts = [
            ("Status", _ipo_status_badge(r.get("status"))),
            ("Security type", {"EQ": "Mainboard", "SME": "SME"}.get(r.get("security_type"), "Not yet disclosed")),
            ("Price band", _esc(r.get("price_band")) if r.get("price_band") else "Not yet disclosed"),
            ("Final issue price", ("Rs %s" % r["issue_price"]) if r.get("issue_price") else "Not yet disclosed"),
            ("Issue size", ("%s shares" % format(int(r["issue_size_shares"]), ","))
             if r.get("issue_size_shares") else "Not disclosed"),
            ("Bidding opens", _ipo_long_date(r["bidding_start"]) if r.get("bidding_start") else "Not yet announced"),
            ("Bidding closes", _ipo_long_date(r["bidding_end"]) if r.get("bidding_end") else "Not yet announced"),
            ("Listing date", _ipo_long_date(r["listing_date"]) if r.get("listing_date") else "Not yet listed"),
        ]
        if r.get("times_subscribed") is not None:
            facts.append(("Subscribed", "%.2fx (%s of %s shares bid)" % (
                r["times_subscribed"], _full_html(r.get("shares_bid")), _full_html(r.get("shares_offered")))))
        facts_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div><div style="margin-top:2px">%s</div></div>'
            % (label, value) for label, value in facts
        )

        faqs = [
            ("What is the price band for the %s IPO?" % company,
             ("The %s IPO price band is %s per share." % (company, r["price_band"])) if r.get("price_band")
             else "The price band has not been announced yet."),
            ("When does the %s IPO open and close?" % company,
             ("Bidding opens %s and closes %s." % (_ipo_long_date(r["bidding_start"]), _ipo_long_date(r["bidding_end"])))
             if r.get("bidding_start") and r.get("bidding_end") else "Bidding dates have not been announced yet."),
            ("Is the %s IPO a mainboard or SME issue?" % company,
             {"EQ": "%s is a mainboard IPO, listing on NSE's main board." % company,
              "SME": "%s is an SME IPO, listing on NSE Emerge." % company}.get(
                 r.get("security_type"), "The listing platform has not been confirmed yet.")),
            ("When did the %s IPO list?" % company,
             ("%s listed on %s." % (company, _ipo_long_date(r["listing_date"]))) if r.get("listing_date")
             else "This IPO has not listed yet."),
            ("Does this page show the grey market premium (GMP) for %s?" % company,
             "No. GMP is an unregulated, off-exchange estimate BrokerLens does not publish - see "
             "methodology. This page shows only NSE's own disclosed facts and, once bidding opens, "
             "NSE's own published subscription figures."),
            ("Is investing in the %s IPO recommended by BrokerLens?" % company,
             "No. BrokerLens does not recommend any IPO, stock or broker. This page states public facts "
             "only; it is not investment advice."),
        ]
        faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in faqs
        )
        crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("IPO", "/ipo/"), (company, None)])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]},
                crumb_jsonld,
            ],
        }
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s IPO <span class="muted">(%s)</span></h1>' % (_esc(company), _esc(symbol))
            + '<div class="grid g3" style="margin-top:16px">' + facts_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">Facts are NSE\'s own public-issue disclosures, '
              'refreshed periodically. Not investment advice; BrokerLens does not publish grey market premium '
              '(GMP) or recommend any IPO.</p>'
            + '<div class="grid g2" style="margin-top:20px">%s%s</div>'
              % (affiliateBanner_html(), fivepaisaBanner_html())
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + faq_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page's facts are NSE's own public-issue disclosures (price band, dates, subscription "
            "and listing status).")}

        dest_dir = os.path.join(ROOT, "site", "ipo", slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1
    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "ipo"), {r["symbol"].lower() for r in records})
    log("IPO pages: %d written%s" % (written, (", %d stale pruned" % pruned) if pruned else ""), "ok")


def _ipo_row_html(r):
    company = r.get("company") or r["symbol"]
    detail = (r.get("price_band") or "") if r.get("status") != "Listed" else (
        ("Rs %s" % r["issue_price"]) if r.get("issue_price") else (r.get("price_band") or ""))
    date_label = {"Listed": "Listed", "Active": "Closes", "Forthcoming": "Opens", "Closed": "Closed"}.get(
        r.get("status"), "")
    date_val = {"Listed": r.get("listing_date"), "Active": r.get("bidding_end"),
                "Forthcoming": r.get("bidding_start"), "Closed": r.get("bidding_end")}.get(r.get("status"))
    sub = ("%.2fx" % r["times_subscribed"]) if r.get("times_subscribed") is not None else "-"
    return (
        '<tr><td><a href="/ipo/%s/">%s</a> <span class="xs faint">%s</span></td>'
        '<td>%s</td><td class="right num">%s</td>'
        '<td class="right">%s %s</td><td class="right num">%s</td></tr>'
    ) % (
        _esc(r["symbol"].lower()), _esc(company), _esc(r["symbol"]),
        _ipo_status_badge(r.get("status")), _esc(detail),
        date_label, _ipo_long_date(date_val) if date_val else "-", sub,
    )


def _write_ipo_hub(records):
    """/ipo/ - currently open (with real subscription data), forthcoming,
    and recently listed, each linking through to the full per-IPO page.
    Deliberately not a GMP tracker - see the FAQ and per-page disclosure."""
    active = [r for r in records if r.get("status") == "Active"]
    forthcoming = [r for r in records if r.get("status") == "Forthcoming"]
    recent = [r for r in records if r.get("status") in ("Listed", "Closed")][:30]

    canonical = "%s/ipo/" % SITE_URL
    title = "IPO Tracker: Live Subscription, Price Band and Listing Dates | BrokerLens"
    description = ("%d IPOs currently open, %d opening soon, tracked from NSE's own public-issue "
                    "disclosures - price band, dates, real subscription figures. No grey market "
                    "premium." % (len(active), len(forthcoming)))[:300]

    def table(rows, empty_msg):
        if not rows:
            return '<p class="small faint">%s</p>' % empty_msg
        return ('<div class="table-scroll"><table class="data"><thead><tr>'
                '<th>Company</th><th>Status</th><th class="right">Price</th>'
                '<th class="right">Date</th><th class="right">Subscribed</th></tr></thead><tbody>'
                + "".join(_ipo_row_html(r) for r in rows) + "</tbody></table></div>")

    _ipo_faqs = [
        ("Does BrokerLens show IPO grey market premium (GMP)?",
         "No. GMP is an unregulated, off-exchange estimate with no exchange oversight - BrokerLens "
         "publishes only NSE's own disclosed facts: price band, dates, and, once bidding opens, NSE's "
         "own published subscription figures."),
        ("What counts as an IPO on this page?",
         "NSE mainboard and SME equity IPOs only. Debt issues, rights issues and other public-issue "
         "types that NSE tracks separately are not included here."),
        ("How often is subscription data updated?",
         "On each site update, from NSE's own ipo-current-issue disclosure - not a live, "
         "second-by-second feed."),
        ("Does BrokerLens recommend applying to any IPO?",
         "No. This page states public facts only; it is not investment advice, and BrokerLens is not "
         "a SEBI-registered investment adviser or research analyst."),
    ]
    faq_html = "".join(
        '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
        for q, a in _ipo_faqs
    )
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("IPO", None)])
    graph = [
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in _ipo_faqs
        ]},
        crumb_jsonld,
    ]
    open_and_forthcoming = active + forthcoming
    if open_and_forthcoming:
        graph.append({
            "@type": "ItemList", "name": "Open and forthcoming IPOs",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": r.get("company") or r["symbol"],
                 "url": "%s/ipo/%s/" % (SITE_URL, r["symbol"].lower())}
                for i, r in enumerate(open_and_forthcoming)
            ],
        })
    jsonld = {"@context": "https://schema.org", "@graph": graph}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += (
        crumb_html
        + '<h1 style="margin-top:0">IPO tracker</h1>'
        + '<p class="muted" style="max-width:70ch">Mainboard and SME IPOs, from NSE\'s own public-issue '
          'disclosures: price band, dates and real subscription figures. No grey market premium, no '
          'recommendations - <a href="/methodology" data-link>see why</a>.</p>'
        + '<div class="section-title" style="margin-top:20px"><h2>Currently open</h2></div>' + table(
            active, "No IPOs are currently open for bidding.")
        + '<div class="section-title" style="margin-top:20px"><h2>Opening soon</h2></div>' + table(
            forthcoming, "No forthcoming IPOs are announced right now.")
        + '<div class="section-title" style="margin-top:20px"><h2>Recently listed</h2></div>' + table(
            recent, "No recent listings.")
        + '<p class="xs faint" style="margin-top:10px"><a href="/ipo/archive/">Browse the full archive '
          '(%d IPOs since 2003) &rarr;</a></p>' % len(records)
        + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
        + '<div style="max-width:68ch">' + faq_html + '</div>'
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page's price bands, dates, subscription and listing facts are NSE's own public-issue "
        "disclosures.")}
    dest_dir = os.path.join(ROOT, "site", "ipo")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("IPO hub: written, %d active, %d forthcoming, %d recent" % (
        len(active), len(forthcoming), len(recent)), "ok")


def _write_ipo_archive(records):
    """/ipo/archive/ - every IPO BrokerLens has a record of, oldest to
    newest bidding activity descending, same "full list, not paginated
    into obscurity" choice as /brokers (48 rows) and /registry's search
    (1,691 entities) - at ~1,200-1,400 rows this is comparable to the
    stock-directory letter pages, not an outlier."""
    canonical = "%s/ipo/archive/" % SITE_URL
    title = "Full IPO Archive Since 2003 | BrokerLens"
    description = ("Every NSE mainboard and SME IPO BrokerLens has a record of, from NSE's own "
                    "public-issue disclosures.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("IPO", "/ipo/"), ("Archive", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "ItemList", "name": title, "url": canonical,
             "itemListElement": [
                 {"@type": "ListItem", "position": i + 1, "url": "%s/ipo/%s/" % (SITE_URL, r["symbol"].lower()),
                  "name": r.get("company") or r["symbol"]}
                 for i, r in enumerate(records)
             ]},
            crumb_jsonld,
        ],
    }
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Full IPO archive</h1>'
        + '<p class="muted" style="max-width:70ch">%d mainboard and SME IPOs, from NSE\'s own '
          'public-issue disclosures. <a href="/ipo/" data-link>Back to currently-open IPOs &rarr;</a></p>'
          % len(records)
        + '<div class="table-scroll" style="margin-top:16px"><table class="data"><thead><tr>'
          '<th>Company</th><th>Status</th><th class="right">Price</th>'
          '<th class="right">Date</th><th class="right">Subscribed</th></tr></thead><tbody>'
        + "".join(_ipo_row_html(r) for r in records) + "</tbody></table></div>"
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page's facts are NSE's own public-issue disclosures.")}
    dest_dir = os.path.join(ROOT, "site", "ipo", "archive")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("IPO archive: written, %d rows" % len(records), "ok")


def _write_crypto_hub(coins):
    """/crypto/ - the entry point named in the nav's markets dropdown, once
    real content exists to put there instead of a coming-soon placeholder."""
    ranked = sorted((c for c in coins or [] if c.get("name")),
                     key=lambda c: c.get("market_cap_rank") or 9999)
    canonical = "%s/crypto/" % SITE_URL
    title = "Crypto Prices and Market Data | BrokerLens"
    description = ("Reference prices and market-cap facts for %d major cryptocurrencies, aggregated from "
                    "public market data." % len(ranked))

    rows_html = "".join(
        '<tr data-crypto-row="%s"><td class="rank-cell">%s</td>'
        '<td><a class="coin-name" href="/crypto/%s/">%s<span>%s</span>'
        '<span class="xs faint">%s</span></a></td>'
        '<td class="right num" data-role="price">-</td>'
        '<td class="right num" data-role="change">-</td>'
        '<td class="right num faint" data-role="volume">-</td></tr>'
        % (_esc(c["symbol"]), ("#%d" % c["market_cap_rank"]) if c.get("market_cap_rank") else "-",
           _esc(c["symbol"].lower()),
           ('<img class="coin-icon" src="%s" width="22" height="22" alt="" loading="lazy">' % _esc(c["image"])
            if c.get("image") else ""),
           _esc(c["name"]), _esc(c["symbol"]))
        for c in ranked
    )
    faq_html = "".join(
        '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
        for q, a in _CRYPTO_HUB_FAQS
    )
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Crypto", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in _CRYPTO_HUB_FAQS
            ]},
            crumb_jsonld,
        ],
    }
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body = body.replace("</head>", _stamp_asset_versions(
        '<script type="module" src="/assets/js/crypto-live.js" defer></script></head>'))
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Crypto prices and market data</h1>'
        + '<p class="muted" style="max-width:70ch">%d cryptocurrencies, ranked by market cap. Reference price '
          "and identity/supply facts aggregated from public market data.</p>" % len(ranked)
        + '<div class="grid g-main" style="margin-top:16px">'
        + '<div class="table-scroll"><table class="data"><thead><tr>'
          "<th>Rank</th><th>Coin</th><th class=\"right\">Price</th><th class=\"right\">24h</th>"
          "<th class=\"right\">Volume (24h)</th>"
          "</tr></thead><tbody>" + rows_html + "</tbody></table></div>"
        + '<div class="stack">' + _crypto_banner_html() + _delta_banner_html() + "</div>"
        + "</div>"
        + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
        + '<div style="max-width:68ch">' + faq_html + '</div>'
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page's reference prices, identity and supply facts are aggregated from public "
        "cryptocurrency market data.")}
    dest_dir = os.path.join(ROOT, "site", "crypto")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("crypto hub: written, %d coins" % len(ranked), "ok")


_CALC_HUB_FAQS = [
    ("Are these calculators free to use?",
     "Yes. Every calculator on this page runs entirely in your browser using a standard, published "
     "financial formula. Nothing is submitted to BrokerLens or anyone else."),
    ("Which calculator should I use for SIP planning?",
     "The SIP Calculator projects a regular monthly investment. If your monthly amount will increase "
     "each year, use the Step-up SIP Calculator instead - a flat SIP calculator understates the result."),
    ("What is the difference between the SIP and lumpsum calculators?",
     "The SIP Calculator assumes a fixed amount invested every month; the Lumpsum Calculator assumes "
     "the entire amount is invested once, upfront. Use whichever matches how you actually plan to invest."),
    ("Do these calculators account for tax?",
     "Only the Capital Gains Tax Calculator and GST Calculator compute tax directly. The others (SIP, "
     "lumpsum, SWP, PPF, retirement) show pre-tax growth; any tax due on withdrawal is not deducted."),
    ("Where can I compare actual broker charges instead of financial formulas?",
     "Use the brokerage cost calculator, which compares real published charges across every broker "
     "BrokerLens tracks, rather than a generic formula."),
]


def _write_methodology_page():
    """/methodology was, until now, reachable only by executing pages.js's
    methodology() client-side - a direct hit or a crawler that doesn't render
    JS got the SPA shell's empty skeleton, not this content. The page has no
    data dependency and no interactivity at all (no onMount in the JS
    version), so - unlike brokers/compare/leaderboards/registry/algo/
    calculator below - it needs no SPA shell or hydration: a plain static
    page, exactly like a stock or fund page, is a strictly complete port of
    what pages.js already renders."""
    canonical = "%s/methodology" % SITE_URL
    title = "Methodology | BrokerLens"
    description = ("How BrokerLens sources and calculates every broker metric: market share, complaints per "
                    "10k clients, the reliability score and cost of a standard month, plus what we deliberately "
                    "do not do.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Methodology", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">Methodology</h1>'
        '<p class="muted" style="max-width:70ch">Every number here should be checkable. This page states where '
        'each figure comes from, how derived metrics are calculated, and what we deliberately do not do.</p>'

        '<div class="section-title"><h2>Where the data comes from</h2></div>'
        '<div class="grid g2">'
        '<div class="card"><div class="card-title">Regulator-sourced %s</div>'
        '<ul class="small" style="padding-left:18px;margin-top:8px">'
        '<li>Legal entity names and SEBI registration numbers (SEBI recognised-intermediary register)</li>'
        '<li>Exchange memberships and registration validity (same register)</li>'
        '<li>Depository-participant licences (SEBI CDSL and NSDL registers)</li>'
        '<li>Defaulter / expelled status (SEBI defaulter list)</li>'
        '<li>Circulars naming a member (NSE circular feed)</li>'
        '</ul></div>'
        '<div class="card"><div class="card-title">Market context %s</div>'
        '<ul class="small" style="padding-left:18px;margin-top:8px">'
        '<li>Index levels and market breadth (NSE)</li>'
        '<li>Institutional flows (NSE FII/DII report)</li>'
        '<li>Cash-market turnover (NSE bhavcopy)</li>'
        '<li>Delivery percentage (BSE scrip-wise gross delivery archive)</li>'
        '<li>Corporate actions (BSE)</li>'
        '</ul></div></div>'

        '<div class="section-title"><h2>Derived metrics</h2></div>'
        '<div class="stack">'
        '<div class="card"><h4>Market share</h4>'
        '<p class="small muted">A broker\'s active clients divided by the total across all tracked brokers, for '
        'the same month. It is share of the tracked set, not of every broker in India: smaller firms '
        'outside the tracked set are not in the denominator.</p></div>'
        '<div class="card"><h4>Complaints per 10,000 clients</h4>'
        '<p class="small muted">Complaints received over 12 months &divide; active clients &times; 10,000. '
        'Normalising matters: a large broker will always show more raw complaints than a small one, which tells '
        'you nothing on its own.</p></div>'
        '<div class="card"><h4>Reliability score (0 to 100)</h4>'
        '<p class="small muted">A weighted composite, disclosed in full: complaint rate percentile against peers '
        '(40%%), resolution rate (20%%), regulatory flags (20%%), complaint backlog in months of current inflow '
        '(10%%), and years since founding (10%%). Missing components are dropped and remaining weights '
        'renormalised, so a broker is not penalised for a dataset we have not ingested: instead the '
        'profile shows lower confidence. It is arithmetic over public disclosures, not an opinion, and it is '
        'not a recommendation.</p></div>'
        '<div class="card"><h4>Cost of a standard month</h4>'
        '<p class="small muted">Brokerage on a fixed basket (&#8377;50,000 of delivery across 4 orders, '
        '&#8377;1,00,000 of intraday turnover across 10 orders, &#8377;2,00,000 of F&amp;O premium turnover '
        'across 10 orders) plus demat AMC divided by twelve. Statutory charges (STT, stamp duty, exchange '
        'transaction charges, SEBI turnover fees, GST) are excluded because they are identical at every broker '
        'for an identical trade; including them would compress the differences that actually depend on your '
        'choice of broker. Use the <a href="/calculator" data-link>calculator</a> to price your own pattern '
        'instead.</p></div>'
        '</div>'

        '<div class="section-title"><h2>What we do not do</h2></div>'
        '<div class="card"><ul class="small" style="padding-left:18px">'
        '<li>We do not name a single &quot;best broker&quot;. It depends entirely on what and how much you '
        'trade.</li>'
        '<li>We do not give investment advice, and we are not a SEBI-registered adviser or research analyst.</li>'
        '<li>We do not scrape competitor comparison sites. Every figure traces to a primary exchange or '
        'regulator source.</li>'
        '<li>We do not let paid placement move a broker up a factual ranking.</li>'
        '<li>We do not invent a number to fill a gap. Missing data shows as &quot;-&quot; or '
        '&quot;unverified&quot;.</li>'
        '</ul></div>'

        '<div class="section-title"><h2>Advertising disclosure</h2></div>'
        '<div class="card"><p class="small muted">Some pages carry a clearly marked &quot;Sponsored&quot; banner '
        'linking to a broker\'s own signup page; BrokerLens may earn a commission if you open an account through '
        'one of those links. This is separate from every ranking, score and comparison on this site, which are '
        'built only from the regulator and exchange data described above and are never affected by who does or '
        'doesn\'t have an affiliate relationship with us.</p></div>'
    ) % (_prov_dot_html("sebi_registry"), _prov_dot_html("nse"))
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page documents BrokerLens's own methodology: where every figure comes from and how derived "
        "metrics are calculated.")}
    dest_dir = os.path.join(ROOT, "site", "methodology")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("methodology page: written", "ok")


# Same text app.js's TITLES/DESCRIPTIONS maps use for these two routes, so a
# client-side navigation here from elsewhere in the SPA doesn't flash a
# different title than what this static page already served a crawler.
_COMING_SOON = {
    "us": {
        "h1": "US stock broker comparison",
        "title": "US stock broker comparison, coming soon: BrokerLens",
        "description": "BrokerLens is researching US stock broker data for a future comparison. Not live yet.",
        "body": "BrokerLens is researching primary-source data for US stock brokers (SEC/FINRA disclosures, "
                "brokerage fee schedules) before building this the same way as the Indian broker comparison: "
                "real regulator data, not marketing copy.",
    },
    "gcc": {
        "h1": "GCC stock broker comparison",
        "title": "GCC stock broker comparison, coming soon: BrokerLens",
        "description": "BrokerLens is researching GCC (UAE, Saudi and Gulf) stock broker data for a future "
                        "comparison. Not live yet.",
        "body": "BrokerLens is researching primary-source data for stock brokers in the UAE, Saudi Arabia and "
                "the wider Gulf before building this section.",
    },
}


def _write_coming_soon_pages():
    """/coming-soon/us and /coming-soon/gcc were, until now, reachable only by
    executing pages.js's comingSoon() client-side - a direct hit or a crawler
    that doesn't render JS fell through Vercel's catch-all rewrite to
    index.html and got the HOMEPAGE's title/canonical/content instead of
    this page's own, the same class of bug _write_broker_pages() had. No
    data dependency and no interactivity, so a plain static page (like
    methodology/sources) is a strictly complete port of what pages.js
    already renders - no SPA shell or hydration needed."""
    for market, m in _COMING_SOON.items():
        canonical = "%s/coming-soon/%s" % (SITE_URL, market)
        crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), (m["h1"], None)])
        jsonld = {"@context": "https://schema.org", "@graph": [
            {"@type": "WebPage", "name": m["title"], "url": canonical, "description": m["description"]},
            crumb_jsonld,
        ]}
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(m["title"]), "description": _esc(m["description"]),
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += crumb_html + (
            '<div style="max-width:60ch;margin-top:16px">'
            '<span class="badge badge-warn">Coming soon</span>'
            '<h1 style="margin-top:12px">%s</h1>'
            '<p class="muted">%s</p>'
            '<p class="small"><a href="/brokers">See the live India broker comparison instead &rarr;</a></p>'
            '</div>'
        ) % (_esc(m["h1"]), _esc(m["body"]))
        body += _REGISTRY_PAGE_FOOT % {"source_note": "Nothing on this page is fabricated to fill the gap: "
                                                        "there is no live data for this market yet."}
        dest_dir = os.path.join(ROOT, "site", "coming-soon", market)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
    log("coming-soon pages: %d written" % len(_COMING_SOON), "ok")


def _write_about_page():
    """/about was reachable nowhere on the site until now: no nav link, no
    footer link, no static file, no SPA route. E-E-A-T (Google's own
    guidance) expects a real page stating who publishes the site and why it
    should be trusted; a comparison site with no About page at all is a
    trust gap, not a stylistic omission. Static, like methodology/sources:
    no data dependency, no interactivity."""
    canonical = "%s/about" % SITE_URL
    title = "About BrokerLens | BrokerLens"
    description = ("What BrokerLens is, how it sources broker, stock, fund and crypto data, and what it "
                    "deliberately does not do.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("About", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "AboutPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">About BrokerLens</h1>'
        '<p class="muted" style="max-width:70ch">BrokerLens compares Indian stock brokers, and tracks stocks, '
        'mutual funds, ETFs, IPOs and crypto assets, using figures taken directly from NSE, BSE, SEBI, AMFI and '
        'exchange disclosures rather than from marketing pages.</p>'

        '<div class="section-title"><h2>What we track</h2></div>'
        '<div class="card"><ul class="small" style="padding-left:18px">'
        '<li>Every SEBI-registered stock broker and depository participant, including the full recognised-'
        'intermediary register</li>'
        '<li>Listed NSE and BSE equities, index constituents and ETFs</li>'
        '<li>AMFI-registered mutual fund schemes, grouped by AMC</li>'
        '<li>Live and forthcoming IPOs, with subscription and allotment status</li>'
        '<li>Major crypto assets by market capitalisation</li>'
        '</ul></div>'

        '<div class="section-title"><h2>How we work</h2></div>'
        '<p class="small muted" style="max-width:70ch">Every figure traces to a named primary source, refreshed '
        'on its own schedule and marked with when it last ran. The full method, including how derived scores '
        'like the reliability rating are calculated, is on the <a href="/methodology" data-link>methodology '
        'page</a>; the complete source list, with cadence and status, is on the '
        '<a href="/sources" data-link>sources page</a>.</p>'

        '<div class="section-title"><h2>What BrokerLens is not</h2></div>'
        '<div class="card"><p class="small muted">BrokerLens is an information service, not a SEBI-registered '
        'investment adviser or research analyst. Nothing on this site is investment advice, and we do not '
        'recommend any broker, security or strategy. Some pages carry a clearly marked sponsored banner linking '
        'to a broker\'s own signup page, and we may earn a commission if you open an account through one of '
        'those links; this never affects any ranking, score or comparison, which is built only from the '
        'regulator and exchange data described above.</p></div>'

        '<div class="section-title"><h2>Get in touch</h2></div>'
        '<p class="small">Questions, corrections or partnership enquiries: see the '
        '<a href="/contact" data-link>contact page</a>, or write to '
        '<a href="mailto:%s">%s</a>.</p>'
    ) % (CONTACT_EMAIL, CONTACT_EMAIL)
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page states who publishes BrokerLens and how it sources its data.")}
    dest_dir = os.path.join(ROOT, "site", "about")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("about page: written", "ok")


def _write_contact_page():
    """/contact: the single place the real support address
    (CONTACT_EMAIL) is published, plus mirrored into the footer of every
    page. Static, like methodology/sources: no data dependency, no
    interactivity."""
    canonical = "%s/contact" % SITE_URL
    title = "Contact BrokerLens | BrokerLens"
    description = "How to reach BrokerLens for data corrections, advertising enquiries, or privacy and legal questions."[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Contact", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "ContactPage", "name": title, "url": canonical, "description": description},
        {"@type": "Organization", "name": "BrokerLens", "url": SITE_URL,
         "contactPoint": [{"@type": "ContactPoint", "email": CONTACT_EMAIL, "contactType": "customer support",
                            "areaServed": "IN", "availableLanguage": "English"}]},
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">Contact BrokerLens</h1>'
        '<p class="muted" style="max-width:70ch">One address for everything below. Tell us which of these it is '
        'so we can route it to the right place, and include the page URL for anything data-related.</p>'

        '<div class="grid g2" style="margin-top:16px">'
        '<div class="card"><div class="card-title">Data corrections</div>'
        '<p class="small muted">Spotted a wrong figure, an outdated registration, or a broker that should be '
        'listed and is not? Tell us the page and what looks wrong, and we will check it against the primary '
        'source (NSE, BSE, SEBI or AMFI).</p></div>'
        '<div class="card"><div class="card-title">Advertising and partnerships</div>'
        '<p class="small muted">Enquiries about a sponsored banner or a broker partnership. This is entirely '
        'separate from our rankings and comparisons, which are never affected by an advertising relationship.'
        '</p></div>'
        '<div class="card"><div class="card-title">Privacy and data requests</div>'
        '<p class="small muted">Questions about the <a href="/privacy-policy" data-link>privacy policy</a>, or a '
        'request to access or delete data we hold about you.</p></div>'
        '<div class="card"><div class="card-title">Everything else</div>'
        '<p class="small muted">General feedback, bug reports, or anything not covered above, including the '
        '<a href="/terms-of-service" data-link>terms of service</a>.</p></div>'
        '</div>'

        '<div class="section-title"><h2>Email</h2></div>'
        '<div class="card"><p style="font-size:1.1rem"><a href="mailto:%s">%s</a></p>'
        '<p class="small muted">We read every message. Response times vary, but data corrections referencing a '
        'primary source are prioritised.</p></div>'
    ) % (CONTACT_EMAIL, CONTACT_EMAIL)
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page states how to reach BrokerLens directly.")}
    dest_dir = os.path.join(ROOT, "site", "contact")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("contact page: written", "ok")


def _write_privacy_page():
    """/privacy-policy: states plainly that BrokerLens runs no third-party
    analytics or tracking cookies (true as of this build - only a
    same-origin theme/exchange preference in localStorage), so this is a
    factual description of the site, not templated boilerplate. Static,
    like methodology/sources."""
    canonical = "%s/privacy-policy" % SITE_URL
    title = "Privacy Policy | BrokerLens"
    description = "What BrokerLens does and does not collect, how affiliate links work, and how to reach us about your data."[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Privacy Policy", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">Privacy Policy</h1>'
        '<p class="muted" style="max-width:70ch">Last updated %s. This page states what BrokerLens collects, '
        'what it does not, and how to reach us about either.</p>'

        '<div class="section-title"><h2>What we collect</h2></div>'
        '<div class="card"><p class="small muted">BrokerLens runs no third-party analytics or advertising '
        'tracking. The site stores two preferences in your own browser\'s local storage (never sent to us or '
        'anyone else): your light or dark theme choice, and your selected market exchange on the price ticker. '
        'Clearing your browser data removes them. If you write to us by email, we hold that message and your '
        'email address only for as long as needed to answer it.</p></div>'

        '<div class="section-title"><h2>Affiliate and sponsored links</h2></div>'
        '<div class="card"><p class="small muted">Some pages carry a clearly marked sponsored banner linking to '
        'a broker\'s own account-opening page. Once you follow that link, you are on the broker\'s own site and '
        'subject to their privacy policy, not ours; BrokerLens may earn a commission if you open an account, '
        'disclosed on the <a href="/methodology" data-link>methodology page</a>. We do not receive or store any '
        'personal or financial information from that process.</p></div>'

        '<div class="section-title"><h2>Hosting and infrastructure</h2></div>'
        '<div class="card"><p class="small muted">The site is served over HTTPS by a standard web hosting '
        'provider, which may log basic technical request data (IP address, timestamp, requested page) for '
        'security and reliability, the same as any web server. BrokerLens does not access this data for '
        'tracking or profiling individual visitors.</p></div>'

        '<div class="section-title"><h2>Your rights</h2></div>'
        '<div class="card"><p class="small muted">You can ask us what data we hold about you, ask us to correct '
        'or delete it, or ask a question about this policy, at any time: write to '
        '<a href="mailto:%s">%s</a>.</p></div>'

        '<div class="section-title"><h2>Children\'s privacy</h2></div>'
        '<div class="card"><p class="small muted">BrokerLens is not directed at children and does not knowingly '
        'collect information from anyone under 18.</p></div>'

        '<div class="section-title"><h2>Changes to this policy</h2></div>'
        '<div class="card"><p class="small muted">If this policy changes, the updated date at the top of this '
        'page will change too. Material changes will be reflected here before they take effect.</p></div>'
    ) % (_month_html(now_iso()[:7]), CONTACT_EMAIL, CONTACT_EMAIL)
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page states BrokerLens's own data-handling practices.")}
    dest_dir = os.path.join(ROOT, "site", "privacy-policy")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("privacy policy page: written", "ok")


def _write_terms_page():
    """/terms-of-service: the disclaimer text here mirrors _APP_SHELL_FOOT's
    sitewide disclaimer verbatim in substance (same "not investment advice"
    facts), because a terms page that contradicted the footer disclaimer
    would itself be a compliance problem. Static, like methodology/sources."""
    canonical = "%s/terms-of-service" % SITE_URL
    title = "Terms of Service | BrokerLens"
    description = "The terms for using BrokerLens: what the site is, the limits on the information it publishes, and your responsibilities."[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Terms of Service", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">Terms of Service</h1>'
        '<p class="muted" style="max-width:70ch">Last updated %s. By using BrokerLens, you agree to the terms '
        'below.</p>'

        '<div class="section-title"><h2>What BrokerLens is</h2></div>'
        '<div class="card"><p class="small muted">BrokerLens is an information service that publishes broker, '
        'stock, mutual fund, ETF, IPO and crypto data assembled from primary NSE, BSE, SEBI and AMFI '
        'disclosures. BrokerLens is not a SEBI-registered investment adviser or research analyst, does not '
        'recommend any broker, security or strategy, and nothing on this site is investment advice. Verify '
        'anything material with the broker or with SEBI before acting on it.</p></div>'

        '<div class="section-title"><h2>Accuracy of information</h2></div>'
        '<div class="card"><p class="small muted">Figures are reproduced from exchange and regulator '
        'disclosures and may lag their source; each page states when its data last refreshed. BrokerLens does '
        'not guarantee that any figure is current or error-free, and is not liable for decisions made in '
        'reliance on it. See the <a href="/methodology" data-link>methodology page</a> for exactly how each '
        'figure is calculated.</p></div>'

        '<div class="section-title"><h2>Sponsored links</h2></div>'
        '<div class="card"><p class="small muted">Some pages carry a clearly marked sponsored banner linking to '
        'a broker\'s own account-opening page; BrokerLens may earn a commission if you open an account through '
        'one of those links. Account opening happens entirely on the broker\'s own site, under their own terms, '
        'not ours.</p></div>'

        '<div class="section-title"><h2>Intellectual property</h2></div>'
        '<div class="card"><p class="small muted">The BrokerLens name, logo and site design belong to '
        'BrokerLens. Underlying facts sourced from NSE, BSE, SEBI and AMFI remain the property of those '
        'regulators and exchanges; BrokerLens republishes and computes derived figures from them under its own '
        'methodology.</p></div>'

        '<div class="section-title"><h2>Limitation of liability</h2></div>'
        '<div class="card"><p class="small muted">BrokerLens is provided as is, without warranty of any kind. '
        'To the fullest extent permitted by law, BrokerLens is not liable for any loss arising from use of, or '
        'reliance on, information published on this site.</p></div>'

        '<div class="section-title"><h2>Governing law</h2></div>'
        '<div class="card"><p class="small muted">These terms are governed by the laws of India.</p></div>'

        '<div class="section-title"><h2>Changes to these terms</h2></div>'
        '<div class="card"><p class="small muted">If these terms change, the updated date at the top of this '
        'page will change too.</p></div>'

        '<div class="section-title"><h2>Contact</h2></div>'
        '<div class="card"><p class="small muted">Questions about these terms: '
        '<a href="mailto:%s">%s</a>.</p></div>'
    ) % (_month_html(now_iso()[:7]), CONTACT_EMAIL, CONTACT_EMAIL)
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page states the terms for using BrokerLens.")}
    dest_dir = os.path.join(ROOT, "site", "terms-of-service")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("terms of service page: written", "ok")


def _status_badge_html(st):
    """Python port of pages.js's statusBadge() - same three-state pipeline
    health indicator (ok/empty/error) on the static /sources page as on the
    SPA's own copy of it."""
    if not st:
        return '<span class="badge">not run</span>'
    if st == "ok":
        return '<span class="badge badge-up">ok</span>'
    if st == "empty":
        return '<span class="badge badge-warn">empty</span>'
    return '<span class="badge badge-down" title="%s">error</span>' % _esc(st)


def _write_sources_page(sources_data):
    """/sources, like /methodology, has no interactivity in the JS version
    (no onMount) - a plain static page is a complete, faithful port, not a
    simplified stand-in."""
    rows = sources_data.get("sources") or []
    groups = {}
    for r in rows:
        groups.setdefault(r.get("publisher"), []).append(r)

    canonical = "%s/sources" % SITE_URL
    title = "Sources & Data Lineage | BrokerLens"
    description = ("Every data source the BrokerLens pipeline touches, when it last ran and what came back - "
                    "published so any figure can be audited back to its origin.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Sources & lineage", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">Sources &amp; data lineage</h1>'
        '<p class="muted" style="max-width:70ch">Every source the pipeline touches, when it last ran and what '
        'came back. Published so that anyone can audit a figure back to its origin.</p>'
    )
    for pub, pub_rows in groups.items():
        body += '<div class="section-title"><h2>%s</h2></div>' % _esc(pub or "Other")
        body += ('<div class="table-scroll"><table class="data">'
                  '<thead><tr><th>Dataset</th><th>Cadence</th><th>Last run</th><th>Status</th><th>Notes</th></tr></thead>'
                  '<tbody>')
        for r in pub_rows:
            last_run = (r.get("last_run") or "-")[:16].replace("T", " ")
            body += (
                '<tr><td><div style="font-weight:560">%s</div>'
                '<div class="xs faint" style="word-break:break-all">%s</div></td>'
                '<td class="small">%s</td>'
                '<td class="small nowrap">%s</td>'
                '<td>%s</td>'
                '<td class="xs muted">%s</td></tr>'
            ) % (
                _esc(r.get("title") or ""), _esc(r.get("url") or ""),
                _esc(r.get("cadence") or "-"), _esc(last_run),
                _status_badge_html(r.get("last_status")), _esc(r.get("notes") or ""),
            )
        body += "</tbody></table></div>"

    licensing = sources_data.get("licensing") or {}
    if licensing:
        body += '<div class="section-title"><h2>Licensing position</h2></div><div class="card"><dl class="kv">'
        for k, v in licensing.items():
            body += "<dt>%s</dt><dd class=\"small muted\">%s</dd>" % (_esc(str(k).upper()), _esc(str(v)))
        body += "</dl></div>"

    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page lists every primary data source the BrokerLens pipeline reads from and when it last ran.")}
    dest_dir = os.path.join(ROOT, "site", "sources")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("sources page: written, %d sources" % len(rows), "ok")


_PRICING_LABEL = {
    "free": "Free", "freemium": "Freemium", "subscription": "Subscription",
    "per-seat licence": "Per-seat licence", "enterprise licence": "Enterprise licence",
}


def _algo_card_html(p):
    """Python port of pages.js's algoCard()."""
    site = _safe_url(p.get("website"))
    works = " ".join(
        '<a class="badge" href="/broker/%s/" data-link title="Executes through %s (view broker profile)">%s</a>'
        % (_esc(b["id"]), _esc(b["brand"]), _esc(b["brand"]))
        for b in (p.get("works_with") or [])
    )
    name_html = ('<a href="%s" target="_blank" rel="noopener nofollow">%s</a>' % (_esc(site), _esc(p.get("name") or ""))
                 if site else _esc(p.get("name") or ""))
    pricing = p.get("pricing")
    return (
        '<div class="card" style="display:flex;flex-direction:column;gap:8px">'
        '<div class="row">%s'
        '<div class="grow"><div style="font-weight:600">%s</div>'
        '<div class="xs muted">%s%s</div></div>'
        '%s</div>'
        '<p class="small" style="margin:0">%s</p>'
        '%s</div>'
    ) % (
        _mark_html(p.get("id"), p.get("name") or "", 30), name_html,
        _esc(p.get("operator") or ""), (" &middot; %s" % _esc(p["hq"])) if p.get("hq") else "",
        ('<span class="badge">%s</span>' % _esc(_PRICING_LABEL.get(pricing, pricing))) if pricing else "",
        _esc(p.get("summary") or ""),
        ('<div class="row-wrap xs"><span class="faint">Executes via:</span> %s</div>' % works) if works else "",
    )


def _write_algo_page(algo_data):
    """/algo is a genuine interactive tool (search + category filter over 28
    curated platforms), so - unlike /methodology and /sources above - this
    uses the hybrid _APP_SHELL_HEAD/_FOOT: real content in the default
    "all categories, no search" state for first paint and crawlers, then
    app.js hydrates the same route for the live search/filter behaviour.
    """
    cats = algo_data.get("categories") or {}
    platforms = algo_data.get("platforms") or []
    count = algo_data.get("count", len(platforms))

    canonical = "%s/algo" % SITE_URL
    title = "Algo Trading Platforms in India | BrokerLens"
    description = ("Official broker APIs, no-code strategy builders, backtesting tools and institutional "
                    "vendors behind broker dealing desks in India, with SEBI's retail algo framework context.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Algo platforms", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList", "name": title, "url": canonical,
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "name": p.get("name")}
                    for i, p in enumerate(platforms)
                ],
            },
            crumb_jsonld,
        ],
    }
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html
    body += (
        '<h1 style="margin-top:16px">Algo trading platforms in India</h1>'
        '<p class="muted" style="max-width:75ch">The execution and automation layer around the brokers we '
        'track: official broker APIs, no-code strategy builders, backtesting tools and the institutional '
        'vendors behind broker dealing desks. Platform details are curated and verified against each '
        'platform\'s own material (not regulator filings), so treat them as a directory, not an '
        'endorsement.</p>'

        '<div class="banner" style="margin-top:14px"><span>&sect;</span>'
        '<div><strong>SEBI\'s retail algo framework (February 2025).</strong> '
        'SEBI has brought retail algo trading inside a formal perimeter: brokers remain responsible for every '
        'algo order, API access requires authentication with static-IP whitelisting, orders above an '
        'exchange-set rate threshold need an exchange-issued algo ID, and algo providers must be empanelled '
        'with the exchanges. Strategies split into <em>white-box</em> (logic disclosed) and <em>black-box</em> '
        '(undisclosed: the provider needs a Research Analyst registration and audit trail). '
        'Implementation timelines have moved; check the latest SEBI and exchange circulars before relying on '
        'any platform\'s compliance claims.</div></div>'

        '<div class="card" style="margin-top:14px"><div class="row-wrap">'
        '<div class="grow" style="min-width:220px">'
        '<input type="search" id="algo-q" placeholder="Search platforms, operators or connected brokers&hellip;">'
        '</div>'
        '<button class="btn btn-sm btn-primary" data-algo-cat="all">All</button>'
        + "".join('<button class="btn btn-sm" data-algo-cat="%s">%s</button>' % (_esc(k), _esc(v.get("label") or k))
                   for k, v in cats.items())
        + '<span class="small faint" id="algo-meta">%d of %d platforms</span></div></div>' % (len(platforms), count)
    )
    body += '<div id="algo-list">'
    for k, v in cats.items():
        cat_rows = [p for p in platforms if p.get("category") == k]
        if not cat_rows:
            continue
        body += (
            '<section style="margin-top:20px"><h2 style="margin-bottom:2px">%s</h2>'
            '<p class="small muted" style="max-width:75ch;margin-top:2px">%s</p>'
            '<div class="grid g3" style="margin-top:10px">%s</div></section>'
        ) % (_esc(v.get("label") or k), _esc(v.get("blurb") or ""),
             "".join(_algo_card_html(p) for p in cat_rows))
    body += "</div>"
    body += (
        '<p class="xs faint" style="margin-top:10px">%s Curated directory, last reviewed %s. Pricing models are '
        'indicative; integrations change frequently. Nothing here is investment advice or a recommendation of '
        'any platform.</p>'
    ) % (_prov_dot_html("curated"), _esc((algo_data.get("last_reviewed") or algo_data.get("generated_at") or "")[:10]))
    body += _APP_SHELL_FOOT
    dest_dir = os.path.join(ROOT, "site", "algo")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("algo page: written, %d platforms" % len(platforms), "ok")


def _sample_banner_html(meta):
    """Python port of pages.js's sampleBanner() - correctly renders nothing
    in production today (data_status/sample_data are all false), but stays
    a faithful port rather than a permanently-empty stub in case that ever
    changes."""
    which = [k.replace("_", " ") for k, v in (meta.get("sample_data") or {}).items() if v]
    if not which:
        return ""
    return (
        '<div class="banner"><span>&#9888;</span><div><strong>Sample data in use for: %s.</strong> '
        'These are placeholder figures generated to exercise the interface, not facts about any broker. '
        'Regulator-sourced fields (legal entity, SEBI registration, exchange memberships, defaulter status) are '
        'real. See <a href="/sources" data-link>sources</a> for what is live.</div></div>'
    ) % _esc(", ".join(which))


def _pending_html(what, detail):
    """Python port of pages.js's pending() - the standing "not published yet"
    notice used whenever a section has no real, source-traced data."""
    return (
        '<div class="pending"><strong>%s not published yet</strong> %s We publish a figure only once it comes '
        'from the primary source, so this section is empty rather than estimated. '
        '<a href="/sources" data-link>What is live today</a>.</div>'
    ) % (_esc(what), _esc(detail))


def _usd_html(n):
    """Adaptive-decimal $ formatter for a leaderboard cell - matches the
    same rule crypto-live.js/crypto-chart.js use client-side, so a coin's
    price reads the same number of decimals wherever it's shown."""
    if n is None:
        return "-"
    d = 6 if n < 1 else 4 if n < 100 else 2
    return "$%.*f" % (d, n)


def _write_leaderboards_page(overview, nse_live, crypto_coins):
    """/leaderboards has no user input at all in the JS version (no onMount
    listeners, just chart draws over server data) - the hybrid shell exists
    here only so the bar charts (drawn client-side onto <canvas>) render in
    once app.js loads; the table/ranking content itself needs no
    hydration to become correct.

    Broker rankings (active clients, complaints, cost) stay gated on real
    NSE/SEBI disclosures not yet ingested - see the pending notice below,
    never sample data standing in for them. But that isn't the only real
    ranking this site can publish honestly: NSE's own gainers/losers/most-
    active feeds and the crypto universe's market-cap and 24h movers are
    already fetched, real, and completely unused as rankings anywhere on
    the site. Until now this whole page was one paragraph explaining why
    it was empty - it doesn't need to be, and shouldn't be.
    """
    boards = [bd for bd in (overview.get("leaderboards") or []) if bd.get("rows")]

    def market_board(rows, currency):
        rows = [r for r in (rows or []) if r.get("symbol") and r.get("last") is not None][:10]
        fmt = _usd_html if currency == "USD" else _inr_html
        href = "/crypto/%s/" if currency == "USD" else "/stock/%s/"
        return rows, fmt, href

    market_boards = []
    g_rows, g_fmt, g_href = market_board(nse_live.get("gainers"), "INR")
    if g_rows:
        market_boards.append(("Today's NSE top gainers", "nse", g_rows, g_fmt, g_href))
    l_rows, l_fmt, l_href = market_board(nse_live.get("losers"), "INR")
    if l_rows:
        market_boards.append(("Today's NSE top losers", "nse", l_rows, l_fmt, l_href))
    a_rows, a_fmt, a_href = market_board(nse_live.get("quotes"), "INR")
    if a_rows:
        market_boards.append(("Most active NSE stocks by volume", "nse", a_rows, a_fmt, a_href))

    cc = [dict(c, symbol=c.get("symbol")) for c in (crypto_coins or []) if c.get("price_usd") is not None]
    by_cap = sorted([c for c in cc if c.get("market_cap_rank")], key=lambda c: c["market_cap_rank"])
    if by_cap:
        rows = [dict(symbol=c["symbol"], last=c["price_usd"], change_pct=c.get("change_pct_24h"))
                for c in by_cap[:10]]
        market_boards.append(("Top crypto by market cap", "crypto", rows, _usd_html, "/crypto/%s/"))
    by_chg = [c for c in cc if c.get("change_pct_24h") is not None]
    gainers_c = sorted(by_chg, key=lambda c: -c["change_pct_24h"])[:10]
    if gainers_c:
        rows = [dict(symbol=c["symbol"], last=c["price_usd"], change_pct=c["change_pct_24h"]) for c in gainers_c]
        market_boards.append(("Top crypto 24h gainers", "crypto", rows, _usd_html, "/crypto/%s/"))
    losers_c = sorted(by_chg, key=lambda c: c["change_pct_24h"])[:10]
    if losers_c:
        rows = [dict(symbol=c["symbol"], last=c["price_usd"], change_pct=c["change_pct_24h"]) for c in losers_c]
        market_boards.append(("Top crypto 24h losers", "crypto", rows, _usd_html, "/crypto/%s/"))

    canonical = "%s/leaderboards" % SITE_URL
    title = "Market Movers: NSE Gainers, Losers and Broker Stats | BrokerLens"
    description = ("Today's real NSE top gainers, losers and most-active stocks, plus crypto market-cap and "
                    "24h movers. Broker rankings by active clients, complaints and cost publish once that "
                    "data is live.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Movers", None)])
    graph = [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]
    for name, _kind, rows, fmt, href in market_boards:
        graph.append({
            "@type": "ItemList", "name": name,
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": r["symbol"],
                 "url": SITE_URL + (href % _esc(_stock_slug(r["symbol"]) if href.startswith("/stock") else r["symbol"].lower()))}
                for i, r in enumerate(rows)
            ],
        })
    jsonld = {"@context": "https://schema.org", "@graph": graph}
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html
    body += (
        '<h1 style="margin-top:16px">Movers</h1>'
        '<p class="muted" style="max-width:64ch">Real movers from NSE and the tracked crypto universe, as of '
        'the last data refresh. Every ranking states the metric it sorts on and where that metric comes from. '
        'We do not publish an overall &quot;best broker&quot;: that depends on what you trade.</p>'
    )

    def board_html(name, kind, rows, fmt, href):
        return (
            '<div class="card" style="margin-top:16px"><div class="card-head">'
            '<div><h3>%s %s</h3></div></div>'
            '<div class="table-scroll"><table class="data"><tbody>%s</tbody></table></div></div>'
        ) % (
            _esc(name), _prov_dot_html(kind),
            "".join(
                '<tr><td class="rank-cell">%d</td>'
                '<td><a href="%s">%s</a></td>'
                '<td class="right num">%s</td>'
                '<td class="right num %s">%s</td></tr>'
                % (i + 1,
                   href % (_esc(_stock_slug(r["symbol"])) if href.startswith("/stock") else _esc(r["symbol"].lower())),
                   _esc(r["symbol"]), fmt(r.get("last")),
                   _cls_class(r.get("change_pct")), _pct_html(r.get("change_pct")))
                for i, r in enumerate(rows)
            ),
        )

    if market_boards:
        body += '<div class="grid g2" style="margin-top:8px">'
        body += "".join(board_html(*b) for b in market_boards)
        body += "</div>"

    if not boards:
        body += '<div style="margin-top:16px">%s</div>' % _pending_html(
            "Broker rankings by active clients, complaints and cost",
            "Those sort on NSE member-wise client counts and SEBI Annexure-B complaint disclosures, which are "
            "being brought in from the primary sources now.")
    for i, bd in enumerate(boards):
        rows = bd.get("rows", [])[:10]
        body += (
            '<div class="card" style="margin-top:16px"><div class="card-head">'
            '<div><h3>%s</h3>%s</div><span class="badge">%s</span></div>'
            '<div class="grid g-main"><div class="chart-box"><canvas id="lb-%d"></canvas></div>'
            '<table class="data"><tbody>%s</tbody></table></div></div>'
        ) % (
            _esc(bd.get("title") or ""),
            ('<p class="xs faint" style="margin-top:4px;max-width:70ch">%s</p>' % _esc(bd["note"])) if bd.get("note") else "",
            _esc(bd.get("unit") or ""), i,
            "".join(
                '<tr><td class="rank-cell">%s</td><td><a href="/broker/%s/" data-link>%s</a></td>'
                '<td class="right num">%s</td></tr>'
                % (r.get("rank"), _esc(r["id"]), _esc(r["brand"]), _fmt_board_html(bd, r.get("value")))
                for r in rows
            ),
        )
    body += _APP_SHELL_FOOT
    dest_dir = os.path.join(ROOT, "site", "leaderboards")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("leaderboards page: written, %d market boards, %d broker boards" % (len(market_boards), len(boards)), "ok")


def _write_registry_directory(reg_rows):
    """A-Z browse pages for every SEBI-registered entity not one of the 48
    tracked in depth.

    /registry only ever hard-links the first 60 of ~1,700 entities (its
    default page of a client-side search widget) - everything past that sat
    behind a JS "Next" button with no href and no new URL, so ~96% of this
    page family had no on-site path a crawler could follow, only a
    sitemap.xml entry. Google's own Page Indexing report showed the result
    directly: "Discovered - currently not indexed" on the overwhelming
    majority of this family. Same fix as _write_stock_directory: a full,
    uncapped, server-rendered A-Z directory with a real <a href> to every
    entity.

    Nested under /registry/az/ rather than under /sebi-registry/ itself -
    that path already belongs to the ~1,700 individual entity pages, and
    _write_registry_pages() prunes anything under it that isn't a current
    entity slug on every run. A letter directory living in that same tree
    would get deleted by that prune the moment it wasn't a recognised slug."""
    groups = {}
    for r in reg_rows or []:
        name = (r.get("name") or "").strip()
        slug = (r.get("slug") or "").strip()
        if not name or not slug:
            continue
        letter = name[0].upper()
        letter = letter if letter.isalpha() else "0-9"
        groups.setdefault(letter, []).append((name, slug))

    letters = sorted(groups.keys(), key=lambda l: (l == "0-9", l))
    nav_html = "".join(
        '<a class="chip" href="/registry/az/%s/">%s</a>' % (_esc(slugify(l)), _esc(l)) for l in letters
    )

    written = 0
    for letter in letters:
        rows = sorted(groups[letter], key=lambda r: r[0])
        letter_slug = slugify(letter)
        canonical = "%s/registry/az/%s/" % (SITE_URL, letter_slug)
        title = "SEBI-Registered Entities Starting With %s | BrokerLens" % letter
        description = _esc(
            "%d SEBI-registered entities whose name starts with %s, each linking to its own registration "
            "page (registration number, category, exchange memberships and validity)." % (len(rows), letter)
        )[:300]
        list_html = "".join(
            '<a href="/sebi-registry/%s/">%s</a>' % (_esc(slug), _esc(name))
            for name, slug in rows
        )
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("SEBI registry", "/registry"), ("Browse A-Z", "/registry/az/"), (letter, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "ItemList", "name": title, "url": canonical,
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1, "url": "%s/sebi-registry/%s/" % (SITE_URL, slug), "name": name}
                        for i, (name, slug) in enumerate(rows)
                    ],
                },
                crumb_jsonld,
            ],
        }
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">SEBI-registered entities starting with %s</h1>' % _esc(letter)
            + '<p class="muted" style="max-width:70ch">%d registered entit%s. Each link goes to that '
              'entity\'s own registration page. <a href="/registry" data-link>Search the full register &rarr;</a></p>'
              % (len(rows), "y" if len(rows) == 1 else "ies")
            + '<div class="row-wrap" style="margin:16px 0">' + nav_html + '</div>'
            + '<div class="link-columns">' + list_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page lists SEBI's own recognised-intermediary register, grouped alphabetically by entity name.")}
        dest_dir = os.path.join(ROOT, "site", "registry", "az", letter_slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1

    total = sum(len(v) for v in groups.values())
    canonical = "%s/registry/az/" % SITE_URL
    title = "Browse SEBI-Registered Entities A-Z | BrokerLens"
    description = ("Every SEBI-registered entity BrokerLens has a registration page for (%d entities), "
                    "browsable alphabetically." % total)
    counts_html = "".join(
        '<a class="card" href="/registry/az/%s/" style="display:block;text-align:center"><h3>%s</h3>'
        '<p class="xs faint" style="margin-top:4px">%d entities</p></a>'
        % (_esc(slugify(l)), _esc(l), len(groups[l]))
        for l in letters
    )
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("SEBI registry", "/registry"), ("Browse A-Z", None)])
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical),
        "jsonld": json.dumps({"@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "name": title, "url": canonical}, crumb_jsonld]}, ensure_ascii=False),
    }
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Browse SEBI-registered entities</h1>'
        '<p class="muted" style="max-width:70ch">%d entities across %d letters, sourced from SEBI\'s own '
        'recognised-intermediary register. <a href="/registry" data-link>Search the full register instead &rarr;</a></p>'
        % (total, len(letters))
        + '<div class="grid g4" style="margin-top:16px">' + counts_html + '</div>'
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page indexes SEBI's own recognised-intermediary register alphabetically by entity name.")}
    dest_dir = os.path.join(ROOT, "site", "registry", "az")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)

    log("registry directory: %d letter pages written, %d entities linked" % (written, total), "ok")
    return letters


def _write_registry_landing_page(reg_rows, overview, registry_letters=None):
    """/registry is a client-side paginated search over up to ~1,700 entities
    (regState = {q:'', page:0, per:60} by default) - pre-rendering page one
    of that default, unfiltered view is a faithful, complete match for what
    a fresh visitor or a crawler would see before typing anything, without
    needing to fake pagination server-side for every possible query.

    The "Browse alphabetically" row below is the other half of the orphan-page
    fix in _write_registry_directory(): this page is the one already-indexed,
    highest-authority page in the whole registry family, so it is also the
    best available inbound link into the ~1,700 individual entity pages -
    every one of them is now two real <a> hops away from a page Google
    already trusts, not just a sitemap.xml entry."""
    per = 60
    page_rows = reg_rows[:per]
    total = len(reg_rows)
    canonical = "%s/registry" % SITE_URL
    title = "SEBI-Registered Brokers and Intermediaries | BrokerLens"
    description = ("Search every SEBI-registered broking and depository-participant entity: legal name, "
                    "registration number, city, exchange memberships and validity.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("SEBI registry", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html
    body += (
        '<h1 style="margin-top:16px">SEBI-registered intermediaries</h1>'
        '<p class="muted" style="max-width:70ch">Every registered entity we hold that is not one of the %d '
        'brokers tracked in depth (%s of them). Straight from SEBI\'s register: legal name, registration '
        'number, city, exchange memberships and validity. Nothing here is curated or scored.</p>'

        '%s'

        '<div class="card" style="margin-top:16px"><div class="row-wrap">'
        '<div class="grow" style="min-width:240px">'
        '<input type="search" id="reg-q" placeholder="Search by name, registration number or city&hellip;">'
        '</div>'
        '<span class="small faint" id="reg-meta">%s entities &middot; showing 1 to %d</span>'
        '<button class="btn btn-sm" id="reg-prev" disabled>&larr; Prev</button>'
        '<button class="btn btn-sm" id="reg-next"%s>Next &rarr;</button>'
        '</div></div>'

        '<div class="table-scroll" style="margin-top:16px"><table class="data">'
        '<thead><tr><th>Legal entity</th><th>Registration</th><th>City</th><th>Exchanges / registers</th>'
        '<th>Validity</th></tr></thead><tbody id="reg-body">%s</tbody></table></div>'
        '<p class="xs faint" style="margin-top:10px">%s Source: SEBI recognised-intermediary register. '
        '<a href="/sources" data-link>Lineage &rarr;</a></p>'
    ) % (
        overview.get("metadata", {}).get("broker_count", 0), _full_html(total),
        (
            '<p class="small" style="margin-top:12px">Browse alphabetically: '
            + " &middot; ".join(
                '<a href="/registry/az/%s/">%s</a>' % (_esc(slugify(l)), _esc(l))
                for l in registry_letters
            ) + '</p>'
        ) if registry_letters else "",
        _full_html(total), min(per, total), "" if total > per else " disabled",
        "".join(
            '<tr><td>%s%s</td><td class="num small">%s</td><td class="small">%s</td>'
            '<td class="xs muted">%s%s</td><td class="small">%s</td></tr>'
            % (
                ('<a href="/sebi-registry/%s/">%s</a>' % (_esc(e["slug"]), _esc(e["name"]))) if e.get("slug") else _esc(e.get("name") or ""),
                ('<div class="xs faint">trading as %s</div>' % _esc(e["trade_name"])) if e.get("trade_name") else "",
                _esc(e.get("reg") or "-"), _esc(e.get("city") or "-"),
                " &middot; ".join(_esc(x) for x in (e.get("exchanges") or [])[:3]),
                (" +%d" % (len(e["exchanges"]) - 3)) if len(e.get("exchanges") or []) > 3 else "",
                _esc(e.get("validity") or "-"),
            )
            for e in page_rows
        ),
        _prov_dot_html("sebi_registry"),
    )
    body += _APP_SHELL_FOOT
    dest_dir = os.path.join(ROOT, "site", "registry")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("registry landing page: written, %d of %d entities shown" % (len(page_rows), total), "ok")


def _write_compare_page(overview):
    """/compare?b=id1,id2 is genuinely arbitrary (any 2-4 of 48 brokers), so
    there is no single "default comparison" worth pre-rendering - but the
    bare /compare (no query string) has one real, complete default state in
    the JS version: the broker picker with nothing selected yet. That's what
    gets prerendered; app.js reads any ?b= query client-side same as today."""
    brokers = sorted(overview.get("brokers") or [], key=lambda b: -(b.get("clients") or 0))
    canonical = "%s/compare" % SITE_URL
    title = "Compare Indian Stock Brokers Side by Side | BrokerLens"
    description = ("Put Indian stock brokers head to head on clients, complaints, regulatory standing and "
                    "real cost, using regulator-sourced figures.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Compare", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html
    body += (
        '<h1 style="margin-top:16px">Compare brokers</h1>'
        '<p class="muted">Pick two to four brokers to see them side by side on clients, growth, complaints, '
        'reliability and cost.</p>'
        '<div class="card" style="max-width:420px;margin-top:16px">'
        '<label for="cmp-add">Add a broker</label>'
        '<select id="cmp-add"><option value="">Select&hellip;</option>%s</select></div>'
    ) % "".join('<option value="%s">%s</option>' % (_esc(b["id"]), _esc(b["brand"])) for b in brokers)
    body += _APP_SHELL_FOOT
    dest_dir = os.path.join(ROOT, "site", "compare")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("compare page: written", "ok")


def _dir_row_html(b):
    """Python port of pages.js's dirRow() - the hasClients=true table row.
    faintDash matches its JS namesake: a dash reading at full text weight
    down a whole column looks broken, not "not published yet"."""
    def faint_dash(s):
        return '<span class="faint">-</span>' if s == "-" else s
    return (
        '<tr class="%s"><td class="rank-cell">%s</td>'
        '<td><div class="bname">%s<span>%s</span> %s</div>'
        '<div class="xs faint">%s%s</div></td>'
        '<td class="right num">%s</td>'
        '<td class="right num %s">%s</td>'
        '<td><canvas class="spark" aria-hidden="true"></canvas></td>'
        '<td class="right num">%s</td>'
        '<td class="right num">%s</td>'
        '<td class="right num">%s</td>'
        '<td class="small">%s</td></tr>'
    ) % (
        "promoted" if b.get("tier") == "featured" else "",
        faint_dash(_full_html(b.get("rank"))) if b.get("rank") is not None else '<span class="faint">-</span>',
        _mark_html(b["id"], b["brand"]), '<a href="/broker/%s/" data-link>%s</a>' % (_esc(b["id"]), _esc(b["brand"])),
        _broker_badge_html(b),
        _esc(b.get("hq") or ""), (" &middot; est. %s" % b["founded"]) if b.get("founded") else "",
        faint_dash(_count_html(b.get("clients"))),
        _cls_class(b.get("clients_yoy")), faint_dash(_pct_html(b.get("clients_yoy"))),
        faint_dash("%.2f" % b["complaints_per_10k"] if b.get("complaints_per_10k") is not None else "-"),
        faint_dash("%.1f" % b["reliability"] if b.get("reliability") is not None else "-"),
        _inr_html(b["cost"], decimals=0) if b.get("cost") is not None else '<span class="faint">unverified</span>',
        _esc(TYPE_LABEL.get(b.get("type"), b.get("type") or "")),
    )


def _dir_row_simple_html(b):
    """Python port of pages.js's dirRowSimple() - the hasClients=false row
    shape (see the /brokers hasClients fix in pages.js for why this exists:
    a wall of dashes reads as broken data, not "not published yet")."""
    return (
        '<tr class="%s"><td><div class="bname">%s<span>%s</span> %s</div>'
        '<div class="xs faint">%s%s</div></td>'
        '<td class="small num">%s</td><td class="small">%s</td>'
        '<td class="xs muted">%s</td><td class="small">%s</td></tr>'
    ) % (
        "promoted" if b.get("tier") == "featured" else "",
        _mark_html(b["id"], b["brand"]), '<a href="/broker/%s/" data-link>%s</a>' % (_esc(b["id"]), _esc(b["brand"])),
        _broker_badge_html(b),
        _esc(b.get("hq") or ""), (" &middot; est. %s" % b["founded"]) if b.get("founded") else "",
        _esc(b.get("sebi_reg_no") or "-"),
        _esc(TYPE_LABEL.get(b.get("type"), b.get("type") or "-")),
        " &middot; ".join(_esc(SEGMENT_LABEL.get(s, s)) for s in (b.get("segments") or [])) or "-",
        _esc(b.get("hq") or "-"),
    )


def _write_brokers_page(overview):
    """The dedicated /brokers directory: full 48-row table, hasClients-aware
    (matching the fix in pages.js's brokers()/dirRow()/dirRowSimple() - see
    that change for why a data-heavy table isn't safe to always render).
    Real content on first paint; app.js re-renders the same live, sortable,
    filterable table moments later, unaffected by any of this."""
    meta = overview.get("metadata") or {}
    has_clients = bool(meta.get("data_status", {}).get("active_clients"))
    brokers = overview.get("brokers") or []
    rows_sorted = sorted(brokers, key=lambda b: -(b.get("clients") or 0)) if has_clients else \
        sorted(brokers, key=lambda b: b.get("brand") or "")

    canonical = "%s/brokers" % SITE_URL
    title = "All Indian Stock Brokers, Compared | BrokerLens"
    description = ("Every Indian stock broker we track, side by side: active clients, growth, complaint rate, "
                    "reliability and monthly cost, from primary regulator and exchange sources.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Brokers", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList", "name": title, "url": canonical,
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "url": "%s/broker/%s/" % (SITE_URL, b["id"]), "name": b["brand"]}
                    for i, b in enumerate(rows_sorted)
                ],
            },
            crumb_jsonld,
        ],
    }
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html
    body += _sample_banner_html(meta)
    body += (
        '<div class="spread" style="margin-top:16px"><div><h1>Brokers</h1>'
        '<p class="muted small">%d brokers tracked in depth. Looking for a smaller firm? '
        '<a href="/registry" data-link>Search all %s SEBI-registered entities</a>.</p></div>'
        '<a class="btn" href="/compare" data-link>Compare selected &rarr;</a></div>'

        '<div class="grid g-main" style="margin-top:16px"><div>'
        '<div class="card"><div class="row-wrap">'
        '<div class="grow" style="min-width:220px"><input type="search" id="dir-q" '
        'placeholder="Search broker or legal entity&hellip;"></div>'
        '<div class="chips">%s%s</div>'
        '<span class="small faint" id="dir-count">%d of %d</span></div></div>'

        '<div class="table-scroll" style="margin-top:16px"><table class="data">'
        '<thead><tr>%s</tr></thead><tbody id="dir-body">%s</tbody></table></div>'
        '<p class="xs faint" style="margin-top:10px">%s</p>'
        '<p class="xs faint" style="margin-top:6px">Dedicated category pages: %s &nbsp;|&nbsp; %s</p>'
        '</div><div class="stack">%s%s</div></div>'
    ) % (
        meta.get("broker_count", 0), _full_html(overview.get("registry_count")),
        "".join('<button class="chip" data-filter="type:%s">%s</button>' % (_esc(k), _esc(v)) for k, v in TYPE_LABEL.items()),
        "".join('<button class="chip" data-filter="segment:%s">%s</button>' % (_esc(k), _esc(v)) for k, v in SEGMENT_LABEL.items()),
        len(rows_sorted), len(brokers),
        (
            '<th data-tip="Rank by active clients. A dash means the client count is not available yet.">#</th>'
            '<th class="sortable sorted" data-sort="brand" data-tip="Consumer brand.">Broker <span class="arrow">&#8597;</span></th>'
            '<th class="sortable right sorted" data-sort="clients" data-tip="Unique clients who placed at least one trade in the last 12 months.">Active clients <span class="arrow">&#8597;</span></th>'
            '<th class="sortable right" data-sort="clients_yoy" data-tip="Change in active clients over the last 12 months.">12-month <span class="arrow">&#8597;</span></th>'
            '<th data-tip="Active client count month by month.">Trend</th>'
            '<th class="sortable right" data-sort="complaints_per_10k" data-tip="Investor complaints per 10,000 active clients.">Complaints /10k <span class="arrow">&#8597;</span></th>'
            '<th class="sortable right tip-end" data-sort="reliability" data-tip="BrokerLens composite score out of 100.">Reliability <span class="arrow">&#8597;</span></th>'
            '<th class="sortable right tip-end" data-sort="cost" data-tip="Estimated brokerage for a fixed monthly basket.">Cost /month <span class="arrow">&#8597;</span></th>'
            '<th class="tip-end" data-tip="Business model.">Type</th>'
            if has_clients else
            '<th class="sortable sorted" data-sort="brand" data-tip="Consumer brand.">Broker <span class="arrow">&#8597;</span></th>'
            '<th data-tip="SEBI registration number for this broker\'s stock-broking licence.">Registration</th>'
            '<th class="tip-end" data-tip="Business model.">Type</th>'
            '<th data-tip="Exchange segments this broker is registered for.">Segments</th>'
            '<th data-tip="City of the broker\'s registered head office.">Head office</th>'
        ),
        "".join((_dir_row_html if has_clients else _dir_row_simple_html)(b) for b in rows_sorted),
        (
            '%s exchange/regulator sourced &middot; %s curated or broker-supplied &middot; %s sample pending '
            'ingest. Cost is a fixed basket of trades (see <a href="/methodology" data-link>methodology</a>).'
            % (_prov_dot_html("nse"), _prov_dot_html("curated"), _prov_dot_html("sample"))
            if has_clients else
            '%s Legal name, registration and segments come straight from SEBI\'s own register. Active-client '
            'counts, complaint records and cost are not yet available for these brokers. They will be shown only '
            'once traced to NSE and SEBI\'s own disclosures, never estimated. See '
            '<a href="/methodology" data-link>methodology</a>.' % _prov_dot_html("sebi_registry")
        ),
        " &middot; ".join('<a href="/brokers-by/type/%s/">%s</a>' % (k.replace("_", "-"), _esc(v)) for k, v in TYPE_LABEL.items()),
        " &middot; ".join('<a href="/brokers-by/segment/%s/">%s</a>' % (k.replace("_", "-"), _esc(v)) for k, v in SEGMENT_LABEL.items()),
        affiliateBanner_html(), fivepaisaBanner_html(),
    )
    body += _APP_SHELL_FOOT
    dest_dir = os.path.join(ROOT, "site", "brokers")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("brokers page: written, %d brokers, hasClients=%s" % (len(rows_sorted), has_clients), "ok")


def _calc_leg_cost(plan, turnover, trades):
    """Python port of the leg() closure inside pages.js's calculator() -
    per-leg brokerage for one basket component (delivery/intraday/F&O)."""
    if not plan or not trades:
        return 0.0
    per_order = (turnover / trades) * plan["pct_of_turnover"] / 100 if plan.get("pct_of_turnover") is not None else 0.0
    flat = plan.get("flat_per_order")
    v = max(per_order, flat) if (flat is not None and plan.get("pct_of_turnover") is not None) else \
        (flat if flat is not None else per_order)
    if plan.get("cap_per_order") is not None:
        v = min(v, plan["cap_per_order"])
    return v * trades


def _fmt_plan_html(plan):
    """Python port of pages.js's fmtPlan()."""
    if not plan:
        return "-"
    bits = []
    if plan.get("flat_per_order") is not None:
        bits.append("Free" if plan["flat_per_order"] == 0 else "&#8377;%s/order" % plan["flat_per_order"])
    if plan.get("pct_of_turnover") is not None:
        bits.append("%s%%" % plan["pct_of_turnover"])
    if plan.get("cap_per_order") is not None:
        bits.append("max &#8377;%s" % plan["cap_per_order"])
    return _esc(", ".join(bits)) if bits else "-"


# Default example basket, identical to the pre-filled <input value> attributes
# in pages.js's calculator() form - this IS the state a fresh visitor sees, so
# it is what gets pre-computed for first paint too.
_CALC_DEFAULT_BASKET = {
    "delivery_buy_value": 50000, "delivery_trades": 4,
    "intraday_turnover": 100000, "intraday_trades": 10,
    "fno_premium_turnover": 200000, "fno_trades": 10,
}


def _write_calculator_tool_page(built):
    """/calculator (the interactive brokerage-cost tool, distinct from the
    informational /calculators/<slug>/ pages) - pre-renders the same default
    basket the JS form is pre-filled with, so first paint already shows a
    real, correct result table instead of an empty form. Matches
    calculator()'s own "nothing to price yet" gate exactly: production has
    zero brokers with verified charges today, so this renders the pending
    notice, not a table of computed zeros."""
    priced = [b for b in built if (b.get("cost") or {}).get("monthly_total") is not None]
    canonical = "%s/calculator" % SITE_URL
    title = "Brokerage Cost Calculator | BrokerLens"
    description = ("Work out what a month of your actual trading costs at each Indian broker, using their "
                    "published charges.")[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Calculator", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": canonical, "description": description},
        crumb_jsonld,
    ]}
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html

    if not priced:
        body += (
            '<h1 style="margin-top:16px">Brokerage cost calculator</h1>'
            '<p class="muted" style="max-width:70ch">Work out what a month of your actual trading costs at '
            'each broker.</p>'
            '<div style="margin-top:16px">%s</div>'
            '<p class="small muted" style="margin-top:16px">In the meantime, the '
            '<a href="/brokers" data-link>broker directory</a> and the '
            '<a href="/registry" data-link>SEBI register</a> carry regulator-sourced facts on every firm.</p>'
        ) % _pending_html(
            "Broker charges",
            "Charges are published only where they can be traced to the broker's own disclosed rate card. "
            "Until those are verified, we show nothing rather than an estimate you might act on.")
    else:
        basket = _CALC_DEFAULT_BASKET
        rows = []
        for b in priced:
            c = b.get("charges") or {}
            total = (
                _calc_leg_cost(c.get("delivery"), basket["delivery_buy_value"], basket["delivery_trades"])
                + _calc_leg_cost(c.get("intraday"), basket["intraday_turnover"], basket["intraday_trades"])
                + _calc_leg_cost(c.get("fno"), basket["fno_premium_turnover"], basket["fno_trades"])
                + (c.get("demat_amc_annual") or 0) / 12
            )
            rows.append((b["id"], b["profile"]["brand"], total))
        rows.sort(key=lambda r: r[2])
        max_total = rows[-1][2] if rows else 0
        body += (
            '<h1 style="margin-top:16px">What will a broker actually cost you?</h1>'
            '<p class="muted" style="max-width:64ch">Enter a typical month of your own trading. We price it '
            'against every broker that has published verified charges, cheapest first.</p>'
            '<div class="grid g-main" style="margin-top:16px">'
            '<form class="card" id="calc-form"><div class="card-title">Your typical month</div>'
            '<div class="grid g2" style="margin-top:12px">'
            '<div class="field"><label for="dv">Delivery buy value (&#8377;)</label>'
            '<input id="dv" name="delivery_value" type="number" min="0" step="1000" value="%d"></div>'
            '<div class="field"><label for="dt">Delivery orders</label>'
            '<input id="dt" name="delivery_trades" type="number" min="0" value="%d"></div>'
            '<div class="field"><label for="it">Intraday turnover (&#8377;)</label>'
            '<input id="it" name="intraday_turnover" type="number" min="0" step="10000" value="%d"></div>'
            '<div class="field"><label for="itr">Intraday orders</label>'
            '<input id="itr" name="intraday_trades" type="number" min="0" value="%d"></div>'
            '<div class="field"><label for="ft">F&amp;O premium turnover (&#8377;)</label>'
            '<input id="ft" name="fno_turnover" type="number" min="0" step="10000" value="%d"></div>'
            '<div class="field"><label for="ftr">F&amp;O orders</label>'
            '<input id="ftr" name="fno_trades" type="number" min="0" value="%d"></div></div>'
            '<button class="btn btn-primary" type="submit" style="margin-top:12px">Recalculate</button></form>'
            '<div id="calc-out"><div class="table-scroll"><table class="data">'
            '<thead><tr><th>#</th><th>Broker</th><th class="right">Your monthly cost</th>'
            '<th class="right">Per year</th><th></th></tr></thead><tbody>%s</tbody></table></div>'
            '<p class="xs faint" style="margin-top:10px">Brokerage plus amortised AMC only. Statutory charges '
            'are excluded because they are identical at every broker for the same trade. Only brokers with '
            'verified published pricing appear (%d of %d today).</p></div></div>'
        ) % (
            basket["delivery_buy_value"], basket["delivery_trades"], basket["intraday_turnover"],
            basket["intraday_trades"], basket["fno_premium_turnover"], basket["fno_trades"],
            "".join(
                '<tr><td class="rank-cell">%d</td><td><div class="bname">%s%s</div></td>'
                '<td class="right num">%s</td><td class="right num">%s</td>'
                '<td class="right"><div class="minibar"><i style="width:%d%%"></i></div></td></tr>'
                % (i + 1, _mark_html(bid, brand, 22), '<a href="/broker/%s/" data-link>%s</a>' % (_esc(bid), _esc(brand)),
                   _inr_html(total, decimals=0), _inr_html(total * 12, decimals=0),
                   round(total / max_total * 100) if max_total else 0)
                for i, (bid, brand, total) in enumerate(rows)
            ),
            len(priced), len(built),
        )
    body += _APP_SHELL_FOOT
    dest_dir = os.path.join(ROOT, "site", "calculator")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("calculator page: written, %d priced brokers" % len(priced), "ok")


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_html(m):
    """Python port of store.js's month()."""
    if not m:
        return "-"
    y, mm = str(m).split("-")
    try:
        name = _MONTH_NAMES[int(mm) - 1]
    except (ValueError, IndexError):
        name = mm
    return "%s %s" % (name, y)


def _stat_tile_html(label, value, sub, extra=""):
    """Python port of pages.js's statTile()."""
    return (
        '<div class="card stat"><div class="stat-label">%s %s</div><div class="stat-value">%s</div>%s</div>'
    ) % (_esc(label), extra, value, ('<div class="stat-sub">%s</div>' % sub) if sub else "")


def _ad_slot_html(overview, placement):
    """Python port of pages.js's adSlot(). JS picks a random featured broker
    per render; deterministically picking the first here (matching
    dirRow()'s use of "featured" ordering elsewhere) avoids a content swap
    the instant app.js re-renders with its own random pick - featured is
    currently always empty in production anyway (no paid placements exist
    yet), so this renders '' either way today."""
    featured = [b for b in (overview.get("brokers") or []) if b.get("tier") == "featured"]
    if not featured:
        return ""
    b = featured[0]
    return (
        '<div class="ad-slot"><div class="ad-tag">Sponsored: %s</div>'
        '<div class="row" style="margin-top:8px">%s<div class="grow">'
        '<div style="font-weight:600">%s</div><div class="xs muted">%s active clients &middot; %s</div></div>'
        '<a class="btn btn-sm btn-primary" href="/broker/%s/" data-link>View</a></div></div>'
    ) % (
        _esc(placement), _mark_html(b["id"], b["brand"], 34), _esc(b["brand"]),
        _count_html(b.get("clients")), _esc(TYPE_LABEL.get(b.get("type"), b.get("type") or "")), _esc(b["id"]),
    )


def _leader_card_html(bd):
    """Python port of pages.js's leaderCard()."""
    return (
        '<div class="card"><div class="card-title">%s</div>'
        '<table class="data" style="margin-top:8px"><tbody>%s</tbody></table></div>'
    ) % (
        _esc(bd.get("title") or ""),
        "".join(
            '<tr><td class="rank-cell">%s</td><td><a href="/broker/%s/" data-link>%s</a></td>'
            '<td class="right num">%s</td></tr>'
            % (r.get("rank"), _esc(r["id"]), _esc(r["brand"]), _fmt_board_html(bd, r.get("value")))
            for r in (bd.get("rows") or [])[:6]
        ),
    )


def _prerender_home(overview):
    """Ports pages.js's home() to Python and injects the result into
    site/index.html's <main id="app">, replacing the empty loading-skeleton
    placeholder that was there before.

    This is the single highest-impact fix in this whole batch: a real-browser
    trace showed the skeleton-to-real-content swap alone caused a Cumulative
    Layout Shift of 0.54-0.58 (Google's "poor" threshold starts at 0.25) on
    the single highest-traffic page on the site, because the footer jumped
    ~1,437px the instant the real content replaced 3 tiny skeleton cards.
    Real content on first paint eliminates that swap almost entirely - app.js
    still re-renders home() moments later (same content, live ticker/chart
    data), but onto a page that's already the right shape, not a blank one.

    <canvas> chart elements are left empty (charts need JS to draw) but are
    otherwise positioned exactly where the live version puts them, so the
    residual shift is bounded to a canvas's own height, not the whole page.
    """
    meta = overview.get("metadata") or {}
    agg = overview.get("aggregates") or {}
    m = overview.get("market") or {}
    conc = agg.get("concentration") or {}
    has_clients = bool(meta.get("data_status", {}).get("active_clients"))
    brokers = overview.get("brokers") or []
    top = (sorted(brokers, key=lambda b: -(b.get("clients") or 0))[:12] if has_clients
           else sorted(brokers, key=lambda b: b.get("brand") or "")[:12])
    nifty = ((m.get("nse") or {}).get("indices") or [{}])[0]
    breadth = (m.get("nse") or {}).get("breadth")
    bse_delivery = m.get("bse_delivery") or []
    delivery = bse_delivery[-1] if bse_delivery else None

    html = _sample_banner_html(meta)
    html += (
        '<section class="pitch" style="margin-top:16px">'
        '<h1 style="max-width:22ch">Every Indian stock broker, measured the same way.</h1>'
        '<p class="muted" style="max-width:62ch;margin-top:12px">%d brokers tracked in depth and %s '
        'SEBI-registered entities on file. %s</p>'
        '<div class="row-wrap" style="margin-top:18px">'
        '<a class="btn btn-primary" href="/brokers" data-link>Browse brokers</a>'
        '<a class="btn" href="/compare" data-link>Compare side by side</a>%s</div></section>'
    ) % (
        meta.get("broker_count", 0), _full_html(overview.get("registry_count")),
        ("Active clients, market share, investor-complaint records, regulatory registrations and real cost, "
         "assembled from NSE, BSE and SEBI primary disclosures, not from marketing pages." if has_clients else
         "Legal entities, SEBI registration numbers, exchange memberships and regulatory standing, taken "
         "straight from the regulator's own register rather than from marketing pages."),
        ('<a class="btn" href="/calculator" data-link>What will it cost me?</a>' if has_clients else
         '<a class="btn" href="/registry" data-link>Search the SEBI register</a>'),
    )

    if has_clients:
        tiles = (
            _stat_tile_html(
                "Total active clients", _count_html(agg.get("total_active_clients")),
                '<span class="%s">%s</span> year on year' % (_cls_class(agg.get("total_yoy_pct")), _pct_html(agg.get("total_yoy_pct"))),
                _prov_dot_html("sample" if (meta.get("sample_data") or {}).get("active_clients") else "nse"))
            + _stat_tile_html(
                "Top 5 brokers hold", _pct_html(conc.get("top5_pct"), sign=False),
                "top 1 is %s &middot; top 10 is %s" % (_pct_html(conc.get("top1_pct"), sign=False), _pct_html(conc.get("top10_pct"), sign=False)))
            + _stat_tile_html("Market concentration", "%.0f" % (agg.get("hhi") or 0),
                               "HHI, above 1,500 is moderately concentrated")
        )
    else:
        tiles = (
            _stat_tile_html("Brokers profiled", str(meta.get("broker_count", 0)),
                             "matched to the SEBI register", _prov_dot_html("sebi_registry"))
            + _stat_tile_html("Entity records verified", str(meta.get("verified_count", 0)),
                               "legal name and registration confirmed", _prov_dot_html("sebi_registry"))
            + _stat_tile_html("Defaulter records on file", _count_html(overview.get("defaulter_count") or 0),
                               "firms declared defaulter or expelled", _prov_dot_html("sebi_registry"))
        )
    tiles += _stat_tile_html("SEBI-registered on file", _count_html(overview.get("registry_count")),
                              "%s tracked brokers matched to the register" % meta.get("verified_count", 0),
                              _prov_dot_html("sebi_registry"))
    html += '<div class="grid g4" style="margin-top:24px">%s</div>' % tiles

    if has_clients:
        total_series = agg.get("total_series") or []
        html += (
            '<div class="grid g-main" style="margin-top:16px">'
            '<div class="card"><div class="card-head"><div>'
            '<div class="card-title">Total active clients across tracked brokers</div>'
            '<div class="xs faint">Monthly, %d months to %s</div></div></div>'
            '<div class="chart-box"><canvas id="mkt-total" height="200"></canvas></div></div>'
            '<div class="card"><div class="card-title">Share of active clients</div>'
            '<div class="row" style="margin-top:12px;align-items:center;gap:16px">'
            '<canvas id="mkt-share" width="168" height="168"></canvas></div>'
            '<div class="legend" id="share-legend" style="margin-top:12px"></div></div></div>'
        ) % (len(total_series), _month_html(total_series[-1][0] if total_series else None))
    else:
        html += '<div style="margin-top:16px">%s</div>' % _pending_html(
            "Client and complaint statistics",
            "NSE publishes member-wise active-client counts monthly, and every broker must publish its "
            "complaint record in SEBI's Annexure-B format. Both are being brought in from those primary sources.")

    table_head = (
        '<th>#</th><th>Broker</th><th class="right">Active clients</th><th class="right">Share</th>'
        '<th class="right">12-month</th><th>Trend</th><th class="right">Complaints /10k</th>'
        '<th class="right">Reliability</th>'
        if has_clients else
        '<th>Broker</th><th>Registration</th><th>Type</th><th>Segments</th><th>Head office</th>'
    )

    def home_row(b):
        if has_clients:
            return (
                '<tr><td class="rank-cell">%s</td><td><div class="bname">%s<span>%s</span> %s</div></td>'
                '<td class="right num">%s</td><td class="right num">%s</td>'
                '<td class="right num %s">%s</td><td><canvas class="spark" aria-hidden="true"></canvas></td>'
                '<td class="right num">%s</td><td class="right num">%s</td></tr>'
            ) % (
                _full_html(b.get("rank")), _mark_html(b["id"], b["brand"]),
                '<a href="/broker/%s/" data-link>%s</a>' % (_esc(b["id"]), _esc(b["brand"])), _broker_badge_html(b),
                _count_html(b.get("clients")), _pct_html(b.get("share"), sign=False),
                _cls_class(b.get("clients_yoy")), _pct_html(b.get("clients_yoy")),
                "%.2f" % b["complaints_per_10k"] if b.get("complaints_per_10k") is not None else "-",
                "%.1f" % b["reliability"] if b.get("reliability") is not None else "-",
            )
        return (
            '<tr><td><div class="bname">%s<span>%s</span> %s</div></td>'
            '<td class="small num">%s</td><td class="small">%s</td>'
            '<td class="xs muted">%s</td><td class="small">%s</td></tr>'
        ) % (
            _mark_html(b["id"], b["brand"]), '<a href="/broker/%s/" data-link>%s</a>' % (_esc(b["id"]), _esc(b["brand"])),
            _broker_badge_html(b), _esc(b.get("sebi_reg_no") or "-"),
            _esc(TYPE_LABEL.get(b.get("type"), b.get("type") or "-")),
            " &middot; ".join(_esc(SEGMENT_LABEL.get(s, s)) for s in (b.get("segments") or [])) or "-",
            _esc(b.get("hq") or "-"),
        )

    html += (
        '<div class="grid g-main" style="margin-top:16px"><div>'
        '<div class="section-title"><h2>%s</h2><a class="small" href="/brokers" data-link>All %d &rarr;</a></div>'
        '<div class="table-scroll"><table class="data"><thead><tr>%s</tr></thead>'
        '<tbody>%s</tbody></table></div></div>'
        '<div class="stack">%s%s%s<div class="card"><div class="card-title">Market snapshot</div>'
        '<dl class="kv" style="margin-top:10px">%s%s%s%s%s</dl>'
        '<div class="xs faint" style="margin-top:10px">%s Live from NSE and BSE at last build.</div></div>%s</div></div>'
    ) % (
        "Largest brokers by active clients" if has_clients else "Brokers on the SEBI register",
        meta.get("broker_count", 0), table_head, "".join(home_row(b) for b in top),
        _ad_slot_html(overview, "homepage rail"), affiliateBanner_html(), fivepaisaBanner_html(),
        ('<dt>NIFTY 50</dt><dd class="num">%s <span class="%s">%s</span></dd>' % (
            _full_html(nifty.get("last")), _cls_class(nifty.get("change_pct")), _pct_html(nifty.get("change_pct")))
         if nifty.get("last") is not None else ""),
        ('<dt>NSE breadth</dt><dd class="num"><span class="up">%s &#9650;</span> / <span class="down">%s &#9660;</span></dd>' % (
            _full_html(breadth.get("advances")), _full_html(breadth.get("declines")))
         if breadth else ""),
        ('<dt>BSE delivery</dt><dd class="num">%.2f%%</dd>' % delivery["delivery_pct"] if delivery else ""),
        ('<dt>NSE symbols</dt><dd class="num">%s</dd>' % _full_html((m.get("universe") or {}).get("nse_symbols"))
         if (m.get("universe") or {}).get("nse_symbols") else ""),
        ('<dt>NSE CM turnover</dt><dd class="num">%s</dd>' % _inr_html(m["turnover"][-1]["turnover_inr"])
         if m.get("turnover") else ""),
        _prov_dot_html("nse"),
        ('<div class="card"><div class="card-title">BSE delivery % (investors vs churn)</div>'
         '<div class="chart-box"><canvas id="bse-delivery" height="160"></canvas></div></div>'
         if bse_delivery else ""),
    )

    boards = (overview.get("leaderboards") or [])[:3]
    html += (
        '<div class="section-title"><h2>Movers</h2><a class="small" href="/leaderboards" data-link>All movers &rarr;</a></div>'
        '<div class="grid g3">%s</div>'
    ) % "".join(_leader_card_html(bd) for bd in boards)

    index_path = os.path.join(ROOT, "site", "index.html")
    try:
        current = open(index_path, encoding="utf-8").read()
    except OSError:
        return
    new_html = re.sub(
        r'(<main id="app" class="wrap" style="padding-top:24px;padding-bottom:24px">).*?(</main>)',
        lambda m2: m2.group(1) + html + m2.group(2),
        current, count=1, flags=re.S,
    )
    if new_html != current:
        _write_text(index_path, new_html)
    log("home page: prerendered into index.html, hasClients=%s" % has_clients, "ok")


def _write_calculator_hub():
    """A hub page at /calculators/ listing every calculator plus the SPA's own
    brokerage cost calculator, so "Calculators" in the nav lands on a real
    index instead of jumping straight into one arbitrarily-chosen tool - the
    same gap a "Compare" nav item pointing at one specific broker pair would
    be. Also the natural place to put the brokerage cost calculator (a
    different, SPA-only tool at the sibling /calculator route) side by side
    with the 13 static financial calculators, since neither page previously
    linked to the other.

    Path is /calculators/ (bare index, sibling to the per-calculator
    directories already written by _write_calculator_pages) - checked against
    the live SPA route list before use (nothing named "calculators" exists
    there; only the singular "/calculator" does).
    """
    canonical = "%s/calculators/" % SITE_URL
    title = "Financial Calculators: SIP, PPF, GST, EMI, Retirement | BrokerLens"
    description = ("Free financial calculators for SIP, lumpsum, step-up SIP, SWP, PPF, retirement, "
                    "inflation, EMI, CAGR, compound interest, simple interest, capital gains tax and GST, "
                    "each using the standard published formula.")[:300]

    cards_html = "".join(
        '<a class="card" href="/calculators/%s/" style="display:block">'
        '<h3 style="font-size:15px">%s</h3>'
        '<p class="small muted" style="margin-top:6px">%s</p></a>'
        % (_esc(c["slug"]), _esc(c["h1"]), _esc(c["description"]))
        for c in CALCULATORS
    )
    faq_html = "".join(
        '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
        for q, a in _CALC_HUB_FAQS
    )
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Calculators", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage", "name": title, "url": canonical,
                "hasPart": [
                    {"@type": "WebApplication", "name": c["h1"], "url": "%s/calculators/%s/" % (SITE_URL, c["slug"])}
                    for c in CALCULATORS
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in _CALC_HUB_FAQS
                ],
            },
            crumb_jsonld,
        ],
    }

    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += (
        crumb_html
        + '<h1 style="margin-top:0">Financial calculators</h1>'
        '<p class="muted" style="max-width:68ch">Thirteen calculators covering investing, saving, loans '
        'and tax, each built on the standard formula the calculation is actually based on, with the '
        'formula itself shown on the page.</p>'

        '<h2 style="margin-top:28px;font-size:18px">Compare broker charges instead</h2>'
        '<a class="card" href="/calculator" style="display:block;max-width:520px">'
        '<h3 style="font-size:15px">Brokerage cost calculator</h3>'
        '<p class="small muted" style="margin-top:6px">Work out what a month of your actual trading '
        'costs at each Indian broker, using their published charges.</p></a>'

        '<h2 style="margin-top:28px;font-size:18px">Investing and savings</h2>'
        '<div class="grid g3">' + cards_html + '</div>'

        + ('<h2 style="margin-top:32px;font-size:18px">Frequently asked questions</h2>'
           '<div style="max-width:68ch">%s</div>' % faq_html)
    )
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page links to calculators that each run a standard, published financial formula entirely "
        "in your browser; it is not generated from any BrokerLens-ingested regulator or exchange dataset.")}

    dest_dir = os.path.join(ROOT, "site", "calculators")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("calculator hub: written", "ok")


def _write_sitemap(built, reg_rows=None, hub_groups=None, companies=None, indices=None, etfs=None,
                    fund_slugs=None, report_slugs=None, calc_slugs=None, stock_letters=None, amc_slugs=None,
                    crypto_slugs=None, ipo_records=None, registry_letters=None):
    _require_site_url()
    urls = ["/", "/brokers", "/leaderboards", "/compare", "/calculator", "/calculators",
            "/registry", "/algo", "/methodology", "/sources", "/stocks", "/funds-by", "/etfs", "/crypto",
            "/ipo", "/ipo/archive", "/about", "/contact", "/privacy-policy", "/terms-of-service"]
    # Trailing slash: /broker/<id>/ is now a real static directory on disk (see
    # _write_broker_pages), and every static host 301s the no-slash form to add
    # it. The sitemap should point straight at the canonical form rather than
    # make every crawl hop through a redirect first.
    urls += ["/broker/%s/" % b["id"] for b in built]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = "".join(
        "<url><loc>%s%s</loc><lastmod>%s</lastmod><changefreq>daily</changefreq></url>"
        % (SITE_URL, u, today) for u in urls
    )
    # The registry long tail rarely changes (a SEBI registration is stable
    # month to month), so these get a lower changefreq than the daily-moving
    # broker pages rather than falsely claiming they're refreshed as often.
    body += "".join(
        "<url><loc>%s/sebi-registry/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
        % (SITE_URL, r["slug"], today) for r in (reg_rows or []) if r.get("slug")
    )
    for dim, key, _label, _rows in (hub_groups or []):
        slug = slugify(key.replace("_", "-"))
        if slug:
            body += ("<url><loc>%s/brokers-by/%s/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                     % (SITE_URL, dim, slug, today))
    # The dimension index itself (e.g. /brokers-by/type/) is a real static
    # page too (see _write_broker_hub_pages) - only emitted when that
    # dimension actually has at least one group, matching what gets written.
    hub_dims_present = {d for d, _, _, _ in (hub_groups or [])}
    for dim in ("type", "segment", "city"):
        if dim in hub_dims_present:
            body += ("<url><loc>%s/brokers-by/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                     % (SITE_URL, dim, today))
    # A company's own listing facts (ISIN, listing date, face value) almost
    # never change, so these get the lowest changefreq of anything published.
    for c in (companies or []):
        slug = _stock_slug(c.get("symbol"))
        if slug:
            body += ("<url><loc>%s/stock/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
                     % (SITE_URL, slug, today))
    # An index's constituent list changes only at NSE's periodic
    # rebalancing (quarterly/semi-annually), so weekly matches the hub pages
    # rather than overclaiming daily freshness.
    for slug in (indices or {}):
        body += ("<url><loc>%s/index/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                 % (SITE_URL, slug, today))
    # An ETF's own listing facts change as rarely as a stock's.
    for e in (etfs or []):
        slug = _stock_slug(e.get("symbol"))
        if slug:
            body += ("<url><loc>%s/etf/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
                     % (SITE_URL, slug, today))
    # A coin's market-cap rank and supply facts move slower than a stock's
    # listing facts but faster than "almost never" - daily matches the price
    # ticker's own refresh cadence without overclaiming the facts are live.
    for slug in (crypto_slugs or []):
        body += ("<url><loc>%s/crypto/%s/</loc><lastmod>%s</lastmod><changefreq>daily</changefreq></url>"
                 % (SITE_URL, slug, today))
    # An open/forthcoming IPO's facts (subscription, dates) move daily; once
    # listed, its facts are as settled as a stock's own listing facts.
    for r in (ipo_records or []):
        freq = "daily" if r.get("status") in ("Active", "Forthcoming") else "monthly"
        body += ("<url><loc>%s/ipo/%s/</loc><lastmod>%s</lastmod><changefreq>%s</changefreq></url>"
                 % (SITE_URL, r["symbol"].lower(), today, freq))
    # A fund's NAV moves daily, but its own scheme facts (plans, ISINs) are
    # stable - weekly matches the other data-heavy static families.
    for slug in (fund_slugs or {}):
        body += ("<url><loc>%s/fund/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                 % (SITE_URL, slug, today))
    for slug in (report_slugs or []):
        body += ("<url><loc>%s/reports/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
                 % (SITE_URL, slug, today))
    # A calculator's own formula never changes; monthly matches other stable,
    # non-data-driven pages rather than overclaiming daily freshness.
    for slug in (calc_slugs or []):
        body += ("<url><loc>%s/calculators/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
                 % (SITE_URL, slug, today))
    # Directory/browse pages exist purely to give crawlers a link path into
    # the page families above; they change whenever their underlying universe
    # does, so weekly matches the hub pages they mirror.
    for letter in (stock_letters or []):
        body += ("<url><loc>%s/stocks/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                 % (SITE_URL, slugify(letter), today))
    if registry_letters:
        body += ("<url><loc>%s/registry/az/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                 % (SITE_URL, today))
    for letter in (registry_letters or []):
        body += ("<url><loc>%s/registry/az/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                 % (SITE_URL, slugify(letter), today))
    for amc_slug in (amc_slugs or {}).values():
        body += ("<url><loc>%s/funds-by/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                 % (SITE_URL, amc_slug, today))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>' % body)
    _write_text(os.path.join(SITE_DATA, "..", "sitemap.xml"), xml)


_REPORT_TITLES = {
    "state-of-indian-broking-2026": "State of Indian Broking, 2026",
}

_CORE_PAGES = [
    ("BrokerLens home", "/", ""),
    ("Brokers", "/brokers", ""),
    ("Compare brokers", "/compare", ""),
    ("Movers", "/leaderboards", ""),
    ("Brokerage cost calculator", "/calculator", ""),
    ("Financial calculators", "/calculators/", ""),
    ("SEBI registry", "/registry", ""),
    ("Algo trading platforms", "/algo", ""),
    ("Methodology", "/methodology", ""),
    ("Sources", "/sources", ""),
    ("Browse stocks A-Z", "/stocks/", ""),
    ("Browse mutual funds by AMC", "/funds-by/", ""),
    ("Browse ETFs", "/etfs/", ""),
    ("Crypto prices and market data", "/crypto/", ""),
    ("IPO tracker", "/ipo/", ""),
    ("Full IPO archive", "/ipo/archive/", ""),
]


def _write_search_index(built, reg_rows, hub_groups, companies, indices, etfs, fund_slugs, report_slugs,
                         amc_slugs=None, crypto_coins=None, ipo_records=None):
    """One flat, client-side search index covering every page family this
    pipeline writes, not just the 48 tracked brokers the original search.json
    carried (which had no reader anywhere in the codebase - confirmed by
    grepping every JS file for it). Shipped as compact 4-element arrays
    (name, url, type, subtitle) rather than keyed objects: at ~8,000 rows the
    repeated key names alone would roughly double the payload, and this is
    fetched lazily by search.js - only when a visitor actually opens search,
    never on first paint.

    No live API, no server: this is a precomputed snapshot rebuilt on every
    publish, matching the rest of the site's read-only-static-JSON contract
    stated at the top of this file.
    """
    rows = []

    for b in built:
        rows.append([b["profile"]["brand"], "/broker/%s/" % b["id"], "broker", b["profile"].get("legal_name") or ""])

    for r in reg_rows:
        slug = r.get("slug")
        if not slug:
            continue
        rows.append([r.get("name") or "Unnamed entity", "/sebi-registry/%s/" % slug, "sebi", r.get("city") or ""])

    for dim, key, label, _grp_rows in (hub_groups or []):
        slug = slugify(key.replace("_", "-"))
        if slug:
            rows.append([label, "/brokers-by/%s/%s/" % (dim, slug), "hub", ""])

    for dim in {d for d, _, _, _ in (hub_groups or [])}:
        rows.append([BROKER_HUB_DIM_NOUN[dim], "/brokers-by/%s/" % dim, "hub", ""])

    for c in (companies or []):
        symbol = (c.get("symbol") or "").strip()
        slug = _stock_slug(symbol)
        if slug:
            rows.append([c.get("name") or symbol, "/stock/%s/" % slug, "stock", symbol])

    for slug, idx in (indices or {}).items():
        rows.append([idx.get("label") or slug, "/index/%s/" % slug, "index", ""])

    for e in (etfs or []):
        symbol = (e.get("symbol") or "").strip()
        slug = _stock_slug(symbol)
        if slug:
            rows.append([e.get("name") or symbol, "/etf/%s/" % slug, "etf", symbol])

    for slug, (amc, name) in (fund_slugs or {}).items():
        rows.append([name, "/fund/%s/" % slug, "fund", amc])

    for slug in (report_slugs or []):
        rows.append([_REPORT_TITLES.get(slug, slug.replace("-", " ").title()), "/reports/%s/" % slug, "report", ""])

    for amc, amc_slug in (amc_slugs or {}).items():
        rows.append([amc, "/funds-by/%s/" % amc_slug, "hub", "Fund house"])

    for c in (crypto_coins or []):
        if c.get("name") and c.get("symbol"):
            rows.append([c["name"], "/crypto/%s/" % c["symbol"].lower(), "crypto", c["symbol"]])

    for r in (ipo_records or []):
        company = r.get("company") or r["symbol"]
        rows.append([company + " IPO", "/ipo/%s/" % r["symbol"].lower(), "ipo", r.get("status") or ""])

    for c in CALCULATORS:
        rows.append([c["h1"], "/calculators/%s/" % c["slug"], "calc", ""])

    for name, url, sub in _CORE_PAGES:
        rows.append([name, url, "page", sub])

    write_json(os.path.join(SITE_DATA, "search.json"), rows, compact=True)
    log("search.json: %d entries indexed" % len(rows), "ok")


def _write_feed(built, aggregates):
    _require_site_url()
    """RSS of notable monthly movements - the SEO/discovery surface."""
    movers = sorted(
        [b for b in built if b["clients"].get("mom_pct") is not None],
        key=lambda b: abs(b["clients"]["mom_pct"]), reverse=True)[:15]
    items = []
    for b in movers:
        c = b["clients"]
        title = "%s: %s%.2f%% month-on-month active clients (%s)" % (
            b["profile"]["brand"], "+" if c["mom_pct"] >= 0 else "", c["mom_pct"], c.get("as_of"))
        items.append(
            "<item><title>%s</title><link>%s/broker/%s</link>"
            "<guid isPermaLink='false'>%s-%s</guid><description>%s</description></item>"
            % (_esc(title), SITE_URL, b["id"], b["id"], c.get("as_of"),
               _esc("Active clients %s, market share %s%%, reliability %s/100." % (
                   c.get("active_clients"), c.get("market_share_pct"),
                   (b.get("reliability") or {}).get("score")))))
    xml = ("<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel>"
           "<title>Indian Stock Broker Marketplace - monthly movers</title>"
           "<link>%s</link><description>Broker statistics from NSE, BSE and SEBI disclosures.</description>"
           "%s</channel></rss>" % (SITE_URL, "".join(items)))
    _write_text(os.path.join(SITE_DATA, "..", "feed.xml"), xml)
    _write_robots()


def _write_text(path, body):
    """Atomic write, so a crash or a CDN read mid-write cannot serve half a file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.replace(tmp, path)


def _prune_stale_dirs(base_dir, keep_slugs):
    """Remove subdirectories left behind by a source entity that was renamed,
    delisted or dropped between runs - otherwise its page keeps being served
    (and stays crawlable) forever, silently drifting out of step with the
    source of truth it claims to reflect."""
    if not os.path.isdir(base_dir):
        return 0
    removed = 0
    for name in os.listdir(base_dir):
        if name not in keep_slugs and os.path.isdir(os.path.join(base_dir, name)):
            shutil.rmtree(os.path.join(base_dir, name))
            removed += 1
    return removed


def _write_robots():
    """Advertise the sitemap; keep crawlers out of raw JSON and the API.

    Without this, /data/*.json competes with the rendered pages in search
    results and every soft-404 URL is crawlable.
    """
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/",
        "Disallow: /data/",
        "",
        "Sitemap: %s/sitemap.xml" % SITE_URL,
        "",
    ])
    _write_text(os.path.join(SITE_DATA, "..", "robots.txt"), body)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
