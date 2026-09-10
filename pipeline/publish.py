"""Assembles ingested + manual data into the static JSON payloads the site reads.

Output contract (site/data/):
  overview.json        market pulse, aggregates, leaderboards, compact broker index
  brokers/<id>.json    full profile, lazily fetched on route change
  sources.json         data lineage - every source, when it last ran, what it fed
  search.json          tiny index for instant client-side search
  sitemap.xml, feed.xml

Design constraint carried over from mtf.trading: the browser must never call a
live API. Everything is precomputed, CDN-cacheable and survives a source going
down.
"""
from __future__ import annotations

import json
import os
import re
import shutil
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

# PUBLISH_MODE=production drops every dataset flagged provenance:"sample" instead
# of publishing it behind a banner. Set it for any build that reaches a public
# origin. Local development stays in the default mode so the UI has data to
# exercise.
PRODUCTION = os.environ.get("PUBLISH_MODE", "").lower() == "production"

# A sitemap and RSS feed of unresolvable URLs is worse than none: search engines
# reject it and the failure is silent. The old default was "https://example.invalid"
# and it shipped in the committed artefacts, so the placeholder is now refused.
_PLACEHOLDER_HOSTS = ("example.invalid", "example.com", "localhost", "127.0.0.1")


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

    write_json(os.path.join(SITE_DATA, "search.json"),
               [{"i": b["id"], "n": b["profile"]["brand"], "l": b["profile"]["legal_name"],
                 "h": b["profile"]["hq"]} for b in built], compact=True)

    _write_sources(sources_cfg, ingest, sample_flags)
    _write_algo(brokers_cfg)
    _write_timings()
    _write_registry_pages(reg_rows)
    _write_broker_pages(built)
    hub_groups = _write_broker_hub_pages(built)
    equity_companies = ((nse_d.get("universe") or {}).get("companies")) or []
    index_universe = nse_d.get("indices") or {}
    _write_stock_pages(equity_companies, read_json(os.path.join(CONFIG, "broker_stocks.json"), {}).get("stocks"),
                        index_universe)
    _write_index_pages(index_universe, equity_companies)
    etf_universe = nse_d.get("etfs") or []
    _write_etf_pages(etf_universe, index_universe)
    mf_schemes = amfi_d.get("schemes") or []
    _funds, fund_slugs = _write_mutual_fund_pages(mf_schemes)
    report_slugs = _write_reports(built, reg_rows, equity_companies, index_universe, etf_universe,
                                   _funds, len(sebi_d.get("defaulters") or []))
    calc_slugs = _write_calculator_pages()
    _write_sitemap(built, reg_rows, hub_groups, equity_companies, index_universe, etf_universe,
                    fund_slugs, report_slugs, calc_slugs)
    _write_feed(built, aggregates)
    build_ticker()
    return overview


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
    """Emit site/data/ticker.json — the payload the rolling header polls.

    Separate from overview.json and deliberately small so it can be refreshed
    every minute (or streamed) without republishing the site.
    """
    ingest = read_json(os.path.join(INGEST_PATH), {}) or {}
    built = feeds.build(ingest)

    payload = {
        "generated_at": now_iso(),
        "order": feeds.FEED_ORDER,
        "feeds": built,
    }
    size = write_json(os.path.join(SITE_DATA, "ticker.json"), payload, compact=True)
    counts = " ".join("%s=%d" % (k, len(v.get("instruments") or [])) for k, v in built.items())
    log("ticker.json %.1f KB (%s)" % (size / 1024, counts), "ok")
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
    write_json(os.path.join(SITE_DATA, "sources.json"),
               {"generated_at": now_iso(), "sources": rows,
                "licensing": cfg.get("licensing"), "sample_data": sample_flags})


def _write_algo(brokers_cfg):
    """Emit site/data/algo.json — the curated algo-platform directory.

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


def _write_timings():
    """Emit site/data/timings.json — curated session timings for the nav mega menu."""
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
<link rel="stylesheet" href="/assets/css/app.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BrokerLens India">
<meta property="og:locale" content="en_IN">
<meta property="og:url" content="%(canonical)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(description)s">
<script type="application/ld+json">%(jsonld)s</script>
</head>
<body>
<header class="site"><div class="wrap nav">
  <a class="brand" href="/">
    <svg class="brand-logo" viewBox="0 0 512 512" width="26" height="26" role="img" aria-label="BrokerLens India">
      <defs><clipPath id="bl-lens-reg"><circle cx="256" cy="256" r="143"/></clipPath></defs>
      <g fill="none" stroke="var(--accent)" stroke-width="30" stroke-linecap="round">
        <path d="M50 369 L84 359" opacity=".38"/><path d="M18 379 L30 375" opacity=".18"/>
        <path d="M438 161 L470 149" opacity=".38"/><path d="M486 143 L496 140" opacity=".18"/>
      </g>
      <circle cx="256" cy="256" r="166" fill="none" stroke="var(--accent)" stroke-width="46"/>
      <path d="M-24 392 L146 340 L212 288 L272 336 L360 190 L528 128" fill="none" stroke="var(--up)"
            stroke-width="46" stroke-linecap="round" stroke-linejoin="round" clip-path="url(#bl-lens-reg)"/>
    </svg>
    <span>BrokerLens<span class="muted" style="font-weight:400"> India</span></span>
  </a>
  <nav class="nav-links" style="display:flex">
    <a href="/brokers">Brokers</a>
    <a href="/registry">SEBI registry</a>
    <a href="/algo">Algo platforms</a>
    <a href="/reports/state-of-indian-broking-2026/">Reports</a>
  </nav>
</div></header>
<main class="wrap" style="padding-top:24px;padding-bottom:24px">
"""

_REGISTRY_PAGE_FOOT = """</main>
<footer class="site"><div class="wrap">
  <p class="small muted" style="max-width:70ch">%(source_note)s</p>
  <p class="small"><a href="/registry">Search the full SEBI registry →</a> ·
  <a href="/brokers">Brokers tracked in depth →</a> · <a href="/">BrokerLens India home →</a></p>
</div></footer>
</body>
</html>
"""


def _source_note(claim):
    """Every static page's footer states, in plain language, exactly what it
    is (and isn't). The claim differs by page type - SEBI's register, NSE's
    listed-securities master and NSE's own index files are three different
    sources, and stating the wrong one on a page is a factual error, not a
    stylistic one - so this is never reused verbatim across page types."""
    return ("%s It is not curated, scored or ranked, and nothing on it is investment advice. "
            "BrokerLens is not a SEBI-registered investment adviser or research analyst." % claim)


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

        title = "%s: SEBI Registration | BrokerLens India" % name
        description = ("%s: SEBI registration number, category, exchange memberships and validity, "
                       "sourced from SEBI's recognised-intermediary register." % name)[:300]

        jsonld = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": name,
            "url": canonical,
        }
        if r.get("trade_name"):
            jsonld["alternateName"] = r["trade_name"]
        if r.get("reg"):
            jsonld["identifier"] = r["reg"]
        if r.get("city"):
            jsonld["address"] = {"@type": "PostalAddress", "addressLocality": r["city"], "addressCountry": "IN"}

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
            '<h1 style="margin-top:0">%s</h1>' % _esc(name)
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
    """
    shell = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
    written = 0
    for b in built:
        bid, brand = b["id"], b["profile"].get("brand") or b["id"]
        canonical = "%s/broker/%s/" % (SITE_URL, bid)
        title = "%s: active clients, complaints and charges | BrokerLens India" % _esc(brand)
        description = _esc(
            "%s: active client count, market share, SEBI complaint record, regulatory registrations "
            "and cost, from primary NSE, BSE and SEBI disclosures." % brand
        )[:300]
        jsonld = {"@context": "https://schema.org", "@type": "FinancialService", "name": brand, "url": canonical}
        if b["profile"].get("legal_name"):
            jsonld["legalName"] = b["profile"]["legal_name"]
        if b["profile"].get("sebi_reg_no"):
            jsonld["identifier"] = b["profile"]["sebi_reg_no"]
        if b["profile"].get("hq"):
            jsonld["address"] = {"@type": "PostalAddress", "addressLocality": b["profile"]["hq"], "addressCountry": "IN"}
        jsonld["areaServed"] = "IN"

        page = shell
        page = page.replace(
            "<title>BrokerLens India: Indian stock broker statistics from NSE, BSE and SEBI</title>",
            "<title>%s</title>" % title, 1)
        page = page.replace(
            'content="Compare every SEBI-registered Indian stock broker on active clients, market share, '
            'complaint records and cost. Built from primary NSE, BSE and SEBI disclosures.">',
            'content="%s">' % description, 1)
        page = page.replace('<link rel="canonical" href="/">', '<link rel="canonical" href="%s">' % canonical, 1)
        page = page.replace('<meta property="og:url" content="/">', '<meta property="og:url" content="%s">' % canonical, 1)
        page = page.replace(
            '<meta property="og:title" content="BrokerLens India: broker statistics from primary sources">',
            '<meta property="og:title" content="%s">' % title, 1)
        page = page.replace(
            '<meta property="og:description" content="Active clients, market share, SEBI complaint records '
            'and cost, for every registered Indian stock broker.">',
            '<meta property="og:description" content="%s">' % description, 1)
        page = page.replace(
            "</head>",
            '<script type="application/ld+json">%s</script>\n</head>' % json.dumps(jsonld, ensure_ascii=False), 1)

        old_main = (
            '<main id="app" class="wrap" style="padding-top:24px;padding-bottom:24px">\n'
            '  <div class="grid g3">\n'
            '    <div class="card skeleton" style="height:96px"></div>\n'
            '    <div class="card skeleton" style="height:96px"></div>\n'
            '    <div class="card skeleton" style="height:96px"></div>\n'
            '  </div>\n'
            '</main>'
        )
        new_main = ('<main id="app" class="wrap" style="padding-top:24px;padding-bottom:24px">'
                    + _broker_facts_html(b) + '</main>')
        if old_main not in page:
            log("broker pages: shell <main> markup did not match expected text for %s; skipping" % bid, "err")
            continue
        page = page.replace(old_main, new_main, 1)

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
        title = ("%s %s | BrokerLens India" % (noun, label)) if dim != "type" else ("%s: %s | BrokerLens India" % (noun, label))
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

        jsonld = {
            "@context": "https://schema.org", "@type": "ItemList", "name": h1, "url": canonical,
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": "%s/broker/%s/" % (SITE_URL, b["id"]),
                 "name": b["profile"].get("brand") or b["id"]}
                for i, b in enumerate(rows_sorted)
            ],
        }

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            '<h1 style="margin-top:0">%s</h1>' % _esc(h1)
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

    pruned = 0
    hub_base = os.path.join(ROOT, "site", "brokers-by")
    for dim in ("type", "segment", "city"):
        keep = {slugify(key.replace("_", "-")) for d, key, _, _ in groups if d == dim}
        pruned += _prune_stale_dirs(os.path.join(hub_base, dim), keep)
    log("broker hub pages: %d written (type/segment/city)%s" % (
        written, (", %d stale pruned" % pruned) if pruned else ""), "ok")
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


def _write_stock_pages(companies, brokers_cfg, indices=None):
    """One static page per NSE-listed equity - Phase 1 of docs/SCALE_TO_60K_PLAN.md.

    The data (NSE's own EQUITY_L.csv) was already being fetched on every run;
    only the page-generation step is new. Unlike the sample-gated broker
    metrics, every field here is always real and always available - there is
    no "not published yet" state for a company's own listing facts.

    Path is /stock/:symbol/, checked against the live SPA route list before
    use (nothing named "stock" exists there) - same discipline that avoided
    two prior collisions (site/registry/, site/brokers/).
    """
    by_symbol = {s["symbol"].upper(): s for s in (brokers_cfg or [])}
    membership = {}
    for slug, idx in (indices or {}).items():
        for con in idx["constituents"]:
            sym = (con.get("symbol") or "").upper()
            if sym:
                membership.setdefault(sym, []).append((slug, idx["label"]))
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
        title = "%s (%s): NSE Listing Details | BrokerLens India" % (_esc(name), _esc(symbol))
        description = _esc(
            "%s (NSE: %s): ISIN, listing date, face value and market lot, "
            "sourced directly from NSE's own listed-securities register." % (name, symbol)
        )[:300]

        jsonld = {"@context": "https://schema.org", "@type": "Corporation", "name": name,
                  "tickerSymbol": symbol, "url": canonical}
        if c.get("isin"):
            jsonld["identifier"] = c["isin"]

        def fact(raw):
            return _esc(raw) if raw else "Not disclosed"

        facts_html = "".join(
            '<div class="mega-seg"><div class="mega-seg-label">%s</div><div style="margin-top:2px">%s</div></div>'
            % (label, value) for label, value in [
                ("NSE symbol", fact(symbol)),
                ("ISIN", fact(c.get("isin"))),
                ("Series", fact(c.get("series"))),
                ("Listed on NSE since", fact(_long_date(c.get("listing_date")) if c.get("listing_date") else None)),
                ("Face value", fact(("Rs %s" % c["face_value"]) if c.get("face_value") else None)),
                ("Market lot", fact(c.get("market_lot"))),
            ]
        )

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

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + '<p class="muted">NSE: %s</p>' % _esc(symbol)
            + broker_link
            + '<div class="grid g3" style="margin-top:16px">' + facts_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">Source: NSE listed-securities master file (EQUITY_L). '
              'Live price and trading data are not carried on this page.</p>'
            + index_html
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
        title = "%s: Constituent Stocks List | BrokerLens India" % label
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
        title = "%s (%s): ETF Listing Details | BrokerLens India" % (_esc(name), _esc(symbol))
        description = _esc(
            "%s (NSE: %s): the ETF's underlying benchmark, ISIN, listing date and market lot, "
            "sourced directly from NSE's own listed-ETF register." % (name, symbol)
        )[:300]

        jsonld = {"@context": "https://schema.org", "@type": "FinancialProduct", "name": name, "url": canonical}
        if e.get("isin"):
            jsonld["identifier"] = e["isin"]
        if e.get("underlying_key"):
            jsonld["category"] = e["underlying_key"]

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

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            '<h1 style="margin-top:0">%s</h1>' % _esc(name)
            + '<p class="muted">NSE: %s</p>' % _esc(symbol)
            + '<div class="grid g3" style="margin-top:16px">' + facts_html + '</div>'
            + '<p class="xs faint" style="margin-top:16px">Source: NSE listed-ETF register. '
              'Live price and trading data are not carried on this page.</p>'
            + index_html
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
        title = "%s: Mutual Fund Scheme Details | BrokerLens India" % _esc(name)
        description = _esc(
            "%s from %s: NAV, ISIN and plan/option details for every variant of this scheme, "
            "sourced directly from AMFI's own daily NAV master file." % (name, amc)
        )[:300]

        jsonld = {"@context": "https://schema.org", "@type": "FinancialProduct", "name": name,
                  "url": canonical, "provider": {"@type": "Organization", "name": amc}}
        if fund["categories"]:
            jsonld["category"] = fund["categories"][0]

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

        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(title), "description": description,
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            '<h1 style="margin-top:0">%s</h1>' % _esc(name)
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
    title = "State of Indian Broking & Investing 2026 | BrokerLens India"
    description = _esc(
        "How many SEBI-registered brokers, NSE-listed companies, ETFs and mutual fund schemes actually "
        "exist in India, counted directly from primary regulator and exchange data."
    )[:300]

    jsonld = {
        "@context": "https://schema.org", "@type": "Article", "headline": "State of Indian Broking & Investing 2026",
        "url": canonical, "datePublished": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "author": {"@type": "Organization", "name": "BrokerLens India", "url": SITE_URL},
        "publisher": {"@type": "Organization", "name": "BrokerLens India", "url": SITE_URL},
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
    body += (
        '<p class="xs faint">Published %s</p>' % datetime.now(timezone.utc).strftime("%-d %B %Y")
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
        "title": "SIP Calculator: Estimate Mutual Fund SIP Returns | BrokerLens India",
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
    },
    {
        "slug": "lumpsum-calculator", "calc": "lumpsum", "h1": "Lumpsum Investment Calculator",
        "title": "Lumpsum Calculator: Estimate One-Time Investment Growth | BrokerLens India",
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
    },
    {
        "slug": "emi-calculator", "calc": "emi", "h1": "EMI Calculator",
        "title": "EMI Calculator: Monthly Loan Instalment | BrokerLens India",
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
    },
    {
        "slug": "cagr-calculator", "calc": "cagr", "h1": "CAGR Calculator",
        "title": "CAGR Calculator: Compound Annual Growth Rate | BrokerLens India",
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
    },
    {
        "slug": "compound-interest-calculator", "calc": "compound", "h1": "Compound Interest Calculator",
        "title": "Compound Interest Calculator | BrokerLens India",
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
    },
    {
        "slug": "capital-gains-tax-calculator", "calc": "capital-gains", "h1": "Capital Gains Tax Calculator",
        "title": "Capital Gains Tax Calculator: Equity LTCG & STCG | BrokerLens India",
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
    },
]


def _write_calculator_pages():
    written = []
    for c in CALCULATORS:
        canonical = "%s/calculators/%s/" % (SITE_URL, c["slug"])
        jsonld = {
            "@context": "https://schema.org", "@type": "WebApplication", "name": c["h1"],
            "url": canonical, "applicationCategory": "FinanceApplication",
            "operatingSystem": "Any (runs in browser)",
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"},
        }
        fields_html = "".join(
            '<div class="field"><label for="%s">%s</label>'
            '<input id="%s" type="number" min="0" step="%s" value="%s"></div>'
            % (fid, _esc(label), fid, step, default)
            for fid, label, default, step in c["fields"]
        )
        body = _REGISTRY_PAGE_HEAD % {
            "title": _esc(c["title"]), "description": _esc(c["description"])[:300],
            "canonical": _esc(canonical), "jsonld": json.dumps(jsonld, ensure_ascii=False),
        }
        body += (
            '<h1 style="margin-top:0">%s</h1>' % _esc(c["h1"])
            + '<p class="muted" style="max-width:68ch">%s</p>' % c["intro"]
            + '<p class="xs faint" style="max-width:68ch;margin-top:8px">%s</p>' % c["formula"]
            + '<div data-calc="%s" class="card" style="margin-top:20px;padding:20px;max-width:480px">' % c["calc"]
            + fields_html
            + '<button type="button" id="calc-btn" class="btn" style="margin-top:8px">Calculate</button>'
            + '<div id="calc-result" class="grid g3" style="margin-top:16px" hidden></div>'
            + '</div>'
            + '<p class="xs faint" style="margin-top:20px">This is a generic financial calculation, not investment, '
              'loan or tax advice specific to you. BrokerLens is not a SEBI-registered investment adviser.</p>'
        )
        body = body.replace("</head>", '<script src="/assets/js/calculators.js" defer></script></head>')
        body += _REGISTRY_PAGE_FOOT % {"source_note": _source_note(
            "This page runs a standard, published financial formula entirely in your browser; it is not "
            "generated from any BrokerLens-ingested regulator or exchange dataset.")}

        dest_dir = os.path.join(ROOT, "site", "calculators", c["slug"])
        os.makedirs(dest_dir, exist_ok=True)
        _write_text(os.path.join(dest_dir, "index.html"), body)
        written.append(c["slug"])

    log("calculator pages: %d written" % len(written), "ok")
    return written


def _write_sitemap(built, reg_rows=None, hub_groups=None, companies=None, indices=None, etfs=None,
                    fund_slugs=None, report_slugs=None, calc_slugs=None):
    _require_site_url()
    urls = ["/", "/brokers", "/leaderboards", "/compare", "/calculator",
            "/registry", "/algo", "/methodology", "/sources"]
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
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>' % body)
    _write_text(os.path.join(SITE_DATA, "..", "sitemap.xml"), xml)


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
