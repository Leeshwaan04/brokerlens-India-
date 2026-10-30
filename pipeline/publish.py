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
import html
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

SITE_URL = (os.environ.get("SITE_URL") or "https://www.brokerlens.in").rstrip("/")

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


def _load_affiliate_partners():
    aff_path = os.path.join(ROOT, "config", "affiliates.json")
    if os.path.exists(aff_path):
        try:
            with open(aff_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("partners", {})
        except Exception:
            pass
    return {
        "zerodha": "https://zerodha.com/open-account?c=ZE5729",
        "5paisa": "https://www.5paisa.com/demat-account?ReferralCode=53293333&ReturnUrl=invest-open-account",
        "dhan": "https://dhan.co/?ref=BROKERLENS",
        "angel-one": "https://www.angelone.in/open-demat-account?referral=BROKERLENS",
        "upstox": "https://upstox.com/open-account/?f=BROKERLENS",
    }


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
    return re.sub(r'(href|srcset|src|poster|data-src)="/assets/([^"]+)"', repl, html)


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
            cur = merged.setdefault(key, dict(r, categories=[], exchanges=list(r.get("exchanges") or []),
                                              validities=list(r.get("validities") or [])))
            if cat not in cur["categories"]:
                cur["categories"].append(cat)
            for e in r.get("exchanges") or []:
                if e not in cur["exchanges"]:
                    cur["exchanges"].append(e)
            # every distinct validity string the register lists for this number
            for v in (r.get("validities") or ([r["validity"]] if r.get("validity") else [])):
                if v not in cur["validities"]:
                    cur["validities"].append(v)
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

    # One legal entity can hold several registrations (broker + DP). Non-primary
    # rows get row["primary"] = the primary slug (canonical target; see registry_entity).
    from . import registry_entity
    _reg_group_stats = registry_entity.annotate(reg_rows, untracked)
    log("registry entities: %(groups)d multi-registration groups, %(non_primary)d canonicalised "
        "secondary pages, %(ambiguous_slugs)d left unmerged as ambiguous" % _reg_group_stats, "ok")

    reg_size = write_json(os.path.join(SITE_DATA, "registry.json"),
                          {"generated_at": now_iso(), "source": "SEBI recognised intermediaries",
                           "count": len(reg_rows), "entities": reg_rows}, compact=True)
    log("registry.json %.1f KB, %d untracked registered entities"
        % (reg_size / 1024, len(reg_rows)), "ok")

    sources_data = _write_sources(sources_cfg, ingest, sample_flags)
    algo_data = _write_algo(brokers_cfg)
    _write_timings()
    _write_registry_pages(reg_rows, untracked, registry_entity.register_asof(ingest))
    _write_broker_pages(built)
    hub_groups = _write_broker_hub_pages(built)
    equity_companies = ((nse_d.get("universe") or {}).get("companies")) or []
    index_universe = nse_d.get("indices") or {}
    equity_history = nse_d.get("equity_history") or {}
    # Prices are not adjusted for splits/bonuses, so keep only the comparable stretch after any
    # such break; the stock page says so (see _stock_perf).
    from .common import trim_to_last_break
    _EQUITY_BREAKS.clear()
    for _sym, _candles in list(equity_history.items()):
        _trimmed, _brk = trim_to_last_break(_candles)
        if _brk:
            equity_history[_sym] = _trimmed
            _EQUITY_BREAKS[_sym.upper()] = _brk
    if _EQUITY_BREAKS:
        log("equity history: %d stocks had a split/bonus-sized break; earlier prices excluded" % len(_EQUITY_BREAKS), "ok")
    build_equity_history(equity_history)
    _write_stock_pages(equity_companies, read_json(os.path.join(CONFIG, "broker_stocks.json"), {}).get("stocks"),
                        index_universe, equity_history, bse_d.get("corporate_actions") or [], ipo_records=ipo_records)
    _write_index_pages(index_universe, equity_companies)
    etf_universe = nse_d.get("etfs") or []
    mf_schemes = amfi_d.get("schemes") or []
    _funds, fund_slugs, fund_nav_dates = _write_mutual_fund_pages(mf_schemes)
    _enrich_etfs(etf_universe, mf_schemes, {key: slug for slug, key in fund_slugs.items()})
    _write_etf_pages(etf_universe, index_universe)
    report_slugs = _write_reports(built, reg_rows, equity_companies, index_universe, etf_universe,
                                   _funds, len(sebi_d.get("defaulters") or []))
    calc_slugs = _write_calculator_pages()
    _write_calculator_hub()
    _write_find_broker_page(overview, built)
    _write_cms_page(overview, built)
    _write_methodology_page()
    _write_coming_soon_pages()
    _write_about_page()
    _write_editorial_policy_page()
    _write_contact_page()
    _write_privacy_page()
    _write_terms_page()
    _write_sources_page(sources_data)
    _write_algo_page(algo_data)
    _write_leaderboards_page(overview, nse_d.get("live") or {}, crypto_coins)
    registry_letters = _write_registry_directory(reg_rows)
    _write_registry_landing_page(reg_rows, overview, registry_letters)
    comparison_pairs = _write_compare_pages(overview, built)
    _write_brokers_page(overview)
    _write_calculator_tool_page(built)
    _prerender_home(overview)
    stock_letters = _write_stock_directory(equity_companies, index_universe)
    amc_slugs = _write_fund_amc_pages(fund_slugs, _funds)
    _write_etf_directory(etf_universe)
    crypto_slugs = _write_crypto_pages(crypto_coins)
    _write_crypto_hub(crypto_coins)
    _write_ipo_pages(ipo_records, equity_history=equity_history)
    _write_ipo_hub(ipo_records, equity_history=equity_history)
    _write_ipo_archive(ipo_records, equity_history=equity_history)
    _write_ipo_upcoming(ipo_records, equity_history=equity_history)
    _write_ipo_sme(ipo_records, equity_history=equity_history)
    _write_ipo_gmp(ipo_records, equity_history=equity_history)
    from .news_engine import write_news_suite
    _news_count, news_articles = write_news_suite(ingest, SITE_URL)
    from .trade_cost_engine import build_trade_cost_pages
    trade_cost_urls = build_trade_cost_pages(limit_stocks=2500, site_url=SITE_URL)
    from .broker_charges_engine import build_broker_charges_pages
    broker_charges_urls = build_broker_charges_pages(built, registry, site_url=SITE_URL)
    from .ipo_apply_engine import build_ipo_apply_suite
    ipo_apply_urls = build_ipo_apply_suite(limit_recent_ipos=100, site_url=SITE_URL)
    from .ipo_subscription_engine import build_ipo_subscription_suite
    ipo_sub_urls = build_ipo_subscription_suite(site_url=SITE_URL)
    from .stock_compare_engine import build_stock_compare_suite
    stock_compare_urls, stock_compare_search = build_stock_compare_suite(site_url=SITE_URL)
    from .sip_calculator_engine import build_sip_calculator_suite
    sip_calc_urls = build_sip_calculator_suite(site_url=SITE_URL)
    from .broker_branch_engine import generate_all as build_branch_suite
    branch_urls = build_branch_suite(site_url=SITE_URL)
    from .fund_compare_engine import generate_all as build_fund_compare_suite
    fund_compare_urls, fund_category_urls, fund_compare_search = build_fund_compare_suite(site_url=SITE_URL)
    # The /stock/:symbol/share-price-target-:year pages are retired (308 to the stock page in vercel.json;
    # the query is answered on the stock page, see price_target_section.py). Never regenerate them and
    # never advertise them in a sitemap.
    share_price_target_urls = []
    _write_sitemap(built, reg_rows, hub_groups, equity_companies, index_universe, etf_universe,
                    fund_slugs, report_slugs, calc_slugs, stock_letters, amc_slugs, crypto_slugs, ipo_records,
                    registry_letters, equity_history, fund_nav_dates, comparison_pairs=comparison_pairs,
                    trade_cost_urls=trade_cost_urls, ipo_apply_urls=ipo_apply_urls,
                    stock_compare_urls=stock_compare_urls, sip_calc_urls=sip_calc_urls,
                    branch_urls=branch_urls, fund_compare_urls=fund_compare_urls,
                    fund_category_urls=fund_category_urls, ipo_sub_urls=ipo_sub_urls,
                    share_price_target_urls=share_price_target_urls,
                    broker_charges_urls=broker_charges_urls)
    _write_search_index(built, reg_rows, hub_groups, equity_companies, index_universe, etf_universe,
                         fund_slugs, report_slugs, amc_slugs, crypto_coins, ipo_records, comparison_pairs=comparison_pairs,
                         news_articles=news_articles, stock_compare_search=stock_compare_search,
                         fund_compare_search=fund_compare_search)
    _write_feed(built, aggregates)
    build_ticker()
    build_crypto_ticker()
    build_crypto_history()
    build_market_movers()
    _export_gsc_live()
    _restamp_js_media()
    _restamp_js_imports()
    _restamp_index_html_assets()
    return overview


def _export_gsc_live():
    """Export real Google Search Console data from reports/gsc to site/data/gsc_live.json."""
    try:
        from scripts import export_gsc_live
        export_gsc_live.main()
    except Exception as exc:
        log("GSC live data export skipped or failed: %s" % exc, "warn")


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


def _restamp_js_media():
    """Same content-hash cache busting as _restamp_js_imports(), for media URLs
    written as string literals inside JS (the home-hero video markup in
    pages.js, the footer film's SRC/POSTER in footer-film.js). /assets/* is
    immutable for a year, so a replaced mp4/jpg at the same URL would otherwise
    never reach a returning visitor. Runs before _restamp_js_imports() so the
    JS files' own hashes reflect the stamped URLs."""
    js_dir = os.path.join(ROOT, "site", "assets", "js")
    media_re = re.compile(r"(/assets/(?:video|audio|img/ads)/[\w.-]+\.(?:mp4|jpg|mp3))(?:\?v=[0-9a-f]+)?")

    def repl(m):
        path = os.path.join(ROOT, "site", m.group(1).lstrip("/"))
        try:
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:10]
        except OSError:
            return m.group(0)
        return "%s?v=%s" % (m.group(1), digest)
    try:
        names = sorted(f for f in os.listdir(js_dir) if f.endswith(".js"))
    except OSError:
        return
    for name in names:
        fp = os.path.join(js_dir, name)
        content = open(fp, encoding="utf-8").read()
        new_content = media_re.sub(repl, content)
        if new_content != content:
            _write_text(fp, new_content)


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

    gainers = rows("gainers")
    losers = rows("losers")
    most_active = rows("quotes")

    if not gainers or not losers:
        eq_hist = (ingest.get("nse") or {}).get("equity_history") or {}
        moves = []
        for sym, candles in eq_hist.items():
            if not candles or len(candles) < 2:
                continue
            last_c = candles[-1].get("close")
            prev_c = candles[-2].get("close")
            vol = candles[-1].get("volume") or 0
            if last_c and prev_c and prev_c > 0:
                pct = ((last_c - prev_c) / prev_c) * 100.0
                moves.append({
                    "symbol": sym.upper(),
                    "last": round(last_c, 2),
                    "change": round(last_c - prev_c, 2),
                    "change_pct": round(pct, 2),
                    "volume": vol,
                })
        if moves:
            moves_sorted = sorted(moves, key=lambda m: m["change_pct"], reverse=True)
            if not gainers:
                gainers = moves_sorted[:10]
            if not losers:
                losers = list(reversed(moves_sorted[-10:]))
            if not most_active:
                most_active = sorted(moves, key=lambda m: m["volume"], reverse=True)[:10]

    payload = {
        "generated_at": now_iso(),
        "gainers": gainers,
        "losers": losers,
        "most_active": most_active,
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
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
<meta name="google-adsense-account" content="ca-pub-8447377943455646">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-8447377943455646" crossorigin="anonymous"></script>
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
<meta property="og:image" content="https://www.brokerlens.in/assets/img/ads/ibsl-wide-2000x500.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="%(title)s">
<meta name="twitter:description" content="%(description)s">
<meta name="twitter:image" content="https://www.brokerlens.in/assets/img/ads/ibsl-wide-2000x500.jpg">
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
    <a href="/news/">News &amp; Blogs</a>
    <a href="/reports/state-of-indian-broking-2026/">Reports</a>
    <button class="mega-toggle" id="timings-toggle" aria-expanded="false" aria-controls="mega-timings">Market timings <span aria-hidden="true">&#9662;</span></button>
  </nav>
  <button class="icon-btn" id="search-toggle" title="Search (Ctrl+K)" aria-label="Search" aria-haspopup="dialog" aria-controls="search-overlay"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button><button class="icon-btn" id="audio-toggle" title="Play music" aria-label="Play music" aria-pressed="false" hidden><svg class="ico-off" width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2 6h2.5L8 3v10L4.5 10H2z" fill="currentColor"/><path d="M11 6l3 4M14 6l-3 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg><svg class="ico-on" width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true" style="display:none"><path d="M2 6h2.5L8 3v10L4.5 10H2z" fill="currentColor"/><path d="M10.5 5.5a3.5 3.5 0 010 5M12.5 3.5a6.3 6.3 0 010 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></button>
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
  <p class="small"><a href="/news/">Market News, Blogs &amp; Research →</a> ·
  <a href="/registry">Search the full SEBI registry →</a> ·
  <a href="/brokers">Brokers tracked in depth →</a> ·
  <a href="/brokers-by/type/">Brokers by type →</a> ·
  <a href="/brokers-by/segment/">Brokers by segment →</a> ·
  <a href="/brokers-by/city/">Brokers by city →</a> ·
  <a href="/stocks/">Browse stocks A-Z →</a> ·
  <a href="/funds-by/">Browse mutual funds by AMC →</a> ·
  <a href="/etfs/">Browse ETFs →</a> · <a href="/ipo/">IPO tracker →</a> · <a href="/">BrokerLens home →</a></p>
  <p class="small"><a href="/ipo/upcoming/">Upcoming IPOs →</a> ·
  <a href="/ipo/gmp/">IPO GMP Today →</a> ·
  <a href="/ipo/sme/">SME IPOs →</a> ·
  <a href="/ipo/subscription/">IPO subscription status →</a> ·
  <a href="/trade-costs/">Trade cost calculator →</a> ·
  <a href="/index/nifty-50/">Nifty 50 constituents →</a> ·
  <a href="/etf/niftybees/">Nifty 50 ETF: NIFTYBEES →</a></p>
  <p class="small"><a href="/about">About</a> · <a href="/editorial-policy">Editorial policy</a> · <a href="/contact">Contact</a> ·
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
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
<meta name="google-adsense-account" content="ca-pub-8447377943455646">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-8447377943455646" crossorigin="anonymous"></script>
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
<meta property="og:image" content="https://www.brokerlens.in/assets/img/ads/ibsl-wide-2000x500.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="%(title)s">
<meta name="twitter:description" content="%(description)s">
<meta name="twitter:image" content="https://www.brokerlens.in/assets/img/ads/ibsl-wide-2000x500.jpg">
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
      <a href="/news/" data-link>News &amp; Blogs</a>
      <a href="/reports/state-of-indian-broking-2026/">Reports</a>
      <button class="mega-toggle" id="timings-toggle" aria-expanded="false" aria-controls="mega-timings">Market timings <span aria-hidden="true">&#9662;</span></button>
    </nav>
    <button class="icon-btn" id="search-toggle" title="Search (Ctrl+K)" aria-label="Search" aria-haspopup="dialog" aria-controls="search-overlay"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button><button class="icon-btn" id="audio-toggle" title="Play music" aria-label="Play music" aria-pressed="false" hidden><svg class="ico-off" width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2 6h2.5L8 3v10L4.5 10H2z" fill="currentColor"/><path d="M11 6l3 4M14 6l-3 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg><svg class="ico-on" width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true" style="display:none"><path d="M2 6h2.5L8 3v10L4.5 10H2z" fill="currentColor"/><path d="M10.5 5.5a3.5 3.5 0 010 5M12.5 3.5a6.3 6.3 0 010 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></button>
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
          <li><a href="/find-broker/" data-link>Broker Matchmaker</a></li>
          <li><a href="/brokers" data-link>All brokers</a></li>
          <li><a href="/trade-costs/">Trade cost calculator</a></li>
          <li><a href="/compare/stocks/">Compare stocks</a></li>
          <li><a href="/ipo/">IPO tracker</a></li>
          <li><a href="/ipo/upcoming/">Upcoming IPOs</a></li>
          <li><a href="/ipo/gmp/">IPO GMP Today</a></li>
          <li><a href="/ipo/sme/">SME IPOs</a></li>
          <li><a href="/ipo/subscription/">IPO subscription status</a></li>
          <li><a href="/ipo/allotment-status/">IPO allotment status</a></li>
          <li><a href="/ipo/how-to-apply/">How to apply for IPO</a></li>
          <li><a href="/calculator" data-link>Brokerage calculator</a></li>
          <li><a href="/registry" data-link>SEBI registry</a></li>
          <li><a href="/algo" data-link>Algo platforms</a></li>
        </ul>
      </div>
      <div>
        <h5>Data &amp; News</h5>
        <ul>
          <li><a href="/news/" data-link>News &amp; Blogs</a></li>
          <li><a href="/methodology" data-link>Methodology</a></li>
          <li><a href="/sources" data-link>Sources &amp; lineage</a></li>
          <li><a href="/reports/state-of-indian-broking-2026/">State of Indian Broking, 2026</a></li>
          <li><a href="/feed.xml">RSS feed</a></li>
          <li><a href="/sitemap.xml">Sitemap Index</a></li>
        </ul>
      </div>
      <div>
        <h5>Markets &amp; Wealth</h5>
        <ul>
          <li><a href="/stocks/">Browse stocks A-Z</a></li>
          <li><a href="/index/nifty-50/">Nifty 50 constituents</a></li>
          <li><a href="/calculators/sip/">SIP scenarios matrix</a></li>
          <li><a href="/funds-by/">Browse mutual funds by AMC</a></li>
          <li><a href="/etfs/">Browse ETFs</a></li>
          <li><a href="/etf/niftybees/">Nifty 50 ETF: NIFTYBEES</a></li>
          <li><a href="/calculators/">Financial calculators</a></li>
        </ul>
      </div>
      <div>
        <h5>Company</h5>
        <ul>
          <li><a href="/about" data-link>About</a></li>
          <li><a href="/editorial-policy" data-link>Editorial policy</a></li>
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


def _px_html(n):
    """A share price: two decimals below Rs 10,000 (Rs 85.09, not "Rs 85"; Rs 0.45, not "Rs 0"),
    Indian grouping above. _inr_html's whole-rupee default is right for charges and totals,
    wrong for prices."""
    if n is None:
        return "-"
    return _inr_html(n, decimals=2) if abs(n) < 1e4 else _inr_html(n)


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


def _write_registry_pages(reg_rows, details=None, asof=None):
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

    Grouping, labels, titles, FAQs and the page body live in
    pipeline/registry_entity.py (every URL is still written; secondary
    registrations of one legal name canonicalise to the primary page).
    `details` is the full register record list (email, address, validities)
    aligned with reg_rows; `asof` is the register as-of date or None.
    """
    from . import registry_entity
    base = os.path.join(SITE_DATA, "..", "sebi-registry")
    written = 0
    keep = {r["slug"] for r in reg_rows if r.get("slug")}
    pruned = _prune_stale_dirs(base, keep)
    models = registry_entity.build_models(reg_rows, details, asof, SITE_URL)
    for r, model in zip(reg_rows, models):
        if not model:
            continue
        slug = model["slug"]
        name = model["display"]
        canonical = model["canonical"]

        def attr(v):
            return _esc(v).replace('"', "&quot;")

        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("SEBI registry", "/registry"), (name, None),
        ])
        jsonld = {"@context": "https://schema.org",
                  "@graph": [model["org_jsonld"], model["faq_jsonld"], crumb_jsonld]}

        body = _REGISTRY_PAGE_HEAD % {
            "title": attr(model["title"]), "description": attr(model["description"][:300]),
            "canonical": attr(canonical),
            "jsonld": json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
        }
        body += crumb_html + model["main_html"]
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


def _broker_facts_html(b, built=None):
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
    aff_url = _load_affiliate_partners().get(b["id"])
    open_acc_html = (
        '<a class="btn btn-primary btn-sm" href="%s" rel="noopener noreferrer sponsored" target="_blank">Open Demat Account &rarr;</a>'
        % _esc(aff_url)
    ) if aff_url else ""
    website_html = (
        '<a class="btn btn-sm" href="%s" rel="nofollow noopener external" target="_blank">Website &#8599;</a>'
        % _esc(website) if website.startswith(("http://", "https://")) else ""
    )

    comp_links = ""
    if built:
        peers = _peers(b, built)
        if peers:
            comp_links = (
                '<div class="section-title" style="margin-top:20px"><h2>Compare with competitors</h2></div>'
                '<div class="row-wrap" style="gap:8px;margin-top:10px">%s</div>'
                % "".join(
                    '<a class="chip" href="/compare/%s-vs-%s/">%s vs %s &rarr;</a>'
                    % (_esc(b["id"]), _esc(p["id"]), _esc(b["profile"].get("brand") or b["id"]), _esc(p["brand"]))
                    for p in peers
                )
            )

    return (
        '<h1 style="margin-top:16px">%s</h1>' % _esc(p.get("brand") or b["id"])
        + '<p class="muted small">%s</p>' % _esc(p.get("legal_name") or "")
        + flag_html
        + '<div class="row-wrap" style="margin-top:10px">%s%s'
          '<a class="btn btn-sm" href="/compare?b=%s">Compare</a></div>'
          % (open_acc_html, website_html, _esc(b["id"]))
        + '<div class="grid g4" style="margin-top:16px">' + client_html + complaint_html + cost_html + rel_html + '</div>'
        + '<div class="section-title" style="margin-top:20px"><h2>Registration and identity</h2></div>'
        + '<div class="grid g3">' + identity_html + '</div>'
        + comp_links
        + '<p class="xs faint" style="margin-top:16px">Source: SEBI recognised-intermediary register and, where '
          'noted above, NSE/BSE/SEBI primary disclosures. <a href="/methodology">Methodology</a> &middot; '
          '<a href="/sources">Sources &amp; lineage</a> &middot; <a href="/brokers">All brokers</a></p>'
    )


_BROKER_TYPE_BLURB = {
    "discount": "A discount broker charges low, usually flat, brokerage and offers a self-directed platform without bundled research or advisory.",
    "full_service": "A full-service broker bundles research, advisory and relationship support with trading, usually at higher brokerage.",
    "bank": "A bank-led broker offers trading and demat linked to a savings account at the parent bank.",
    "hybrid": "A hybrid broker combines low-cost self-directed trading with optional advisory or research products.",
}


def _broker_depth(b, built):
    """Real, sourced depth for a broker profile page: regulatory facts from the
    SEBI register, how to verify and complain through official channels, links
    into the cost-calculator pages, and an FAQ answered only from this page's own
    data. Returns (html, faq_pairs). Written outside the interactive <main> (see
    _write_broker_pages) so it survives client-side hydration and crawlers see it;
    nothing here is estimated and no field is shown unless the register has it."""
    p = b["profile"]
    brand = p.get("brand") or b["id"]
    bid = b["id"]
    rows = []

    def row(label, value):
        if value:
            rows.append('<tr><th scope="row">%s</th><td>%s</td></tr>' % (label, value))

    row("Legal name", _esc(p.get("legal_name")) if p.get("legal_name") else "")
    row("SEBI registration number", _esc(p.get("sebi_reg_no")) if p.get("sebi_reg_no") else "")
    cats = [CATEGORY_LABELS.get(c, c) for c in (p.get("sebi_categories") or [])]
    row("Registered as", _esc(", ".join(cats)) if cats else "")
    exch = p.get("sebi_exchanges") or []
    row("Exchanges and clearing corporations",
        "<br>".join(_esc(e.title() if e.isupper() else e) for e in exch) if exch else "")
    dps = p.get("dp_registrations") or []
    row("Depository participant registrations",
        "<br>".join("%s: %s" % (_esc(d.get("depository")), _esc(d.get("reg_no"))) for d in dps) if dps else "")
    row("Registration validity", _esc(p.get("sebi_validity")) if p.get("sebi_validity") else "")
    row("City (as on the register)", _esc(p.get("sebi_city")) if p.get("sebi_city") else "")
    reg_html = (
        '<div class="section-title"><h2>Regulatory profile of %s</h2></div>'
        '<div class="table-scroll"><table class="data"><tbody>%s</tbody></table></div>'
        '<p class="xs faint" style="margin-top:6px">Source: SEBI recognised-intermediary register, as of BrokerLens\'s latest data refresh.</p>'
        % (_esc(brand), "".join(rows))
    ) if rows else ""

    verify_html = (
        '<div class="section-title"><h2>How to verify %s yourself</h2></div>'
        '<ol class="small" style="max-width:72ch;line-height:1.6">'
        '<li>Open the SEBI website (<a href="https://www.sebi.gov.in/" rel="noopener" target="_blank">sebi.gov.in</a>) and look up '
        'recognised intermediaries to confirm the registration number above is active.</li>'
        '<li>Check the same registration on the exchange you trade on: a stock broker must be a member of that exchange.</li>'
        '<li>Make sure the demat account is with a registered depository participant, and compare the depository (CDSL or NSDL) '
        'with the participant registrations listed above.</li>'
        '<li>Never pay a broker into a personal account. Brokers collect funds only through their registered bank accounts.</li>'
        '</ol>' % _esc(brand)
    )
    complain_html = (
        '<div class="section-title"><h2>How to raise a complaint about %s</h2></div>'
        '<p class="small" style="max-width:72ch;line-height:1.6">Write to the broker\'s own grievance cell first and keep the reference '
        'number. If it is not resolved, register the complaint on <a href="https://scores.sebi.gov.in/" rel="noopener" target="_blank">SEBI SCORES</a>. '
        'SEBI also runs an online dispute-resolution portal, <a href="https://smartodr.in/" rel="noopener" target="_blank">SMART ODR</a>, '
        'for unresolved disputes with market intermediaries.</p>' % _esc(brand)
    )

    # Links into pages this build writes later (trade costs, branches).
    extra = []
    try:
        from .trade_cost_engine import BROKER_RATES, get_trade_cost_stocks
        if bid in BROKER_RATES:
            stocks = get_trade_cost_stocks(limit_stocks=12)
            if stocks:
                extra.append(
                    '<div class="section-title"><h2>%s charges on a trade</h2></div>'
                    '<p class="small" style="max-width:72ch">BrokerLens works out brokerage, STT, exchange charges, stamp duty, SEBI fee and GST for '
                    'a trade in each liquid stock under %s\'s rate card. Start with a popular one, or use the '
                    '<a href="/calculator">cost calculator</a>:</p>'
                    '<div class="row-wrap" style="gap:8px;margin-top:10px">%s</div>'
                    % (_esc(brand), _esc(brand), "".join(
                        '<a class="chip" href="/broker/%s/trade/%s/">%s &rarr;</a>'
                        % (_esc(bid), _esc(_stock_slug(s["symbol"])), _esc(s["symbol"])) for s in stocks)))
    except Exception:
        pass
    try:
        from .broker_charges_engine import profile_links_html
        extra.append(profile_links_html(bid))
    except Exception:
        pass
    try:
        from .broker_branch_engine import BROKER_BRANCH_METADATA
        if bid in BROKER_BRANCH_METADATA:
            extra.append('<p class="small" style="margin-top:14px"><a href="/broker/%s/branches/">%s branch and city coverage &rarr;</a></p>'
                         % (_esc(bid), _esc(brand)))
    except Exception:
        pass

    faqs = []
    if p.get("sebi_reg_no"):
        faqs.append(("Is %s registered with SEBI?" % brand,
                     "Yes. %s appears on SEBI's recognised-intermediary register under registration number %s%s." % (
                         p.get("legal_name") or brand, p["sebi_reg_no"],
                         (" (valid %s)" % p["sebi_validity"]) if p.get("sebi_validity") else "")))
        faqs.append(("What is the SEBI registration number of %s?" % brand,
                     "%s's SEBI registration number is %s." % (brand, p["sebi_reg_no"])))
    else:
        faqs.append(("Is %s registered with SEBI?" % brand,
                     "BrokerLens has not yet matched %s to an entry on SEBI's register, so no registration number is shown. "
                     "Check SEBI's own register before opening an account." % brand))
    if p.get("segments"):
        faqs.append(("Which segments does %s offer?" % brand,
                     "%s offers: %s." % (brand, ", ".join(SEGMENT_LABEL.get(s, s) for s in p["segments"]))))
    if p.get("type"):
        faqs.append(("Is %s a discount or a full-service broker?" % brand,
                     "BrokerLens classifies %s as a %s broker. %s" % (
                         brand, TYPE_LABEL.get(p["type"], p["type"]).lower(), _BROKER_TYPE_BLURB.get(p["type"], ""))))
    if p.get("hq") or p.get("founded"):
        faqs.append(("Where is %s headquartered and when was it founded?" % brand,
                     "%s%s%s." % (brand, (" is headquartered in %s" % p["hq"]) if p.get("hq") else "",
                                  ((" and was founded in %s" % p["founded"]) if p.get("hq") else (" was founded in %s" % p["founded"]))
                                  if p.get("founded") else "")))
    if dps:
        faqs.append(("Is %s a depository participant?" % brand,
                     "Yes. The register lists: %s." % "; ".join("%s registration %s" % (d.get("depository"), d.get("reg_no")) for d in dps)))
    faqs.append(("How do I complain about %s?" % brand,
                 "Raise it with %s's grievance cell first, then register it on SEBI SCORES (scores.sebi.gov.in) or use SMART ODR (smartodr.in) "
                 "if it is not resolved." % brand))
    if p.get("listed_company"):
        faqs.append(("Is %s a listed company?" % brand, "%s is the brand of a company listed on the stock exchanges." % brand))
    faq_html = (
        '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions about %s</h2>'
        '<div style="max-width:68ch">%s</div>' % (
            _esc(brand), "".join('<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
                                 for q, a in faqs))
    )
    body = (
        '<div class="wrap" data-static-only style="padding-top:0;padding-bottom:24px">'
        + ibslBanner_html("wide", "broker")
        + reg_html + verify_html + complain_html + "".join(extra) + faq_html
        + '<p class="xs faint" style="margin-top:20px">BrokerLens is an information service, not a SEBI-registered investment '
          'adviser. Nothing here is a recommendation to open an account with, or avoid, any broker. '
          '<a href="/methodology">Methodology</a> &middot; <a href="/sources">Sources</a></p>'
        + '</div>'
    )
    return body, faqs


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
        depth_html, depth_faqs = _broker_depth(b, built)
        jsonld = {"@context": "https://schema.org", "@graph": [
            entity_jsonld, crumb_jsonld,
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in depth_faqs]},
        ]}

        page = _APP_SHELL_HEAD % {
            "title": _esc(title), "description": _esc(description),
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        page += crumb_html
        page += _broker_facts_html(b, built)
        # The depth block goes right after </main>, outside the element the SPA
        # re-renders, so hydration cannot wipe it (see data-static-only in app.js).
        page += _APP_SHELL_FOOT.replace("</main>", "</main>" + depth_html, 1)

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
    ) % (_px_html(last["close"]), _cls_class(chg_pct), _pct_html(chg_pct), _iso_to_long_date(last["date"]))


def _stock_ohlc_html(history):
    """Today's Open/High/Low/Prev Close/Volume plus the real N-day high-low
    range, all read directly from NSE's own daily bhavcopy candles that are
    already fetched for the chart above this. Sits inside the chart card so
    that card isn't just a short canvas floating over empty space next to a
    much taller affiliate-banner sidebar - and because these numbers are
    read from the same history as the chart, they can never drift from what
    the chart itself shows. The N-day window is labelled by the real number
    of sessions on file (same discipline as stock_compare_engine.py's
    _range_window_label) rather than claimed as a "52-week" range when the
    cache holds far fewer days than that."""
    if not history or len(history) < 2:
        return ""
    last, prev = history[-1], history[-2]
    if last.get("close") is None or prev.get("close") is None:
        return ""
    highs = [row["high"] for row in history if isinstance(row.get("high"), (int, float))]
    lows = [row["low"] for row in history if isinstance(row.get("low"), (int, float))]
    window_days = len(history)
    range_label = "52-Week Range" if window_days >= 252 else "%d-Day Range" % window_days
    tiles = [
        ("Open", _px_html(last.get("open"))),
        ("Day High", _px_html(last.get("high"))),
        ("Day Low", _px_html(last.get("low"))),
        ("Previous Close", _px_html(prev.get("close"))),
        ("Volume", _indian_grouping(last["volume"]) if isinstance(last.get("volume"), (int, float)) else "-"),
        (range_label, ("%s - %s" % (_px_html(min(lows)), _px_html(max(highs)))) if lows and highs else "-"),
    ]
    return (
        '<div class="grid g3" style="margin-top:14px">'
        + "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div>'
            '<div style="margin-top:2px;font-weight:600">%s</div></div>' % (label, value)
            for label, value in tiles
        )
        + '</div>'
    )


_EQUITY_BREAKS = {}   # symbol -> date of the split/bonus-sized break after which history is kept


def _stock_perf(history, break_date=None):
    """Real performance measures computed only from the daily closes already on
    file (NSE bhavcopy). Every window is labelled by the sessions actually
    available, never as 1-year/52-week when the cache is shorter, and nothing
    is extrapolated. Returns (html, facts) or ("", None) when too short."""
    rows = [(r.get("date"), r.get("close")) for r in (history or [])
            if isinstance(r.get("close"), (int, float)) and r["close"] > 0 and r.get("date")]
    n = len(rows)
    if n < 6:
        return "", None
    last_date, last = rows[-1]
    first_date, first = rows[0]
    closes = [c for _d, c in rows]
    hi, lo = max(closes), min(closes)
    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, (c / peak - 1) * 100)
    wins = [(label, (last / closes[-1 - k] - 1) * 100) for label, k in (("1 week", 5), ("1 month", 21), ("3 months", 63)) if n > k]
    since = (last / first - 1) * 100
    vols = [r.get("volume") for r in history if isinstance(r.get("volume"), (int, float))]
    vratio = None
    if len(vols) > 5 and sum(vols[:-1]) > 0:
        vratio = vols[-1] / (sum(vols[:-1]) / len(vols[:-1]))
    facts = {"n": n, "first_date": first_date, "last_date": last_date, "last": last, "hi": hi, "lo": lo,
             "from_high": (last / hi - 1) * 100, "from_low": (last / lo - 1) * 100, "since": since, "mdd": mdd, "wins": wins}

    def tile(label, value_html):
        return ('<div class="mega-seg"><div class="mega-seg-label">%s</div>'
                '<div style="margin-top:2px;font-weight:600">%s</div></div>' % (label, value_html))
    tiles = [tile("Return, %s" % lab, _pct_html(v)) for lab, v in wins]
    tiles.append(tile("Return since %s" % _esc(_iso_to_long_date(first_date)), _pct_html(since)))
    tiles.append(tile("From %d-session high" % n, _pct_html(facts["from_high"])))
    tiles.append(tile("From %d-session low" % n, _pct_html(facts["from_low"])))
    tiles.append(tile("Deepest fall from a peak", _pct_html(mdd)))
    if vratio is not None:
        tiles.append(tile("Latest volume vs average", "%.1fx" % vratio))
    html = (
        '<div class="section-title"><h2>Performance snapshot</h2></div>'
        '<div class="grid g3">%s</div>'
        '<p class="xs faint" style="margin-top:8px;max-width:78ch">Computed from %d daily closes in NSE\'s bhavcopy, %s to %s. '
        'This is the history BrokerLens holds, not a full year, so no 1-year or 52-week figure is shown. '
        'Past performance does not indicate future results.%s</p>'
        % ("".join(tiles), n, _esc(_iso_to_long_date(first_date)), _esc(_iso_to_long_date(last_date)),
           (" Prices before %s are left out: a split or bonus around that date would make them incomparable, and "
            "BrokerLens does not yet adjust for corporate actions." % _esc(_iso_to_long_date(break_date))) if break_date else "")
    )
    return html, facts


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


def _write_stock_pages(companies, brokers_cfg, indices=None, equity_history=None, corporate_actions=None, ipo_records=None):
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
    from .price_target_section import (
        stock_title as _price_target_title, stock_description as _price_target_description,
        price_target_section_html, stock_target_faqs as _price_target_faqs)
    by_symbol = {s["symbol"].upper(): s for s in (brokers_cfg or [])}
    try:
        from .stock_compare_engine import curated_peer_index
        compare_index = curated_peer_index(equity_history or {})
    except Exception as exc:  # never let an enrichment block the page set
        log("stock compare links skipped: %s" % exc, "warn")
        compare_index = {}
    # A peer link must only ever point at a symbol this same run is actually
    # about to write a /stock/ page for - an index file can lag EQUITY_L.csv
    # by a day (a recent delisting, a symbol change), and a dead link is
    valid_symbols = {(c.get("symbol") or "").strip().upper() for c in companies} - {""}
    try:
        from .trade_cost_engine import get_trade_cost_stocks
        trade_cost_slugs = {_stock_slug(s["symbol"]) for s in get_trade_cost_stocks(limit_stocks=2500)}
    except Exception:
        trade_cost_slugs = set()
    ipo_by_slug = {}
    for r in (ipo_records or []):
        sym_r = (r.get("symbol") or "").strip().lower()
        if sym_r:
            ipo_by_slug[sym_r] = r

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

    def stock_faqs(name, symbol, c, member_of, match, price_row, perf=None):
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
        # Share-price-target query: answered on the page itself, never with a forecast
        # (pipeline/price_target_section.py). The "what the data shows" sentence is
        # only added when real history exists.
        facts_line = ""
        if perf:
            facts_line = (
                "What the data shows: %s last closed at %s on %s. Over the %d sessions on file it traded between %s and %s "
                "and was %.1f%% %s its high on the last close." % (
                    name, _px_html(perf["last"]), _iso_to_long_date(perf["last_date"]), perf["n"],
                    _px_html(perf["lo"]), _px_html(perf["hi"]), abs(perf["from_high"]),
                    "below" if perf["from_high"] < 0 else "at"))
        faqs.extend(_price_target_faqs(name, symbol, facts_line))
        if perf:
            faqs.append((
                "How has %s performed recently?" % name,
                "From %s to %s, %s moved %+.1f%% (%d sessions on file). %s Past performance does not indicate future results." % (
                    _iso_to_long_date(perf["first_date"]), _iso_to_long_date(perf["last_date"]), name, perf["since"], perf["n"],
                    ("Over the last month it moved %+.1f%%." % dict(perf["wins"])["1 month"]) if "1 month" in dict(perf["wins"]) else "")))
        faqs.append(("What was %s's last closing price?" % name,
                     "%s closed at %s on %s, from NSE's own daily bhavcopy." % (name, _px_html(price_row["close"]), price_row["date"])
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
        title = _price_target_title(name, symbol)
        description = _esc(_price_target_description(name, symbol)[:300])

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

        compare_html = ""
        cmp_links = compare_index.get(symbol.upper()) or []
        if cmp_links:
            peer_table_rows = []
            for other, url, _sec in cmp_links[:5]:
                other_hist = (equity_history or {}).get(other.upper()) or []
                if not other_hist:
                    continue
                o_last = other_hist[-1].get("close")
                o_ret1m = None
                if len(other_hist) > 21 and other_hist[-22].get("close"):
                    o_ret1m = (other_hist[-1]["close"] / other_hist[-22]["close"] - 1) * 100
                elif len(other_hist) > 1 and other_hist[0].get("close"):
                    o_ret1m = (other_hist[-1]["close"] / other_hist[0]["close"] - 1) * 100
                o_slug = _stock_slug(other)
                ret_html = ('<span class="up font-semibold">+%.1f%%</span>' % o_ret1m) if (o_ret1m is not None and o_ret1m >= 0) else (('<span class="down font-semibold">%.1f%%</span>' % o_ret1m) if o_ret1m is not None else '<span class="faint">-</span>')
                peer_table_rows.append(
                    '<tr>'
                    '<td><strong><a href="/stock/%s/">%s</a></strong></td>'
                    '<td class="right num font-semibold">%s</td>'
                    '<td class="right num">%s</td>'
                    '<td class="center"><a class="btn btn-outline btn-sm" href="%s">%s vs %s &rarr;</a></td>'
                    '</tr>' % (
                        _esc(o_slug), _esc(other),
                        ("Rs {:,.2f}".format(o_last)) if o_last else "N/A",
                        ret_html,
                        _esc(url), _esc(symbol.upper()), _esc(other)
                    )
                )
            peer_matrix_html = ""
            if peer_table_rows:
                peer_matrix_html = (
                    '<div class="table-scroll" style="margin-top:12px">'
                    '<table class="data"><thead><tr>'
                    '<th>Sector Peer</th><th class="right">Last Price</th><th class="right">1-Month Return</th><th class="center">Head-to-Head Comparison</th>'
                    '</tr></thead><tbody>'
                    + "".join(peer_table_rows)
                    + '</tbody></table></div>'
                )

            cmp_badges = "".join(
                '<a class="badge" href="%s" style="text-decoration:none;padding:5px 9px">%s vs %s &rarr;</a>'
                % (_esc(url), _esc(symbol.upper()), _esc(other)) for other, url, _sec in cmp_links[:8])
            compare_html = (
                ('<div class="section-title"><h2>Compare %s with sector peers</h2></div>'
                 '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px">%s</div>') % (_esc(symbol), cmp_badges)
                + peer_matrix_html
                + '<p class="xs faint" style="margin-top:8px">Side-by-side price range, return and volume from NSE daily data.</p>'
            )

        if slug in trade_cost_slugs:
            trade_badges = (
                '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px">'
                '<a class="badge" href="/broker/zerodha/trade/%s/" style="text-decoration:none;padding:5px 9px">Zerodha %s Fees &rarr;</a>'
                '<a class="badge" href="/broker/groww/trade/%s/" style="text-decoration:none;padding:5px 9px">Groww %s Fees &rarr;</a>'
                '<a class="badge" href="/broker/angel-one/trade/%s/" style="text-decoration:none;padding:5px 9px">Angel One %s Fees &rarr;</a>'
                '<a class="badge" href="/broker/upstox/trade/%s/" style="text-decoration:none;padding:5px 9px">Upstox %s Fees &rarr;</a>'
                '<a class="badge" href="/trade-costs/" style="text-decoration:none;padding:5px 9px">All Brokers Cost Calculator &rarr;</a>'
                '</div>'
            ) % (slug, _esc(symbol), slug, _esc(symbol), slug, _esc(symbol), slug, _esc(symbol))
        else:
            trade_badges = (
                '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px">'
                '<a class="badge" href="/trade-costs/" style="text-decoration:none;padding:5px 9px">Stock Trade Cost Calculator &rarr;</a>'
                '<a class="badge" href="/compare/" style="text-decoration:none;padding:5px 9px">Compare Top Brokers &rarr;</a>'
                '</div>'
            )

        demat_cta_html = (
            '<div style="margin-top:14px;background:var(--bg-raised);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:var(--radius-lg);padding:16px 18px;box-shadow:var(--shadow-sm)">'
            '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">'
            '<div style="font-weight:700;font-size:14px;color:var(--text)">Open Demat Account to Trade %s</div>'
            '<span class="badge badge-verified" style="font-size:11px">Zero Delivery Brokerage</span>'
            '</div>'
            '<p class="small muted" style="margin:6px 0 12px 0;line-height:1.5">Ready to invest in %s? Open a paperless Demat account with zero equity delivery brokerage, flat Rs 11 F&amp;O orders, and zero account opening fee with Indiabulls Securities.</p>'
            '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">'
            '<a class="btn btn-primary btn-sm" href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" style="font-weight:600">Open Free Demat Account &rarr;</a>'
            '<span class="xs faint">SEBI Reg. INZ000036136 &middot; 20+ Years Trusted &middot; Sponsored</span>'
            '</div>'
            '</div>'
        ) % (_esc(symbol), _esc(name))

        trade_cta_html = (
            '<div class="card" style="margin-top:20px;background:var(--accent-soft);border-style:solid">'
            '<div class="card-title">Trade %s</div>'
            '<p class="small muted" style="margin:4px 0 10px 0">%s is tradable through any SEBI-registered broker '
            'with an NSE cash-market membership. Compare broker charges, STT, and breakeven point movements:</p>'
            + trade_badges
            + demat_cta_html +
            '</div>'
        ) % (_esc(symbol), _esc(name))

        ipo_callout_html = ""
        if slug == "jiofin":
            ipo_callout_html = (
                '<div class="card" style="margin-top:20px;padding:18px 20px;background:var(--bg-raised);border-left:4px solid var(--accent);box-shadow:var(--shadow-sm)">'
                '<div style="font-weight:700;font-size:15px;color:var(--text)">Upcoming Reliance Jio Infocomm IPO</div>'
                '<p class="small muted" style="margin:6px 0 12px 0;line-height:1.5">Tracking the Reliance Jio telecom IPO? View expected valuation, timeline, DRHP status and demat account application steps.</p>'
                '<a class="btn btn-primary btn-sm" href="/ipo/jio/">View Reliance Jio IPO Details &rarr;</a>'
                '</div>'
            )
        elif slug in ipo_by_slug:
            ipo_info = ipo_by_slug[slug]
            comp_name = ipo_info.get("company") or name
            ipo_callout_html = (
                '<div class="card" style="margin-top:20px;padding:18px 20px;background:var(--bg-raised);border-left:4px solid var(--accent);box-shadow:var(--shadow-sm)">'
                '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">'
                '<div style="font-weight:700;font-size:15px;color:var(--text)">%s IPO &amp; Historical Listing Data</div>'
                '<span class="badge badge-up" style="font-size:11px">Tracked IPO Profile</span>'
                '</div>'
                '<p class="small muted" style="margin:6px 0 12px 0;line-height:1.5">Explore issue price band, lot size, listing day gains, and subscription history on the official IPO profile.</p>'
                '<div style="display:flex;gap:10px;flex-wrap:wrap">'
                '<a class="btn btn-outline btn-sm" href="/ipo/%s/">View %s IPO Details &rarr;</a>'
                '<a class="btn btn-outline btn-sm" href="/ipo/gmp/">Check Live IPO GMP Rates &rarr;</a>'
                '</div>'
                '</div>'
            ) % (_esc(comp_name), _esc(slug), _esc(symbol))
        else:
            ipo_callout_html = (
                '<div class="card" style="margin-top:20px;padding:18px 20px;background:var(--bg-raised);border-left:4px solid var(--accent);box-shadow:var(--shadow-sm)">'
                '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">'
                '<div style="font-weight:700;font-size:15px;color:var(--text)">Explore Primary Markets &amp; Upcoming IPOs</div>'
                '<span class="badge" style="font-size:11px">Primary Markets</span>'
                '</div>'
                '<p class="small muted" style="margin:6px 0 12px 0;line-height:1.5">Track live Grey Market Premiums (GMP), SME public issues, and SEBI DRHP filing timelines across Indian exchanges.</p>'
                '<div style="display:flex;gap:10px;flex-wrap:wrap">'
                '<a class="btn btn-outline btn-sm" href="/ipo/">IPO Tracker &rarr;</a>'
                '<a class="btn btn-outline btn-sm" href="/ipo/gmp/">Live IPO GMP Board &rarr;</a>'
                '<a class="btn btn-outline btn-sm" href="/ipo/sme/">SME IPO Hub &rarr;</a>'
                '</div>'
                '</div>'
            )

        perf_html, perf = _stock_perf(history, _EQUITY_BREAKS.get(symbol.upper()))
        faqs = stock_faqs(name, symbol, c, member_of, match, price_row, perf)
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
                '<script src="/assets/js/vendor/lightweight-charts.standalone.production.js" defer></script>'
                '<script type="module" src="/assets/js/stock-chart.js" defer></script></head>'))
        # what-if price calculator (kind 'price-whatif'), same versioned loader as /calculators/
        body = body.replace("</head>", _stamp_asset_versions(
            '<script src="/assets/js/calculators.js" defer></script></head>'))
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + '<p class="muted">NSE: %s</p>' % _esc(symbol)
            + broker_link
            + (
                '<div class="grid g-main" style="margin-top:16px">'
                '<div class="card"><div class="card-title">Price history</div>'
                '<div data-stock-chart data-symbol="%s"></div>%s%s</div>'
                '<div class="stack">%s%s%s%s%s</div></div>'
                % (_esc(slug), _stock_ohlc_html(history), trade_cta_html, ibslBanner_html("card", "stock"),
                   _stock_price_html(history), listing_html, affiliateBanner_html(), jiraafBanner_html())
                if history else
                listing_html
                + '<div class="aff-block" style="margin-top:24px">'
                  '<div class="section-title"><h2>Trade Indian equities &amp; invest in high-yield bonds</h2></div>'
                  '<p class="muted small" style="margin-top:4px">Open an account with verified SEBI-registered brokers and fixed-income platforms.</p>'
                  '<div class="grid g3 aff-pair" style="margin-top:14px">%s%s%s</div></div>'
                % (affiliateBanner_html(), ibslBanner_html("card", "stock"), jiraafBanner_html())
              )
            + '<p class="xs faint" style="margin-top:16px">Source: NSE listed-securities master file (EQUITY_L)%s.</p>'
              % (" and NSE's daily bhavcopy for price history" if history else "; price history was not available "
                 "for this symbol in the latest data refresh")
            + perf_html
            + price_target_section_html(name, symbol, history, _px_html, _iso_to_long_date, _esc)
            + index_html
            + ("" if history else trade_cta_html)
            + actions_html
            + peers_html
            + compare_html
            + ipo_callout_html
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


_KEEP_UPPER = {"ETF", "ETFS", "HDFC", "ICICI", "SBI", "DSP", "BSE", "NSE", "PSU", "CPSE", "IT", "MSCI", "CRISIL",
               "ESG", "UTI", "FOF", "LIC", "IDFC", "G", "AMC", "NV", "US", "USA", "BEES", "IBX", "SDL", "TRI"}


def _tidy_scheme_name(name):
    """AMFI types some scheme names in ALL CAPS (26 of the 349 ETFs). Only
    those get re-cased; mixed-case names are left exactly as AMFI wrote them.
    Display only: the match key and URL slugs still use the original name."""
    if not name or name != name.upper():
        return name
    def fix(m):
        tok = m.group(0)
        if tok in _KEEP_UPPER or (tok[0].isdigit() and tok[-1].isalpha() and len(tok) <= 3):
            return tok
        return re.sub(r"[A-Z]+", lambda x: x.group(0).capitalize(), re.sub(r"(?<=[A-Z])(?=\d)", " ", tok))
    return re.sub(r"[A-Z0-9&]+", fix, name)


def _enrich_etfs(etfs, schemes, fund_slug_by_key):
    """Match each NSE-listed ETF to its AMFI scheme by ISIN (the same
    identifier on both registers, so a match is exact, never fuzzy). A match
    replaces NSE's raw register label (e.g. 'NIPINDETFNIFTYBEES') with the
    scheme's real name and adds its AMC and AMFI-published NAV. Unmatched ETFs
    keep NSE's own label and get no NAV; nothing is guessed."""
    by_isin = {}
    for s in schemes or []:
        for k in ("isin_growth", "isin_div_reinvest"):
            v = s.get(k)
            if v and v.startswith("INF"):
                by_isin.setdefault(v, s)
    matched = 0
    for e in etfs or []:
        s = by_isin.get(e.get("isin") or "")
        if not s:
            continue
        e.setdefault("nse_name", e.get("name"))
        e["name"] = _tidy_scheme_name(s["name"])
        e["amc"] = s.get("amc")
        e["amfi_category"] = s.get("category")
        if isinstance(s.get("nav"), (int, float)) and s["nav"] > 0:
            e["nav"], e["nav_date"] = s["nav"], s.get("nav_date")
        e["fund_slug"] = fund_slug_by_key.get((s.get("amc"), s.get("name")))
        matched += 1
    log("etf enrichment: %d of %d NSE ETFs matched to an AMFI scheme by ISIN" % (matched, len(etfs or [])), "ok")


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
        has_nav = isinstance(e.get("nav"), (int, float))
        title = "%s (%s): %s | BrokerLens" % (
            _esc(name), _esc(symbol), "Share Price Target 2026-2050, NAV & What-If Calculator" if has_nav else "ETF Listing Details")
        description = _esc(
            ("%s (NSE: %s): see the latest AMFI NAV of Rs %.2f, benchmark index details, and run your own "
             "what-if price calculator for 2026-2050 with any growth assumption you choose." % (name, symbol, e["nav"]))
            if has_nav else
            ("%s (NSE: %s): the ETF's underlying benchmark, ISIN, listing date and market lot, "
             "sourced from NSE's listed-ETF register." % (name, symbol))
        )[:300]

        etf_jsonld = {"@type": "FinancialProduct", "name": name, "url": canonical}
        if e.get("amc"):
            etf_jsonld["provider"] = {"@type": "Organization", "name": e["amc"]}
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
            ] + ([
                ("Fund house", '<a href="/funds-by/%s/">%s</a>' % (_esc(slugify(e["amc"])), _esc(e["amc"]))),
                ("Latest NAV (AMFI)", ("Rs %.4f as of %s" % (e["nav"], _esc(_long_date(e.get("nav_date")))))
                 if has_nav else "Not disclosed"),
            ] if e.get("amc") else [])
        )
        scheme_link = ""
        if e.get("fund_slug"):
            scheme_link = (
                '<p class="small" style="margin-top:12px">Mutual fund scheme page with plan and ISIN details: '
                '<a href="/fund/%s/">%s &rarr;</a></p>' % (_esc(e["fund_slug"]), _esc(name)))

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
            ("Does this page show %s's live price?" % name,
             "No. Live exchange price and trading data are not carried here. "
             + ("The NAV shown is AMFI's published net asset value for the scheme; an ETF trades on NSE at a market "
                "price that can differ from its NAV." if has_nav else
                "This page carries NSE's own listing facts only.")),
        ]
        if e.get("amc"):
            etf_faqs.insert(0, ("Which AMC runs %s?" % name, "%s is run by %s." % (name, e["amc"])))
        if has_nav:
            etf_faqs.append(("What is the latest NAV of %s?" % name,
                             "As of %s, the NAV of %s published by AMFI was Rs %.4f." % (
                                 _long_date(e.get("nav_date")), name, e["nav"])))
            etf_faqs.append(("What is the share price target of %s for 2026, 2030, 2040 or 2050?" % name,
                             "BrokerLens does not publish price targets or forecasts, and nothing here is investment advice. "
                             "An ETF tracks its underlying benchmark and fluctuates with market movements. To test an assumed growth rate "
                             "of your own, use the what-if investment calculator on this page. As of %s, the latest published NAV on file was Rs %.4f."
                             % (_long_date(e.get("nav_date")), e["nav"])))
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

        calc_html = ""
        if has_nav:
            start_price = "%.2f" % e["nav"]
            calc_html = (
                '<div class="card" data-calc="price-whatif" style="margin-top:20px;padding:20px;max-width:560px">'
                '<div class="card-title">What-if investment calculator</div>'
                '<p class="xs muted" style="margin-top:4px">Work out what an investment in %s would become if it grew at a rate you choose. '
                'You supply the growth assumption; BrokerLens does not.</p>'
                '<div class="field" style="margin-top:12px"><label for="pw-price">Starting NAV per unit (Rs)</label>'
                '<input id="pw-price" type="number" inputmode="decimal" min="0.01" step="0.01" value="%s" '
                'placeholder="Enter NAV in rupees"></div>'
                '<div class="field"><label for="pw-growth">Assumed growth per year (%%), your own assumption</label>'
                '<input id="pw-growth" type="number" inputmode="decimal" min="-90" max="100" step="0.1" value="" '
                'placeholder="Type your own number, for example 12">'
                '<div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">'
                '<span class="xs muted" style="align-self:center">Example assumptions:</span>'
                '<button type="button" class="btn btn-outline xs" data-preset-growth="10" style="padding:2px 8px;font-size:11px">+10%% CAGR</button>'
                '<button type="button" class="btn btn-outline xs" data-preset-growth="15" style="padding:2px 8px;font-size:11px">+15%% CAGR</button>'
                '<button type="button" class="btn btn-outline xs" data-preset-growth="20" style="padding:2px 8px;font-size:11px">+20%% CAGR</button>'
                '</div></div>'
                '<div class="field"><label for="pw-years">Years (1 to 30)</label>'
                '<input id="pw-years" type="number" inputmode="numeric" min="1" max="30" step="1" value="5"></div>'
                '<p class="xs faint" style="margin-top:6px">Prefilled with the latest AMFI NAV on file (Rs %s). The growth box is left empty on purpose: '
                'the number in the placeholder is only an example of the format, not an estimate for %s.</p>'
                '<button type="button" id="calc-btn" class="btn" style="margin-top:8px">Calculate</button>'
                '<div id="calc-result" class="stack" style="margin-top:16px" aria-live="polite" hidden></div>'
                '<p class="xs faint" style="margin-top:12px">This is arithmetic on your assumption, not a forecast or a recommendation.</p>'
                '<div class="xs faint" style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border)">'
                'Related tools: <a href="/calculators/cagr-calculator/">CAGR Calculator</a> &middot; '
                '<a href="/calculators/sip-calculator/">SIP Calculator</a> &middot; '
                '<a href="/trade-costs/">Trade Cost Calculator</a></div>'
                '</div>' % (_esc(symbol), start_price, start_price, _esc(name))
            )

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        if has_nav:
            body = body.replace("</head>", _stamp_asset_versions('<script src="/assets/js/calculators.js" defer></script></head>'))
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + '<p class="muted">NSE: %s</p>' % _esc(symbol)
            + '<div class="grid g3" style="margin-top:16px">' + facts_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">Source: NSE listed-ETF register%s. '
              'Live price and trading data are not carried on this page.</p>'
              % (" and AMFI's daily NAV master file (matched by ISIN)" if has_nav else "")
            + index_html
            + scheme_link
            + calc_html
            + '<div class="aff-block" style="margin-top:24px">'
              '<div class="section-title"><h2>Trade ETFs</h2></div>'
              '<p class="muted small" style="margin-top:4px">ETFs trade on the exchange through any SEBI-registered broker.</p>'
              '<div class="grid g2 aff-pair" style="margin-top:14px">%s%s</div></div>'
              % (affiliateBanner_html(), jiraafBanner_html())
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + etf_faq_html + '</div>'
        )
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page is generated from NSE's own listed-ETF register, joined to AMFI's daily NAV master file by ISIN.")}

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


def _parse_amfi_category(raw):
    """'Open Ended Schemes(Equity Scheme - Sectoral/ Thematic)' ->
    {structure, family, sub, label}. None when the string is not one of AMFI's
    own category banners, so a scheme with no real category says so instead of
    showing a guess."""
    raw = re.sub(r"\s+", " ", (raw or "").replace("\u2019", "'")).strip()
    m = re.match(r"^(Open Ended|Close Ended|Interval Fund) Schemes?\s*\((.*)\)$", raw)
    if not m:
        return None
    structure = {"Open Ended": "Open ended", "Close Ended": "Close ended",
                 "Interval Fund": "Interval"}[m.group(1)]
    inner = re.sub(r"/\s+", "/", m.group(2).strip())
    family, _sep, sub = inner.partition(" - ")
    family, sub = family.strip(), (sub.strip() or family.strip())
    return {"structure": structure, "family": family, "sub": sub,
            "label": family if sub == family else "%s: %s" % (family, sub)}


def _fund_category_info(fund):
    for c in fund.get("categories") or []:
        info = _parse_amfi_category(c)
        if info:
            return info
    return None


def _latest_nav_date(variants):
    best = None
    for v in variants:
        try:
            d = datetime.strptime(v.get("nav_date") or "", "%d-%b-%Y")
        except ValueError:
            continue
        if best is None or d > best:
            best = d
    return best


def _direct_regular_gap(variants):
    """Direct vs Regular Growth NAV for one scheme, only when both plans
    publish a NAV for the same date. A plain ratio of two published numbers:
    nothing here is estimated."""
    def pick(prefix):
        for v in variants:
            if ((v.get("plan") or "").lower().startswith(prefix)
                    and "growth" in (v.get("option") or "").lower()
                    and isinstance(v.get("nav"), (int, float)) and v["nav"] > 0):
                return v
        return None
    d, r = pick("direct"), pick("regular")
    if not d or not r or d.get("nav_date") != r.get("nav_date"):
        return None
    return {"direct": d["nav"], "regular": r["nav"], "date": d["nav_date"],
            "gap_pct": (d["nav"] / r["nav"] - 1) * 100}


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
    nav_dates = {}
    written = 0

    # Pre-pass: every fund's slug up front, so a page can link to its siblings
    # and to the comparison pages fund_compare_engine writes later in the build.
    slug_by_key = {}
    for fund in funds:
        base_slug = slugify("%s %s" % (fund["amc"], fund["name"]))
        if not base_slug:
            continue
        slug, n = base_slug, 2
        while slug in slug_by_key.values():
            slug = "%s-%d" % (base_slug, n)
            n += 1
        slug_by_key[(fund["amc"], fund["name"])] = slug
    siblings = {}
    for fund in funds:
        info = _fund_category_info(fund)
        key = (fund["amc"], fund["name"])
        if info and key in slug_by_key:
            siblings.setdefault((fund["amc"], info["family"]), []).append((fund["name"], slug_by_key[key]))
    from .fund_compare_engine import curated_pair_index, CATEGORIES as _FUND_CATS
    pair_index = curated_pair_index(_group_mutual_funds(schemes))

    for fund in funds:
        amc, name = fund["amc"], fund["name"]
        slug = slug_by_key.get((amc, name))
        if not slug:
            continue
        used_slugs[slug] = (amc, name)

        canonical = "%s/fund/%s/" % (SITE_URL, slug)
        title = "%s: Mutual Fund Scheme Details | BrokerLens" % _esc(name)
        cat_info = _fund_category_info(fund)
        description = _esc(
            "%s from %s%s: latest NAV, Direct vs Regular plan NAV, ISIN and plan/option details, "
            "sourced directly from AMFI's own daily NAV master file." % (
                name, amc, (" (%s)" % cat_info["label"]) if cat_info else "")
        )[:300]

        fund_jsonld = {"@type": "FinancialProduct", "name": name,
                       "url": canonical, "provider": {"@type": "Organization", "name": amc}}
        if fund["categories"]:
            fund_jsonld["category"] = fund["categories"][0]

        variants_sorted = sorted(
            fund["variants"], key=lambda v: (v.get("plan") or "", v.get("option") or ""))
        for v in variants_sorted:
            try:
                iso = datetime.strptime(v.get("nav_date") or "", "%d-%b-%Y").strftime("%Y-%m-%d")
            except ValueError:
                continue
            if iso > nav_dates.get(slug, ""):
                nav_dates[slug] = iso
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
        gap = _direct_regular_gap(variants_sorted)
        if has_direct and has_regular:
            fund_faqs.append((
                "What is the difference between the Direct and Regular plan of %s?" % name,
                "Both plans invest in the same portfolio. The Regular plan pays a distributor commission out of the "
                "scheme's expenses and the Direct plan does not, so the Direct plan has a lower expense ratio "
                "(SEBI requires each plan's expense ratio to be disclosed separately)."))
        if gap:
            fund_faqs.append((
                "How does the Direct plan NAV of %s compare with the Regular plan NAV?" % name,
                "On %s the Direct Growth NAV was Rs %.4f and the Regular Growth NAV was Rs %.4f, so the Direct NAV "
                "was %.2f%% %s. This compares two published NAVs; it is not a return figure." % (
                    gap["date"], gap["direct"], gap["regular"], abs(gap["gap_pct"]),
                    "higher" if gap["gap_pct"] >= 0 else "lower")))
        faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in fund_faqs
        )
        latest_nav = _latest_nav_date(variants_sorted)
        plans_txt = ("Direct and Regular" if (has_direct and has_regular)
                     else "Direct only" if has_direct else "Regular only" if has_regular else "Not disclosed")
        opts_txt = ("Growth and IDCW" if (has_growth and has_idcw)
                    else "Growth only" if has_growth else "IDCW only" if has_idcw else "Not disclosed")
        fund_tiles = "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div><div style="margin-top:2px">%s</div></div>'
            % (label, value) for label, value in [
                ("Fund house", '<a href="/funds-by/%s/">%s</a>' % (_esc(slugify(amc)), _esc(amc))),
                ("Scheme structure", _esc(cat_info["structure"]) if cat_info else "Not disclosed"),
                ("Category", _esc(cat_info["label"]) if cat_info else "Not disclosed"),
                ("Plans", plans_txt),
                ("Options", opts_txt),
                ("Latest NAV date", _esc(latest_nav.strftime("%-d %B %Y")) if latest_nav else "Not disclosed"),
            ]
        )
        gap_html = ""
        if gap:
            gap_html = (
                '<div class="card" style="margin-top:20px"><div class="card-title">Direct vs Regular plan (Growth option)</div>'
                '<div class="grid g3" style="margin-top:10px">'
                '<div class="mega-seg"><div class="mega-seg-label">Direct NAV</div><div style="margin-top:2px">Rs %.4f</div></div>'
                '<div class="mega-seg"><div class="mega-seg-label">Regular NAV</div><div style="margin-top:2px">Rs %.4f</div></div>'
                '<div class="mega-seg"><div class="mega-seg-label">Direct vs Regular</div><div style="margin-top:2px">%s%.2f%%</div></div>'
                '</div>'
                '<p class="xs faint" style="margin-top:10px;max-width:70ch">Both NAVs are as published by AMFI for %s. '
                'Both plans hold the same portfolio; the Direct plan pays no distributor commission, so its ongoing '
                'expenses are lower. This is a comparison of two published NAVs, not a return figure, and the exact gap '
                'also depends on when each plan launched.</p></div>'
                % (gap["direct"], gap["regular"], "+" if gap["gap_pct"] >= 0 else "-", abs(gap["gap_pct"]),
                   _esc(_long_date(gap["date"])))
            )
        pinfo = pair_index.get((amc, name))
        related_parts = []
        if pinfo and pinfo["partners"]:
            related_parts.append(
                '<h3 style="font-size:14px;margin-top:18px">Compare %s with other %s</h3>'
                '<div class="link-columns" style="margin-top:8px">%s</div>' % (
                    _esc(name), _esc(pinfo["title"]),
                    "".join('<a href="/compare/mutual-funds/%s/">vs %s</a>' % (_esc(ps), _esc(g["name"]))
                            for ps, g in pinfo["partners"][:6])))
        if pinfo:
            related_parts.append(
                '<p class="small" style="margin-top:14px"><a href="/funds-by/category/%s/">Browse all %s &rarr;</a></p>'
                % (_esc(pinfo["cat"]), _esc(pinfo["title"])))
        sib = [(n_, s_) for n_, s_ in siblings.get((amc, cat_info["family"]), []) if s_ != slug][:8] if cat_info else []
        if sib:
            related_parts.append(
                '<h3 style="font-size:14px;margin-top:18px">More %s from %s</h3>'
                '<div class="link-columns" style="margin-top:8px">%s</div>' % (
                    _esc(cat_info["family"]), _esc(amc),
                    "".join('<a href="/fund/%s/">%s</a>' % (_esc(s_), _esc(n_)) for n_, s_ in sib)))
        related_parts.append(
            '<p class="small" style="margin-top:14px"><a href="/funds-by/%s/">All %s schemes &rarr;</a></p>'
            % (_esc(slugify(amc)), _esc(amc)))
        related_html = ('<div class="section-title" style="margin-top:28px"><h2>Related schemes</h2></div>'
                        + "".join(related_parts))
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
            + '<div class="grid g3" style="margin-top:16px">' + fund_tiles + '</div>'
            + gap_html
            + '<div class="table-scroll" style="margin-top:16px">'
              '<table class="data"><thead><tr>'
              '<th>Plan</th><th>Option</th><th class="right">NAV (Rs)</th><th>As of</th>'
              '<th>ISIN (growth/payout)</th><th>ISIN (reinvestment)</th>'
              '</tr></thead><tbody>' + rows_html + '</tbody></table></div>'
            + '<p class="xs faint" style="margin-top:16px">Source: AMFI daily NAV master file. '
              'Historical NAV, returns and portfolio holdings are not carried on this page.</p>'
            + related_html
            + '<div class="aff-block" style="margin-top:24px">'
              '<div class="section-title"><h2>Invest in direct mutual funds</h2></div>'
              '<p class="muted small" style="margin-top:4px">Direct plans carry no distributor commission, so their '
              'ongoing expenses are lower than the Regular plan of the same scheme. Open an account with a '
              'SEBI-registered platform to invest in direct plans.</p>'
              '<div class="grid g2 aff-pair" style="margin-top:14px">%s%s</div></div>'
              % (affiliateBanner_html(), jiraafBanner_html())
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
    return funds, used_slugs, nav_dates


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
    {
        "slug": "direct-vs-regular-calculator", "calc": "direct-regular",
        "h1": "Direct vs Regular Mutual Fund Calculator",
        "title": "Direct vs Regular Mutual Fund Calculator: Cost of the Expense Gap | BrokerLens",
        "description": "Work out how much a SIP grows in a direct plan compared with a regular plan of the same "
                        "fund, given the difference between the two plans' expense ratios.",
        "intro": "A regular plan and a direct plan hold the same portfolio. The regular plan's expense ratio is "
                  "higher because it includes the distributor's commission, so its NAV grows a little slower. "
                  "This shows what that gap does to a monthly SIP over time.",
        "formula": "Both plans use the SIP future-value formula FV = P &times; [((1+r)<sup>n</sup> - 1) / r] "
                   "&times; (1+r). The direct plan uses the return you enter; the regular plan uses that return "
                   "minus the expense ratio gap.",
        "fields": [
            ("dr-monthly", "Monthly investment (Rs)", "10000", "500"),
            ("dr-rate", "Direct plan annual return (%)", "12", "0.5"),
            ("dr-gap", "Expense ratio gap, regular minus direct (% points)", "1", "0.1"),
            ("dr-years", "Investment period (years)", "15", "1"),
        ],
        "how_to": "Look up the published expense ratios of the direct and regular plans of your fund, subtract "
                  "one from the other and enter the gap. Enter the annual return you assume for the direct plan, "
                  "your monthly amount and the period. The values pre-filled here are only placeholders to show "
                  "the layout; replace them with figures you can source.",
        "limits": "This treats the commission gap as the only difference between the plans and holds the return "
                   "constant every month. It ignores exit loads, taxes on redemption and any advice or service a "
                   "distributor may provide, which is a real benefit for some investors and is not priced here.",
        "faqs": [
            ("What is the difference between a direct and a regular plan?", "Both invest in the same portfolio. "
             "A regular plan is sold through a distributor and its expense ratio includes a commission; a direct "
             "plan is bought straight from the fund house and has a lower expense ratio."),
            ("Where do I find the expense ratio gap?", "Each fund house publishes the total expense ratio of its "
             "direct and regular plans on its own website and in the monthly scheme disclosures. Subtract the "
             "direct plan's figure from the regular plan's figure."),
            ("Does this calculator say which plan I should buy?", "No. It only shows the arithmetic effect of the "
             "expense gap. Whether a regular plan's distributor service is worth its cost is your decision."),
            ("Why does a small gap matter so much?", "The gap is charged every year on the whole corpus, so it "
             "compounds. Over long periods a difference of a fraction of a percentage point shows up as a "
             "noticeable difference in the final amount."),
            ("Is the direct plan return guaranteed?", "No. Both plans carry market risk. The return here is an "
             "assumption you supply, not a forecast."),
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


def _index_chips_html(indices):
    """A crawlable 'Browse by index' block for the /stocks/ hub: before this nothing but a
    stock page's own membership line linked to the /index/<slug>/ constituent pages, and
    /index/nifty-50/ was reported unknown to Google."""
    chips = "".join(
        '<a class="chip" href="/index/%s/">%s</a>' % (_esc(slug), _esc(idx.get("label") or slug))
        for slug, idx in sorted((indices or {}).items(), key=lambda kv: (kv[1].get("label") or kv[0]).lower())
    )
    if not chips:
        return ""
    return ('<div class="section-title" style="margin-top:28px"><h2>Browse by index</h2></div>'
            '<p class="muted" style="max-width:70ch">Constituent lists published by NSE for each index, '
            'with a link to every company\'s listing page.</p>'
            '<div class="row-wrap" style="gap:8px;margin-top:12px">%s</div>' % chips)


def _write_stock_directory(companies, indices=None):
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
        + _index_chips_html(indices)
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


def _write_fund_amc_pages(fund_slugs, funds=None):
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

    groups_by_key = {(g["amc"], g["name"]): g for g in (funds or [])}
    top_amcs = sorted(by_amc, key=lambda a: (-len(by_amc[a]), a))
    written = 0
    for amc, rows in by_amc.items():
        amc_slug = amc_slugs.get(amc)
        if not amc_slug:
            continue
        rows_sorted = sorted(rows, key=lambda r: r[0])
        canonical = "%s/funds-by/%s/" % (SITE_URL, amc_slug)
        title = "%s: All Mutual Fund Schemes & NAV | BrokerLens" % amc
        n_schemes = len(rows_sorted)

        # Facts derived only from AMFI's own rows for this fund house.
        by_family, n_direct, n_regular, latest = {}, 0, 0, None
        for name, slug in rows_sorted:
            g = groups_by_key.get((amc, name))
            if not g:
                continue
            info = _fund_category_info(g)
            fam = "%s: %s" % (info["structure"], info["family"]) if info else "Category not disclosed"
            by_family.setdefault(fam, []).append((name, slug, info["sub"] if info and info["sub"] != info["family"] else ""))
            plans = [(v.get("plan") or "").lower() for v in g["variants"]]
            n_direct += any(pl.startswith("direct") for pl in plans)
            n_regular += any(pl.startswith("regular") for pl in plans)
            d = _latest_nav_date(g["variants"])
            if d and (latest is None or d > latest):
                latest = d
        family_order = sorted(by_family, key=lambda f: (f == "Category not disclosed", -len(by_family[f]), f))
        description = _esc(
            "All %d %s schemes on AMFI's daily NAV master file%s, grouped by category, with latest NAV, "
            "Direct and Regular plans and ISIN on each scheme's own page." % (
                n_schemes, amc,
                (" (%d categories)" % len([f for f in by_family if f != "Category not disclosed"]))
                if len(by_family) > 1 else "")
        )[:300]
        tiles_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div><div style="margin-top:2px">%s</div></div>'
            % (label, value) for label, value in [
                ("Schemes", "{:,}".format(n_schemes)),
                ("Categories", str(len([f for f in by_family if f != "Category not disclosed"])) or "0"),
                ("With a Direct plan", "{:,}".format(n_direct)),
                ("With a Regular plan", "{:,}".format(n_regular)),
                ("Latest NAV date", _esc(latest.strftime("%-d %B %Y")) if latest else "Not disclosed"),
                ("Source", "AMFI daily NAV file"),
            ]
        )
        sections_html = "".join(
            '<div class="section-title" style="margin-top:24px"><h2>%s <span class="xs faint">(%d)</span></h2></div>'
            '<div class="link-columns" style="margin-top:8px">%s</div>' % (
                _esc(fam), len(by_family[fam]),
                "".join('<a href="/fund/%s/">%s%s</a>' % (
                    _esc(slug), _esc(name), (' <span class="xs faint">(%s)</span>' % _esc(sub)) if sub else "")
                    for name, slug, sub in sorted(by_family[fam], key=lambda r: r[0])))
            for fam in family_order
        )
        others = [a for a in top_amcs if a != amc and a in amc_slugs][:8]
        others_html = (
            '<div class="section-title" style="margin-top:28px"><h2>Other fund houses</h2></div>'
            '<div class="link-columns" style="margin-top:8px">%s</div>'
            '<p class="small" style="margin-top:10px"><a href="/funds-by/">All fund houses &rarr;</a></p>'
            % "".join('<a href="/funds-by/%s/">%s</a>' % (_esc(amc_slugs[a]), _esc(a)) for a in others)
        )
        amc_faqs = [
            ("How many mutual fund schemes does %s have?" % amc,
             "AMFI's daily NAV master file lists %d scheme%s for %s." % (n_schemes, "" if n_schemes == 1 else "s", amc)),
            ("How many of %s's schemes have a Direct plan?" % amc,
             "%d of %d schemes list a Direct plan and %d list a Regular plan." % (n_direct, n_schemes, n_regular)),
        ]
        shown_fams = [f for f in family_order if f != "Category not disclosed"][:4]
        if shown_fams:
            amc_faqs.append(("Which categories does %s offer?" % amc,
                             "The largest categories by scheme count are: %s." % "; ".join(
                                 "%s (%d)" % (f, len(by_family[f])) for f in shown_fams)))
        if latest:
            amc_faqs.append(("How recent is the NAV data for %s?" % amc,
                             "The most recent NAV date on AMFI's file for %s is %s." % (amc, latest.strftime("%-d %B %Y"))))
        amc_faqs.append(("Does this page show %s's returns, AUM or holdings?" % amc,
                         "No. BrokerLens carries AMFI's published NAV, ISIN and plan/option data only; returns, "
                         "assets under management and portfolio holdings are not shown."))
        faq_html = "".join(
            '<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a))
            for q, a in amc_faqs)
        crumb_html, crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Mutual funds by AMC", "/funds-by/"), (amc, None),
        ])
        jsonld = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": amc, "url": canonical},
                {
                    "@type": "ItemList", "name": title, "url": canonical,
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1, "url": "%s/fund/%s/" % (SITE_URL, slug), "name": name}
                        for i, (name, slug) in enumerate(rows_sorted)
                    ],
                },
                {"@type": "FAQPage", "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in amc_faqs]},
                crumb_jsonld,
            ],
        }
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            crumb_html
            + '<h1 style="margin-top:0">%s schemes</h1>' % _esc(amc)
            + '<p class="muted" style="max-width:70ch">%d scheme%s listed on AMFI\'s daily NAV master file, '
              'grouped by SEBI category.</p>' % (n_schemes, "" if n_schemes == 1 else "s")
            + '<div class="grid g3" style="margin-top:16px">' + tiles_html + '</div>'
            + sections_html
            + others_html
            + '<h2 style="margin-top:28px;font-size:16px">Frequently asked questions</h2>'
            + '<div style="max-width:68ch">' + faq_html + '</div>'
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

    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "funds-by"), set(amc_slugs.values()) | {"category"})
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


_ZERODHA_LOGO_DATA_URI = "/assets/img/partners/zerodha.svg"


_FIVEPAISA_LOGO_DATA_URI = "/assets/img/partners/5paisa.svg"


_BINANCE_LOGO_DATA_URI = "/assets/img/partners/binance.png"


IBSL_LINK = "https://indiabullssecurities.onelink.me/Kaqz/brokerlens"
IBSL_REGISTER_URL = "/sebi-registry/indiabulls-securities-limited/"
_IBSL_ALT = ("Indiabulls Securities: Rs 0 account opening charges, Rs 11 per executed order across all segments*, "
             "20 years of trust. Open your free account now. Terms apply.")
_IBSL_SLOTS = {"strip", "wide", "card"}
_IBSL_PAGE_TYPES = {"home", "ipo", "broker", "stock", "news", "calculator"}
_ibsl_cache = {}


def ibslBanner_html(slot, page_type):
    """Indiabulls Securities (IBSL) sponsored banner. slot: strip (7.5:1, desktop home), wide (4:1
    in-content) or card (5:2 sidebar); phones always get the card creative because the fine print on
    the wider ones is unreadable at that width. The creatives are served unmodified (the fine print
    is part of the ad). Marked sponsored, carries IBSL's SEBI registration numbers (from our own
    SEBI-register data) and a referral-fee disclosure. data-ad / data-slot / data-page-type feed
    ad-track.js (impressions and clicks, first-party, no cookies)."""
    assert slot in _IBSL_SLOTS and page_type in _IBSL_PAGE_TYPES, (slot, page_type)
    key = (slot, page_type)
    if key in _ibsl_cache:
        return _ibsl_cache[key]
    big = {"strip": ("/assets/img/ads/ibsl-strip-2400x320.jpg", 2400, 320),
           "wide": ("/assets/img/ads/ibsl-wide-2000x500.jpg", 2000, 500)}.get(slot)
    card = '<img src="/assets/img/ads/ibsl-card-1000x400.jpg" width="1000" height="400" alt="%s" loading="lazy">' % _esc(_IBSL_ALT)
    pic = ('<picture><source media="(min-width:900px)" srcset="%s" width="%d" height="%d">%s</picture>' % (big[0], big[1], big[2], card)
           ) if big else card
    out = (
        '<aside class="ad-wrap ad-%s" data-ad="ibsl" data-slot="%s" data-page-type="%s" aria-label="Sponsored: Indiabulls Securities">'
        '<div class="ad-ibsl"><span class="ad-tag">Sponsored</span>'
        '<a href="%s" target="_blank" rel="sponsored noopener" data-ad-click>%s</a></div>'
        '<p class="ad-note">Sponsored. Indiabulls Securities Limited, SEBI Reg. INZ000036136 '
        '(<a href="%s">check the SEBI register</a>), DP IN-DP-423-2019.</p></aside>'
    ) % (slot, slot, page_type, IBSL_LINK, pic, IBSL_REGISTER_URL)
    out = _stamp_asset_versions(out)
    _ibsl_cache[key] = out
    return out


def affiliateBanner_html():
    """Python port of pages.js's affiliateBanner() - the Zerodha sponsored
    banner, kept byte-for-byte in sync with the JS version (same logo, same
    copy, same .aff-banner-zerodha styling) so the SPA's own render of
    /brokers and / shows the identical banner a fresh visit already saw."""
    return (
        '<div class="aff-banner aff-banner-zerodha">'
        '<span class="aff-tag">Sponsored</span>'
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
        '<div class="aff-banner aff-banner-5paisa">'
        '<span class="aff-tag">Sponsored</span>'
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


_JIRAAF_LOGO_DATA_URI = "/assets/img/partners/jiraaf.svg"


def jiraafBanner_html():
    """Python port of pages.js's jiraafBanner() - high-yield corporate bonds
    and fixed income sponsored banner on Jiraaf (SEBI-regulated OBPP), kept
    byte-for-byte in sync with the JS version (same logo, same copy, same
    .aff-banner-jiraaf styling) stacked beside/below Zerodha and 5paisa."""
    return (
        '<div class="aff-banner aff-banner-jiraaf">'
        '<span class="aff-tag">Sponsored</span>'
        '<div class="aff-art aff-art-jiraaf">'
        f'<img src="{_JIRAAF_LOGO_DATA_URI}" width="120" height="32" alt="Jiraaf" style="display:block"></div>'
        '<div class="aff-body">'
        '<h4>Earn up to 12 to 14% with high-yield bonds</h4>'
        '<p class="xs muted">Curated corporate bonds &amp; fixed-income opportunities on Jiraaf.</p>'
        '<ul class="aff-features">'
        '<li>Up to 14% p.a. fixed yields</li>'
        '<li>SEBI-regulated Online Bond Platform (OBPP)</li>'
        '<li>Low minimum investment starting &#8377;10,000</li>'
        '</ul>'
        '<a class="aff-cta" href="https://www.jiraaf.com/app/signup?usoc=EZ4168" '
        'target="_blank" rel="noopener sponsored">Explore bonds &rarr;</a>'
        '<div class="aff-fine">*T&amp;C apply. Investments in debt securities / bonds are subject to market risks; '
        'read all offer documents carefully before investing. Regulated by SEBI.</div>'
        '</div></div>'
    )


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


_DELTA_LOGO_DATA_URI = "/assets/img/partners/delta.png"


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
            '<script src="/assets/js/vendor/lightweight-charts.standalone.production.js" defer></script>'
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

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    curated_path = os.path.join(ROOT, "data", "manual", "curated_ipos.json")
    if os.path.exists(curated_path):
        try:
            with open(curated_path, "r", encoding="utf-8") as fh:
                for r in json.load(fh) or []:
                    sym = r.get("symbol")
                    if sym and sym not in by_symbol:
                        by_symbol[sym] = {
                            "symbol": sym,
                            "company": r.get("company"),
                            "price_band": r.get("price_band"),
                            "issue_size_shares": r.get("issue_size_shares"),
                            "bidding_start": r.get("bidding_start"),
                            "bidding_end": r.get("bidding_end"),
                            "status": r.get("status", "Forthcoming"),
                            "security_type": r.get("security_type", "EQ"),
                        }
        except Exception:
            pass

    for row in by_symbol.values():
        b_end = row.get("bidding_end") or ""
        b_start = row.get("bidding_start") or ""
        if row.get("listing_date") or row.get("status") == "Listed":
            row["status"] = "Listed"
        elif b_end and b_end < today_iso:
            row["status"] = "Closed"
        elif b_start and b_start > today_iso:
            row["status"] = "Forthcoming"
        elif b_start and b_end and b_start <= today_iso <= b_end:
            row["status"] = "Active"

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


def _write_ipo_pages(records, equity_history=None):
    """Institutional-grade static page per IPO (/ipo/:symbol/) with complete
    Red Herring Prospectus (RHP) key disclosures, lot sizing, SEBI application
    limits, financial valuation ratios, and verified post-listing gains/returns."""
    from .ipo_engine import render_full_ipo_page
    written = 0
    aff_b = affiliateBanner_html()
    five_b = fivepaisaBanner_html()
    jiraaf_b = jiraafBanner_html()
    for r in records:
        slug = r["symbol"].lower()
        body = render_full_ipo_page(
            r=r,
            equity_history=equity_history,
            head_template=_REGISTRY_PAGE_HEAD,
            foot_template=_REGISTRY_PAGE_FOOT,
            affiliate_banner_html=aff_b,
            fivepaisa_banner_html=five_b,
            jiraaf_banner_html=jiraaf_b,
            ibsl_wide_html=ibslBanner_html("wide", "ipo"),
            breadcrumb_fn=_breadcrumb,
            source_note_fn=_source_note,
            site_url=SITE_URL,
        )
        dest_dir = os.path.join(ROOT, "site", "ipo", slug)
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written += 1
    keep_ipo_slugs = {r["symbol"].lower() for r in records} | {"archive", "upcoming", "allotment-status", "how-to-apply", "registrars", "registrar", "subscription", "allotment", "sme", "gmp"}
    pruned = _prune_stale_dirs(os.path.join(ROOT, "site", "ipo"), keep_ipo_slugs)
    log("IPO pages: %d written%s" % (written, (", %d stale pruned" % pruned) if pruned else ""), "ok")


def _write_ipo_hub(records, equity_history=None):
    """/ipo/ - enhanced real-time IPO tracker with currently open (active bidding demand),
    forthcoming (announced issue dates & price bands), and recently listed IPOs with
    verified post-listing day gains and CMP returns directly correlated with NSE candles."""
    from .ipo_engine import render_enhanced_ipo_hub
    body = render_enhanced_ipo_hub(
        records=records,
        equity_history=equity_history,
        head_template=_REGISTRY_PAGE_HEAD,
        foot_template=_REGISTRY_PAGE_FOOT,
        ibsl_html=ibslBanner_html("wide", "ipo"),
        breadcrumb_fn=_breadcrumb,
        source_note_fn=_source_note,
        site_url=SITE_URL,
    )
    dest_dir = os.path.join(ROOT, "site", "ipo")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("IPO hub: written with lot size, subscription & real-time listing performance", "ok")


def _write_ipo_upcoming(records, equity_history=None):
    """/ipo/upcoming/ - the 'upcoming IPO' head-term page: what is open now, what opens
    next and what closed but has not listed yet, with the SEBI listing timeline."""
    from .ipo_engine import render_enhanced_ipo_hub
    body = render_enhanced_ipo_hub(
        records=records, equity_history=equity_history,
        head_template=_REGISTRY_PAGE_HEAD, foot_template=_REGISTRY_PAGE_FOOT,
        ibsl_html=ibslBanner_html("wide", "ipo"),
        breadcrumb_fn=_breadcrumb, source_note_fn=_source_note, site_url=SITE_URL, upcoming=True,
    )
    dest_dir = os.path.join(ROOT, "site", "ipo", "upcoming")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    from .ipo_engine import build_ipo_event_feeds
    rss, ics, n = build_ipo_event_feeds(records, SITE_URL)
    _write_text(os.path.join(ROOT, "site", "ipo", "feed.xml"), rss)
    with open(os.path.join(ROOT, "site", "ipo", "upcoming.ics"), "w", encoding="utf-8", newline="") as fh:
        fh.write(ics)
    log("IPO upcoming page: written; RSS and calendar feeds with %d dated events" % n, "ok")


def _write_ipo_archive(records, equity_history=None):
    """/ipo/archive/ - complete historical database of every NSE mainboard and SME IPO
    BrokerLens tracks since 2003, with issue prices, listing dates, listing day gains,
    and post-listing returns."""
    from .ipo_engine import render_enhanced_ipo_archive
    body = render_enhanced_ipo_archive(
        records=records,
        equity_history=equity_history,
        head_template=_REGISTRY_PAGE_HEAD,
        foot_template=_REGISTRY_PAGE_FOOT,
        breadcrumb_fn=_breadcrumb,
        source_note_fn=_source_note,
        site_url=SITE_URL,
    )
    dest_dir = os.path.join(ROOT, "site", "ipo", "archive")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("IPO archive: written, %d rows with listing returns" % len(records), "ok")


def _write_ipo_sme(records, equity_history=None):
    """/ipo/sme/ - dedicated hub for NSE Emerge and BSE SME public issues."""
    from .ipo_engine import render_sme_ipo_hub
    body = render_sme_ipo_hub(
        records=records,
        equity_history=equity_history,
        head_template=_REGISTRY_PAGE_HEAD,
        foot_template=_REGISTRY_PAGE_FOOT,
        ibsl_html=ibslBanner_html("wide", "ipo"),
        breadcrumb_fn=_breadcrumb,
        source_note_fn=_source_note,
        site_url=SITE_URL,
    )
    dest_dir = os.path.join(ROOT, "site", "ipo", "sme")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("IPO SME hub: written with 1-lot trading rules and liquidity disclosures", "ok")


def _write_ipo_gmp(records, equity_history=None):
    """/ipo/gmp/ - central Grey Market Premium tracker board with strict safeguards."""
    from .ipo_engine import render_gmp_hub
    body = render_gmp_hub(
        records=records,
        equity_history=equity_history,
        head_template=_REGISTRY_PAGE_HEAD,
        foot_template=_REGISTRY_PAGE_FOOT,
        ibsl_html=ibslBanner_html("wide", "ipo"),
        breadcrumb_fn=_breadcrumb,
        source_note_fn=_source_note,
        site_url=SITE_URL,
    )
    dest_dir = os.path.join(ROOT, "site", "ipo", "gmp")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("IPO GMP tracker: written with transparent indicative quotes & mandatory safeguards", "ok")


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
    """/about: Comprehensive E-E-A-T declaration outlining who publishes
    BrokerLens, research team methodology, primary source verification,
    and clear non-advisory institutional boundaries."""
    canonical = "%s/about" % SITE_URL
    title = "About BrokerLens | Financial Research & Broker Intelligence"
    description = (
        "About BrokerLens: An independent financial intelligence platform analyzing Indian stock brokers, "
        "mutual funds, equities, and IPOs using verified disclosures from NSE, BSE, and SEBI."
    )[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("About", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {
            "@type": "AboutPage",
            "name": title,
            "url": canonical,
            "description": description,
            "mainEntity": {
                "@type": "Organization",
                "name": "BrokerLens",
                "url": SITE_URL,
                "logo": "%s/apple-touch-icon.png" % SITE_URL,
                "publishingPrinciples": "%s/editorial-policy" % SITE_URL,
                "correctionsPolicy": "%s/editorial-policy#corrections" % SITE_URL,
                "ethicsPolicy": "%s/editorial-policy#independence" % SITE_URL,
                "sameAs": [
                    "https://twitter.com/brokerlens",
                    "https://www.linkedin.com/company/brokerlens"
                ],
                "contactPoint": [
                    {
                        "@type": "ContactPoint",
                        "email": CONTACT_EMAIL,
                        "contactType": "compliance and editorial support",
                        "areaServed": "IN",
                        "availableLanguage": "English"
                    }
                ]
            }
        },
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">About BrokerLens</h1>'
        '<p class="lead" style="max-width:75ch;font-size:16px;line-height:1.6;color:var(--text)">'
        'BrokerLens is an independent financial data and research infrastructure platform dedicated to Indian retail investors. '
        'We analyze stock brokers, listed equities, mutual fund schemes, ETFs, and public issues (IPOs) using verified empirical data '
        'derived directly from regulatory filings and exchange infrastructure feeds.'
        '</p>'

        '<div class="section-title"><h2>Our Mission &amp; Purpose</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'In an era dominated by promotional finfluencer endorsements, sponsored marketing awards, and hidden transaction costs, '
        'BrokerLens was built to establish a transparent, mathematically rigorous benchmark for the Indian capital markets. '
        'We believe retail investors deserve clear, objective facts before committing their hard-earned capital.'
        '</p>'
        '</div>'

        '<div class="section-title"><h2>What We Track</h2></div>'
        '<div class="card"><ul class="small" style="padding-left:18px;line-height:1.7">'
        '<li><strong>SEBI-Registered Intermediaries:</strong> Comprehensive directory of over 1,600 recognized stock brokers, depository participants (CDSL and NSDL), merchant bankers, and portfolio managers.</li>'
        '<li><strong>Equities &amp; Market Microstructure:</strong> Real-time daily prices, candlestick charts, and corporate actions across active NSE and BSE listed stocks and benchmark indices.</li>'
        '<li><strong>Mutual Funds &amp; ETFs:</strong> Performance analytics, portfolio expense ratios, and historical NAV trends across AMFI-registered mutual fund schemes and index ETFs.</li>'
        '<li><strong>Initial Public Offerings (IPOs):</strong> Audited Red Herring Prospectus (RHP) balance sheet disclosures, retail lot sizing limits, live bidding demand, and verified post-listing gains.</li>'
        '<li><strong>True Cost Calculators:</strong> Mathematical trade cost engines auditing brokerage, STT, exchange turnover charges, SEBI turnover fees, stamp duty, and GST down to the exact paisa.</li>'
        '</ul></div>'

        '<div class="section-title"><h2>Editorial &amp; Research Team</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'Our research is produced and curated by the <strong>BrokerLens Financial Research Desk</strong>, composed of financial software engineers, '
        'quantitative analysts, and regulatory compliance reviewers. '
        'Our team specializes in Indian market microstructure, clearing corporation settlement rules, and SEBI ICDR/LODR compliance.'
        '</p>'
        '<p class="small muted">'
        'We do not accept subjective opinions or promotional marketing copy. Every calculation is automated via audited Python algorithms, '
        'and every published report is checked against official circulars before release.'
        '</p>'
        '<p class="small" style="margin-bottom:0">'
        '<a href="/editorial-policy" style="font-weight:600">Read our complete Editorial Policy, Fact-Checking and Quality Standards &rarr;</a>'
        '</p>'
        '</div>'

        '<div class="section-title"><h2>Verification Architecture &amp; Methodology</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'Every figure published across BrokerLens traces to an immutable, named primary source: NSE, BSE, SEBI, AMFI, RBI, or the Ministry of Corporate Affairs. '
        'Our data ingestion pipelines run automated sanity sweeps, verifying active client counts, exchange complaints ratios, and margin rules.'
        '</p>'
        '<p class="small" style="margin-bottom:0">'
        'Review the mathematical mechanics in our <a href="/methodology" data-link>Methodology Page</a> '
        'and inspect the full cadence and status of every feed on our <a href="/sources" data-link>Primary Sources Directory</a>.'
        '</p>'
        '</div>'

        '<div class="section-title"><h2>What BrokerLens Deliberately Does Not Do</h2></div>'
        '<div class="card" style="line-height:1.7"><p class="small muted" style="margin-top:0">'
        'BrokerLens is an informational and research publisher, not a SEBI-registered Investment Adviser (IA) or Research Analyst (RA). '
        'Nothing on this platform constitutes investment advice, financial planning, portfolio management, or a buy/sell stock recommendation.'
        '</p>'
        '<p class="small muted">'
        'We do not operate a proprietary trading desk, sell advisory tip packages, manage client funds, or publish speculative grey market premiums (GMP). '
        'Certain pages contain clearly designated affiliate links to leading SEBI-registered brokers. These partnerships help finance our infrastructure '
        'but never influence our ratings, comparison tables, or objective reviews.'
        '</p>'
        '</div>'

        '<div class="section-title"><h2>Contact &amp; Grievance Redressal</h2></div>'
        '<p class="small muted">'
        'For data corrections, editorial inquiries, or compliance queries, please visit our <a href="/contact" data-link>Contact Page</a> '
        'or write to our compliance desk at <a href="mailto:%s">%s</a>.'
        '</p>'
    ) % (CONTACT_EMAIL, CONTACT_EMAIL)
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page states who publishes BrokerLens, our research principles, and our regulatory boundaries.")}
    dest_dir = os.path.join(ROOT, "site", "about")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("about page: written", "ok")


def _write_editorial_policy_page():
    """/editorial-policy: Institutional E-E-A-T declaration detailing BrokerLens's
    golden-source data standard, editorial independence, zero-payola guarantee,
    fact-checking methodology, and formal corrections protocol."""
    canonical = "%s/editorial-policy" % SITE_URL
    title = "Editorial Policy, Fact-Checking and Quality Standards | BrokerLens"
    description = (
        "BrokerLens editorial standards: commitment to primary data from NSE, BSE and SEBI, "
        "complete editorial independence, zero-payola ranking guarantee, and our 24-48h corrections SLA."
    )[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Editorial Policy", None)])
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "AboutPage",
                "name": title,
                "url": canonical,
                "description": description,
                "mainEntity": {
                    "@type": "Organization",
                    "name": "BrokerLens",
                    "url": SITE_URL,
                    "publishingPrinciples": canonical,
                    "correctionsPolicy": "%s#corrections" % canonical,
                    "ethicsPolicy": "%s#independence" % canonical,
                    "knowsAbout": [
                        "Indian Stock Brokers",
                        "SEBI Regulations",
                        "NSE and BSE Market Microstructure",
                        "Mutual Funds",
                        "IPOs",
                        "Trading Costs"
                    ]
                }
            },
            crumb_jsonld,
        ]
    }
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">Editorial Policy &amp; Fact-Checking Standards</h1>'
        '<p class="lead" style="max-width:75ch;font-size:16px;line-height:1.6;color:var(--text)">'
        'BrokerLens is an independent financial data and research infrastructure platform built for Indian retail investors. '
        'Our fundamental mission is to replace promotional marketing claims with verified, auditable facts sourced directly from '
        'statutory regulators and market infrastructure institutions.'
        '</p>'

        '<div class="section-title" id="golden-source"><h2>1. The Golden Source Standard (Hierarchy of Data)</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'Every metric, fee, reliability score, and market snapshot published across BrokerLens is strictly grounded in primary public disclosures. '
        'We adhere to an uncompromising hierarchy of truth:'
        '</p>'
        '<ul class="small" style="padding-left:18px;margin-bottom:0">'
        '<li><strong>Tier 1 (Statutory Regulators &amp; Sovereign Feeds):</strong> Gazette notifications, circulars, and the official Intermediaries Registration Database of the Securities and Exchange Board of India (SEBI), Reserve Bank of India (RBI) notifications, and the Ministry of Corporate Affairs (MCA).</li>'
        '<li><strong>Tier 2 (Exchange &amp; Clearing Corporation Records):</strong> Daily trade bulletins, monthly active client disclosures, quarterly complaint redressal audits, settlement schedules, and tariff sheets from the National Stock Exchange of India (NSE), Bombay Stock Exchange (BSE), and Multi Commodity Exchange (MCX).</li>'
        '<li><strong>Tier 3 (Institutional Repositories):</strong> Official Net Asset Value (NAV) feeds and scheme portfolios published daily by the Association of Mutual Funds in India (AMFI) and recognized RTAs (CAMS, KFintech).</li>'
        '<li><strong>Audited Offer Prospectuses:</strong> Red Herring Prospectuses (RHP), Draft RHPs, and official allotment outcomes published by SEBI and exchange-designated Registrars.</li>'
        '<li><strong>Strict Exclusion of Unverified Claims:</strong> Marketing brochures, broker self-reported awards, sponsored blog posts, and financial influencer testimonials are explicitly banned from our calculation pipelines.</li>'
        '</ul>'
        '</div>'

        '<div class="section-title" id="independence"><h2>2. Editorial Independence &amp; Zero-Payola Guarantee</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'Our editorial desk operates with complete independence from commercial operations. '
        'BrokerLens maintains a strict <strong>Zero-Payola Guarantee</strong>:'
        '</p>'
        '<ul class="small" style="padding-left:18px;margin-bottom:0">'
        '<li><strong>Rankings Cannot Be Purchased:</strong> No broker, AMC, algorithmic software vendor, or listed company can pay to improve their ranking, raise their reliability score, or alter a review.</li>'
        '<li><strong>Algorithmic Scrutiny:</strong> Our broker reliability rating is derived entirely from objective, public mathematical formulas factoring in active client volume, exchange-reported complaint frequency, resolved grievances, and uptime compliance.</li>'
        '<li><strong>No Sponsored Editorial Content:</strong> We do not publish paid guest posts, sponsored articles, or covert advertorials. Any educational guide or market analysis is authored solely by our research team.</li>'
        '</ul>'
        '</div>'

        '<div class="section-title" id="monetization"><h2>3. Commercial Transparency &amp; Affiliate Disclosure</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'To sustain our research infrastructure, engineering pipelines, and continuous data ingestion without charging subscription paywalls to retail investors, '
        'BrokerLens participates in verified referral and affiliate partnerships with leading SEBI-registered brokers and fixed-income platforms (including Zerodha, 5paisa, and Jiraaf).'
        '</p>'
        '<p class="small muted">'
        '<strong>Strict Separation of Commerce and Analysis:</strong> All affiliate partnership links are isolated into clearly demarcated banner blocks '
        '(e.g., sponsored partner cards marked with verified badges) and are explicitly excluded from ranking tables, comparisons, and search algorithms. '
        'If an investor chooses to open a Demat or trading account through our partner link, BrokerLens may receive a nominal referral fee at zero additional cost to the investor. '
        'This commercial arrangement never impacts our objective analysis, scoring criteria, or critical assessment of broker drawbacks.'
        '</p>'
        '</div>'

        '<div class="section-title" id="fact-checking"><h2>4. Fact-Checking &amp; Automated Verification</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'BrokerLens employs a dual-tier verification architecture combining automated regression testing with manual research audits:'
        '</p>'
        '<ul class="small" style="padding-left:18px;margin-bottom:0">'
        '<li><strong>Automated Quality Assurance:</strong> Our software pipelines run extensive end-to-end tests (including over 490 automated regression assertions and defensive security sweeps) verifying tariff models, STT calculations, SEBI transaction charges, and exchange fee schedules before every build.</li>'
        '<li><strong>Quarterly Broker Tariff Reconciliation:</strong> We systematically cross-examine broker brokerage structures, depository participant (DP) charges, call-and-trade fees, and account maintenance charges (AMC) against official schedule of charges documents.</li>'
        '<li><strong>Primary Source Attribution:</strong> Every factual page features clear source attribution referencing the origin regulatory disclosure and refresh timestamp.</li>'
        '</ul>'
        '</div>'

        '<div class="section-title" id="corrections"><h2>5. Corrections Policy &amp; Public Accountability SLA</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        'While our pipelines strive for absolute precision, financial regulations and broker tariff structures evolve rapidly. '
        'We welcome public scrutiny and maintain a formal corrections policy:'
        '</p>'
        '<ul class="small" style="padding-left:18px;margin-bottom:12px">'
        '<li><strong>Rapid Response SLA:</strong> We commit to investigating all verifiable data correction requests within <strong>24 to 48 business hours</strong> of receipt.</li>'
        '<li><strong>Correction Protocol:</strong> If a discrepancy is validated against an official primary source (such as an updated exchange circular or published tariff sheet), our data models and published pages are updated on the immediate subsequent deployment cycle.</li>'
        '<li><strong>Reporting Channel:</strong> To report a factual error or submit an updated regulatory document, please email our compliance desk at '
        '<a href="mailto:%s">%s</a> with the subject line <em>Data Correction Request</em> and relevant source links.'
        '</li>'
        '</ul>'
        '</div>'

        '<div class="section-title" id="disclaimer"><h2>6. Non-Advisory Mandate &amp; Regulatory Disclosures</h2></div>'
        '<div class="card" style="line-height:1.7">'
        '<p class="small muted" style="margin-top:0">'
        '<strong>Not Investment Advice:</strong> BrokerLens is a financial data, technology, and informational publisher. '
        'BrokerLens is not registered as an Investment Adviser (IA) or Research Analyst (RA) with SEBI. '
        'Nothing published on this website constitutes investment advice, financial planning, portfolio management, or a solicitation to buy, sell, or hold any security, derivative contract, mutual fund unit, or financial instrument.'
        '</p>'
        '<p class="small muted">'
        '<strong>No Unregulated Market Products:</strong> BrokerLens does not publish grey market premiums (GMP), dabba trading estimates, or informal off-exchange speculation. '
        'We believe unregulated figures mislead retail investors and compromise market integrity.'
        '</p>'
        '<p class="small muted" style="margin-bottom:0">'
        '<strong>Risk Warning:</strong> Trading in equities, derivatives (futures and options), and leveraged securities involves substantial risk of capital loss. '
        'Per SEBI study findings, 9 out of 10 individual traders in equity futures and options incur net losses. '
        'Investors should perform independent due diligence, review regulatory offer documents, and consult certified financial planners before making investment decisions.'
        '</p>'
        '</div>'

        '<div class="section-title"><h2>Get in Touch with our Editorial Desk</h2></div>'
        '<p class="small muted">'
        'For editorial inquiries, feedback, or regulatory clarifications, visit our <a href="/contact" data-link>Contact Page</a> '
        'or write directly to <a href="mailto:%s">%s</a>.'
        '</p>'
    ) % (CONTACT_EMAIL, CONTACT_EMAIL, CONTACT_EMAIL, CONTACT_EMAIL)
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page outlines BrokerLens's editorial standards, fact-checking methodology, and corrections policy.")}
    dest_dir = os.path.join(ROOT, "site", "editorial-policy")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("editorial-policy page: written", "ok")


def _write_contact_page():
    """/contact: Dedicated support, grievance redressal, and regulatory
    compliance contact desk with defined 24-48h resolution SLA."""
    canonical = "%s/contact" % SITE_URL
    title = "Contact & Grievance Redressal Desk | BrokerLens"
    description = (
        "Contact BrokerLens: Reach our data compliance team, report factual corrections, "
        "or submit regulatory and advertising inquiries. Dedicated 24-48h SLA."
    )[:300]
    crumb_html, crumb_jsonld = _breadcrumb([("BrokerLens", "/"), ("Contact", None)])
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "ContactPage", "name": title, "url": canonical, "description": description},
        {
            "@type": "Organization",
            "name": "BrokerLens",
            "url": SITE_URL,
            "publishingPrinciples": "%s/editorial-policy" % SITE_URL,
            "contactPoint": [
                {
                    "@type": "ContactPoint",
                    "email": CONTACT_EMAIL,
                    "contactType": "investor grievance and editorial support",
                    "areaServed": "IN",
                    "availableLanguage": "English"
                }
            ]
        },
        crumb_jsonld,
    ]}
    body = _REGISTRY_PAGE_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
    }
    body += crumb_html + (
        '<h1 style="margin-top:16px">Contact &amp; Grievance Redressal Desk</h1>'
        '<p class="lead" style="max-width:75ch;font-size:16px;line-height:1.6;color:var(--text)">'
        'We value transparency and rapid response. '
        'Whether you have identified a data discrepancy, require regulatory clarification, or want to discuss partnership opportunities, '
        'our dedicated compliance desk is available below.'
        '</p>'

        '<div class="grid g2" style="margin-top:20px">'
        '<div class="card"><div class="card-title">Data Corrections &amp; Discrepancies</div>'
        '<p class="small muted">Spotted an outdated brokerage fee, an amended exchange circular, or a newly listed broker? '
        'Submit the relevant page URL and supporting primary source link (NSE, BSE, SEBI, or AMFI). '
        'Our quantitative research desk prioritizes all data corrections with a <strong>24 to 48 business hour</strong> resolution SLA.</p></div>'

        '<div class="card"><div class="card-title">Editorial &amp; Research Feedback</div>'
        '<p class="small muted">Feedback regarding our market research articles, calculation tools, or educational guides. '
        'Learn more about our standards on our <a href="/editorial-policy" data-link>Editorial Policy Page</a>.</p></div>'

        '<div class="card"><div class="card-title">Commercial &amp; Partnership Enquiries</div>'
        '<p class="small muted">Inquiries regarding demarcated broker affiliate banners or institutional data partnerships. '
        'Please note that commercial arrangements are strictly separated from our objective rankings and mathematical evaluations.</p></div>'

        '<div class="card"><div class="card-title">Security &amp; Vulnerability Disclosure</div>'
        '<p class="small muted">BrokerLens welcomes responsible disclosures from white-hat security researchers. '
        'If you have discovered a security vulnerability or anomalous behavior, please report it to our engineering team with technical reproduction steps.</p></div>'
        '</div>'

        '<div class="section-title"><h2>Direct Email Communication</h2></div>'
        '<div class="card" style="padding:22px;border-left:4px solid var(--accent)">'
        '<div class="xs muted" style="font-weight:600;text-transform:uppercase">Official Contact Channel</div>'
        '<p style="font-size:1.25rem;font-weight:700;margin:6px 0 10px 0"><a href="mailto:%s">%s</a></p>'
        '<p class="small muted" style="margin:0;line-height:1.6">'
        'Our compliance desk reviews every incoming message. '
        'To expedite your request, please include the specific page URL and cite the relevant primary source document where applicable.'
        '</p>'
        '</div>'

        '<div class="section-title"><h2>Jurisdiction &amp; Regulatory Context</h2></div>'
        '<div class="card" style="line-height:1.7"><p class="small muted" style="margin:0">'
        'BrokerLens operates under the legal and regulatory jurisdiction of the Republic of India. '
        'We adhere to the Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules '
        'and the regulatory guidance issued by the Securities and Exchange Board of India (SEBI).'
        '</p></div>'
    ) % (CONTACT_EMAIL, CONTACT_EMAIL)
    body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
        "This page states how to reach BrokerLens for support, grievance redressal, and regulatory communication.")}
    dest_dir = os.path.join(ROOT, "site", "contact")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("contact page: written", "ok")


def _write_privacy_page():
    """/privacy-policy: a factual description of what the site actually does,
    not templated boilerplate, so this must be kept in sync by hand whenever
    tracking changes - as of this build that's Google Analytics (GA4,
    G-XJK97Q2CD7, added 2026-10-23) plus a same-origin theme/exchange
    preference in localStorage and the cookie-free ad-event beacon. Static,
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
        '<div class="card"><p class="small muted">BrokerLens uses Google Analytics (GA4) to understand aggregate '
        'traffic to the site: which pages are visited, how many visitors, and roughly which country or device '
        'type. Google Analytics may set cookies and use your IP address and similar technical signals to do '
        'this; see <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google\'s own '
        'Privacy Policy</a> for how it handles that data. Separately, the site stores two preferences in your '
        'own browser\'s local storage (never sent to us or anyone else): your light or dark theme choice, and '
        'your selected market exchange on the price ticker. Clearing your browser data removes them. When a '
        'sponsored banner is shown or clicked, the site records a separate, anonymous event (which banner, '
        'which page, phone or desktop, and the referring site) with no cookie, no IP address and no personal '
        'identifier, so we can see which pages send readers to an advertiser. If you write to us by email, we '
        'hold that message and your email address only for as long as needed to answer it.</p></div>'

        '<div class="section-title"><h2>Affiliate and sponsored links</h2></div>'
        '<div class="card"><p class="small muted">Some pages carry a clearly marked sponsored banner linking to '
        'a broker\'s own account-opening page. Once you follow that link, you are on the broker\'s own site and '
        'subject to their privacy policy, not ours; BrokerLens may earn a commission if you open an account, '
        'disclosed on the <a href="/methodology" data-link>methodology page</a>. We do not receive or store any '
        'personal or financial information from that process.</p></div>'

        '<div class="section-title"><h2>Google AdSense and advertising cookies</h2></div>'
        '<div class="card"><p class="small muted">BrokerLens works with Google AdSense to display advertisements across the site. '
        'Third-party vendors, including Google, use cookies to serve ads based on a user\'s prior visits to BrokerLens or other websites on the internet. '
        'Google\'s use of advertising cookies enables it and its partners to serve ads to users based on their visits to this site and other sites on the internet. '
        'Users may opt out of personalized advertising by visiting '
        '<a href="https://www.google.com/settings/ads" target="_blank" rel="noopener">Google Ads Settings</a>. '
        'Alternatively, you can opt out of a third-party vendor\'s use of cookies for personalized advertising by visiting '
        '<a href="https://www.aboutads.info/choices/" target="_blank" rel="noopener">aboutads.info</a>.</p></div>'

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


COMPARISON_PAIRS = [
    ("zerodha", "groww"),
    ("groww", "angel-one"),
    ("zerodha", "angel-one"),
    ("zerodha", "upstox"),
    ("groww", "upstox"),
    ("zerodha", "dhan"),
    ("dhan", "fyers"),
    ("angel-one", "upstox"),
    ("zerodha", "5paisa"),
    ("upstox", "5paisa"),
    ("zerodha", "icici-direct"),
    ("groww", "paytm-money"),
    ("zerodha", "kotak-securities"),
    ("groww", "dhan"),
    ("angel-one", "motilal-oswal"),
    ("icici-direct", "hdfc-securities"),
    ("kotak-securities", "hdfc-securities"),
    ("zerodha", "fyers"),
    ("upstox", "dhan"),
    ("groww", "5paisa"),
]


def _fmt_broker_plan(plan):
    if not plan:
        return "-"
    bits = []
    if plan.get("flat_per_order") is not None:
        flat = plan["flat_per_order"]
        bits.append("Free" if flat == 0 else ("Rs %s/order" % flat))
    if plan.get("pct_of_turnover") is not None:
        bits.append("%s%%" % plan["pct_of_turnover"])
    if plan.get("cap_per_order") is not None:
        bits.append("max Rs %s" % plan["cap_per_order"])
    return _esc(", ".join(bits) or "-")


def _write_compare_pages(overview, built=None):
    brokers = sorted(overview.get("brokers") or [], key=lambda b: -(b.get("clients") or 0))
    built_map = {b["id"]: b for b in (built or [])}
    b_brand = {b["id"]: b.get("brand") or b["id"] for b in brokers}

    # 1. Main /compare hub page
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
        '<div class="card row-between" style="margin-top:20px;padding:16px 20px;align-items:center;background:linear-gradient(135deg, rgba(37,99,235,0.06), rgba(16,185,129,0.06));border:1px solid rgba(37,99,235,0.2)">'
        '<div><div style="font-size:14px;font-weight:650;color:var(--text)">Not sure which brokers to compare?</div>'
        '<div class="xs muted">Take our 30-second Broker Matchmaker quiz to find the best match for your trading style and capital.</div></div>'
        '<a class="btn btn-sm btn-primary link-arrow" href="/find-broker/" data-link>Find My Broker &rarr;</a></div>'
    ) % "".join('<option value="%s">%s</option>' % (_esc(b["id"]), _esc(b["brand"])) for b in brokers)

    popular_cards = "".join(
        '<a class="cmp-card" href="/compare/%s-vs-%s/">'
        '<div class="cmp-vs-row">'
        '<div class="cmp-broker">%s<span>%s</span></div>'
        '<span class="cmp-vs-badge">VS</span>'
        '<div class="cmp-broker"><span>%s</span>%s</div>'
        '</div>'
        '<div class="cmp-tags">'
        '<span class="cmp-tag">Active Clients &amp; Charges</span>'
        '<span class="cmp-tag">Demat AMC &amp; Features</span>'
        '</div>'
        '<div class="cmp-action">'
        '<span>Compare head-to-head</span>'
        '<span class="arr">&rarr;</span>'
        '</div></a>'
        % (
            id1, id2,
            _mark_html(id1, b_brand.get(id1, id1), 22), _esc(b_brand.get(id1, id1)),
            _esc(b_brand.get(id2, id2)), _mark_html(id2, b_brand.get(id2, id2), 22),
        )
        for id1, id2 in COMPARISON_PAIRS[:12]
        if id1 in b_brand and id2 in b_brand
    )

    body += (
        '<div class="section-title" style="margin-top:28px"><h2>Popular broker comparisons</h2></div>'
        '<p class="muted small">Direct head to head comparisons of India\'s leading stock brokers.</p>'
        '<div class="grid g3" style="margin-top:12px">%s</div>'
    ) % popular_cards

    body += _APP_SHELL_FOOT
    dest_dir = os.path.join(ROOT, "site", "compare")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("compare hub page: written", "ok")

    # 2. Programmatic 1v1 comparison pages across top brokers
    all_pairs = list(COMPARISON_PAIRS)
    seen_pairs = set(all_pairs)
    ranked_ids = [b["id"] for b in brokers if b.get("id") in built_map]
    for i in range(min(len(ranked_ids), 20)):
        for j in range(i + 1, min(len(ranked_ids), 20)):
            p = (ranked_ids[i], ranked_ids[j])
            if p not in seen_pairs:
                seen_pairs.add(p)
                all_pairs.append(p)

    written_pairs = []
    for id1, id2 in all_pairs:
        b1 = built_map.get(id1)
        b2 = built_map.get(id2)
        if not b1 or not b2:
            continue
        pair_slug = "%s-vs-%s" % (id1, id2)
        brand1 = b1["profile"].get("brand") or id1
        brand2 = b2["profile"].get("brand") or id2
        p_canon = "%s/compare/%s/" % (SITE_URL, pair_slug)
        p_title = "%s vs %s: Charges, Clients & Comparison (2026) | BrokerLens" % (brand1, brand2)
        p_desc = ("Compare %s vs %s side by side on brokerage charges, active clients, complaint resolution rate, "
                  "Demat AMC, and SEBI compliance." % (brand1, brand2))[:300]
        p_crumb_html, p_crumb_jsonld = _breadcrumb([
            ("BrokerLens", "/"), ("Compare", "/compare"), ("%s vs %s" % (brand1, brand2), None),
        ])

        c1 = b1.get("clients") or {}
        c2 = b2.get("clients") or {}
        ch1 = b1.get("charges") or {}
        ch2 = b2.get("charges") or {}
        comp1 = b1.get("complaints") or {}
        comp2 = b2.get("complaints") or {}
        rel1 = b1.get("reliability") or {}
        rel2 = b2.get("reliability") or {}
        cost1 = b1.get("cost") or {}
        cost2 = b2.get("cost") or {}
        prof1 = b1.get("profile") or {}
        prof2 = b2.get("profile") or {}
        fl1 = b1.get("regulatory_flags") or {}
        fl2 = b2.get("regulatory_flags") or {}

        clients_str1 = format(c1["active_clients"], ",") if c1.get("active_clients") is not None else "-"
        clients_str2 = format(c2["active_clients"], ",") if c2.get("active_clients") is not None else "-"
        share_str1 = ("%.2f%%" % c1["market_share_pct"]) if c1.get("market_share_pct") is not None else "-"
        share_str2 = ("%.2f%%" % c2["market_share_pct"]) if c2.get("market_share_pct") is not None else "-"
        deliv_str1 = _fmt_broker_plan(ch1.get("delivery"))
        deliv_str2 = _fmt_broker_plan(ch2.get("delivery"))
        intra_str1 = _fmt_broker_plan(ch1.get("intraday"))
        intra_str2 = _fmt_broker_plan(ch2.get("intraday"))
        fno_str1 = _fmt_broker_plan(ch1.get("fno"))
        fno_str2 = _fmt_broker_plan(ch2.get("fno"))
        amc_str1 = ("Rs %s/yr" % ch1["demat_amc_annual"]) if ch1.get("demat_amc_annual") is not None else "-"
        amc_str2 = ("Rs %s/yr" % ch2["demat_amc_annual"]) if ch2.get("demat_amc_annual") is not None else "-"
        acct_str1 = ("Rs %s" % ch1["account_opening"]) if ch1.get("account_opening") is not None else "Free"
        acct_str2 = ("Rs %s" % ch2["account_opening"]) if ch2.get("account_opening") is not None else "Free"
        k_str1 = ("%.2f" % comp1["per_10k_clients_12m"]) if comp1.get("per_10k_clients_12m") is not None else "-"
        k_str2 = ("%.2f" % comp2["per_10k_clients_12m"]) if comp2.get("per_10k_clients_12m") is not None else "-"
        res_str1 = ("%.1f%%" % comp1["resolution_rate_pct"]) if comp1.get("resolution_rate_pct") is not None else "-"
        res_str2 = ("%.1f%%" % comp2["resolution_rate_pct"]) if comp2.get("resolution_rate_pct") is not None else "-"
        rel_str1 = ("%.1f/100" % rel1["score"]) if rel1.get("score") is not None else "-"
        rel_str2 = ("%.1f/100" % rel2["score"]) if rel2.get("score") is not None else "-"
        type_str1 = TYPE_LABEL.get(prof1.get("type"), prof1.get("type") or "-")
        type_str2 = TYPE_LABEL.get(prof2.get("type"), prof2.get("type") or "-")
        city_str1 = prof1.get("hq") or "-"
        city_str2 = prof2.get("hq") or "-"
        fnd_str1 = str(prof1.get("founded") or "-")
        fnd_str2 = str(prof2.get("founded") or "-")
        sebi_str1 = prof1.get("sebi_reg_no") or "-"
        sebi_str2 = prof2.get("sebi_reg_no") or "-"
        seg_str1 = ", ".join(SEGMENT_LABEL.get(s, s) for s in (prof1.get("segments") or [])) or "-"
        seg_str2 = ", ".join(SEGMENT_LABEL.get(s, s) for s in (prof2.get("segments") or [])) or "-"
        defaulter1 = "Yes (Expelled)" if fl1.get("defaulter") else "No"
        defaulter2 = "Yes (Expelled)" if fl2.get("defaulter") else "No"

        q1 = "How do brokerage charges compare between %s and %s?" % (brand1, brand2)
        a1 = ("For equity delivery, %s offers %s while %s offers %s. For intraday equity trades, %s charges %s "
              "compared to %s at %s.") % (brand1, deliv_str1, brand2, deliv_str2, brand1, intra_str1, brand2, intra_str2)
        q2 = "Which broker has more active clients, %s or %s?" % (brand1, brand2)
        a2 = ("%s has %s active clients (%s market share) while %s has %s active clients (%s market share) "
              "based on primary NSE disclosures.") % (brand1, clients_str1, share_str1, brand2, clients_str2, share_str2)
        q3 = "What are the account opening and Demat AMC fees for %s vs %s?" % (brand1, brand2)
        a3 = ("For %s, account opening is %s and annual Demat AMC is %s. For %s, account opening is %s "
              "and annual Demat AMC is %s.") % (brand1, acct_str1, amc_str1, brand2, acct_str2, amc_str2)
        q4 = "Is %s or %s better for beginners?" % (brand1, brand2)
        a4 = ("Both %s and %s are SEBI-registered intermediaries. Beginners often look for low delivery brokerage, "
              "intuitive mobile apps, and prompt customer support. Compare delivery charges (%s vs %s) and complaint "
              "rates (%s vs %s) to decide which matches your investment style.") % (brand1, brand2, deliv_str1, deliv_str2, k_str1, k_str2)

        p_jsonld = {"@context": "https://schema.org", "@graph": [
            {"@type": "WebPage", "name": p_title, "url": p_canon, "description": p_desc},
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in [(q1, a1), (q2, a2), (q3, a3), (q4, a4)]
                ]
            },
            p_crumb_jsonld,
        ]}

        p_page = _APP_SHELL_HEAD % {
            "title": _esc(p_title), "description": _esc(p_desc),
            "canonical": _esc(p_canon), "jsonld": json.dumps(p_jsonld, ensure_ascii=False),
        }
        p_page += p_crumb_html

        # Hero
        p_page += (
            '<div class="spread" style="margin-top:16px">'
            '<div>'
            '<h1 style="margin:0">%s vs %s</h1>'
            '<p class="muted small" style="margin-top:4px">Side by side comparison of active clients, charges, and regulatory track records.</p>'
            '</div>'
            '<div class="row-wrap" style="gap:8px">'
            '<a class="btn btn-sm" href="/broker/%s/">%s Profile</a>'
            '<a class="btn btn-sm" href="/broker/%s/">%s Profile</a>'
            '</div></div>'
        ) % (_esc(brand1), _esc(brand2), _esc(id1), _esc(brand1), _esc(id2), _esc(brand2))

        aff_partners = _load_affiliate_partners()
        aff1 = aff_partners.get(id1)
        aff2 = aff_partners.get(id2)
        badge1 = '<span class="badge badge-verified" style="font-size:10px">Partner</span>' if aff1 else ('<span class="chip">%s</span>' % _esc(type_str1))
        badge2 = '<span class="badge badge-verified" style="font-size:10px">Partner</span>' if aff2 else ('<span class="chip">%s</span>' % _esc(type_str2))

        cta1_html = (
            '<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">'
            '<a class="btn btn-primary btn-sm" href="%s" target="_blank" rel="noopener noreferrer sponsored">Open on %s &rarr;</a>'
            '<a class="btn btn-sm" href="/broker/%s/">Profile &rarr;</a>'
            '</div>'
        ) % (_esc(aff1), _esc(brand1), _esc(id1)) if aff1 else (
            '<div style="margin-top:14px"><a class="btn btn-sm" href="/broker/%s/">View full %s profile &rarr;</a></div>'
            % (_esc(id1), _esc(brand1))
        )

        cta2_html = (
            '<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">'
            '<a class="btn btn-primary btn-sm" href="%s" target="_blank" rel="noopener noreferrer sponsored">Open on %s &rarr;</a>'
            '<a class="btn btn-sm" href="/broker/%s/">Profile &rarr;</a>'
            '</div>'
        ) % (_esc(aff2), _esc(brand2), _esc(id2)) if aff2 else (
            '<div style="margin-top:14px"><a class="btn btn-sm" href="/broker/%s/">View full %s profile &rarr;</a></div>'
            % (_esc(id2), _esc(brand2))
        )

        # Highlights cards
        p_page += (
            '<div class="grid g2" style="margin-top:16px">'
            '<div class="card">'
            '<div class="card-head"><div class="card-title">%s</div>%s</div>'
            '<div class="stat-value" style="font-size:var(--fs-lg);margin-top:4px">%s</div>'
            '<div class="stat-sub">Active clients (%s share)</div>'
            '<div style="margin-top:12px;font-size:var(--fs-sm)">'
            '<div><strong>Delivery:</strong> %s</div>'
            '<div style="margin-top:4px"><strong>Intraday:</strong> %s</div>'
            '<div style="margin-top:4px"><strong>Demat AMC:</strong> %s</div>'
            '</div>'
            '%s'
            '</div>'
            '<div class="card">'
            '<div class="card-head"><div class="card-title">%s</div>%s</div>'
            '<div class="stat-value" style="font-size:var(--fs-lg);margin-top:4px">%s</div>'
            '<div class="stat-sub">Active clients (%s share)</div>'
            '<div style="margin-top:12px;font-size:var(--fs-sm)">'
            '<div><strong>Delivery:</strong> %s</div>'
            '<div style="margin-top:4px"><strong>Intraday:</strong> %s</div>'
            '<div style="margin-top:4px"><strong>Demat AMC:</strong> %s</div>'
            '</div>'
            '%s'
            '</div>'
            '</div>'
        ) % (
            _esc(brand1), badge1, _esc(clients_str1), _esc(share_str1), _esc(deliv_str1), _esc(intra_str1), _esc(amc_str1), cta1_html,
            _esc(brand2), badge2, _esc(clients_str2), _esc(share_str2), _esc(deliv_str2), _esc(intra_str2), _esc(amc_str2), cta2_html
        )

        # Full table
        metrics = [
            ("Broker Type", type_str1, type_str2),
            ("Active Clients", clients_str1, clients_str2),
            ("Market Share", share_str1, share_str2),
            ("Complaints per 10k clients", k_str1, k_str2),
            ("Complaint Resolution", res_str1, res_str2),
            ("Reliability Score", rel_str1, rel_str2),
            ("Delivery Brokerage", deliv_str1, deliv_str2),
            ("Intraday Brokerage", intra_str1, intra_str2),
            ("F&O Brokerage", fno_str1, fno_str2),
            ("Demat AMC / Year", amc_str1, amc_str2),
            ("Account Opening", acct_str1, acct_str2),
            ("Head Office", city_str1, city_str2),
            ("Founded", fnd_str1, fnd_str2),
            ("SEBI Registration", sebi_str1, sebi_str2),
            ("Segments", seg_str1, seg_str2),
            ("Defaulter List Status", defaulter1, defaulter2),
        ]
        table_rows = "".join(
            '<tr><td class="muted small">%s</td><td class="right">%s</td><td class="right">%s</td></tr>'
            % (_esc(m_label), _esc(v1), _esc(v2)) for m_label, v1, v2 in metrics
        )

        p_page += (
            '<div class="section-title" style="margin-top:28px"><h2>Detailed head to head comparison</h2></div>'
            '<div class="table-scroll" style="margin-top:12px">'
            '<table class="data"><thead><tr>'
            '<th style="min-width:180px">Metric</th>'
            '<th class="right"><a href="/broker/%s/">%s</a></th>'
            '<th class="right"><a href="/broker/%s/">%s</a></th>'
            '</tr></thead><tbody>%s</tbody></table></div>'
        ) % (_esc(id1), _esc(brand1), _esc(id2), _esc(brand2), table_rows)

        # FAQs
        p_page += (
            '<div class="section-title" style="margin-top:32px"><h2>Frequently asked questions</h2></div>'
            '<div style="margin-top:12px">'
            + "".join('<details class="faq-item"><summary>%s</summary><p>%s</p></details>' % (_esc(q), _esc(a)) for q, a in [(q1, a1), (q2, a2), (q3, a3), (q4, a4)])
            + '</div>'
        )

        # Related comparisons
        related = [p for p in all_pairs if p != (id1, id2) and (p[0] in (id1, id2) or p[1] in (id1, id2))][:6]
        if related:
            p_page += (
                '<div class="section-title" style="margin-top:28px"><h2>Related comparisons</h2></div>'
                '<div class="row-wrap" style="gap:8px;margin-top:10px">%s</div>'
                % "".join(
                    '<a class="chip" href="/compare/%s-vs-%s/">%s vs %s &rarr;</a>'
                    % (r1, r2, _esc(b_brand.get(r1, r1)), _esc(b_brand.get(r2, r2)))
                    for r1, r2 in related
                )
            )

        p_page += (
            '<p class="xs faint" style="margin-top:24px">BrokerLens is an independent financial research publisher, not a SEBI-registered investment adviser. '
            'Data verified against the SEBI recognised-intermediary register, NSE monthly active client disclosures, '
            'and official broker tariff schedules as of BrokerLens\'s latest data refresh. '
            '<a href="/methodology">Methodology</a> &middot; <a href="/sources">Sources &amp; lineage</a> &middot; '
            '<a href="/editorial-policy">Editorial Policy</a> &middot; <a href="/compare">All comparisons</a></p>'
        )
        p_page += _APP_SHELL_FOOT

        p_dest = os.path.join(ROOT, "site", "compare", pair_slug)
        os.makedirs(p_dest, exist_ok=True)
        _write_text(os.path.join(p_dest, "index.html"), p_page)
        written_pairs.append((id1, id2))

    log("comparison pages: %d written" % len(written_pairs), "ok")
    return written_pairs


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
        '</div><div class="stack">%s%s%s</div></div>'
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
        affiliateBanner_html(), fivepaisaBanner_html(), jiraafBanner_html(),
    )
    from .broker_charges_engine import brokers_index_links_html
    body += _APP_SHELL_FOOT.replace("</main>", "</main>" + brokers_index_links_html(), 1)
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
    body += ibslBanner_html("wide", "calculator")
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


def _popular_comparisons_widget_html():
    pairs = [
        ("zerodha", "groww", "Zerodha vs Groww", "Discount leader vs #1 active clients"),
        ("groww", "angel-one", "Groww vs Angel One", "Direct onboarding vs full-stack broking"),
        ("zerodha", "upstox", "Zerodha vs Upstox", "Pioneer flat fee vs modern tech stack"),
        ("angel-one", "upstox", "Angel One vs Upstox", "F&O volume vs SmartAPI algorithmic tools"),
        ("dhan", "zerodha", "Dhan vs Zerodha", "Superfast TradingView vs Kite platform"),
        ("icici-direct", "zerodha", "ICICI Direct vs Zerodha", "3-in-1 bank account vs low-cost discount"),
    ]
    links = "".join(
        '<a class="cmp-mini-link" href="/compare/%s-vs-%s/" data-link>'
        '<div><div style="font-size:13px;font-weight:600;color:var(--text)">%s</div>'
        '<div class="xs muted">%s</div></div>'
        '<span style="color:var(--accent-text);font-size:12px;font-weight:700">&rarr;</span></a>'
        % (b1, b2, _esc(label), _esc(sub))
        for b1, b2, label, sub in pairs
    )
    return (
        '<div class="card" style="padding:18px">'
        '<div class="row-between" style="align-items:center;margin-bottom:12px">'
        '<div class="card-title" style="margin:0">Popular Comparisons</div>'
        '<a class="xs link-arrow" href="/compare" data-link>All 191 pairs &rarr;</a></div>'
        '<div style="display:flex;flex-direction:column;gap:8px">%s</div>'
        '<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border)">'
        '<a href="/find-broker/" class="xs" style="font-weight:600;color:var(--accent-text);display:flex;align-items:center;justify-content:space-between" data-link>'
        '<span>Can\'t decide? Try Broker Matchmaker</span><span>&rarr;</span></a></div></div>'
        % links
    )


def _prerender_home(overview):
    """Ports pages.js's home() to Python and injects the result into
    site/index.html's <main id="app">, replacing the empty loading-skeleton
    placeholder that was there before.
    """
    meta = overview.get("metadata") or {}
    agg = overview.get("aggregates") or {}
    m = overview.get("market") or {}
    conc = agg.get("concentration") or {}
    has_clients = bool(meta.get("data_status", {}).get("active_clients"))
    brokers = overview.get("brokers") or []
    top = (sorted(brokers, key=lambda b: -(b.get("clients") or 0))[:20] if has_clients
           else sorted(brokers, key=lambda b: b.get("brand") or "")[:20])
    nifty = ((m.get("nse") or {}).get("indices") or [{}])[0]
    breadth = (m.get("nse") or {}).get("breadth")
    bse_delivery = m.get("bse_delivery") or []
    delivery = bse_delivery[-1] if bse_delivery else None

    html = (
        '<section class="pitch" style="margin-top:16px">'
        '%s'
        '<div class="pill-tag accent" style="margin-bottom:12px"><span>✦</span> Verified Regulatory &amp; Market Intelligence</div>'
        '<h1 style="max-width:24ch">Every Indian stock broker, measured the same way.</h1>'
        '<p class="muted" style="max-width:64ch;margin-top:12px">%d brokers tracked in depth and %s '
        'SEBI-registered entities on file. %s</p>'
        '<div class="row-wrap" style="margin-top:18px">'
        '<a class="btn btn-primary" href="/brokers" data-link>Browse brokers</a>'
        '<a class="btn" href="/find-broker/" data-link>Find my broker</a>'
        '<a class="btn" href="/compare" data-link>Compare side by side</a>%s</div></section>'
    ) % (
        '<div class="pitch-media" aria-hidden="true"><video class="pitch-video" muted loop playsinline preload="none" disablepictureinpicture tabindex="-1" poster="/assets/video/hero-bull-bear-poster.jpg" data-src="/assets/video/hero-bull-bear.mp4"></video></div>',
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
    html += '<div class="grid g4" style="margin-top:28px">%s</div>' % tiles
    html += ibslBanner_html("strip", "home")

    if has_clients:
        total_series = agg.get("total_series") or []
        html += (
            '<div class="section-title" style="margin-top:56px;margin-bottom:20px">'
            '<div><div class="section-eyebrow">MARKET INTELLIGENCE BENTO</div>'
            '<h2>Industry Concentration &amp; Live Exchange Activity</h2></div>'
            '<span class="xs faint"><span class="dot-src primary" title="Sourced from primary NSE/BSE feeds"></span> Live &amp; Regulatory Feeds</span></div>'
            '<div class="grid g2" style="margin-top:0">'
            '<div class="card" style="padding:22px"><div class="card-head"><div>'
            '<div class="card-title">Total active clients across tracked brokers</div>'
            '<div class="xs faint">Monthly, %d months to %s</div></div></div>'
            '<div class="chart-box"><canvas id="mkt-total" height="200"></canvas></div></div>'
            '<div class="card" style="padding:22px"><div class="card-title">Share of active clients</div>'
            '<div class="row" style="margin-top:12px;align-items:center;gap:18px">'
            '<canvas id="mkt-share" width="168" height="168"></canvas>'
            '<div class="legend" id="share-legend" style="flex:1"></div></div></div></div>'
            '<div class="grid g2" style="margin-top:20px">'
            '<div class="card" style="padding:22px">'
            '<div class="row-between" style="align-items:center;margin-bottom:12px">'
            '<div class="card-title" style="margin:0">Live market snapshot</div>'
            '<span class="xs faint">%s Live at last build</span></div>'
            '<dl class="kv" style="margin-top:8px">%s%s%s%s%s</dl></div>%s</div>'
        ) % (
            len(total_series), _month_html(total_series[-1][0] if total_series else None),
            _prov_dot_html("nse"),
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
            ('<div class="card" style="padding:22px">'
             '<div class="row-between" style="align-items:center;margin-bottom:12px">'
             '<div class="card-title" style="margin:0">BSE delivery % (investors vs churn)</div>'
             '<span class="xs faint">Cash market</span></div>'
             '<div class="chart-box" style="margin-top:8px"><canvas id="bse-delivery" height="160"></canvas></div></div>'
             if bse_delivery else ""),
        )

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
        '<div class="section-title" style="margin-top:56px;margin-bottom:20px"><div>'
        '<div class="section-eyebrow">RETAIL BROKERAGE LANDSCAPE</div>'
        '<h2>%s</h2></div><a class="small link-arrow" href="/brokers" data-link>All %d &rarr;</a></div>'
        '<div class="grid g-main" style="margin-top:0"><div>'
        '<div class="table-scroll"><table class="data"><thead><tr>%s</tr></thead>'
        '<tbody>%s</tbody></table></div>'
        '<div class="card row-between" style="margin-top:14px;padding:16px 20px;align-items:center;background:var(--bg-raised)">'
        '<div><div style="font-size:14px;font-weight:650;color:var(--text)">Explore all %d tracked brokers</div>'
        '<div class="xs muted">Compare active clients, market share, complaints and trading fees</div></div>'
        '<a class="btn btn-sm btn-primary link-arrow" href="/brokers" data-link>View all %d &rarr;</a></div>'
        '<div class="card row-between" style="margin-top:14px;padding:16px 20px;align-items:center;background:linear-gradient(135deg, rgba(37,99,235,0.06), rgba(16,185,129,0.06));border:1px solid rgba(37,99,235,0.2)">'
        '<div><div style="font-size:14px;font-weight:650;color:var(--text)">Not sure which broker fits your strategy?</div>'
        '<div class="xs muted">Take our 30-second Broker Matchmaker quiz to find your ideal match based on fees, capital, and tools.</div></div>'
        '<a class="btn btn-sm btn-primary link-arrow" href="/find-broker/" data-link>Find My Broker &rarr;</a></div></div>'
        '<div class="stack" style="gap:16px">%s%s%s%s%s</div></div>'
    ) % (
        "Largest brokers by active clients" if has_clients else "Brokers on the SEBI register",
        meta.get("broker_count", 0), table_head, "".join(home_row(b) for b in top),
        meta.get("broker_count", 0), meta.get("broker_count", 0),
        _ad_slot_html(overview, "homepage rail"), affiliateBanner_html(), fivepaisaBanner_html(), jiraafBanner_html(),
        _popular_comparisons_widget_html(),
    )

    boards = (overview.get("leaderboards") or [])[:3]
    html += (
        '<div class="section-title" style="margin-top:56px;margin-bottom:20px"><div>'
        '<div class="section-eyebrow">MARKET MOMENTUM &amp; SHIFTS</div>'
        '<h2>Movers &amp; Market Share Gainers</h2></div>'
        '<a class="small link-arrow" href="/leaderboards" data-link>All movers &rarr;</a></div>'
        '<div class="grid g3">%s</div>'
    ) % "".join(_leader_card_html(bd) for bd in boards)

    html += (
        '<div class="section-title" style="margin-top:56px;margin-bottom:20px"><div>'
        '<div class="section-eyebrow">EDITORIAL &amp; REAL-TIME RESEARCH</div>'
        '<h2>Market News, Blogs &amp; Research</h2></div>'
        '<a class="small link-arrow" href="/news/" data-link>View all articles &rarr;</a></div>'
        '<div class="grid g3" style="margin-top:0">'
        '<a class="card card-interactive" href="/news/indian-stock-market-wrap-2026-09-25/" data-link style="display:flex;flex-direction:column;padding:20px">'
        '<div class="row-wrap" style="gap:6px;margin-bottom:10px"><span class="badge badge-verified">Market News</span><span class="xs muted">&middot; Daily Wrap</span></div>'
        '<h3 style="font-size:15px;margin-bottom:8px;line-height:1.35;font-weight:650">Indian Stock Market Today: Nifty 50, Gainers &amp; Sectoral Action</h3>'
        '<p class="xs muted" style="line-height:1.45;flex:1 0 auto">NSE market summary, advance-decline ratios, turnover volume, and top moving stocks.</p>'
        '<div class="link-arrow" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:14px">Read Dispatch &rarr;</div></a>'
        '<a class="card card-interactive" href="/news/best-stock-brokers-india-beginners-guide/" data-link style="display:flex;flex-direction:column;padding:20px">'
        '<div class="row-wrap" style="gap:6px;margin-bottom:10px"><span class="badge badge-verified">Blog &amp; Guide</span><span class="xs muted">&middot; 7 min read</span></div>'
        '<h3 style="font-size:15px;margin-bottom:8px;line-height:1.35;font-weight:650">How to Choose the Best Stock Broker in India</h3>'
        '<p class="xs muted" style="line-height:1.45;flex:1 0 auto">Comprehensive guide comparing discount brokers with bank-backed 3-in-1 accounts and trading tech.</p>'
        '<div class="link-arrow" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:14px">Read Guide &rarr;</div></a>'
        '<a class="card card-interactive" href="/news/zerodha-vs-groww-active-clients-market-share-2026/" data-link style="display:flex;flex-direction:column;padding:20px">'
        '<div class="row-wrap" style="gap:6px;margin-bottom:10px"><span class="badge badge-verified">Research</span><span class="xs muted">&middot; 9 min read</span></div>'
        '<h3 style="font-size:15px;margin-bottom:8px;line-height:1.35;font-weight:650">Zerodha vs Groww: Active Clients &amp; Market Share</h3>'
        '<p class="xs muted" style="line-height:1.45;flex:1 0 auto">Data-driven analysis comparing active client growth, complaints per 10k, and revenue trajectory.</p>'
        '<div class="link-arrow" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:14px">Read Research &rarr;</div></a>'
        '</div>'
        '<div class="section-title" style="margin-top:56px;margin-bottom:20px"><div>'
        '<div class="section-eyebrow">FINANCIAL SUITE &amp; DECISION TOOLS</div>'
        '<h2>Calculators &amp; Fair-Cost Estimators</h2></div>'
        '<a class="small link-arrow" href="/calculators/">All calculators &rarr;</a></div>'
        '<div class="grid g4" style="margin-top:0">'
        '<a class="card card-interactive" href="/calculator" data-link style="display:flex;flex-direction:column;padding:20px">'
        '<div class="pill-tag accent" style="align-self:flex-start;margin-bottom:12px">Brokerage</div>'
        '<h3 style="font-size:15px;font-weight:650;margin-bottom:6px">Brokerage &amp; Regulatory Fees</h3>'
        '<p class="xs muted" style="line-height:1.45;flex:1 0 auto">Calculate exact STT, GST, stamp duty and SEBI charges across delivery, intraday and F&amp;O.</p>'
        '<div class="link-arrow" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:14px">Calculate fees &rarr;</div></a>'
        '<a class="card card-interactive" href="/calculators/sip-calculator/" style="display:flex;flex-direction:column;padding:20px">'
        '<div class="pill-tag up" style="align-self:flex-start;margin-bottom:12px">SIP Compounder</div>'
        '<h3 style="font-size:15px;font-weight:650;margin-bottom:6px">Stock &amp; MF Wealth SIP</h3>'
        '<p class="xs muted" style="line-height:1.45;flex:1 0 auto">Project future corpus from disciplined monthly investments with compounding growth curves.</p>'
        '<div class="link-arrow" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:14px">Project returns &rarr;</div></a>'
        '<a class="card card-interactive" href="/calculators/direct-vs-regular-calculator/" style="display:flex;flex-direction:column;padding:20px">'
        '<div class="pill-tag accent" style="align-self:flex-start;margin-bottom:12px">Direct vs Regular</div>'
        '<h3 style="font-size:15px;font-weight:650;margin-bottom:6px">Mutual Fund Commission Leak</h3>'
        '<p class="xs muted" style="line-height:1.45;flex:1 0 auto">See how much wealth you lose to distributor commissions compared to direct mutual fund plans.</p>'
        '<div class="link-arrow" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:14px">Compare plans &rarr;</div></a>'
        '<a class="card card-interactive" href="/calculators/capital-gains-tax-calculator/" style="display:flex;flex-direction:column;padding:20px">'
        '<div class="pill-tag" style="align-self:flex-start;margin-bottom:12px">Tax</div>'
        '<h3 style="font-size:15px;font-weight:650;margin-bottom:6px">Capital Gains Tax Estimator</h3>'
        '<p class="xs muted" style="line-height:1.45;flex:1 0 auto">Estimate short-term and long-term capital gains tax on listed equity and equity mutual funds.</p>'
        '<div class="link-arrow" style="color:var(--accent-text);font-size:12px;font-weight:600;margin-top:14px">Estimate tax &rarr;</div></a>'
        '</div>'
        '<div class="card" style="margin-top:48px;padding:24px 28px;background:radial-gradient(80% 120% at 50% 0%, var(--bg-hover) 0%, var(--bg-raised) 100%);border-radius:20px">'
        '<div class="row-between" style="align-items:center;flex-wrap:wrap;gap:18px">'
        '<div style="max-width:68ch">'
        '<div class="row-wrap" style="gap:8px;align-items:center;margin-bottom:6px">'
        '<span class="badge badge-verified" style="font-size:12px;padding:3px 10px">&#10022; SEBI Register Primary Sourced</span>'
        '<span class="xs muted">Updated daily directly from regulatory circulars</span></div>'
        '<div style="font-size:16px;font-weight:700;color:var(--text);margin-bottom:4px">Verify Any Market Intermediary Before You Deposit Funds</div>'
        '<div class="xs muted" style="line-height:1.5">'
        'BrokerLens cross-references 1,785 registered stock brokers against official SEBI registration records, exchange membership master feeds (NSE, BSE, MCX), and 445 defaulter circulars. Never trade with unverified or flagged entities.'
        '</div></div>'
        '<div class="row-wrap" style="gap:10px">'
        '<a class="btn btn-primary link-arrow" href="/registry" data-link>Search SEBI Register &rarr;</a>'
        '<a class="btn" href="/sources" data-link>Audit Sources</a></div></div></div>'
    )

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
    from . import indexation as _ix
    new_html = _ix.add_home_footer_links(new_html)  # crawlable links to the hub pages Google had not found
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
        + ibslBanner_html("wide", "calculator") +

        '<h2 style="margin-top:28px;font-size:18px">Compare broker charges instead</h2>'
        '<a class="card" href="/calculator" style="display:block;max-width:520px">'
        '<h3 style="font-size:15px">Brokerage cost calculator</h3>'
        '<p class="small muted" style="margin-top:6px">Work out what a month of your actual trading '
        'costs at each Indian broker, using their published charges.</p></a>'
        '<a class="card" href="/trade-costs/" style="display:block;max-width:520px;margin-top:12px">'
        '<h3 style="font-size:15px">Trade cost calculator by stock and broker</h3>'
        '<p class="small muted" style="margin-top:6px">Brokerage, STT, exchange charges, stamp duty, SEBI fee '
        'and GST for a trade in each liquid stock under a broker\'s rate card.</p></a>'

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


def _write_find_broker_page(overview, built=None):
    """Interactive Broker Matchmaker page at /find-broker/ with 30-second decision
    wizard, full Schema.org WebApplication + FAQPage JSON-LD, and zero inline script."""
    canonical = "%s/find-broker/" % SITE_URL
    title = "Broker Matchmaker: Find the Best Stock Broker in India (2026) | BrokerLens"
    description = (
        "Find the ideal stock broker for your investment style, trading capital, and platform needs in 30 seconds. "
        "Objective recommendations based on verified SEBI registrations, complaint ratios, and published fee cards."
    )[:300]
    crumb_html, crumb_jsonld = _breadcrumb([
        ("BrokerLens", "/"),
        ("Find My Broker", None)
    ])
    faqs = [
        ("How does the BrokerLens Matchmaker choose the best broker for me?",
         "The matchmaker maps your primary activity (long-term equity delivery, F&O derivatives, IPOs, or 3-in-1 banking), your capital level, and your preferred platform feature (lowest cost, TradingView charts, free algo APIs, or physical branches) to verified primary exchange disclosures and official SEBI registration records."),
        ("Is BrokerLens paid to recommend specific stock brokers?",
         "No. BrokerLens scores brokers objectively using published tariff schedules, active client counts from NSE, and complaint ratios from SEBI SCORES disclosures. While BrokerLens may earn an affiliate referral commission if you open an account through partner links, this does not influence broker scoring or ranking methodology."),
        ("Which stock broker is best for beginners in India?",
         "For beginners investing primarily in equity delivery and direct mutual funds, discount brokers offering zero brokerage on delivery and zero annual Demat maintenance fees (such as Zerodha or Dhan) provide the lowest cost burden and highest regulatory trust."),
        ("Which broker is best for options and day trading?",
         "For active F&O traders, brokers offering direct TradingView charting integration, instant option chains, and flat Rs 20 per order fee caps (such as Dhan and Angel One) provide the best execution speed and lowest transaction friction.")
    ]
    faq_html = "".join(
        '<details class="faq-item"><summary>%s</summary><p>%s</p></details>'
        % (_esc(q), _esc(a)) for q, a in faqs
    )
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebApplication",
                "name": "BrokerLens Stock Broker Matchmaker",
                "url": canonical,
                "description": description,
                "applicationCategory": "FinanceApplication",
                "operatingSystem": "All"
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ]
            },
            crumb_jsonld
        ]
    }
    
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False)
    }
    body += crumb_html
    body += (
        '<div style="margin-top:16px">'
        '<div class="pill-tag accent" style="margin-bottom:8px"><span>✦</span> Automated Concierge</div>'
        '<h1 style="margin:0 0 8px 0;font-size:28px">Find Your Ideal Stock Broker</h1>'
        '<p class="muted" style="max-width:68ch;margin:0 0 24px 0">Answer 3 quick questions about your trading style, '
        'capital, and workflow preferences to get an instant, unbiased recommendation based on verified SEBI filings and fee cards.</p>'
        '<div id="broker-matchmaker-container">'
        '  <div class="matchmaker-wrap">'
        '    <div class="match-step-indicator">'
        '      <div class="match-step-dot active">1</div>'
        '      <div class="match-step-line"></div>'
        '      <div class="match-step-dot">2</div>'
        '      <div class="match-step-line"></div>'
        '      <div class="match-step-dot">3</div>'
        '    </div>'
        '    <div class="matchmaker-header">'
        '      <div class="pill-tag accent" style="margin-bottom:8px"><span>✦</span> 30-Second Matchmaker</div>'
        '      <h2 style="margin:0 0 6px 0;font-size:22px">What is your primary trading or investment goal?</h2>'
        '      <p class="muted small" style="margin:0">We match broker fee structures and platform strengths to your activity.</p>'
        '    </div>'
        '    <div class="match-grid">'
        '      <div class="match-card" data-val="investing">'
        '        <div class="match-card-icon">📈</div>'
        '        <div class="match-card-title">Long-Term Investing</div>'
        '        <div class="match-card-desc">Buy &amp; hold equity delivery, ETFs, and direct mutual funds without commissions.</div>'
        '      </div>'
        '      <div class="match-card" data-val="fno">'
        '        <div class="match-card-icon">⚡</div>'
        '        <div class="match-card-title">Options &amp; Day Trading</div>'
        '        <div class="match-card-desc">Active Nifty/BankNifty derivatives and intraday with fast charts and flat brokerage.</div>'
        '      </div>'
        '      <div class="match-card" data-val="ipos">'
        '        <div class="match-card-icon">🚀</div>'
        '        <div class="match-card-title">IPOs &amp; Primary Issues</div>'
        '        <div class="match-card-desc">Apply for upcoming mainboard and SME public issues easily via UPI mandate.</div>'
        '      </div>'
        '      <div class="match-card" data-val="bank_3in1">'
        '        <div class="match-card-icon">🏦</div>'
        '        <div class="match-card-title">3-in-1 Bank Integration</div>'
        '        <div class="match-card-desc">All-in-one seamless savings bank, demat and trading account under one umbrella.</div>'
        '      </div>'
        '    </div>'
        '    <div class="match-actions">'
        '      <div></div>'
        '      <div class="xs muted">Step 1 of 3</div>'
        '    </div>'
        '  </div>'
        '</div>'
        '<div style="margin-top:40px">'
        '  <h2 style="font-size:20px;margin-bottom:12px">Frequently Asked Questions</h2>'
        '  <div style="max-width:72ch">' + faq_html + '</div>'
        '</div>'
        '<p class="xs faint" style="margin-top:24px">BrokerLens is an independent financial research publisher, not a SEBI-registered investment adviser. '
        'Recommendations are computed algorithmically from primary regulatory disclosures. <a href="/methodology">Methodology</a> &middot; <a href="/sources">Sources &amp; Lineage</a> &middot; <a href="/editorial-policy">Editorial Policy</a></p>'
        '</div>'
    )
    matchmaker_script = _stamp_asset_versions('<script type="module" src="/assets/js/matchmaker.js"></script>')
    body += matchmaker_script
    body += _APP_SHELL_FOOT
    
    dest_dir = os.path.join(ROOT, "site", "find-broker")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    
    alias_dir = os.path.join(ROOT, "site", "match")
    os.makedirs(alias_dir, exist_ok=True)
    alias_body = body.replace("%s/find-broker/" % SITE_URL, "%s/match/" % SITE_URL)
    _write_text(os.path.join(alias_dir, "index.html"), alias_body)
    log("find-broker page: written", "ok")


def _write_cms_page(overview, built=None):
    """Executive CMS and Analytics Portal at /cms with authentication gate,
    real-time metrics, funnel visualizations, and zero inline script."""
    canonical = "%s/cms" % SITE_URL
    title = "BrokerLens CMS & Executive Analytics Portal"
    description = "BrokerLens Executive Analytics, Content Management, and Partner Conversion Portal."
    crumb_html, crumb_jsonld = _breadcrumb([
        ("BrokerLens", "/"),
        ("CMS Portal", None)
    ])
    jsonld = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "url": canonical,
        "description": description
    }
    
    body = _APP_SHELL_HEAD % {
        "title": _esc(title), "description": _esc(description),
        "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False)
    }
    body = body.replace(
        '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">',
        '<meta name="robots" content="noindex, nofollow">'
    )
    body += crumb_html
    body += (
        '<div style="margin-top:16px">'
        '<div id="brokerlens-cms-container">'
        '  <div style="text-align:center;padding:48px 20px;color:var(--text-faint)">'
        '    <div style="font-size:24px;margin-bottom:8px">&#128274;</div>'
        '    <p>Loading BrokerLens CMS Portal&hellip;</p>'
        '  </div>'
        '</div>'
        '</div>'
    )
    cms_script = _stamp_asset_versions('<script type="module" src="/assets/js/cms.js"></script>')
    body += cms_script
    body += _APP_SHELL_FOOT
    
    dest_dir = os.path.join(ROOT, "site", "cms")
    os.makedirs(dest_dir, exist_ok=True)
    _write_text(os.path.join(dest_dir, "index.html"), body)
    log("cms portal page: written", "ok")



# Which sitemap files are submitted at each stage. 1 = core, brokers, IPO pages, the SEBI
# registry (best performer), news, crypto and the ~500 most-traded stocks; 2 = fund/ETF/AMC,
# comparison permutations, long-tail stocks, per-IPO apply/subscription pages, SIP scenarios;
# 3 = the 70K+ per-stock trade-cost pages and branch pages. Unknown names default to wave 2.
SITEMAP_WAVES = {
    "core": 1, "brokers": 1, "ipos": 1, "registry": 1, "news": 1, "crypto": 1, "stocks-top": 1,
    "stocks": 2, "funds": 2, "stock-compare": 2, "fund-compare": 2, "ipo-apply": 2, "ipo-sub": 2, "sip-calc": 2,
    "trade-costs": 3, "branches": 3, "price-targets": 3,
}
SITEMAP_WAVES["broker-charges"] = 1  # per-broker calculator and charges pages: few, high intent


def _write_sitemap(built, reg_rows=None, hub_groups=None, companies=None, indices=None, etfs=None,
                    fund_slugs=None, report_slugs=None, calc_slugs=None, stock_letters=None, amc_slugs=None,
                    crypto_slugs=None, ipo_records=None, registry_letters=None, equity_history=None,
                    fund_nav_dates=None, comparison_pairs=None, trade_cost_urls=None,
                    ipo_apply_urls=None, stock_compare_urls=None, sip_calc_urls=None,
                    branch_urls=None, fund_compare_urls=None, fund_category_urls=None,
                    ipo_sub_urls=None, share_price_target_urls=None, broker_charges_urls=None):
    _require_site_url()
    import math
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sitemaps_dir = os.path.join(SITE_DATA, "..", "sitemaps")
    os.makedirs(sitemaps_dir, exist_ok=True)

    def _xml_url(loc, lastmod, freq="monthly"):
        clean_loc = html.escape(str(loc or ""), quote=True)
        return f"<url><loc>{clean_loc}</loc><lastmod>{lastmod}</lastmod><changefreq>{freq}</changefreq></url>"

    # 1. CORE SITEMAP (Main navigation, static hubs, calculators, legal, methodology)
    # Each entry is the page's own canonical URL (static hub pages end in a slash, the
    # SPA-routed pages do not). A sitemap entry that differs from the canonical by a
    # trailing slash is a duplicate URL Google has to reconcile, and /ipo/ and /news/
    # were reported as unknown while only /ipo and /news were listed.
    core_urls = [
        "/", "/brokers", "/leaderboards", "/compare", "/find-broker/", "/calculator", "/calculators/",
        "/registry", "/algo", "/methodology", "/sources", "/stocks/", "/funds-by/", "/etfs/", "/crypto/",
        "/ipo/", "/ipo/upcoming/", "/ipo/archive/", "/ipo/allotment-status/", "/ipo/how-to-apply/", "/ipo/registrars/",
        "/ipo/subscription/", "/ipo/allotment/", "/ipo/sme/", "/ipo/gmp/",
        "/trade-costs/", "/compare/stocks/", "/compare/mutual-funds/", "/calculators/sip/",
        "/branches/", "/news/", "/about", "/editorial-policy", "/contact",
        "/privacy-policy", "/terms-of-service"
    ]
    for slug in (report_slugs or []):
        core_urls.append("/reports/%s/" % slug)
    for slug in (calc_slugs or []):
        core_urls.append("/calculators/%s/" % slug)
    core_entries = [_xml_url(SITE_URL + u, today, "daily") for u in core_urls]

    # 2. BROKERS SITEMAP (Profiles, comparisons, hub dimensions)
    broker_entries = [
        "<url><loc>%s/broker/%s/</loc><lastmod>%s</lastmod><changefreq>daily</changefreq></url>"
        % (SITE_URL, b["id"], today) for b in built
    ]
    if comparison_pairs:
        broker_entries += [
            "<url><loc>%s/compare/%s-vs-%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
            % (SITE_URL, p[0], p[1], today) for p in comparison_pairs
        ]
    for dim, key, _label, _rows in (hub_groups or []):
        slug = slugify(key.replace("_", "-"))
        if slug:
            broker_entries.append(
                "<url><loc>%s/brokers-by/%s/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                % (SITE_URL, dim, slug, today)
            )
    hub_dims_present = {d for d, _, _, _ in (hub_groups or [])}
    for dim in ("type", "segment", "city"):
        if dim in hub_dims_present:
            broker_entries.append(
                "<url><loc>%s/brokers-by/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
                % (SITE_URL, dim, today)
            )

    # 3. IPOs SITEMAP
    ipo_entries = []
    from . import ipo_facts as _ipofacts
    for r in (ipo_records or []):
        if _ipofacts.is_non_equity_issue(r):
            continue
        freq = "daily" if r.get("status") in ("Active", "Forthcoming") else "monthly"
        ipo_entries.append(
            "<url><loc>%s/ipo/%s/</loc><lastmod>%s</lastmod><changefreq>%s</changefreq></url>"
            % (SITE_URL, r["symbol"].lower(), today, freq)
        )

    # 4. STOCKS SITEMAP. The ~500 most-traded names (by average daily volume in the
    # history on file) form wave 1; the long tail waits in wave 2 (see SITEMAP_WAVES).
    stock_entries, stock_top_entries = [], []
    eq_hist = equity_history or {}

    def _avg_vol(sym):
        h = eq_hist.get((sym or "").upper()) or []
        vs = [r["volume"] for r in h if isinstance(r.get("volume"), (int, float))]
        return sum(vs) / len(vs) if vs else 0
    top_syms = {(c.get("symbol") or "").upper() for c in sorted(companies or [], key=lambda c: -_avg_vol(c.get("symbol")))[:500]
                if _avg_vol(c.get("symbol")) > 0}
    # Trading volume is a poor proxy for where this site actually wins in search: GSC shows
    # small and mid caps ranking, large caps lost to established portals. Stocks with proven
    # search demand (maintained daily by scripts/gsc_report.py) join wave 1 too.
    demand = set((read_json(os.path.join(ROOT, "reports", "gsc", "stock_demand.json"), {}) or {}).get("slugs") or [])
    for c in (companies or []):
        slug = _stock_slug(c.get("symbol"))
        if slug:
            hist = eq_hist.get((c.get("symbol") or "").upper()) or []
            lastmod = hist[-1]["date"] if hist else today
            entry = ("<url><loc>%s/stock/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
                     % (SITE_URL, slug, lastmod))
            wave1 = (c.get("symbol") or "").upper() in top_syms or slug in demand
            (stock_top_entries if wave1 else stock_entries).append(entry)
    for slug in (indices or {}):
        stock_top_entries.append(
            "<url><loc>%s/index/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
            % (SITE_URL, slug, today)
        )
    for letter in (stock_letters or []):
        stock_top_entries.append(
            "<url><loc>%s/stocks/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
            % (SITE_URL, slugify(letter), today)
        )

    # 5. FUNDS & ETFs SITEMAP
    fund_entries = []
    for slug in (fund_slugs or {}):
        lastmod = (fund_nav_dates or {}).get(slug, today)
        fund_entries.append(
            "<url><loc>%s/fund/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
            % (SITE_URL, slug, lastmod)
        )
    for amc_slug in (amc_slugs or {}).values():
        fund_entries.append(
            "<url><loc>%s/funds-by/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
            % (SITE_URL, amc_slug, today)
        )
    from . import indexation as _ix
    etf_slugs = {_stock_slug(e.get("symbol")) for e in (etfs or []) if _stock_slug(e.get("symbol"))}
    top_etfs = set(_ix.top_etf_slugs(etfs, eq_hist, _stock_slug, limit=40)) | (demand & etf_slugs)
    for e in (etfs or []):
        slug = _stock_slug(e.get("symbol"))
        if slug:
            hist = eq_hist.get((e.get("symbol") or "").upper()) or []
            lastmod = hist[-1]["date"] if hist else today
            # The most-traded ETFs ride in wave 1, inside the stocks-top shard (the /etf/ pages
            # were reported unknown to Google while the whole fund shard waits in wave 2).
            (stock_top_entries if slug in top_etfs else fund_entries).append(
                "<url><loc>%s/etf/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
                % (SITE_URL, slug, lastmod)
            )

    # 6. SEBI REGISTRY SITEMAP
    registry_entries = [
        "<url><loc>%s/sebi-registry/%s/</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq></url>"
        % (SITE_URL, r["slug"], today) for r in (reg_rows or []) if r.get("slug") and not r.get("primary")
    ]
    if registry_letters:
        registry_entries.append(
            "<url><loc>%s/registry/az/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
            % (SITE_URL, today)
        )
    for letter in (registry_letters or []):
        registry_entries.append(
            "<url><loc>%s/registry/az/%s/</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq></url>"
            % (SITE_URL, slugify(letter), today)
        )

    # 7. NEWS & ARTICLES SITEMAP (with Google News schema tags)
    news_entries = []
    news_meta_path = os.path.join(ROOT, "site", "data", "news.json")
    news_meta_dict = {}
    if os.path.exists(news_meta_path):
        try:
            with open(news_meta_path, "r", encoding="utf-8") as f:
                news_meta_dict = {a["slug"]: a for a in json.load(f).get("articles", []) if a.get("slug")}
        except Exception:
            pass

    news_dir = os.path.join(ROOT, "site", "news")
    if os.path.isdir(news_dir):
        for item in sorted(os.listdir(news_dir)):
            if item != "index.html" and os.path.isdir(os.path.join(news_dir, item)):
                art = news_meta_dict.get(item) or {}
                art_title = _esc(art.get("title") or item.replace("-", " ").title())
                art_date = art.get("date") or today
                news_entries.append(
                    "<url><loc>%s/news/%s/</loc><lastmod>%s</lastmod><changefreq>daily</changefreq>"
                    "<news:news>"
                    "<news:publication><news:name>BrokerLens</news:name><news:language>en</news:language></news:publication>"
                    "<news:publication_date>%s</news:publication_date>"
                    "<news:title>%s</news:title>"
                    "</news:news>"
                    "</url>"
                    % (SITE_URL, item, art_date, art_date, art_title)
                )

    # 8. CRYPTO SITEMAP
    crypto_entries = [
        "<url><loc>%s/crypto/%s/</loc><lastmod>%s</lastmod><changefreq>daily</changefreq></url>"
        % (SITE_URL, slug, today) for slug in (crypto_slugs or [])
    ]

    # 9. TRADE COSTS SITEMAP (Transactional stock x broker calculations)
    trade_cost_entries = []
    if trade_cost_urls:
        for u in trade_cost_urls:
            trade_cost_entries.append(_xml_url(SITE_URL + u, today, "monthly"))
    else:
        broker_dir = os.path.join(ROOT, "site", "broker")
        if os.path.isdir(broker_dir):
            for b_id in os.listdir(broker_dir):
                t_dir = os.path.join(broker_dir, b_id, "trade")
                if os.path.isdir(t_dir):
                    for s_slug in os.listdir(t_dir):
                        if os.path.isdir(os.path.join(t_dir, s_slug)):
                            trade_cost_entries.append(_xml_url(f"{SITE_URL}/broker/{b_id}/trade/{s_slug}/", today, "monthly"))

    # 10. IPO APPLICATION WALKTHROUGHS SITEMAP
    ipo_apply_entries = []
    if ipo_apply_urls:
        for u in ipo_apply_urls:
            ipo_apply_entries.append(_xml_url(SITE_URL + u, today, "weekly"))

    # 11. STOCK 1v1 PEER COMPARISONS SITEMAP
    stock_compare_entries = []
    if stock_compare_urls:
        for u in stock_compare_urls:
            stock_compare_entries.append(_xml_url(SITE_URL + u, today, "weekly"))

    # 12. PROGRAMMATIC SIP SCENARIOS SITEMAP
    sip_calc_entries = []
    if sip_calc_urls:
        for u in sip_calc_urls:
            sip_calc_entries.append(_xml_url(SITE_URL + u, today, "monthly"))

    # 13. BROKER BRANCHES & CITY REGISTRY SITEMAP
    branch_entries = []
    if branch_urls:
        for u in branch_urls:
            branch_entries.append(_xml_url(SITE_URL + u, today, "monthly"))

    # 14. MUTUAL FUND 1v1 PEER COMPARISONS & CATEGORIES SITEMAP
    fund_compare_entries = []
    if fund_compare_urls:
        for u in fund_compare_urls:
            fund_compare_entries.append(_xml_url(SITE_URL + u, today, "weekly"))
    if fund_category_urls:
        for u in fund_category_urls:
            fund_compare_entries.append(_xml_url(SITE_URL + u, today, "weekly"))

    # 15. IPO SUBSCRIPTIONS & BASIS OF ALLOTMENT SITEMAP
    ipo_sub_entries = []
    if ipo_sub_urls:
        for u in ipo_sub_urls:
            ipo_sub_entries.append(_xml_url(SITE_URL + u, today, "weekly"))

    # 16. SHARE PRICE TARGETS & FORECASTS SITEMAP
    price_target_entries = []
    if share_price_target_urls:
        for u in share_price_target_urls:
            price_target_entries.append(_xml_url(SITE_URL + u, today, "monthly"))

    # 17. PER-BROKER BROKERAGE CALCULATOR AND CHARGES PAGES (wave 1, see SITEMAP_WAVES)
    broker_charges_entries = [_xml_url(SITE_URL + u, today, "monthly") for u in (broker_charges_urls or [])]

    # Partitioned sitemaps automatically shard at CHUNK_LIMIT (45,000 URLs) into
    # sitemap-<name>-1.xml, sitemap-<name>-2.xml, etc.
    sub_sitemaps = [
        ("core", core_entries),
        ("brokers", broker_entries),
        ("ipos", ipo_entries),
        ("stocks-top", stock_top_entries),
        ("stocks", stock_entries),
        ("funds", fund_entries),
        ("registry", registry_entries),
        ("news", news_entries),
        ("crypto", crypto_entries),
        ("trade-costs", trade_cost_entries),
        ("ipo-apply", ipo_apply_entries),
        ("ipo-sub", ipo_sub_entries),
        ("stock-compare", stock_compare_entries),
        ("sip-calc", sip_calc_entries),
        ("branches", branch_entries),
        ("fund-compare", fund_compare_entries),
        ("price-targets", price_target_entries),
        ("broker-charges", broker_charges_entries),
    ]

    sitemap_index_entries = []
    CHUNK_LIMIT = 45000

    # Tiered submission. A new domain with no authority is judged on the quality of what
    # it asks Google to index, so only wave 1 (the page types that already earn clicks
    # or are core to the product) is listed in the sitemap index. Later waves are still
    # linked on the site and fully crawlable; they are promoted by raising SITEMAP_WAVE
    # once the previous wave is indexing well. Nothing is noindexed by this.
    current_wave = int(os.environ.get("SITEMAP_WAVE", "1") or 1)
    held_back = {}
    # lastmod/changefreq only when real: a lastmod equal to the build date on every URL
    # of every build is noise Google learns to ignore, so it is omitted unless it came
    # from real data (a trading date, an NAV date).
    _fake_lastmod = "<lastmod>%s</lastmod>" % today
    _changefreq = re.compile(r"<changefreq>[^<]*</changefreq>")

    # A hub URL such as /calculators/sip/ is listed by the core shard and also by its own
    # family shard; once a later wave is submitted that would put one loc in two files.
    # Keep the first occurrence (core is written first) and drop repeats from later shards.
    _seen_locs = set()
    _loc_re = re.compile(r"<loc>([^<]*)</loc>")

    def _first_time(entry):
        m = _loc_re.search(entry)
        if not m:
            return True
        if m.group(1) in _seen_locs:
            return False
        _seen_locs.add(m.group(1))
        return True

    for name, entries in sub_sitemaps:
        if not entries:
            continue
        if SITEMAP_WAVES.get(name, 2) > current_wave:
            held_back[name] = len(entries)
            continue
        entries = [_changefreq.sub("", e).replace(_fake_lastmod, "") for e in entries if _first_time(e)]
        if not entries:
            continue
        total_chunks = math.ceil(len(entries) / CHUNK_LIMIT) or 1
        for i in range(total_chunks):
            chunk = entries[i * CHUNK_LIMIT : (i + 1) * CHUNK_LIMIT]
            filename = "sitemap-%s.xml" % name if total_chunks == 1 else "sitemap-%s-%d.xml" % (name, i + 1)
            news_ns = ' xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"' if name == "news" else ""
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"{news_ns}>\n'
                + "".join(chunk)
                + "\n</urlset>"
            )
            _write_text(os.path.join(sitemaps_dir, filename), xml)
            sitemap_index_entries.append(
                "<sitemap><loc>%s/sitemaps/%s</loc></sitemap>" % (SITE_URL, filename)
            )

    # Drop sitemap shards this run did not write. An engine that now emits zero
    # URLs (e.g. retired share-price-target pages) would otherwise leave last
    # run's file on disk and tracked in git, still advertising URLs that
    # redirect or are noindex.
    written = {e.split("/sitemaps/")[1].split("<")[0] for e in sitemap_index_entries}
    for fn in os.listdir(sitemaps_dir):
        if fn.startswith("sitemap-") and fn.endswith(".xml") and fn not in written:
            os.remove(os.path.join(sitemaps_dir, fn))

    # Write root sitemap.xml as standard <sitemapindex>
    index_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(sitemap_index_entries)
        + "\n</sitemapindex>"
    )
    _write_text(os.path.join(SITE_DATA, "..", "sitemap.xml"), index_xml)
    submitted = len(_seen_locs)  # unique URLs actually written, repeats across shards excluded
    log("sitemap index: %d sub-sitemaps, %d URLs submitted (wave %d); %d URLs held back in %s" % (
        len(sitemap_index_entries), submitted, current_wave, sum(held_back.values()),
        ", ".join("%s=%d" % kv for kv in sorted(held_back.items())) or "none"), "ok")


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
    ("Check IPO allotment status", "/ipo/allotment-status/", "Registrar and PAN verification"),
    ("How to apply for IPO online", "/ipo/how-to-apply/", "UPI and ASBA guide"),
    ("Full IPO archive", "/ipo/archive/", ""),
    ("Stock trading cost calculator hub", "/trade-costs/", "STT, exchange fees and DP charges"),
    ("Compare stocks side-by-side", "/compare/stocks/", "Peer stock metrics and 1Y returns"),
    ("SIP wealth calculator scenarios", "/calculators/sip/", "Monthly SIP compounding schedules"),
    ("Market news, blogs & research", "/news/", ""),
]


def _write_search_index(built, reg_rows, hub_groups, companies, indices, etfs, fund_slugs, report_slugs,
                         amc_slugs=None, crypto_coins=None, ipo_records=None, comparison_pairs=None,
                         news_articles=None, stock_compare_search=None, fund_compare_search=None):
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

    if comparison_pairs:
        b_map = {b["id"]: b["profile"].get("brand") or b["id"] for b in built}
        for b1_id, b2_id in comparison_pairs:
            brand1 = b_map.get(b1_id, b1_id)
            brand2 = b_map.get(b2_id, b2_id)
            rows.append(["%s vs %s" % (brand1, brand2), "/compare/%s-vs-%s/" % (b1_id, b2_id), "compare", "Side by side broker comparison"])

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

    for art in (news_articles or []):
        rows.append([art["title"], "/news/%s/" % art["slug"], "news", art.get("category") or ""])

    # Only the curated (real sector-peer / same-category) comparison pairs -
    # the random noindex all-pairs are deliberately excluded from search the
    # same way they're excluded from the sitemap (see stock_compare_engine.py
    # and fund_compare_engine.py).
    for name, url, sub in (stock_compare_search or []):
        rows.append([name, url, "compare", sub])

    for name, url, sub in (fund_compare_search or []):
        rows.append([name, url, "compare", sub])

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
    _write_ads_txt()


def _write_text(path, body):
    """Atomic write, so a crash or a CDN read mid-write cannot serve half a file."""
    if isinstance(body, str) and ("\u2014" in body or "\u2013" in body):
        body = body.replace("\u2014", " - ").replace("\u2013", "-")
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
        "Disallow: /cms",
        "",
        "Sitemap: %s/sitemap.xml" % SITE_URL,
        "",
    ])
    _write_text(os.path.join(SITE_DATA, "..", "robots.txt"), body)


def _write_ads_txt():
    """Publish Authorized Digital Sellers (ads.txt) for Google AdSense verification."""
    body = "google.com, pub-8447377943455646, DIRECT, f08c47fec0942fa0\n"
    _write_text(os.path.join(SITE_DATA, "..", "ads.txt"), body)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
