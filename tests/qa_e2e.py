"""End-to-end QA suite. Functional correctness, not security (see vapt.py).

  python3 tests/qa_e2e.py                 # offline checks only
  python3 tests/qa_e2e.py --url http://127.0.0.1:8000   # + live server checks

Exit code is the number of failures, so CI can gate on it.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import feeds as feedmod          # noqa: E402
from pipeline import metrics                    # noqa: E402
from pipeline.identity import Resolver          # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print("  %s %-58s %s" % ("PASS" if cond else "FAIL", name, detail if not cond else ""))
    return bool(cond)


def skip(name, why):
    SKIP.append((name, why))
    print("  SKIP %-58s %s" % (name, why))


def load(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def section(t):
    print("\n== %s ==" % t)


# ------------------------------------------------------------------- config

def test_config():
    section("config integrity")
    master = load("config/brokers_master.json")
    check("brokers_master.json parses", bool(master))
    if not master:
        return
    brokers = master.get("brokers", [])
    ids = [b["id"] for b in brokers]
    check("broker ids are unique", len(ids) == len(set(ids)),
          "dupes: %s" % [i for i in ids if ids.count(i) > 1])
    check("every broker id is url-safe",
          all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids),
          "bad: %s" % [i for i in ids if not re.fullmatch(r"[a-z0-9-]+", i)])
    check("every broker has a brand and type",
          all(b.get("brand") and b.get("type") for b in brokers))
    check("listing tiers are defined", set(master.get("tiers", {})) >= {"free", "verified", "featured"})

    for name in ("sources.json", "stream.json", "watchlist.json", "broker_stocks.json"):
        check("config/%s parses" % name, load("config/" + name) is not None)

    stream = load("config/stream.json") or {}
    srcs = stream.get("sources") or {}
    check("every stream source declares a feed", all("feed" in s for s in srcs.values()),
          "missing: %s" % [k for k, s in srcs.items() if "feed" not in s])
    check("every stream source declares wire_bytes + budget",
          all(s.get("wire_bytes") and s.get("max_mb_per_min") for s in srcs.values()))
    check("stream feeds all exist in FEED_META",
          all(s["feed"] in feedmod.FEED_META for s in srcs.values() if s.get("feed")))

    # A source whose payload cannot fit its budget at the configured interval
    # must be visibly throttled rather than silently exceeding it.
    for k, s in srcs.items():
        need = s["wire_bytes"] * 60.0 / (s["max_mb_per_min"] * 1e6)
        if need > s["interval"]:
            print("       note: %s configured %ss but budget forces %.1fs" % (k, s["interval"], need))

    bs = load("config/broker_stocks.json") or {}
    stocks = bs.get("stocks") or []
    check("broker stocks have scrip codes and relations",
          all(x.get("bse_scrip") and x.get("relation") in ("self", "parent") for x in stocks))
    known = set(ids)
    check("broker stocks reference real broker ids",
          all(x["broker_id"] in known for x in stocks),
          "unknown: %s" % [x["broker_id"] for x in stocks if x["broker_id"] not in known])


# ----------------------------------------------------------------- identity

def test_identity():
    section("identity resolution")
    master = load("config/brokers_master.json") or {}
    r = Resolver(master.get("brokers", []))

    bid, method, _ = r.resolve("ZERODHA BROKING LIMITED")
    check("exact alias resolves", bid == "zerodha", "got %s via %s" % (bid, method))

    bid, _, _ = r.resolve("Zerodha Broking Ltd.")
    check("punctuation/suffix variant resolves", bid == "zerodha", "got %s" % bid)

    bid, _, _ = r.resolve("NEXTBILLION TECHNOLOGY PRIVATE LIMITED")
    check("former legal name resolves to current brand", bid == "groww", "got %s" % bid)

    bid, method, _ = r.resolve("Totally Unrelated Trading Co")
    check("unknown name is rejected, not guessed", bid is None, "got %s via %s" % (bid, method))

    bid, method, _ = r.resolve("")
    check("empty name is rejected", bid is None and method == "empty")

    # Ambiguity must fail closed: attributing one broker's complaints to another
    # is worse than a gap.
    bid, method, _ = r.resolve("Securities Limited")
    check("generic all-noise name does not resolve", bid is None, "got %s via %s" % (bid, method))


# ------------------------------------------------------------------ metrics

def test_metrics():
    section("metrics maths")
    check("pct_change basic", metrics.pct_change(110, 100) == 10.0)
    check("pct_change zero base is None", metrics.pct_change(10, 0) is None)
    check("pct_change None-safe", metrics.pct_change(None, 100) is None)

    # Contiguous months: period maths is calendar-based, so a gap deliberately
    # yields None rather than silently comparing non-adjacent months.
    series = [["2026-04", 100], ["2026-05", 110], ["2026-06", 200]]
    totals = {"2026-04": 1000, "2026-05": 1000, "2026-06": 1000}
    cm = metrics.client_metrics(series, totals)
    check("client_metrics latest", cm["active_clients"] == 200)
    check("client_metrics share", cm["market_share_pct"] == 20.0, str(cm["market_share_pct"]))
    check("client_metrics mom", cm["mom_pct"] == metrics.pct_change(200, 110))

    # A full 12 months, because a rate is only published over a complete window.
    monthly = [{"month": "2026-%02d" % i, "received": 10, "resolved": 9, "pending": 1}
               for i in range(1, 13)]
    km = metrics.complaint_metrics(monthly, active_clients=100000)
    check("complaints per 10k", km["per_10k_clients_12m"] == round(120 / 100000 * 10000, 2),
          str(km["per_10k_clients_12m"]))
    check("resolution rate", km["resolution_rate_pct"] == 90.0, str(km["resolution_rate_pct"]))
    check("empty complaints -> unavailable", metrics.complaint_metrics([], 100)["available"] is False)

    charges = {"delivery": {"flat_per_order": 0},
               "intraday": {"flat_per_order": 20, "pct_of_turnover": 0.03, "cap_per_order": 20},
               "fno": {"flat_per_order": 20}, "demat_amc_annual": 300}
    cost = metrics.cost_of_basket(charges)
    check("free delivery costs nothing", cost["delivery"] == 0)
    check("flat F&O = 20 x 10 orders", cost["fno"] == 200)
    check("AMC amortised monthly", cost["amc_monthly"] == 25.0)
    check("basket total adds up",
          cost["monthly_total"] == round(cost["delivery"] + cost["intraday"] + cost["fno"] + cost["amc_monthly"], 2))
    check("no charges -> None", metrics.cost_of_basket(None) is None)

    # Reliability must renormalise when inputs are missing rather than penalising.
    full = {"complaints": {"per_10k_clients_12m": 1.0, "resolution_rate_pct": 95,
                           "pending_latest": 1, "received_12m": 120},
            "regulatory_flags": {"checked": True}, "profile": {"founded": 2010}}
    peers = [full, {"complaints": {"per_10k_clients_12m": 5.0}}]
    r_full = metrics.reliability_score(full, peers)
    check("reliability in range", 0 <= r_full["score"] <= 100, str(r_full["score"]))
    # Weights must renormalise to 1 over the components actually present, so a
    # broker is not penalised for a dataset we have not ingested yet. Comparing
    # the sum to itself (as this once did) asserts nothing.
    check("reliability weights renormalise to 1",
          abs(sum(r_full["weights"].values()) - 1.0) < 1e-9,
          "sum=%s" % sum(r_full["weights"].values()))
    sparse = {"complaints": {}, "regulatory_flags": {}, "profile": {}}
    r_sparse = metrics.reliability_score(sparse, peers)
    check("sparse input lowers confidence, not score to zero",
          r_sparse["confidence"] in ("low", "medium", "none"), r_sparse["confidence"])

    flagged = dict(full, regulatory_flags={"checked": True, "defaulter": True})
    check("defaulter flag drives regulatory component to 0",
          metrics.reliability_score(flagged, peers)["components"]["regulatory"] == 0)


# ---------------------------------------------------------------- published

def test_regression_guards():
    """One test per defect found in the 2026-08-01 audit. Each of these shipped."""
    section("audit regressions")

    # Cost basket used max() where Indian brokers charge "whichever is lower",
    # overstating Zerodha's monthly cost by 6.7x and inverting cost rankings.
    z = {"delivery": {"flat_per_order": 0},
         "intraday": {"flat_per_order": 20, "pct_of_turnover": 0.03, "cap_per_order": 20},
         "fno": {"flat_per_order": 20}, "demat_amc_annual": 300}
    c = metrics.cost_of_basket(z)
    check("cost basket takes the LOWER of flat vs percentage", c["intraday"] == 30.0,
          "intraday=%s (expected 30.0)" % c["intraday"])
    check("cost basket total is right", c["monthly_total"] == 255.0, str(c["monthly_total"]))
    check("'whichever is higher' plans still honoured",
          metrics.cost_of_basket({"intraday": {"flat_per_order": 20, "pct_of_turnover": 0.03,
                                               "pricing": "higher"}})["intraday"] == 200)
    check("a cap-only plan is priceable",
          metrics.cost_of_basket({"fno": {"cap_per_order": 20}})["fno"] == 200)

    # A broker with no data scored 100/100 and topped the reliability board.
    r = metrics.reliability_score({"id": "x", "profile": {}}, [])
    check("no data yields no reliability score", r["score"] is None, str(r["score"]))
    check("no data is never rankable", not r.get("rankable"))
    unchecked = metrics.reliability_score(
        {"id": "y", "profile": {"founded": 2010}, "regulatory_flags": {}}, [])
    check("an unscanned regulatory record is not scored as clean",
          "regulatory" not in (unchecked.get("components") or {}))

    # Positional date maths published a 16-month gap as "month-on-month".
    gap = metrics.client_metrics([["2025-01", 100], ["2025-02", 110], ["2026-06", 200]], {})
    check("a gap yields no month-on-month figure", gap["mom_pct"] is None, str(gap["mom_pct"]))
    adjacent = metrics.client_metrics([["2026-05", 110], ["2026-06", 200]], {})
    check("genuinely adjacent months still compute", adjacent["mom_pct"] == 81.82)
    reversed_in = metrics.client_metrics([["2026-06", 200], ["2026-05", 100]], {})
    check("newest-first input does not invert growth", reversed_in["mom_pct"] == 100.0,
          str(reversed_in["mom_pct"]))

    # Complaint windows: partial history was published as a 12-month figure.
    three = [{"month": "2026-%02d" % i, "received": 100, "resolved": 90, "pending": 10}
             for i in range(1, 4)]
    t = metrics.complaint_metrics(three, 100000)
    check("a 3-month history publishes no 12-month total", t["received_12m"] is None)
    check("a 3-month history publishes no normalised rate", t["per_10k_clients_12m"] is None)
    check("months_covered is disclosed", t["months_covered"] == 3)
    over = metrics.complaint_metrics(
        [{"month": "2026-01", "received": 10, "resolved": 50, "pending": 0}], 10000)
    check("resolution rate is capped at 100", over["resolution_rate_pct"] == 100.0,
          str(over["resolution_rate_pct"]))
    flat = [{"month": "2025-%02d" % i, "received": 100, "resolved": 100, "pending": 0}
            for i in range(1, 13)]
    check("a flat complaint record is not reported as a trend",
          metrics.complaint_metrics(flat, 100000)["trend_pct"] is None)

    # Substring matching attributed unrelated companies, including on the
    # defaulter list. Adverse attribution now demands an exact match.
    master = load("config/brokers_master.json") or {}
    res = Resolver(master.get("brokers", []))
    for name in ("ARIHANT ACADEMY LIMITED", "VENTURA TEXTILES LIMITED",
                 "CHOICE FINSTOCK PRIVATE LIMITED"):
        bid, method, _ = res.resolve(name)
        check("unrelated company not resolved: %s" % name.split()[0].title(),
              bid is None, "matched %s via %s" % (bid, method))
    check("real broker still resolves", res.resolve("ZERODHA BROKING LIMITED")[0] == "zerodha")
    check("strict mode refuses anything but an exact match",
          res.resolve("CHOICE FINSTOCK PRIVATE LIMITED", strict=True)[0] is None)

    # Provenance must be declared; an unknown value must abort the publish.
    for name in ("active_clients", "complaints", "charges"):
        raw = load("data/manual/%s.json" % name)
        if raw is not None:
            check("data/manual/%s.json declares a provenance" % name,
                  raw.get("provenance") in ("sample", "nse_ucc", "sebi_annexure_b",
                                            "broker_supplied", "manual", "estimate"),
                  "got %r" % raw.get("provenance"))

    # The exit-code contract: an all-empty adapter result must not read as ok.
    from pipeline import run as runmod
    check("an empty source is detected as a shortfall",
          runmod._shortfalls("nse", {"pulse": {}, "live": {}, "circulars": {}}),
          "empty NSE payload reported no shortfall")
    check("a populated source reports no shortfall",
          not runmod._shortfalls("nse", {"pulse": {"indices": [1]}, "live": {"quotes": [1]}}))


def test_published():
    section("published payloads")
    ov = load("site/data/overview.json")
    if not check("overview.json exists", bool(ov), "run: python3 -m pipeline.run all"):
        return
    brokers = ov["brokers"]
    check("broker index non-empty", len(brokers) > 0)
    ids = [b["id"] for b in brokers]
    check("index ids unique", len(ids) == len(set(ids)))

    ranks = [b["rank"] for b in brokers if b.get("rank")]
    check("ranks are unique", len(ranks) == len(set(ranks)))
    check("ranks start at 1", min(ranks) == 1 if ranks else True)

    # In production mode the client dataset is dropped, so there are no shares to
    # sum. That is the correct state, not a failure.
    shares = [b["share"] for b in brokers if b.get("share")]
    if shares:
        check("market shares sum to ~100", abs(sum(shares) - 100) < 1.0, "sum=%.2f" % sum(shares))
        check("no share exceeds 100", all(s <= 100 for s in shares))
    else:
        skip("market shares sum to ~100", "no client data published (production mode)")

    # Production mode must publish nothing that is flagged sample.
    meta = ov.get("metadata") or {}
    if meta.get("production"):
        check("production build publishes no sample data",
              not any((meta.get("sample_data") or {}).values()),
              "sample flags: %s" % meta.get("sample_data"))
        check("production build drops sample-derived client counts",
              all(b.get("clients") is None for b in brokers)
              or meta.get("data_status", {}).get("active_clients"))

    for b in brokers[:10]:
        p = os.path.join(ROOT, "site", "data", "brokers", "%s.json" % b["id"])
        if not os.path.exists(p):
            check("profile file exists for %s" % b["id"], False)
            break
    else:
        check("profile files exist for indexed brokers", True)

    # Static, server-rendered /broker/:id pages (progressive enhancement: real
    # facts with zero JS, app.js hydrates the same #app element on top). These
    # reuse the SPA's own URL, so the biggest risk is silent corruption of the
    # shell template rather than a missing file.
    broker_dir = os.path.join(ROOT, "site", "broker")
    check("site/broker/ static pages exist on disk", os.path.isdir(broker_dir))
    if os.path.isdir(broker_dir) and brokers:
        ids = {b["id"] for b in brokers}
        on_disk = {d for d in os.listdir(broker_dir) if os.path.isdir(os.path.join(broker_dir, d))}
        check("every tracked broker has a static page", ids <= on_disk,
              "missing: %s" % sorted(ids - on_disk)[:5])
        sample_id = brokers[0]["id"]
        sample_path = os.path.join(broker_dir, sample_id, "index.html")
        html = open(sample_path, encoding="utf-8").read() if os.path.exists(sample_path) else ""
        check("broker page carries the app.js hydration script",
              "/assets/js/app.js" in html)
        check("broker page has no leaked 'None' from an unset field",
              ">None<" not in html and "None</p>" not in html)
        check("broker page has an id=app element for app.js to hydrate",
              'id="app"' in html)
        check("broker page has real FinancialService JSON-LD",
              '"@type": "FinancialService"' in html or '"@type":"FinancialService"' in html)

    # Leaderboards must actually be sorted the way they claim.
    ok = True
    for bd in ov["leaderboards"]:
        vals = [r["value"] for r in bd["rows"]]
        asc, desc = vals == sorted(vals), vals == sorted(vals, reverse=True)
        if vals and not (asc or desc):
            ok = False
            print("       %s is not monotonic" % bd["key"])
    check("every leaderboard is sorted", ok)
    check("leaderboard ranks are 1..n",
          all([r["rank"] for r in bd["rows"]] == list(range(1, len(bd["rows"]) + 1))
              for bd in ov["leaderboards"]))

    check("sample-data flags are published", "sample_data" in ov["metadata"])
    sample = ov["metadata"]["sample_data"]
    if any(sample.values()):
        prov = [b for b in brokers if b.get("clients")]
        check("sample data is flagged for the UI to badge", bool(sample), str(sample))

    # A NaN or Infinity would be invalid JSON for strict parsers.
    raw = open(os.path.join(ROOT, "site/data/overview.json")).read()
    check("no NaN/Infinity in overview.json",
          not re.search(r"\b(NaN|-?Infinity)\b", raw))

    reg = load("site/data/registry.json")
    check("registry.json exists and has entities", bool(reg and reg.get("entities")))
    if reg:
        check("registry entities carry a name",
              all(e.get("name") for e in reg["entities"][:200]))

        # A directory literally named site/registry/ makes os.path.exists("/registry")
        # true on the file system, which silences the SPA-fallback rewrite for
        # the bare /registry route (the interactive search page) and turns it
        # into a broken directory listing. This shipped once; the static entity
        # pages must live under a sibling path (site/sebi-registry/) instead.
        check("no site/registry/ directory shadowing the SPA /registry route",
              not os.path.isdir(os.path.join(ROOT, "site", "registry")))

        slugs = [e["slug"] for e in reg["entities"] if e.get("slug")]
        check("every registry entity has a slug", len(slugs) == len(reg["entities"]))
        check("registry slugs are unique", len(slugs) == len(set(slugs)),
              "dupes: %s" % [s for s in set(slugs) if slugs.count(s) > 1][:5])

        reg_dir = os.path.join(ROOT, "site", "sebi-registry")
        check("sebi-registry/ static pages exist on disk", os.path.isdir(reg_dir))
        if os.path.isdir(reg_dir):
            on_disk = {d for d in os.listdir(reg_dir) if os.path.isdir(os.path.join(reg_dir, d))}
            missing = [s for s in slugs if s not in on_disk]
            check("every registry slug has a static page", not missing,
                  "missing: %s" % missing[:5])
            sample = slugs[0]
            sample_path = os.path.join(reg_dir, sample, "index.html")
            html = open(sample_path, encoding="utf-8").read() if os.path.exists(sample_path) else ""
            check("static entity page has no leaked 'None' from an unset field",
                  ">None<" not in html and "None</p>" not in html)
            check("static entity page loads no app bundle (must be readable with zero JS)",
                  "/assets/js/app.js" not in html)

    # Category hub pages (type/segment/city). Same collision class as the
    # registry pages: site/brokers/ would shadow the SPA's own /brokers
    # directory route, so these must live under a sibling prefix instead.
    check("no site/brokers/ directory shadowing the SPA /brokers route",
          not os.path.isdir(os.path.join(ROOT, "site", "brokers")))
    hub_dir = os.path.join(ROOT, "site", "brokers-by")
    check("brokers-by/ hub pages exist on disk", os.path.isdir(hub_dir))
    if os.path.isdir(hub_dir):
        dims = {d for d in os.listdir(hub_dir) if os.path.isdir(os.path.join(hub_dir, d))}
        check("hub pages cover type, segment and city", {"type", "segment", "city"} <= dims,
              "found: %s" % sorted(dims))
        sample_hub = next(
            (os.path.join(hub_dir, dim, slug, "index.html")
             for dim in sorted(dims) for slug in sorted(os.listdir(os.path.join(hub_dir, dim)))),
            None)
        if sample_hub and os.path.exists(sample_hub):
            html = open(sample_hub, encoding="utf-8").read()
            check("hub page has no leaked 'None' from an unset field",
                  ">None<" not in html and "None</p>" not in html)
            check("hub page has real ItemList JSON-LD",
                  '"@type": "ItemList"' in html or '"@type":"ItemList"' in html)
            check("hub page links at least one broker profile",
                  "/broker/" in html)

    src = load("site/data/sources.json")
    check("sources.json lists every configured source",
          len(src["sources"]) == len((load("config/sources.json") or {}).get("sources", {})))


def test_ticker():
    section("ticker feeds")
    t = load("site/data/ticker.json")
    if not check("ticker.json exists", bool(t), "run: python3 -m pipeline.run ticker"):
        return
    check("declares a feed order", isinstance(t.get("order"), list) and t["order"])
    check("every ordered feed exists", all(f in t["feeds"] for f in t["order"]))
    check("all configured feeds present", set(t["feeds"]) >= set(feedmod.FEED_ORDER),
          "missing %s" % (set(feedmod.FEED_ORDER) - set(t["feeds"])))

    for fid, f in t["feeds"].items():
        rows = f.get("instruments") or []
        if not rows:
            print("       note: feed %s is empty (%s)" % (fid, f.get("note") or "no note"))
            continue
        check("%s instruments have symbol+last" % fid,
              all(r.get("symbol") and r.get("last") is not None for r in rows))
        syms = [r["symbol"] for r in rows]
        check("%s has no duplicate symbols" % fid, len(syms) == len(set(syms)))
        check("%s prices are positive numbers" % fid,
              all(isinstance(r["last"], (int, float)) and r["last"] > 0 for r in rows))

    brokers_feed = t["feeds"].get("BROKERS", {}).get("instruments") or []
    if brokers_feed:
        check("broker stocks carry broker_id and relation",
              all(r.get("broker_id") and r.get("relation") in ("self", "parent")
                  for r in brokers_feed))
        ov = load("site/data/overview.json") or {}
        known = {b["id"] for b in ov.get("brokers", [])}
        check("broker stock ids match real profiles",
              all(r["broker_id"] in known for r in brokers_feed))

    size = os.path.getsize(os.path.join(ROOT, "site/data/ticker.json"))
    check("ticker payload stays small (<64KB)", size < 65536, "%d bytes" % size)


# ---------------------------------------------------------------- hub logic

def test_hub():
    section("stream hub logic")
    sys.path.insert(0, os.path.join(ROOT, "server"))
    try:
        from quotes import Bandwidth, Breaker, Hub
    except Exception as exc:
        skip("stream hub", "import failed: %s" % exc)
        return

    hub = Hub()
    hub.seed_from_disk()
    sub, snap = hub.subscribe("1.2.3.4")
    check("subscribe returns a snapshot with feeds", bool(snap.get("feeds")))

    base = (snap["feeds"]["NSE"]["instruments"] or [])[:2]
    if not base:
        skip("delta detection", "no seeded NSE instruments")
    else:
        check("unchanged prices broadcast nothing",
              hub.apply("NSE", instruments=[dict(q) for q in base]) == 0)
        moved = [dict(base[0], last=base[0]["last"] + 1)] + [dict(q) for q in base[1:]]
        check("a moved price broadcasts exactly one instrument",
              hub.apply("NSE", instruments=moved) == 1)
        ev, payload = sub.get(timeout=2)
        check("frame is a quotes event for the right feed",
              ev == "quotes" and payload["feed"] == "NSE")
        check("frame carries only the changed instrument", len(payload["instruments"]) == 1)

    check("a new symbol counts as a change",
          hub.apply("MCX", instruments=[{"symbol": "QATEST", "last": 1.0}]) == 1)

    # Per-IP cap
    limit = hub.limits["max_sse_clients_per_ip"]
    extra = [hub.subscribe("9.9.9.9") for _ in range(limit + 2)]
    rejected = [q for q, _ in extra if q is None]
    check("per-IP subscriber cap rejects excess", len(rejected) >= 2,
          "cap=%d rejected=%d" % (limit, len(rejected)))

    # Slow subscriber must be dropped, not block the poller
    before = hub.subscriber_count()
    for i in range(hub.limits["subscriber_queue_depth"] + 20):
        hub.apply("MCX", instruments=[{"symbol": "QATEST", "last": 1.0 + i}])
    check("slow subscribers are dropped", hub.subscriber_count() < before,
          "before=%d after=%d" % (before, hub.subscriber_count()))

    # Instrument cap
    many = [{"symbol": "S%04d" % i, "last": 1.0} for i in range(hub.limits["max_instruments_per_exchange"] + 50)]
    hub.apply("LOSERS", instruments=many)
    check("instrument list is capped",
          len(hub.snapshot["feeds"]["LOSERS"]["instruments"]) <= hub.limits["max_instruments_per_exchange"])

    b = Breaker({"breaker_failures_to_open": 2, "breaker_base_backoff_s": 1, "breaker_max_backoff_s": 10})
    check("breaker starts closed", b.state == "closed" and b.allow())
    b.fail()
    check("one failure is half-open, still allowed", b.state == "half-open" and b.allow())
    backoff = b.fail()
    check("breaker opens after threshold", b.state == "open" and not b.allow() and backoff > 0)
    b.ok()
    check("breaker resets on success", b.state == "closed")

    bw = Bandwidth(total_mb_per_min=1)
    bw.record("x", 500_000)
    check("bandwidth accounting tracks bytes", bw.rate("x") == 500_000)
    check("under budget is not flagged", not bw.over_total())
    bw.record("x", 600_000)
    check("over budget is flagged", bw.over_total())


# ------------------------------------------------------------------- server

def http(url, method="GET", data=None, headers=None, timeout=10):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}


def test_server(base):
    section("http routes")
    routes = ["/", "/brokers", "/broker/zerodha", "/compare", "/leaderboards",
              "/calculator", "/registry", "/algo", "/methodology", "/sources"]
    for r in routes:
        code, body, _ = http(base + r)
        check("GET %s" % r, code == 200 and b'id="app"' in body, "code=%s" % code)

    # Static SEBI-registry entity pages live outside the SPA (see test_published
    # for why: site/registry/ would shadow the /registry SPA route on disk).
    # They must serve directly, with zero redirect, and carry real content with
    # no client bundle - a crawler that cannot run JS must still see the facts.
    reg = load("site/data/registry.json") or {}
    sample_slug = next((e["slug"] for e in (reg.get("entities") or []) if e.get("slug")), None)
    if sample_slug:
        code, body, _ = http(base + "/sebi-registry/%s/" % sample_slug)
        check("GET /sebi-registry/<slug>/ serves the static entity page",
              code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)

    # /broker/:id/ reuses the SPA's own URL (unlike the registry pages), so the
    # static file must carry BOTH real content and id="app", ready for app.js
    # to hydrate on top of it.
    ov = load("site/data/overview.json") or {}
    sample_bid = next((b["id"] for b in (ov.get("brokers") or [])), None)
    if sample_bid:
        code, body, _ = http(base + "/broker/%s/" % sample_bid)
        check("GET /broker/<id>/ serves the static profile page",
              code == 200 and b"<h1" in body and b'id="app"' in body, "code=%s" % code)

    for a in ["/assets/js/app.js", "/assets/js/pages.js", "/assets/css/app.css",
              "/data/overview.json", "/data/ticker.json", "/sitemap.xml", "/feed.xml"]:
        code, body, _ = http(base + a)
        check("GET %s" % a, code == 200 and len(body) > 0, "code=%s" % code)

    code, _, _ = http(base + "/definitely-not-a-route")
    check("unknown route falls back to the SPA shell", code == 200)

    code, body, _ = http(base + "/api/health")
    check("health endpoint responds", code == 200 and b"ok" in body)

    section("no data collection")
    # The site collects no personal data at all: no lead capture, no contact
    # form, no write endpoint. POST must be refused, and nothing may persist.
    for path in ("/api/leads", "/api/contact", "/"):
        code, _, _ = http(base + path, "POST", b'{"name":"x"}',
                          {"Content-Type": "application/json"})
        check("POST %s is refused" % path, code in (404, 405),
              "expected 404 or 405, got %s" % code)

    check("no lead store on disk", not os.path.exists(os.path.join(ROOT, "data", "leads")))

    for fn, needles in (("store.js", ("submitLead", "leadEndpoint")),
                        ("pages.js", ("lead-form", "wireLeadForm"))):
        try:
            src = open(os.path.join(ROOT, "site", "assets", "js", fn), encoding="utf-8").read()
        except OSError:
            src = ""
        found = [n for n in needles if n in src]
        check("%s has no lead-capture code" % fn, not found, "still present: %s" % found)

    src = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
    check("no input elements anywhere in the shell",
          "<input" not in src.lower(), "the shell must not collect input")


def _dechunk(raw):
    """Minimal HTTP/1.1 chunked-transfer decoder for the SSE probe."""
    out, i = b"", 0
    while i < len(raw):
        j = raw.find(b"\r\n", i)
        if j < 0:
            break
        try:
            size = int(raw[i:j].split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        out += raw[j + 2:j + 2 + size]
        i = j + 2 + size + 2
    return out


def test_sse(base):
    section("sse stream")
    import socket as _s
    from urllib.parse import urlparse
    u = urlparse(base)
    try:
        sock = _s.create_connection((u.hostname, u.port or 80), timeout=10)
        sock.sendall(b"GET /api/stream HTTP/1.1\r\nHost: %s\r\nAccept: text/event-stream\r\n\r\n"
                     % u.netloc.encode())
        sock.settimeout(8)
        buf = b""
        # Read until a COMPLETE snapshot frame has arrived. The frame is ~15KB
        # with seven feeds, so stopping at the first few KB truncates the JSON.
        deadline = __import__("time").time() + 12
        while __import__("time").time() < deadline and len(buf) < 262144:
            try:
                chunk = sock.recv(16384)
            except _s.timeout:
                break
            if not chunk:
                break
            buf += chunk
            head, _, rest = buf.partition(b"\r\n\r\n")
            probe = _dechunk(rest) if b"chunked" in head.lower() else rest
            if re.search(rb"event: snapshot\ndata: \{.*?\}\n\n", probe, re.S):
                break
        sock.close()
    except Exception as exc:
        skip("sse", "connect failed: %s" % exc)
        return

    check("stream sets the event-stream content type", b"text/event-stream" in buf)
    head, _, rest = buf.partition(b"\r\n\r\n")
    body = _dechunk(rest) if b"chunked" in head.lower() else rest
    check("stream sends a retry directive", b"retry:" in body)
    check("stream sends a snapshot frame", b"event: snapshot" in body)
    m = re.search(rb"event: snapshot\ndata: (\{.*?\})\n\n", body, re.S)
    if not m:
        check("snapshot frame is complete", False, "no terminated frame in %d bytes" % len(body))
        return
    try:
        snap = json.loads(m.group(1).decode("utf-8", "replace"))
        check("snapshot frame is valid JSON", True)
        check("snapshot carries feeds", bool(snap.get("feeds")))
        check("snapshot declares feed order", bool(snap.get("order")))
        check("snapshot feeds carry instruments",
              any(f.get("instruments") for f in snap["feeds"].values()))
    except Exception as exc:
        check("snapshot frame is valid JSON", False, str(exc)[:60])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="base URL of a running server, e.g. http://127.0.0.1:8000")
    args = ap.parse_args()

    print("QA E2E suite")
    test_config()
    test_identity()
    test_metrics()
    test_regression_guards()
    test_published()
    test_ticker()
    test_hub()
    if args.url:
        test_server(args.url.rstrip("/"))
        test_sse(args.url.rstrip("/"))
    else:
        skip("http + sse checks", "pass --url to include them")

    print("\n%d passed, %d failed, %d skipped" % (len(PASS), len(FAIL), len(SKIP)))
    for name, detail in FAIL:
        print("  FAILED: %s %s" % (name, detail))
    return len(FAIL)


if __name__ == "__main__":
    sys.exit(main())
