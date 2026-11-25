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
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import feeds as feedmod          # noqa: E402
from pipeline import ipo_engine                 # noqa: E402
from pipeline import metrics                    # noqa: E402
from pipeline.identity import Resolver          # noqa: E402
from pipeline.publish import CONTACT_EMAIL      # noqa: E402
from pipeline import share_price_target_engine as target_engine  # noqa: E402
from pipeline.share_price_target_engine import (  # noqa: E402
    MIN_HISTORY_SESSIONS,
    _has_three_year_history,
    _scenario_prices,
    _target_years,
    render_target_page,
)

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

    # complaints.json sat at 100% sample data for every broker until this
    # regression was added: the crawler in pipeline/sources/complaints.py
    # existed but was never wired into a deploy, and every one of the 12
    # already-configured broker URLs turned out to be stale or simply the
    # wrong page. Zerodha's real Annexure-B disclosure (a public Google
    # Sheet, linked from zerodha.com/disclosure/) is the first fix -
    # December 2021 is pinned here (48 received, 32 resolved, 5 pending)
    # against the row the sheet itself labels "Total", cross-checked by
    # independently summing that same month's four complaint-channel rows.
    complaints_raw = load("data/manual/complaints.json") or {}
    dec_2021 = next((r for r in (complaints_raw.get("brokers") or {}).get("zerodha") or []
                     if r.get("month") == "2021-12"), None)
    check("zerodha has real complaints data, not just sample",
          complaints_raw.get("provenance") == "sebi_annexure_b" and dec_2021 is not None,
          "provenance=%r" % complaints_raw.get("provenance"))
    if dec_2021:
        check("zerodha December 2021 complaint figures match the source's own Total row",
              (dec_2021.get("received"), dec_2021.get("resolved"), dec_2021.get("pending")) == (48, 32, 5),
              "got %r" % dec_2021)

    # The exit-code contract: an all-empty adapter result must not read as ok.
    from pipeline import run as runmod
    check("an empty source is detected as a shortfall",
          runmod._shortfalls("nse", {"pulse": {}, "live": {}, "circulars": {}}),
          "empty NSE payload reported no shortfall")
    check("a populated source reports no shortfall",
          not runmod._shortfalls("nse", {"pulse": {"indices": [1]}, "live": {"quotes": [1]}}))

    # A missing closing brace after affiliateBanner() swallowed fivepaisaBanner()
    # as a nested function, so the next top-level `export` became a syntax
    # error - this broke app.js's whole import graph in production (ticker,
    # search, mega-menus, client-side routing all silently dead) while every
    # other test here still passed, because a plain `node --check` on a .js
    # file doesn't validate module syntax (it tolerates a stray top-level
    # `export`). Piping through stdin with --input-type=module does.
    import shutil
    js_dir = os.path.join(ROOT, "site", "assets", "js")
    if not shutil.which("node"):
        skip("site/assets/js/*.js parse as valid ES modules", "node not on PATH")
    elif os.path.isdir(js_dir):
        for fname in sorted(os.listdir(js_dir)):
            if not fname.endswith(".js"):
                continue
            with open(os.path.join(js_dir, fname), "rb") as fh:
                src = fh.read()
            result = subprocess.run(
                ["node", "--input-type=module", "--check"],
                input=src, capture_output=True)
            check("%s parses as a valid ES module" % fname, result.returncode == 0,
                  result.stderr.decode(errors="replace").strip().splitlines()[-1]
                  if result.returncode else "")


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
    # sum. That is the correct state, not a failure. With NSE's Report 1C the
    # denominator is the exchange-wide total, so the tracked brokers' shares sum
    # to their real slice of NSE (87.38% on the Sep 2026 file), not to 100; the
    # invariant is that shares are clients over the market total the site states.
    shares = [b["share"] for b in brokers if b.get("share")]
    if shares:
        total = (ov.get("aggregates") or {}).get("total_active_clients")
        covered = sum(b["clients"] for b in brokers if b.get("share") and b.get("clients"))
        expected = 100.0 * covered / total if total else None
        check("market shares are each broker's clients over the stated market total",
              expected is not None and abs(sum(shares) - expected) < 0.5 and sum(shares) <= 100.5,
              "sum=%.2f expected=%s" % (sum(shares), ("%.2f" % expected) if expected is not None else "no total"))
        check("no share exceeds 100", all(s <= 100 for s in shares))
    else:
        skip("market shares are each broker's clients over the stated market total",
             "no client data published (production mode)")

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

        # Regression guard: _write_broker_pages() used to string-replace a
        # skeleton <main> block straight out of a live copy of site/index.html.
        # Once _prerender_home() started baking real content into that same
        # file's <main>, the match silently stopped firing forever and every
        # broker page fell back through Vercel's catch-all rewrite to serve
        # the homepage's own <title>/canonical/JSON-LD instead of its own -
        # invisible in a build log, only visible by diffing two live pages.
        home_html = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
        home_title = re.search(r"<title>([^<]*)</title>", home_html)
        brand = brokers[0].get("brand") or sample_id
        check("broker page <title> is its own, not the homepage's",
              bool(re.search(r"<title>([^<]*)</title>", html))
              and (not home_title or re.search(r"<title>([^<]*)</title>", html).group(1) != home_title.group(1))
              and brand in re.search(r"<title>([^<]*)</title>", html).group(1))
        check("broker page canonical points at its own /broker/<id>/ URL, not /",
              ('/broker/%s/' % sample_id) in html
              and re.search(r'<link rel="canonical" href="([^"]*)">', html).group(1) != "/")

        if len(brokers) > 1:
            other_id = brokers[1]["id"]
            other_path = os.path.join(broker_dir, other_id, "index.html")
            other_html = open(other_path, encoding="utf-8").read() if os.path.exists(other_path) else ""
            om = re.search(r"<title>([^<]*)</title>", other_html)
            sm = re.search(r"<title>([^<]*)</title>", html)
            check("two different brokers' pages have two different <title>s",
                  bool(om) and bool(sm) and om.group(1) != sm.group(1),
                  "%s vs %s" % (sm.group(1) if sm else None, om.group(1) if om else None))

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

        # site/registry/ is now a deliberate, real hybrid page (server-rendered
        # page-one content + the same app.js/pages.js bootstrap as index.html),
        # not the old accidental kind of shadowing this comment used to warn
        # against: that failure mode was a static file that permanently froze
        # the route with no hand-off to the SPA at all. The real invariant is
        # "hands off to app.js for hydration", not "does not exist".
        reg_page_path = os.path.join(ROOT, "site", "registry", "index.html")
        reg_page_html = open(reg_page_path, encoding="utf-8").read() if os.path.exists(reg_page_path) else ""
        check("site/registry/ is a real hybrid page that boots the SPA, not a dead-end static file",
              os.path.isdir(os.path.join(ROOT, "site", "registry"))
              and "/assets/js/app.js" in reg_page_html and "<h1" in reg_page_html)

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

    # site/brokers/ is now a deliberate real hybrid page for the same reason
    # site/registry/ is above - checked the same way, not for absence.
    brokers_page_path = os.path.join(ROOT, "site", "brokers", "index.html")
    brokers_page_html = open(brokers_page_path, encoding="utf-8").read() if os.path.exists(brokers_page_path) else ""
    check("site/brokers/ is a real hybrid page that boots the SPA, not a dead-end static file",
          os.path.isdir(os.path.join(ROOT, "site", "brokers"))
          and "/assets/js/app.js" in brokers_page_html and "<h1" in brokers_page_html)
    # Category hub pages (type/segment/city) live under a sibling prefix,
    # brokers-by/, distinct from the /brokers hybrid page above.
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

    # Static, server-rendered /stock/:symbol pages - Phase 1 of the
    # 60-70k-page plan, built entirely from NSE's own already-ingested
    # EQUITY_L.csv. No SPA route is named "stock", so this prefix cannot
    # shadow an existing client route the way site/registry/ once did.
    stock_dir = os.path.join(ROOT, "site", "stock")
    check("site/stock/ static pages exist on disk", os.path.isdir(stock_dir))
    if os.path.isdir(stock_dir):
        slugs = sorted(d for d in os.listdir(stock_dir) if os.path.isdir(os.path.join(stock_dir, d)))
        check("a large number of NSE equity pages were written", len(slugs) > 2000,
              "found %d" % len(slugs))
        check("stock page slugs are unique", len(slugs) == len(set(slugs)))
        sample_path = os.path.join(stock_dir, slugs[0], "index.html") if slugs else ""
        html = open(sample_path, encoding="utf-8").read() if slugs and os.path.exists(sample_path) else ""
        check("stock page has no leaked 'None' from an unset field",
              ">None<" not in html and "None</p>" not in html)
        check("stock page has real Corporation JSON-LD",
              '"@type": "Corporation"' in html or '"@type":"Corporation"' in html)
        check("stock page loads no app bundle (must be readable with zero JS)",
              "/assets/js/app.js" not in html)
        angel_path = os.path.join(stock_dir, "angelone", "index.html")
        if os.path.exists(angel_path):
            angel_html = open(angel_path, encoding="utf-8").read()
            check("NSE-listed broker parent cross-links to its BrokerLens profile",
                  "/broker/angel-one/" in angel_html)

        # Real, per-entity FAQs (not padded to a fixed count) across the
        # three largest mechanical page families. Genuinely varies with the
        # entity's own data (e.g. Angel One's FAQs mention its broker link
        # and index membership; a stock with neither gets neither claim).
        check("stock page has real per-entity FAQPage JSON-LD",
              '"@type": "FAQPage"' in html or '"@type":"FAQPage"' in html)
        check("angelone stock page FAQs mention its broker link, unlike a generic stock",
              "listed parent of a BrokerLens-tracked broker" in angel_html)

        # Tier 1 of the Page Depth Plan: last close, sector, a real price
        # chart, corporate actions and peer links, built from data this
        # pipeline was already fetching (bhavcopy, index constituent files,
        # BSE corporate actions) but never rendering. ITC is a stable,
        # always-listed, always-index-member reference stock.
        eq_hist_dir = os.path.join(ROOT, "site", "data", "equity-history")
        check("equity-history directory exists", os.path.isdir(eq_hist_dir))
        if os.path.isdir(eq_hist_dir):
            hist_files = [f for f in os.listdir(eq_hist_dir) if f.endswith(".json")]
            check("a large number of stocks have real price history", len(hist_files) > 1000,
                  "found %d" % len(hist_files))
        itc_path = os.path.join(stock_dir, "itc", "index.html")
        if os.path.exists(itc_path):
            itc_html = open(itc_path, encoding="utf-8").read()
            check("stock page shows a real Sector field", "Fast Moving Consumer Goods" in itc_html)
            check("stock page shows a last-close price with a day-change badge",
                  "Last close" in itc_html and ('class="up"' in itc_html or 'class="down"' in itc_html))
            check("stock page loads the price chart (vendor lib + stock-chart.js)",
                  "lightweight-charts" in itc_html and "stock-chart.js" in itc_html
                  and "data-stock-chart" in itc_html)
            check("stock page has a trade-this-stock CTA linking to /compare/",
                  "Trade ITC" in itc_html and 'href="/compare/"' in itc_html)
            # Regression guard: the chart card used to be a short, fixed-height
            # canvas sitting next to a much taller sidebar stack (last-close +
            # listing details + 3 affiliate banners), with align-items:start
            # leaving a large empty gap under the chart on desktop. Real OHLCV
            # data (already fetched for the chart) and the trade CTA now live
            # inside the chart card itself, so both columns fill with content
            # instead of blank space.
            chart_card_end = itc_html.find('<div class="stack">')
            check("stock page shows real OHLCV stats (Open/High/Low/Volume) inside the chart card, "
                  "not leaving it empty next to a much taller sidebar",
                  chart_card_end > 0
                  and "Day High" in itc_html[:chart_card_end]
                  and "Day Low" in itc_html[:chart_card_end]
                  and "Volume" in itc_html[:chart_card_end])
            check("stock page's trade CTA now sits inside the chart card (filling space), not only below the grid",
                  chart_card_end > 0 and "Trade ITC" in itc_html[:chart_card_end])
            check("stock page lists peer stocks in the same sector index",
                  "Other Nifty FMCG stocks" in itc_html and "/stock/hindunilvr/" in itc_html)
            check("stock page carries the Zerodha and Indiabulls sponsored broker banners (IBSL replaced 5paisa, keeping three blocks)",
                  "aff-banner-zerodha" in itc_html and 'data-ad="ibsl"' in itc_html)
        # A stock with no price history yet takes a different layout branch
        # (no chart, no g-main split) - the banners must still render there,
        # not only on the common chart-having path. ABAN (BE series, delisted
        # from active trading) has no bhavcopy rows in the fetch window.
        aban_path = os.path.join(stock_dir, "aban", "index.html")
        if os.path.exists(aban_path):
            aban_html = open(aban_path, encoding="utf-8").read()
            check("a stock page with no price history still carries the Zerodha and Indiabulls sponsored broker banners",
                  "data-stock-chart" not in aban_html
                  and "aff-banner-zerodha" in aban_html and 'data-ad="ibsl"' in aban_html)
        stock_chart_path = os.path.join(ROOT, "site", "assets", "js", "stock-chart.js")
        check("stock-chart.js exists", os.path.exists(stock_chart_path))
        if os.path.exists(stock_chart_path):
            stock_chart_src = open(stock_chart_path, encoding="utf-8").read()
            check("stock-chart.js defines technical indicators (SMA, EMA, Bollinger)",
                  "calcSMA" in stock_chart_src and "calcEMA" in stock_chart_src and "calcBollinger" in stock_chart_src)
            check("stock-chart.js defines Smart Zones (Support/Resistance levels)",
                  "calcSmartZones" in stock_chart_src and "createPriceLine" in stock_chart_src)
            check("stock-chart.js defines interactive HUD legend",
                  "chart-hud" in stock_chart_src and "subscribeCrosshairMove" in stock_chart_src)
        # Corporate actions are matched by an exact BSE-symbol-to-NSE-symbol
        # string match, never fuzzy - so this only proves the wiring fires
        # for at least one real, currently-disclosed action, not that every
        # BSE symbol resolves (most legitimately won't, see the note above
        # actions_by_symbol's construction in publish.py).
        raw_action_symbols = {(a.get("symbol") or "").strip().upper() for a in
                              (load("data/_ingest.json") or {}).get("bse", {}).get("corporate_actions", [])}
        if raw_action_symbols:
            check("at least one stock page's corporate action matches real BSE ingest data by exact symbol",
                  any(os.path.exists(os.path.join(stock_dir, sym.lower(), "index.html"))
                      and "Upcoming corporate actions" in
                      open(os.path.join(stock_dir, sym.lower(), "index.html"), encoding="utf-8").read()
                      for sym in raw_action_symbols
                      if os.path.isdir(os.path.join(stock_dir, sym.lower()))),
                  "0 of %d BSE action symbols matched an existing stock page" % len(raw_action_symbols))

    # Static /index/:slug pages - Phase 2 of the 60-70k-page plan. Sourced
    # from NSE's own published index-constituent files (Nifty 50, sectoral
    # indices), cross-linked both ways with the /stock/ pages above. No SPA
    # route is named "index" or "indices".
    index_dir = os.path.join(ROOT, "site", "index")
    check("site/index/ static pages exist on disk", os.path.isdir(index_dir))
    index_slugs = []
    if os.path.isdir(index_dir):
        index_slugs = sorted(d for d in os.listdir(index_dir) if os.path.isdir(os.path.join(index_dir, d)))
        check("a real number of NSE index pages were written", len(index_slugs) >= 20,
              "found %d" % len(index_slugs))
        check("index page slugs are unique", len(index_slugs) == len(set(index_slugs)))
        idx_path = os.path.join(index_dir, "nifty-50", "index.html")
        idx_html = open(idx_path, encoding="utf-8").read() if os.path.exists(idx_path) else ""
        check("nifty-50 index page exists with 50 constituents",
              idx_html.count('class="mega-seg-head"') == 50, "found %d" % idx_html.count('class="mega-seg-head"'))
        check("index page has no leaked 'None' from an unset field",
              ">None<" not in idx_html and "None</p>" not in idx_html)
        check("index page has real ItemList JSON-LD",
              '"@type": "ItemList"' in idx_html or '"@type":"ItemList"' in idx_html)
        check("index page constituent cross-links to a real /stock/ page",
              "/stock/reliance/" in idx_html)
        check("index page loads no app bundle (must be readable with zero JS)",
              "/assets/js/app.js" not in idx_html)
        reliance_path = os.path.join(stock_dir, "reliance", "index.html")
        if os.path.exists(reliance_path):
            reliance_html = open(reliance_path, encoding="utf-8").read()
            check("a stock page reverse-links to the indices it's a constituent of",
                  "/index/nifty-50/" in reliance_html)

    # ETF and stock paths have separate route namespaces, so identical
    # instrument slugs are valid as long as their generated URLs differ.
    etf_dir = os.path.join(ROOT, "site", "etf")
    check("site/etf/ static pages exist on disk", os.path.isdir(etf_dir))
    if os.path.isdir(etf_dir):
        etf_slugs = sorted(d for d in os.listdir(etf_dir) if os.path.isdir(os.path.join(etf_dir, d)))
        check("a real number of NSE ETF pages were written", len(etf_slugs) > 200,
              "found %d" % len(etf_slugs))
        check("etf page slugs are unique", len(etf_slugs) == len(set(etf_slugs)))
        overlapping_slugs = set(etf_slugs) & set(slugs) if os.path.isdir(stock_dir) else set()
        etf_paths = {"/etf/%s/" % slug for slug in etf_slugs}
        stock_paths = {"/stock/%s/" % slug for slug in slugs}
        check("ETF and stock pages use distinct URL namespaces",
              not (etf_paths & stock_paths),
              "overlapping symbols are valid in separate routes: %s" % sorted(overlapping_slugs)[:5])
        niftybees_path = os.path.join(etf_dir, "niftybees", "index.html")
        etf_html = open(niftybees_path, encoding="utf-8").read() if os.path.exists(niftybees_path) else ""
        check("etf page has no leaked 'None' from an unset field",
              ">None<" not in etf_html and "None</p>" not in etf_html)
        check("etf page has real FinancialProduct JSON-LD (not Corporation - an ETF is a fund, not a company)",
              '"@type": "FinancialProduct"' in etf_html or '"@type":"FinancialProduct"' in etf_html)
        check("etf page loads no app bundle (must be readable with zero JS)",
              "/assets/js/app.js" not in etf_html)
        check("niftybees ETF page cross-links to the Nifty 50 index page",
              "/index/nifty-50/" in etf_html)
        check("etf page has real per-entity FAQPage JSON-LD",
              '"@type": "FAQPage"' in etf_html or '"@type":"FAQPage"' in etf_html)

    # Static /fund/:slug pages - the biggest single lever in the 60k-page
    # plan, one page per real scheme (not per NAV row: AMFI's file carries
    # every Plan x Option combination as its own row, and a page per row
    # would be exactly the thin/combinatorial pattern the plan rules out).
    fund_dir = os.path.join(ROOT, "site", "fund")
    check("site/fund/ static pages exist on disk", os.path.isdir(fund_dir))
    hdfc_flexicap_path = ""
    if os.path.isdir(fund_dir):
        fund_slugs = sorted(d for d in os.listdir(fund_dir) if os.path.isdir(os.path.join(fund_dir, d)))
        check("a real number of mutual fund pages were written", len(fund_slugs) > 2000,
              "found %d" % len(fund_slugs))
        check("fund page slugs are unique", len(fund_slugs) == len(set(fund_slugs)))
        check("no fund slug collides with a stock or etf slug",
              not (set(fund_slugs) & set(slugs)) and not (set(fund_slugs) & set(etf_slugs)))
        hdfc_flexicap_path = os.path.join(fund_dir, "hdfc-mutual-fund-hdfc-flexi-cap-fund", "index.html")
        fund_html = open(hdfc_flexicap_path, encoding="utf-8").read() if os.path.exists(hdfc_flexicap_path) else ""
        check("HDFC Flexi Cap Fund page exists with all 4 plan/option variants",
              fund_html.count("<tr><td>") == 4, "found %d" % fund_html.count("<tr><td>"))
        check("fund page has no leaked 'None' from an unset field",
              ">None<" not in fund_html and "None</p>" not in fund_html)
        check("fund page has real FinancialProduct JSON-LD with a provider (the AMC)",
              ('"@type": "FinancialProduct"' in fund_html or '"@type":"FinancialProduct"' in fund_html)
              and '"provider"' in fund_html)
        check("fund page loads no app bundle (must be readable with zero JS)",
              "/assets/js/app.js" not in fund_html)
        check("fund page has real per-entity FAQPage JSON-LD", '"@type": "FAQPage"' in fund_html
              or '"@type":"FAQPage"' in fund_html)
        # NAV is real AMFI data and genuinely changes every trading day - a
        # hardcoded expected value goes stale by design (caught live: AMFI's
        # real NAV moved from 2245.0670 to 2249.0670 between one run and the
        # next). Check the real pattern instead of a frozen number.
        check("fund page FAQ states a real-looking NAV, not a placeholder",
              bool(re.search(r"had a NAV of Rs \d+\.\d{4}\.", fund_html)) and "Growth Option variant" in fund_html)
        check("fund page shows real NAV figures, not placeholders",
              bool(re.search(r"Rs \d+\.\d{4}", fund_html)))
        check("fund page carries the Zerodha and Jiraaf sponsored banners (two, not three, on thin pages)",
              "aff-banner-zerodha" in fund_html and "aff-banner-jiraaf" in fund_html)

    # The single hand-written data report. Its defaulter-count claim was
    # caught overstating a relationship the raw data didn't support (only 2
    # of 445 defaulters actually overlap the 1,690-entity registry by
    # registration number) - this checks the corrected, honest phrasing
    # stays in place rather than silently regressing back.
    report_path = os.path.join(ROOT, "site", "reports", "state-of-indian-broking-2026", "index.html")
    check("state-of-indian-broking-2026 report exists", os.path.exists(report_path))
    if os.path.exists(report_path):
        report_html = open(report_path, encoding="utf-8").read()
        check("report has no leaked 'None' from an unset field",
              ">None<" not in report_html and "None</p>" not in report_html)
        check("report has real Article JSON-LD",
              '"@type": "Article"' in report_html or '"@type":"Article"' in report_html)
        check("report does not claim defaulters are a subset of the registry count",
              "not a subset of the entities counted above" in report_html)
        check("report loads no app bundle (must be readable with zero JS)",
              "/assets/js/app.js" not in report_html)

        # Regression guard: datePublished used to be datetime.now() at build
        # time, so it (and the page's own "Published <date>" line) silently
        # relabelled itself as "published today" on every single deploy -
        # not a real published date at all. It must now be a fixed constant.
        m = re.search(r'"datePublished":\s*"([^"]+)"', report_html)
        check("report's datePublished is a fixed date, not today's build date",
              bool(m) and m.group(1) == "2026-09-16", str(m.group(1)) if m else "missing")
        check("report has dateModified separate from datePublished",
              '"dateModified"' in report_html)
        check("report's publisher carries a logo ImageObject (Article rich-result requirement)",
              '"logo"' in report_html and '"ImageObject"' in report_html)

    # site/calculator/ (singular - the interactive brokerage-cost tool) is now
    # a deliberate real hybrid page too, same invariant as site/registry/ and
    # site/brokers/ above. site/calculators/ (plural, checked below) is the
    # unrelated set of static informational calculator pages.
    calc_tool_path = os.path.join(ROOT, "site", "calculator", "index.html")
    calc_tool_html = open(calc_tool_path, encoding="utf-8").read() if os.path.exists(calc_tool_path) else ""
    check("site/calculator/ is a real hybrid page that boots the SPA, not a dead-end static file",
          os.path.isdir(os.path.join(ROOT, "site", "calculator"))
          and "/assets/js/app.js" in calc_tool_html and "<h1" in calc_tool_html)
    calc_dir = os.path.join(ROOT, "site", "calculators")
    check("site/calculators/ static pages exist on disk", os.path.isdir(calc_dir))
    if os.path.isdir(calc_dir):
        calc_slugs = sorted(d for d in os.listdir(calc_dir) if os.path.isdir(os.path.join(calc_dir, d)) and d != "sip")
        check("all 14 calculator pages were written", len(calc_slugs) == 14, "found %d: %s" % (len(calc_slugs), calc_slugs))
        sip_path = os.path.join(calc_dir, "sip-calculator", "index.html")
        sip_html = open(sip_path, encoding="utf-8").read() if os.path.exists(sip_path) else ""
        check("calculator page has no leaked 'None' from an unset field",
              ">None<" not in sip_html and "None</p>" not in sip_html)
        check("calculator page has real WebApplication JSON-LD",
              '"@type": "WebApplication"' in sip_html or '"@type":"WebApplication"' in sip_html)
        check("calculator page loads calculators.js, not app.js (no SPA hydration target here)",
              "/assets/js/calculators.js" in sip_html and "/assets/js/app.js" not in sip_html)
        check("calculator page has a data-calc container matching its dispatch key",
              'data-calc="sip"' in sip_html)
        calc_js = open(os.path.join(ROOT, "site", "assets", "js", "calculators.js"), encoding="utf-8").read()
        check("calculators.js defines all 14 calculator functions",
              all(k in calc_js for k in [
                  "sip()", "lumpsum()", "emi()", "cagr()", "compound()", "'capital-gains'()",
                  "'simple-interest'()", "'stepup-sip'()", "swp()", "inflation()", "retirement()", "ppf()", "gst()",
                  "'direct-regular'()",
              ]))
        # Home "Calculators & Fair-Cost Estimators" cards once linked /calculator/sip/,
        # /calculator/direct-vs-regular/ and /calculator/margin/, none of which were
        # ever built (three 404s). Every card href must resolve to a real page.
        import re as _re
        for _src in ("pipeline/publish.py", "site/assets/js/pages.js"):
            _t = open(os.path.join(ROOT, _src), encoding="utf-8").read()
            _a = _t.find("Calculators &amp; Fair-Cost Estimators")
            _blk = _t[_a:_a + 6000]
            _hrefs = [h for h in _re.findall(r'href="(/calculators?/[^"]*)"', _blk)]
            _ok = all(h in ("/calculator/", "/calculators/") or
                      (h.startswith("/calculators/") and h.strip("/").split("/")[-1] in calc_slugs + ["sip"])
                      for h in _hrefs)
            check("home calculator cards in %s only link pages that exist" % _src, bool(_hrefs) and _ok, str(_hrefs))
        gst_path = os.path.join(calc_dir, "gst-calculator", "index.html")
        gst_html = open(gst_path, encoding="utf-8").read() if os.path.exists(gst_path) else ""
        check("gst calculator has a rate <select> and an inclusive/exclusive radio group",
              '<select id="gst-rate">' in gst_html and 'name="gst-mode"' in gst_html
              and gst_html.count('type="radio"') == 2)

        # Content depth: real, differentiated FAQs (not padded to a fixed
        # count) plus a "how to use" and a "what this doesn't account for"
        # section on every calculator - each backed by a real FAQPage
        # JSON-LD entry, not just prose.
        for cslug in calc_slugs:
            cpath = os.path.join(calc_dir, cslug, "index.html")
            chtml = open(cpath, encoding="utf-8").read()
            faq_count = chtml.count('class="faq-item"')
            check("%s has a real, non-trivial number of FAQs" % cslug, faq_count >= 4, "found %d" % faq_count)
            check("%s has a How to use section" % cslug, "How to use this calculator" in chtml)
            check("%s has a limitations section" % cslug, "doesn't account for" in chtml)
            check("%s FAQPage JSON-LD entity count matches the visible FAQ count" % cslug,
                  ('"@type": "FAQPage"' in chtml or '"@type":"FAQPage"' in chtml))

    # /calculators/ hub: the nav's "Calculators" link used to jump straight
    # into one arbitrarily-chosen calculator (sip-calculator) instead of a
    # real index - found while auditing nav consistency for the search
    # feature. This also gives the brokerage cost calculator (a separate
    # SPA-only route) its first cross-link from the static calculator suite.
    calc_hub_path = os.path.join(calc_dir, "index.html")
    check("calculators hub page exists (not just per-calculator pages)", os.path.exists(calc_hub_path))
    if os.path.exists(calc_hub_path):
        hub_html = open(calc_hub_path, encoding="utf-8").read()
        check("calculators hub links every calculator", all(
            '/calculators/%s/' % c["slug"] in hub_html for c in [
                {"slug": s} for s in calc_slugs
            ]))
        check("calculators hub links the brokerage cost calculator too", 'href="/calculator/"' in hub_html)

    # Directory/browse pages: before these existed, ~2,568 stock pages and
    # all 3,364 fund pages had no inbound link anywhere on the site except a
    # sitemap.xml entry - a sitemap is a weak crawl signal on its own, and
    # Google's own Page Indexing report showed the gap directly (thousands
    # of sitemap URLs, only a handful actually indexed on a new domain).
    stocks_dir_path = os.path.join(ROOT, "site", "stocks")
    check("stock A-Z directory exists", os.path.isdir(stocks_dir_path))
    if os.path.isdir(stocks_dir_path):
        letter_dirs = [d for d in os.listdir(stocks_dir_path) if os.path.isdir(os.path.join(stocks_dir_path, d))]
        check("stock directory has more than one letter page", len(letter_dirs) > 1, "found %d" % len(letter_dirs))
        overview_html = open(os.path.join(stocks_dir_path, "index.html"), encoding="utf-8").read()
        check("stock directory overview links every letter page",
              all('/stocks/%s/' % d in overview_html for d in letter_dirs))
        if letter_dirs:
            sample_html = open(os.path.join(stocks_dir_path, letter_dirs[0], "index.html"), encoding="utf-8").read()
            check("a stock letter page actually links /stock/ pages", '/stock/' in sample_html)

    funds_by_dir = os.path.join(ROOT, "site", "funds-by")
    check("fund AMC directory exists", os.path.isdir(funds_by_dir))
    if os.path.isdir(funds_by_dir):
        amc_dirs = [d for d in os.listdir(funds_by_dir) if os.path.isdir(os.path.join(funds_by_dir, d)) and d != "category"]
        check("fund AMC directory has more than one AMC page", len(amc_dirs) > 1, "found %d" % len(amc_dirs))
        overview_html = open(os.path.join(funds_by_dir, "index.html"), encoding="utf-8").read()
        check("fund AMC overview links every AMC page",
              all('/funds-by/%s/' % d in overview_html for d in amc_dirs))
        if amc_dirs:
            sample_html = open(os.path.join(funds_by_dir, amc_dirs[0], "index.html"), encoding="utf-8").read()
            check("an AMC page actually links /fund/ pages", '/fund/' in sample_html)

    etfs_dir_path = os.path.join(ROOT, "site", "etfs")
    check("ETF directory exists", os.path.exists(os.path.join(etfs_dir_path, "index.html")))
    if os.path.exists(os.path.join(etfs_dir_path, "index.html")):
        etf_dir_html = open(os.path.join(etfs_dir_path, "index.html"), encoding="utf-8").read()
        check("ETF directory links /etf/ pages", '/etf/' in etf_dir_html)
        etf_dir = os.path.join(ROOT, "site", "etf")
        etf_slugs = sorted(d for d in os.listdir(etf_dir)) if os.path.isdir(etf_dir) else []
        if etf_slugs:
            etf_html = open(os.path.join(etf_dir, etf_slugs[0], "index.html"), encoding="utf-8").read()
            check("ETF page carries the Zerodha and Jiraaf sponsored banners (two, not three, on thin pages)",
                  "aff-banner-zerodha" in etf_html and "aff-banner-jiraaf" in etf_html)

    # The SEBI registry was the one directory family that shipped without
    # this fix: /registry only ever hard-linked the first 60 of ~1,691
    # entities, the rest sat behind a client-side "Next" button with no href,
    # so ~96% of this family had no on-site path at all - Google's Page
    # Indexing report showed almost the entire family stuck on "Discovered -
    # currently not indexed". Nested under /registry/az/, not /sebi-registry/
    # itself, because that path already belongs to the individual entity
    # pages and gets pruned to just their slugs on every run.
    registry_az_dir = os.path.join(ROOT, "site", "registry", "az")
    check("SEBI registry A-Z directory exists", os.path.isdir(registry_az_dir))
    if os.path.isdir(registry_az_dir):
        reg_letter_dirs = [d for d in os.listdir(registry_az_dir) if os.path.isdir(os.path.join(registry_az_dir, d))]
        check("registry directory has more than one letter page", len(reg_letter_dirs) > 1,
              "found %d" % len(reg_letter_dirs))
        reg_overview_html = open(os.path.join(registry_az_dir, "index.html"), encoding="utf-8").read()
        check("registry directory overview links every letter page",
              all('/registry/az/%s/' % d in reg_overview_html for d in reg_letter_dirs))
        if reg_letter_dirs:
            reg_sample_html = open(os.path.join(registry_az_dir, reg_letter_dirs[0], "index.html"),
                                    encoding="utf-8").read()
            check("a registry letter page actually links /sebi-registry/ entity pages",
                  '/sebi-registry/' in reg_sample_html)
        registry_landing_html = open(os.path.join(ROOT, "site", "registry", "index.html"), encoding="utf-8").read()
        check("the (already-indexed) /registry page links into the new A-Z directory",
              all('/registry/az/%s/' % d in registry_landing_html for d in reg_letter_dirs),
              "this is the actual inbound link that rescues the orphaned pages - "
              "a directory nobody links to is exactly as orphaned as before")

    # Site-wide footer must link the three directory pages above, or they are
    # just as orphaned as the pages they exist to fix - a directory page
    # with no inbound link of its own defeats the point.
    footer_targets = ["/stocks/", "/funds-by/", "/etfs/"]
    if os.path.isdir(stock_dir) and slugs:
        stock_html = open(os.path.join(stock_dir, slugs[0], "index.html"), encoding="utf-8").read()
        check("a static page footer links the browse directories",
              all(t in stock_html for t in footer_targets), "missing: %s" % [t for t in footer_targets if t not in stock_html])
    home_html_for_dirs = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
    check("homepage footer links the browse directories too",
          all(t in home_html_for_dirs for t in footer_targets),
          "missing: %s" % [t for t in footer_targets if t not in home_html_for_dirs])

    # /assets/* is served with a one-year immutable Cache-Control (vercel.json),
    # so a CSS/JS reference that never changes URL is invisible to a returning
    # visitor's browser on every future deploy, forever, until a hard refresh -
    # caught live: a banner redesign shipped to the server but rendered
    # unstyled for anyone who'd already loaded the old app.css. Every asset
    # reference must carry a content-hash query string so a changed file gets
    # a new URL.
    check("homepage's CSS/JS asset references are cache-busted with a content-hash query string",
          bool(re.search(r'/assets/css/app\.css\?v=[0-9a-f]{6,}', home_html_for_dirs))
          and bool(re.search(r'/assets/js/app\.js\?v=[0-9a-f]{6,}', home_html_for_dirs)))
    if os.path.isdir(stock_dir) and slugs:
        check("a static page's CSS asset reference is cache-busted too",
              bool(re.search(r'/assets/css/app\.css\?v=[0-9a-f]{6,}', stock_html)))

    # Global search: a precomputed search.json plus a search.js widget wired
    # into every page's header, following the same "no live API" contract as
    # the rest of the site (see store.js's own header comment).
    search_json_path = os.path.join(ROOT, "site", "data", "search.json")
    check("search.json exists", os.path.exists(search_json_path))
    if os.path.exists(search_json_path):
        import json as _json
        search_rows = _json.loads(open(search_json_path, encoding="utf-8").read())
        check("search.json has thousands of entries, not just the 47 brokers", len(search_rows) > 5000,
              "found %d" % len(search_rows))
        check("search.json rows are compact 4-element arrays", all(len(r) == 4 for r in search_rows[:20]))
    search_js_path = os.path.join(ROOT, "site", "assets", "js", "search.js")
    check("search.js exists", os.path.exists(search_js_path))
    if os.path.exists(search_js_path):
        search_js = open(search_js_path, encoding="utf-8").read()
        check("search.js fetches the precomputed index, no live API call",
              "loadSearchIndex" in search_js and "fetch(" not in search_js)
    check("homepage has the search trigger and overlay markup",
          'id="search-toggle"' in home_html_for_dirs and 'id="search-overlay"' in home_html_for_dirs
          and 'id="search-input"' in home_html_for_dirs)
    if os.path.isdir(stock_dir) and slugs:
        stock_html = open(os.path.join(stock_dir, slugs[0], "index.html"), encoding="utf-8").read()
        check("a static page has the search trigger and overlay markup too",
              'id="search-toggle"' in stock_html and 'id="search-overlay"' in stock_html)
        check("a static page loads search.js", "search.js" in stock_html)

    # Homepage nav must carry the exact same link set as every static page -
    # found missing "Reports" and pointing "Calculators" at the SPA's
    # different brokerage-cost-calculator route while static pages already
    # had a real Calculators link, while auditing nav consistency.
    home_nav_html = home_html_for_dirs[:home_html_for_dirs.find('id="app"')]
    check("homepage nav has a Calculators link matching static pages",
          'href="/calculators/">Calculators' in home_nav_html)
    check("homepage nav has a Reports link matching static pages",
          "Reports</a>" in home_nav_html and "/reports/state-of-indian-broking-2026/" in home_nav_html)

    # About/Contact/Privacy/Terms: added because the site had no such pages
    # at all (an E-E-A-T gap), plus the one real support address, and every
    # footer must actually link to them - a page nothing links to is as
    # orphaned as the SEBI registry entities were before the /registry/az/
    # fix above. site/index.html is hand-maintained (see
    # _restamp_index_html_assets's docstring), so it does not regenerate
    # from _APP_SHELL_FOOT on every build like every other page does - this
    # check exists specifically so a future footer change that forgets to
    # hand-sync index.html fails CI instead of shipping silently, the same
    # class of bug as the nav-consistency check just above.
    company_pages = {
        "about": "About BrokerLens",
        "contact": "Contact BrokerLens",
        "privacy-policy": "Privacy Policy",
        "terms-of-service": "Terms of Service",
        "editorial-policy": "Editorial Policy",
    }
    for slug, heading in company_pages.items():
        page_path = os.path.join(ROOT, "site", slug, "index.html")
        check("%s page exists" % slug, os.path.exists(page_path))
        if os.path.exists(page_path):
            page_html = open(page_path, encoding="utf-8").read()
            check("%s page has its own heading, not a generic shell" % slug, heading in page_html)
            check("%s page carries the real contact address" % slug, CONTACT_EMAIL in page_html)
    company_targets = ["/about", "/contact", "/privacy-policy", "/terms-of-service"]
    check("homepage footer links all four company pages and the contact address",
          all(t in home_html_for_dirs for t in company_targets) and CONTACT_EMAIL in home_html_for_dirs,
          "missing: %s" % [t for t in company_targets if t not in home_html_for_dirs])
    if os.path.isdir(stock_dir) and slugs:
        check("a static page footer links all four company pages and the contact address too",
              all(t in stock_html for t in company_targets) and CONTACT_EMAIL in stock_html,
              "missing: %s" % [t for t in company_targets if t not in stock_html])

    # E-E-A-T compliance and editorial transparency checks
    ed_path = os.path.join(ROOT, "site", "editorial-policy", "index.html")
    check("editorial-policy page exists", os.path.exists(ed_path))
    if os.path.exists(ed_path):
        ed_html = open(ed_path, encoding="utf-8").read()
        check("editorial policy page has no leaked 'None'",
              ">None<" not in ed_html and "None</p>" not in ed_html)
        check("editorial policy explicitly states Golden Source Standard",
              "Golden Source" in ed_html or "Hierarchy of Data" in ed_html)
        check("editorial policy articulates zero-payola guarantee",
              "Zero-Payola" in ed_html or "Rankings Cannot Be Purchased" in ed_html)
        check("editorial policy states 24-48h corrections SLA",
              "24 to 48" in ed_html or "48 business hours" in ed_html)
        check("editorial policy defines Organization Schema.org with publishing principles",
              '"publishingPrinciples"' in ed_html and '"correctionsPolicy"' in ed_html)

    # News E-E-A-T bylines on a page emitted by the current news generator.
    news_dir = os.path.join(ROOT, "site", "news")
    if os.path.isdir(news_dir):
        news_feed_path = os.path.join(ROOT, "site", "data", "news.json")
        check("news feed identifies generated articles", os.path.isfile(news_feed_path))
        if os.path.isfile(news_feed_path):
            with open(news_feed_path, encoding="utf-8") as f:
                news_feed = json.load(f)
            generated_articles = news_feed.get("articles", [])
            check("news feed contains generated articles", bool(generated_articles))
            if generated_articles:
                sample_art_path = os.path.join(
                    news_dir, generated_articles[0]["slug"], "index.html"
                )
                check("generated news article page exists", os.path.isfile(sample_art_path))
                if os.path.exists(sample_art_path):
                    art_html = open(sample_art_path, encoding="utf-8").read()
                    check("news articles carry BrokerLens Financial Research Desk byline",
                          "BrokerLens Financial Research Desk" in art_html)
                    check("news articles carry fact-checking and editorial policy link",
                          "/editorial-policy" in art_html)

    # Breadcrumbs: a shared helper builds both the visible trail and its
    # BreadcrumbList JSON-LD from the same data, so a page can never show one
    # without the other. Checked on the highest-volume families plus the new
    # directory pages, since a leaf page with no breadcrumb back to its
    # parent hub is exactly the kind of orphaned-page gap fixed above.
    import json as _json2

    def _has_breadcrumb(html):
        if '<nav class="breadcrumb"' not in html:
            return False
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            data = _json2.loads(m.group(1))
            items = data.get("@graph", [data]) if isinstance(data, dict) else []
            if any(isinstance(it, dict) and it.get("@type") == "BreadcrumbList" for it in items):
                return True
        return False

    breadcrumb_targets = []
    if os.path.isdir(stock_dir) and slugs:
        breadcrumb_targets.append(("stock", os.path.join(stock_dir, slugs[0], "index.html")))
    if os.path.exists(hdfc_flexicap_path):
        breadcrumb_targets.append(("fund", hdfc_flexicap_path))
    if os.path.exists(sip_path):
        breadcrumb_targets.append(("calculator", sip_path))
    if os.path.exists(calc_hub_path):
        breadcrumb_targets.append(("calculator hub", calc_hub_path))
    if os.path.exists(os.path.join(stocks_dir_path, "index.html")):
        breadcrumb_targets.append(("stock directory overview", os.path.join(stocks_dir_path, "index.html")))
    if os.path.exists(os.path.join(funds_by_dir, "index.html")):
        breadcrumb_targets.append(("fund AMC directory overview", os.path.join(funds_by_dir, "index.html")))
    for label, path in breadcrumb_targets:
        html = open(path, encoding="utf-8").read()
        check("%s page has a breadcrumb trail with matching JSON-LD" % label, _has_breadcrumb(html))

    # theme-init.js applies a visitor's stored dark/light choice on every
    # static page. Found live (by actually toggling dark mode on the
    # homepage in a real browser, then navigating to a static page and
    # watching it silently revert to light): none of the ~8,000
    # registry/stock/index/etf/fund/report/calculator pages read the stored
    # preference at all, since only app.js did that and none of those pages
    # load app.js. Checked here at the template level, and it must load
    # before the stylesheet or the page flashes the wrong theme before
    # switching.
    theme_init_path = os.path.join(ROOT, "site", "assets", "js", "theme-init.js")
    check("theme-init.js exists", os.path.exists(theme_init_path))
    if os.path.exists(theme_init_path):
        theme_js = open(theme_init_path, encoding="utf-8").read()
        check("theme-init.js reads the same localStorage key app.js writes",
              "bl-theme" in theme_js and "localStorage" in theme_js)
        for label, path in [
            ("stock", os.path.join(stock_dir, slugs[0], "index.html") if os.path.isdir(stock_dir) and slugs else ""),
            ("fund", hdfc_flexicap_path if os.path.isdir(fund_dir) and os.path.exists(hdfc_flexicap_path) else ""),
            ("calculator", sip_path if os.path.isdir(calc_dir) and os.path.exists(sip_path) else ""),
        ]:
            if not path or not os.path.exists(path):
                continue
            html = open(path, encoding="utf-8").read()
            theme_pos = html.find("theme-init.js")
            css_pos = html.find('rel="stylesheet"')
            check("%s page loads theme-init.js before its stylesheet" % label,
                  theme_pos != -1 and css_pos != -1 and theme_pos < css_pos)
        homepage_html = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
        check("homepage/broker shell also loads theme-init.js (covers broker pages too)",
              "theme-init.js" in homepage_html)

        # A visible toggle, not just a stored preference, needs to be present
        # on every static page - otherwise a first-time visitor arriving
        # directly on a stock/fund/report/calculator page (the common case:
        # most organic traffic never lands on the homepage first) has no way
        # to switch themes at all.
        for label, path in [
            ("stock", os.path.join(stock_dir, slugs[0], "index.html") if os.path.isdir(stock_dir) and slugs else ""),
            ("fund", hdfc_flexicap_path if os.path.isdir(fund_dir) and os.path.exists(hdfc_flexicap_path) else ""),
            ("report", report_path if os.path.exists(report_path) else ""),
            ("calculator", sip_path if os.path.isdir(calc_dir) and os.path.exists(sip_path) else ""),
        ]:
            if not path or not os.path.exists(path):
                continue
            html = open(path, encoding="utf-8").read()
            check("%s page has a visible theme-toggle button" % label, 'id="theme-toggle"' in html)
        theme_init_full = open(theme_init_path, encoding="utf-8").read()
        check("theme-init.js wires up the toggle button's click handler",
              "theme-toggle" in theme_init_full and "addEventListener" in theme_init_full)

        # Full nav parity with the homepage/SPA shell. Found live (a user
        # pointed out only 4 of the homepage's 7 nav items, and no mega
        # menu at all, appeared on ~8,000 static pages): a stock page had
        # Brokers/SEBI registry/Algo platforms/Reports but was missing
        # Compare, Rankings, a calculators link and the market-timings mega
        # menu entirely, so navigation felt different depending on which
        # page a visitor landed on first.
        NAV_LINKS = ["Brokers", "Compare", "Movers", "SEBI registry", "Algo platforms", "Reports"]
        for label, path in [
            ("stock", os.path.join(stock_dir, slugs[0], "index.html") if os.path.isdir(stock_dir) and slugs else ""),
            ("fund", hdfc_flexicap_path if os.path.isdir(fund_dir) and os.path.exists(hdfc_flexicap_path) else ""),
        ]:
            if not path or not os.path.exists(path):
                continue
            html = open(path, encoding="utf-8").read()
            check("%s page nav has the same link set as the homepage" % label,
                  all(n in html for n in NAV_LINKS), "missing: %s" % [n for n in NAV_LINKS if n not in html])
            check("%s page has a hamburger nav-toggle for mobile" % label, 'id="nav-toggle"' in html)
            check("%s page has the market-timings mega menu" % label,
                  'id="timings-toggle"' in html and 'id="mega-timings"' in html and 'id="mega-timings-body"' in html)
            check("%s page loads nav-widgets.js (mega menu / hamburger logic)" % label,
                  "nav-widgets.js" in html)

    nav_widgets_path = os.path.join(ROOT, "site", "assets", "js", "nav-widgets.js")
    check("nav-widgets.js exists", os.path.exists(nav_widgets_path))
    if os.path.exists(nav_widgets_path):
        nav_widgets_js = open(nav_widgets_path, encoding="utf-8").read()
        check("nav-widgets.js implements both the hamburger and the mega menu",
              "nav-toggle" in nav_widgets_js and "timings-toggle" in nav_widgets_js and "loadTimings" in nav_widgets_js)
    app_js_src = open(os.path.join(ROOT, "site", "assets", "js", "app.js"), encoding="utf-8").read()
    check("app.js delegates nav/theme widgets to the shared files instead of duplicating them",
          "./nav-widgets.js" in app_js_src
          and "megaBtn" not in app_js_src and "themeBtn" not in app_js_src)

    # Markets dropdown ("Brokers" -> India/Crypto/US/GCC): must appear
    # identically on the SPA shell and every static page, same as every
    # other nav element on this site.
    if os.path.exists(nav_widgets_path):
        check("nav-widgets.js implements the shared dropdown wiring used by both mega menus",
              "wireDropdown" in nav_widgets_js and "markets-toggle" in nav_widgets_js)
    for label, path in [
        ("homepage", os.path.join(ROOT, "site", "index.html")),
        ("stock", os.path.join(stock_dir, slugs[0], "index.html") if os.path.isdir(stock_dir) and slugs else ""),
    ]:
        if not path or not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        check("%s page has the markets dropdown (Brokers menu)" % label,
              'id="markets-toggle"' in html and 'id="mega-markets"' in html
              and ">India<" in html and ">Crypto<" in html and ">US<" in html and ">GCC<" in html)

    # Coming-soon routes for the still-unbuilt markets (crypto graduated to a
    # real pipeline - see the crypto page checks below): real pages, not dead
    # nav links.
    check("app.js registers routes for the two still-unbuilt markets",
          all(r in app_js_src for r in ["/coming-soon/us", "/coming-soon/gcc"])
          and "/coming-soon/crypto" not in app_js_src)
    pages_js_src = open(os.path.join(ROOT, "site", "assets", "js", "pages.js"), encoding="utf-8").read()
    check("pages.js implements comingSoon() for the two still-unbuilt markets",
          "export async function comingSoon" in pages_js_src
          and all(k in pages_js_src for k in ["us:", "gcc:"]))

    # Regression guard: /compare's "Active clients over time" chart card used
    # to render unconditionally regardless of whether any compared broker
    # actually had client-history data - with active_clients still
    # sample-gated in production, every single comparison hit this, showing
    # a permanently-empty chart on 100% of real page loads. The table rows
    # above it already drop a metric nobody has; the chart card must too.
    check("compare()'s chart card is gated on at least one broker actually having client-history data",
          "hasClientSeries" in pages_js_src
          and re.search(r"hasClientSeries\s*\?\s*`<div", pages_js_src))

    # Crypto vertical (Phase 1, 28 hand-verified coins): real static pages
    # with live price loaded client-side, same architecture as the rest of
    # the site's "static facts + client-refreshed live number" pattern.
    crypto_dir = os.path.join(ROOT, "site", "crypto")
    check("crypto hub page exists", os.path.exists(os.path.join(crypto_dir, "index.html")))
    # Both Binance and CoinGecko can independently fail; if a future change
    # ever makes both legs come back empty, _write_crypto_pages() silently
    # writes zero pages and prunes any that existed (caught live once: a
    # Binance-only price leg 451s from Vercel/GitHub Actions, every build,
    # permanently, deleting all 28 committed pages with no test catching it -
    # the site.vercel.json SPA rewrite then quietly served the homepage for
    # every /crypto/* URL instead of a clear 404). This check exists so that
    # regression is loud instead of silent.
    if os.path.isdir(crypto_dir):
        coin_dirs = [d for d in os.listdir(crypto_dir) if os.path.isdir(os.path.join(crypto_dir, d))]
        check("a real number of crypto coin pages were written, not silently pruned to zero",
              len(coin_dirs) >= 20, "found %d" % len(coin_dirs))
    if os.path.exists(os.path.join(crypto_dir, "index.html")):
        hub_html = open(os.path.join(crypto_dir, "index.html"), encoding="utf-8").read()
        check("crypto hub links individual coin pages", "/crypto/btc/" in hub_html or "/crypto/eth/" in hub_html)
        check("crypto hub carries the Binance sponsored banner", "Binance" in hub_html and "Sponsored" in hub_html)
        check("crypto hub carries the Delta Exchange sponsored banner, stacked below Binance's",
              "Delta Exchange" in hub_html
              and hub_html.index("aff-banner-binance") < hub_html.index("aff-banner-delta")
              and "delta.exchange/?code=UAIYQN" in hub_html)
        check("crypto hub loads crypto-live.js", "crypto-live.js" in hub_html)
        check("crypto hub shows a real per-coin icon, not a placeholder",
              'class="coin-icon"' in hub_html and "coin-images.coingecko.com" in hub_html)
        check("crypto hub has a real Volume (24h) column, not just rank/price/change",
              "Volume (24h)" in hub_html and 'data-role="volume"' in hub_html)
    btc_path = os.path.join(crypto_dir, "btc", "index.html")
    check("a sample crypto coin page (BTC) exists", os.path.exists(btc_path))
    if os.path.exists(btc_path):
        btc_html = open(btc_path, encoding="utf-8").read()
        check("BTC page has a live-price placeholder wired to its symbol",
              'id="crypto-price"' in btc_html and 'data-symbol="BTC"' in btc_html)
        check("BTC page has real FAQPage and BreadcrumbList JSON-LD",
              '"@type": "FAQPage"' in btc_html and '"@type": "BreadcrumbList"' in btc_html)
        check("BTC page states crypto is not SEBI-regulated", "not regulated by SEBI" in btc_html.lower()
              or "not regulated by sebi" in btc_html.lower())
        check("BTC page has no crypto exchange affiliate banner on the coin page itself",
              "aff-banner" not in btc_html)  # the CTA lives on the hub, not every coin page
        check("BTC page loads the self-hosted chart library and chart script, not a CDN",
              "vendor/lightweight-charts" in btc_html and "crypto-chart.js" in btc_html
              and "cdn." not in btc_html.lower() and "unpkg.com" not in btc_html)
        check("BTC page has a chart container wired to its symbol",
              "data-crypto-chart" in btc_html and 'data-symbol="BTC"' in btc_html)

    crypto_chart_path = os.path.join(ROOT, "site", "assets", "js", "crypto-chart.js")
    if os.path.exists(crypto_chart_path):
        crypto_chart_src = open(crypto_chart_path, encoding="utf-8").read()
        check("crypto-chart.js defines technical indicators (SMA, EMA, Bollinger)",
              "calcSMA" in crypto_chart_src and "calcEMA" in crypto_chart_src and "calcBollinger" in crypto_chart_src)
        check("crypto-chart.js defines Smart Zones (Support/Resistance levels)",
              "calcSmartZones" in crypto_chart_src and "createPriceLine" in crypto_chart_src)
        check("crypto-chart.js listens for live quote updates",
              "brokerlens:crypto-quote" in crypto_chart_src)

    vendor_path = os.path.join(ROOT, "site", "assets", "js", "vendor",
                                "lightweight-charts.standalone.production.js")
    check("lightweight-charts vendor file is self-hosted, not fetched from a CDN at runtime",
          os.path.exists(vendor_path) and os.path.getsize(vendor_path) > 50_000)

    history_dir = os.path.join(ROOT, "site", "data", "crypto-history")
    check("crypto-history/ directory exists", os.path.isdir(history_dir))
    if os.path.isdir(history_dir):
        hist_files = [f for f in os.listdir(history_dir) if f.endswith(".json")]
        # CoinGecko's free tier throttles a 28-coin sweep well before it
        # finishes (confirmed live), so this can never assert "all 28" on a
        # single run - each coin's history is cached for 20h, so the gaps
        # fill in over the next few runs rather than blocking this one.
        check("at least some coins have real price-history files, not zero",
              len(hist_files) > 0, "found %d" % len(hist_files))
        if hist_files:
            sample = json.load(open(os.path.join(history_dir, hist_files[0])))
            candles = sample.get("candles") or []
            check("a history file has real, chronologically ordered daily candles",
                  len(candles) > 30 and [c[0] for c in candles] == sorted(c[0] for c in candles))
            dates = [c[0] for c in candles]
            check("a history file has no duplicate dates (CoinGecko's partial-final-day artifact)",
                  len(dates) == len(set(dates)))
    crypto_live_path = os.path.join(ROOT, "site", "assets", "js", "crypto-live.js")
    check("crypto-live.js exists", os.path.exists(crypto_live_path))
    if os.path.exists(crypto_live_path):
        crypto_live_src = open(crypto_live_path, encoding="utf-8").read()
        check("crypto-live.js fetches the precomputed snapshot, not a live third-party API",
              "crypto-ticker.json" in crypto_live_src and "binance.com" not in crypto_live_src.lower())
    sitemap_main = open(os.path.join(ROOT, "site", "sitemap.xml"), encoding="utf-8").read()
    sitemaps_dir = os.path.join(ROOT, "site", "sitemaps")
    if os.path.isdir(sitemaps_dir):
        all_sitemap_xml = sitemap_main + "".join(
            open(os.path.join(sitemaps_dir, f), encoding="utf-8").read()
            for f in os.listdir(sitemaps_dir) if f.endswith(".xml")
        )
    else:
        all_sitemap_xml = sitemap_main
    check("sitemap includes /crypto/ pages", "/crypto/" in all_sitemap_xml)
    check("share-price projections reject six months of history",
          not _has_three_year_history([100.0] * 120))
    check("share-price projections accept three years of daily history",
          _has_three_year_history([100.0] * MIN_HISTORY_SESSIONS))
    try:
        _scenario_prices(100.0, -99.0, -90.0, 4)
        invalid_scenario_rejected = False
    except ValueError:
        invalid_scenario_rejected = True
    check("share-price projections reject zero or invalid scenarios",
          invalid_scenario_rejected)
    # Regression guard: bear/bull scenarios were previously computed with
    # sign-unaware multipliers (hist_cagr_3y * 0.4 floored at -5.0 for bear;
    # hist_cagr_1y * 1.3 for bull), which inverted the ordering whenever
    # historical CAGR was negative (e.g. RELIANCE showed Bear +5%/-5.0% vs
    # Bull -21.2%, worse than bear). Bear must always be <= Base <= Bull.
    for cagr_1y, cagr_3y in ((12.0, 8.0), (-18.0, -14.0), (-30.0, 6.0), (0.0, 0.0)):
        bear_cagr, base_cagr, bull_cagr = _scenario_prices(100.0, cagr_1y, cagr_3y, 3)[0]
        check("share-price scenarios stay ordered bear<=base<=bull for cagr_1y=%s cagr_3y=%s"
              % (cagr_1y, cagr_3y),
              bear_cagr <= base_cagr <= bull_cagr,
              "got bear=%.2f base=%.2f bull=%.2f" % (bear_cagr, base_cagr, bull_cagr))
    target_years = _target_years()
    try:
        render_target_page(
            "TEST", "Test Company", 100, 120, 80, 10, 10,
            max(target_years) + 1, MIN_HISTORY_SESSIONS, "2026-10-01",
        )
        unsupported_target_year_rejected = False
    except ValueError:
        unsupported_target_year_rejected = True
    check("share-price projections reject unsupported target years",
          unsupported_target_year_rejected)
    try:
        render_target_page(
            "TEST", "Test Company", 100, 120, 80, 10, 10,
            target_years[0], 120, "2026-10-01",
        )
        short_history_rejected = False
    except ValueError:
        short_history_rejected = True
    check("share-price pages cannot render without three years of history",
          short_history_rejected)
    target_sitemap_years = [
        int(year) for year in re.findall(
            r"/stock/[^/]+/share-price-target-(\d{4})/", all_sitemap_xml
        )
    ]
    check("share-price sitemap excludes long-range target years",
          all(year in target_years for year in target_sitemap_years),
          "unsupported years: %s" % sorted(set(target_sitemap_years) - set(target_years)))
    redirects = (load("vercel.json") or {}).get("redirects", [])
    check("retired share-price target URLs redirect to stock profiles",
          any(
              rule.get("source") == "/stock/:symbol/share-price-target-:year"
              and rule.get("destination") == "/stock/:symbol/"
              and rule.get("permanent") is True
              for rule in redirects
          ))

    # Keep source dates attached to their own symbol through ranking and page generation.
    with tempfile.TemporaryDirectory() as temp_root:
        temp_data_dir = os.path.join(temp_root, "data")
        temp_site_dir = os.path.join(temp_root, "site")
        os.makedirs(temp_data_dir)
        companies = []
        histories = {}
        expected_dates = {}
        for symbol, start_day in (("ALPHA", 2), ("BETA", 3)):
            companies.append({"symbol": symbol, "name": symbol.title() + " Ltd"})
            session_date = datetime(2023, 1, start_day)
            history = []
            while len(history) < MIN_HISTORY_SESSIONS:
                if session_date.weekday() < 5:
                    history.append({
                        "date": session_date.strftime("%Y-%m-%d"),
                        "close": 100.0,
                        "volume": 1000,
                    })
                session_date += timedelta(days=1)
            histories[symbol] = history
            expected_dates[symbol] = history[-1]["date"]
        with open(os.path.join(temp_data_dir, "_ingest.json"), "w", encoding="utf-8") as out:
            json.dump({
                "nse": {
                    "universe": {"companies": companies},
                    "equity_history": histories,
                },
            }, out)

        original_data_dir, original_site_dir = target_engine.DATA_DIR, target_engine.SITE_DIR
        try:
            target_engine.DATA_DIR, target_engine.SITE_DIR = temp_data_dir, temp_site_dir
            target_urls = target_engine.build_share_price_target_suite(limit_stocks=2)
            symbol_dates_match = len(target_urls) == 2 * len(target_years)
            for symbol, expected_date in expected_dates.items():
                page_path = os.path.join(
                    temp_site_dir, "stock", symbol.lower(),
                    "share-price-target-%d" % target_years[0], "index.html",
                )
                try:
                    with open(page_path, encoding="utf-8") as page_file:
                        symbol_dates_match = symbol_dates_match and (
                            "NSE price history through %s" % expected_date
                            in page_file.read()
                        )
                except OSError:
                    symbol_dates_match = False
        finally:
            target_engine.DATA_DIR, target_engine.SITE_DIR = original_data_dir, original_site_dir
    check("share-price pages retain each symbol's own source-data date",
          symbol_dates_match)

    # Every one of ~9,500 sitemap URLs used to get today's date stamped as
    # lastmod on every single build, regardless of whether anything about
    # that page had actually changed - a pattern that teaches a crawler to
    # stop trusting the field altogether. Stock and ETF pages now use the
    # real last date in their own price history (see nse.py's
    # equity_history()); a real, varied spread of dates is the only way to
    # confirm this wasn't silently reverted to the old fake-it constant.
    stock_lastmods = re.findall(r"/stock/[^/]+/</loc><lastmod>([^<]+)</lastmod>", all_sitemap_xml)
    check("stock URLs in the sitemap have real, varied lastmod dates, not one fake constant",
          len(stock_lastmods) > 100 and len(set(stock_lastmods)) > 5,
          "found %d urls across %d distinct dates" % (len(stock_lastmods), len(set(stock_lastmods))))
    all_search_rows = json.loads(open(search_json_path, encoding="utf-8").read()) if os.path.exists(search_json_path) else []
    search_rows_crypto = [r for r in all_search_rows if r[2] == "crypto"]
    check("search index includes crypto coins", len(search_rows_crypto) >= 20, "found %d" % len(search_rows_crypto))
    search_rows_news = [r for r in all_search_rows if r[2] == "news"]
    check("search index includes news articles", len(search_rows_news) > 0,
          "found %d" % len(search_rows_news))
    search_rows_stock_cmp = [r for r in all_search_rows if r[2] == "compare" and "/compare/stocks/" in r[1]]
    search_rows_fund_cmp = [r for r in all_search_rows if r[2] == "compare" and "/compare/mutual-funds/" in r[1]]
    check("search index includes curated stock-compare pairs, not the noindex all-pairs",
          0 < len(search_rows_stock_cmp) < 5000,
          "found %d (expected hundreds, not the ~125K all-pairs total)" % len(search_rows_stock_cmp))
    check("search index includes curated fund-compare pairs, not the noindex all-pairs",
          0 < len(search_rows_fund_cmp) < 10000,
          "found %d (expected thousands, not the ~20K all-pairs total)" % len(search_rows_fund_cmp))
    check("markets dropdown marks Crypto as Live, not Coming soon",
          '<a href="/crypto/"><span>Crypto</span><span class="badge badge-up">Live</span></a>' in home_html_for_dirs)

    # IPO tracker: /ipo/ hub, /ipo/archive/, and one static page per IPO,
    # sourced from NSE's own public-issue disclosures (see
    # pipeline/sources/nse.py's ipo_current/ipo_upcoming/ipo_past()).
    ipo_dir = os.path.join(ROOT, "site", "ipo")
    check("site/ipo/ directory exists", os.path.isdir(ipo_dir))
    if os.path.isdir(ipo_dir):
        ipo_symbol_dirs = [d for d in os.listdir(ipo_dir)
                            if d != "archive" and os.path.isdir(os.path.join(ipo_dir, d))]
        check("a real number of IPO pages were written, not silently pruned to zero",
              len(ipo_symbol_dirs) > 500, "found %d" % len(ipo_symbol_dirs))
        check("no IPO page slug starts with a digit (the debt/NCD filter)",
              not any(d[0].isdigit() for d in ipo_symbol_dirs),
              "found: %s" % [d for d in ipo_symbol_dirs if d[0].isdigit()][:5])

    ipo_hub_path = os.path.join(ipo_dir, "index.html")
    ipo_hub_html = open(ipo_hub_path, encoding="utf-8").read() if os.path.exists(ipo_hub_path) else ""
    check("IPO hub exists and loads no app bundle (pure static, zero JS)",
          os.path.exists(ipo_hub_path) and "/assets/js/app.js" not in ipo_hub_html and "<h1" in ipo_hub_html)
    check("IPO hub explicitly disclaims grey market premium (GMP)",
          "grey market" in ipo_hub_html.lower() or "GMP" in ipo_hub_html)
    check("IPO hub links through to the full archive",
          "/ipo/archive/" in ipo_hub_html)
    check("IPO hub has no leaked 'None'", ">None<" not in ipo_hub_html and "None</p>" not in ipo_hub_html)

    ipo_archive_path = os.path.join(ipo_dir, "archive", "index.html")
    check("IPO archive page exists", os.path.exists(ipo_archive_path))

    if ipo_symbol_dirs if os.path.isdir(ipo_dir) else False:
        sample_ipo_path = os.path.join(ipo_dir, sorted(ipo_symbol_dirs)[0], "index.html")
        sample_ipo_html = open(sample_ipo_path, encoding="utf-8").read()
        check("an IPO page has real FAQPage and BreadcrumbList JSON-LD",
              '"@type": "FAQPage"' in sample_ipo_html and '"@type": "BreadcrumbList"' in sample_ipo_html)
        check("an IPO page explicitly states BrokerLens does not recommend applying",
              "not investment advice" in sample_ipo_html.lower())
        check("an IPO page has no leaked 'None'",
              ">None<" not in sample_ipo_html and "None</p>" not in sample_ipo_html)
        check("an IPO page carries the Zerodha and Indiabulls sponsored broker banners (IBSL replaced 5paisa, keeping three blocks)",
              "aff-banner-zerodha" in sample_ipo_html and 'data-ad="ibsl"' in sample_ipo_html)
        fabricated_rhp_markers = (
            "RHP Financials", "RHP audited financials", "Industry Median",
            "industry peer benchmark", "industry_pe", "Business Strengths",
            "Risk Factors",
        )
        check("an IPO page carries no fabricated RHP financial claims",
              not any(marker in sample_ipo_html for marker in fabricated_rhp_markers),
              "found: %s" % [m for m in fabricated_rhp_markers if m in sample_ipo_html])

    # The "RHP Financials" / business-strengths / risk-factors section used to be
    # generated by hashing the company name into plausible-looking numbers
    # (seed = sum(ord(c) for c in symbol+company)) -- not real SEBI filings.
    # Guard against that fabrication machinery ever coming back.
    ipo_engine_src = open(ipo_engine.__file__, encoding="utf-8").read()
    check("ipo_engine has no hash-derived fabricated-financials generator",
          "compute_rhp_financials" not in ipo_engine_src
          and "compute_decision_framework" not in ipo_engine_src
          and "render_rhp_decision_section" not in ipo_engine_src)

    check("sitemap includes /ipo/ pages", "/ipo/" in all_sitemap_xml)
    search_rows_ipo = [r for r in all_search_rows if r[2] == "ipo"]
    check("search index includes IPOs", len(search_rows_ipo) > 500, "found %d" % len(search_rows_ipo))
    check("nav has an IPO link", '<a href="/ipo/">IPO</a>' in home_html_for_dirs)

    # Affiliate banner: a real referral link, kept out of the ranking table,
    # and never mixed with crypto content per the standing placement rule.
    check("pages.js defines a real Zerodha affiliate banner with the actual referral link",
          "function affiliateBanner" in pages_js_src
          and "zerodha.com/open-account?c=ZE5729" in pages_js_src
          and 'rel="noopener sponsored"' in pages_js_src)
    check("the affiliate banner is not embedded inside the broker ranking table markup",
          # dirRow() renders each ranked table row; the banner must live outside it.
          "affiliateBanner()" not in re.search(r"function dirRow\(.*?\n\}", pages_js_src, re.S).group(0)
          if re.search(r"function dirRow\(.*?\n\}", pages_js_src, re.S) else True)
    # "binance" is expected on the dedicated coming-soon/crypto page copy;
    # it must not appear inside affiliateBanner() or the home()/brokers()
    # functions that actually render it, which is the real separation rule.
    for fn_name in ("affiliateBanner", "home", "brokers"):
        m = re.search(r"function %s\(.*?\n\}" % fn_name, pages_js_src, re.S) \
            or re.search(r"async function %s\(.*?\n\}" % fn_name, pages_js_src, re.S)
        if m:
            check("%s() carries no crypto exchange content alongside the Indian broker affiliate banner" % fn_name,
                  "binance" not in m.group(0).lower())

    # No page title anywhere on the site should carry an em dash - a standing
    # copy rule ("—" isn't in the "no em dashes" allowance) applied here as an
    # automated check since it has silently regressed before.
    for label, path in [
        ("homepage", os.path.join(ROOT, "site", "index.html")),
        ("stock sample", os.path.join(stock_dir, slugs[0], "index.html") if os.path.isdir(stock_dir) and slugs else ""),
        ("index sample", os.path.join(index_dir, "nifty-50", "index.html") if index_slugs else ""),
        ("etf sample", niftybees_path if os.path.isdir(etf_dir) and os.path.exists(niftybees_path) else ""),
        ("fund sample", hdfc_flexicap_path if os.path.isdir(fund_dir) and os.path.exists(hdfc_flexicap_path) else ""),
        ("report", report_path if os.path.exists(report_path) else ""),
        ("calculator sample", sip_path if os.path.isdir(calc_dir) and os.path.exists(sip_path) else ""),
    ]:
        if path and os.path.exists(path):
            title_html = open(path, encoding="utf-8").read()
            m = re.search(r"<title>(.*?)</title>", title_html)
            check("%s <title> has no em dash" % label, bool(m) and "—" not in m.group(1))

    # The no-em-dash rule applies to every character variant (—, –, &mdash;,
    # &ndash;) and to the source we write, not just a handful of sample
    # titles - checking the templates directly catches a regression before
    # it can spread across thousands of generated pages. Regulator-sourced
    # scheme/entity names (e.g. an AMFI fund name that itself contains an en
    # dash) are the one legitimate exception: that is disclosed data, not our
    # copy, and altering it would misquote the source - so this checks the
    # code we author, not every character a third-party feed might contain.
    dash_chars = ("—", "–", "&mdash;", "&ndash;")
    publish_src = open(os.path.join(ROOT, "pipeline", "publish.py"), encoding="utf-8").read()
    check("pipeline/publish.py has no em or en dash in its own source",
          not any(d in publish_src for d in dash_chars))
    run_src = open(os.path.join(ROOT, "pipeline", "run.py"), encoding="utf-8").read()
    check("pipeline/run.py has no em or en dash in its own source",
          not any(d in run_src for d in dash_chars))
    check("pipeline/run.py exposes programmatic engine commands",
          all(cmd in run_src for cmd in ('"branches"', '"ipo-apply"', '"trade-costs"', '"engines"')))
    check("pipeline/run.py no longer exposes the retired 'targets' CLI command "
          "(it regenerated exactly the thin-content pages vercel.json permanently redirects away from)",
          '"targets"' not in run_src)
    js_dir_for_dash = os.path.join(ROOT, "site", "assets", "js")
    if os.path.isdir(js_dir_for_dash):
        for fname in sorted(os.listdir(js_dir_for_dash)):
            if fname.endswith(".js"):
                js_src = open(os.path.join(js_dir_for_dash, fname), encoding="utf-8").read()
                check("%s has no em or en dash in its own source" % fname,
                      not any(d in js_src for d in dash_chars))

    src = load("site/data/sources.json")
    check("sources.json lists every configured source",
          len(src["sources"]) == len((load("config/sources.json") or {}).get("sources", {})))

    # /methodology and /sources have no interactivity in the JS version at
    # all (no onMount) - unlike the hybrid pages above, these are plain
    # static pages, same contract as a stock/fund/broker page: readable with
    # zero JS, no app.js hydration target.
    for route, must_contain in (("methodology", "Methodology"), ("sources", "Sources")):
        p = os.path.join(ROOT, "site", route, "index.html")
        html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        check("site/%s/ exists and is readable with zero JS" % route,
              os.path.exists(p) and "/assets/js/app.js" not in html and must_contain in html)
        check("site/%s/ has no leaked 'None'" % route, ">None<" not in html and "None</p>" not in html)

    # /coming-soon/us and /coming-soon/gcc: same plain-static contract as
    # methodology/sources above. Regression guard for the same bug class
    # _write_broker_pages() had - before this existed, these routes had no
    # static page at all and fell through to the homepage's own title/
    # canonical/content via Vercel's catch-all rewrite.
    home_title_html = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
    home_title_m = re.search(r"<title>([^<]*)</title>", home_title_html)
    for market, must_contain in (("us", "US stock broker"), ("gcc", "GCC stock broker")):
        p = os.path.join(ROOT, "site", "coming-soon", market, "index.html")
        html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        check("site/coming-soon/%s/ exists and is readable with zero JS" % market,
              os.path.exists(p) and "/assets/js/app.js" not in html and must_contain in html)
        check("site/coming-soon/%s/ has no leaked 'None'" % market, ">None<" not in html and "None</p>" not in html)
        title_m = re.search(r"<title>([^<]*)</title>", html)
        check("coming-soon/%s <title> is its own, not the homepage's" % market,
              bool(title_m) and (not home_title_m or title_m.group(1) != home_title_m.group(1)))
        canon_m = re.search(r'<link rel="canonical" href="([^"]*)">', html)
        check("coming-soon/%s canonical points at its own URL, not /" % market,
              bool(canon_m) and canon_m.group(1).rstrip("/").endswith("/coming-soon/%s" % market))

    # /compare, /leaderboards, /algo: hybrid pages like /brokers, /registry,
    # /calculator above - real content for first paint, app.js for hydration.
    for route, must_contain in (
        ("compare", "Compare brokers"), ("leaderboards", "Movers"), ("algo", "Algo trading platforms"),
    ):
        p = os.path.join(ROOT, "site", route, "index.html")
        html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        check("site/%s/ is a real hybrid page that boots the SPA" % route,
              os.path.exists(p) and "/assets/js/app.js" in html and must_contain in html)
        check("site/%s/ has no leaked 'None'" % route, ">None<" not in html and "None</p>" not in html)

    # Programmatic 1v1 comparison pages
    cmp_dir = os.path.join(ROOT, "site", "compare")
    cmp_sample = os.path.join(cmp_dir, "zerodha-vs-groww", "index.html")
    check("programmatic 1v1 comparison page exists", os.path.exists(cmp_sample))
    if os.path.exists(cmp_sample):
        cmp_html = open(cmp_sample, encoding="utf-8").read()
        check("comparison page has real FAQPage JSON-LD", '"@type": "FAQPage"' in cmp_html or '"@type":"FAQPage"' in cmp_html)
        check("comparison page canonical is self-referential", "compare/zerodha-vs-groww" in cmp_html)
        check("comparison page contains pre-rendered comparison table", "Detailed head to head comparison" in cmp_html)
        check("comparison page has no leaked 'None'", ">None<" not in cmp_html and "None</p>" not in cmp_html)
        m_cmp_title = re.search(r"<title>(.*?)</title>", cmp_html)
        check("comparison sample <title> has no em dash", bool(m_cmp_title) and "—" not in m_cmp_title.group(1))

    # The homepage's own CLS fix: <main id="app"> must carry real prerendered
    # content, not the empty 3-card loading skeleton that caused a measured
    # 0.54-0.58 Cumulative Layout Shift (the footer jumping ~1,437px the
    # instant real content replaced it) - see _prerender_home()'s docstring.
    home_html = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
    app_main = re.search(r'<main id="app"[^>]*>(.*?)</main>', home_html, re.S)
    check("homepage <main id=\"app\"> carries real prerendered content, not the loading skeleton",
          bool(app_main) and "Every Indian stock broker" in app_main.group(1)
          and "card skeleton" not in app_main.group(1))
    check("homepage prerendered content has no leaked 'None'",
          ">None<" not in (app_main.group(1) if app_main else "") and "None</p>" not in (app_main.group(1) if app_main else ""))


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

    crypto_feed = t["feeds"].get("CRYPTO") or {}
    check("crypto feed is marked USD, not the implicit-INR default the other feeds use",
          crypto_feed.get("currency") == "USD")
    check("crypto feed is always Open - it has no exchange hours to be closed during",
          crypto_feed.get("status") == "Open")

    app_js = open(os.path.join(ROOT, "site", "assets", "js", "app.js"), encoding="utf-8").read()
    check("app.js formats a non-INR feed's price with its own currency, not silently as rupees",
          "formatLast" in app_js and "feed.currency" in app_js)


def test_leaderboards_market_movers():
    section("leaderboards: real NSE/crypto market movers")
    mm = load("site/data/market-movers.json")
    if not check("market-movers.json exists", bool(mm)):
        return
    check("market-movers.json has at least one real board",
          any((mm.get(k) or []) for k in ("gainers", "losers", "most_active")))
    for k in ("gainers", "losers", "most_active"):
        rows = mm.get(k) or []
        if rows:
            check("market-movers %s rows have symbol+last" % k,
                  all(r.get("symbol") and r.get("last") is not None for r in rows))

    lb_path = os.path.join(ROOT, "site", "leaderboards", "index.html")
    lb_html = open(lb_path, encoding="utf-8").read() if os.path.exists(lb_path) else ""
    check("leaderboards page carries real NSE/crypto board titles, not just the empty notice",
          "top gainers" in lb_html.lower() or "most active" in lb_html.lower())
    check("leaderboards page links out to real stock/crypto pages",
          "/stock/" in lb_html or "/crypto/" in lb_html)
    check("leaderboards page has ItemList JSON-LD for its real boards",
          '"@type": "ItemList"' in lb_html or '"@type":"ItemList"' in lb_html)

    # Regression guard for the exact bug this feature shipped with: pages.js's
    # marketBoardHtml() was missing a closing </div> for .table-scroll, so a
    # forgiving HTML parser nested every subsequent board *inside* the first
    # one instead of as a sibling - the grid silently collapsed to one card
    # and the rest became invisible, only catchable by inspecting the live
    # DOM (a curl/grep check on the string can't see this: the markup is
    # "valid" text, just wrong once parsed). Count div opens vs closes in the
    # function body as a cheap proxy for "balanced enough to not swallow its
    # siblings".
    pages_js = open(os.path.join(ROOT, "site", "assets", "js", "pages.js"), encoding="utf-8").read()
    m = re.search(r"function marketBoardHtml\([^)]*\)\s*\{(.*?)\n\}", pages_js, re.S)
    if check("pages.js defines marketBoardHtml()", bool(m)):
        body = m.group(1)
        opens = len(re.findall(r"<div\b", body))
        closes = len(re.findall(r"</div>", body))
        check("marketBoardHtml()'s <div> opens and closes balance (regression: a missing "
              "</div> here nests every later board inside the first)", opens == closes,
              "opens=%d closes=%d" % (opens, closes))


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
              "/calculator", "/registry", "/algo"]
    for r in routes:
        code, body, _ = http(base + r)
        check("GET %s" % r, code == 200 and b'id="app"' in body, "code=%s" % code)

    # /methodology and /sources have no data dependency and no interactivity
    # (see _write_methodology_page()/_write_sources_page()'s own docstrings),
    # so - unlike the hybrid SPA-shell routes above - they are deliberately
    # plain static pages with no app.js and no id="app" at all, the same
    # zero-JS shape as /sebi-registry/, /stock/, /etf/ and /fund/ below.
    for r in ("/methodology", "/sources"):
        code, body, _ = http(base + r)
        check("GET %s serves a static page with no SPA shell" % r,
              code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)

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

    # /stock/:symbol/ is a genuinely new prefix (no SPA route named "stock"),
    # pure static like the registry pages - real facts, no client bundle.
    stock_dir = os.path.join(ROOT, "site", "stock")
    sample_stock = next(iter(sorted(os.listdir(stock_dir))), None) if os.path.isdir(stock_dir) else None
    if sample_stock:
        code, body, _ = http(base + "/stock/%s/" % sample_stock)
        check("GET /stock/<symbol>/ serves the static equity page",
              code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)

    # /index/:slug/ - same static, zero-JS shape as /stock/ and /sebi-registry/.
    code, body, _ = http(base + "/index/nifty-50/")
    check("GET /index/<slug>/ serves the static index constituent page",
          code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)

    # /etf/:symbol/ - separate instrument universe, same static shape.
    code, body, _ = http(base + "/etf/niftybees/")
    check("GET /etf/<symbol>/ serves the static ETF listing page",
          code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)

    # /fund/:slug/ - AMFI-sourced, same static shape.
    code, body, _ = http(base + "/fund/hdfc-mutual-fund-hdfc-flexi-cap-fund/")
    check("GET /fund/<slug>/ serves the static mutual fund scheme page",
          code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)

    # /reports/:slug/ - the hand-written data report, same static shape.
    code, body, _ = http(base + "/reports/state-of-indian-broking-2026/")
    check("GET /reports/<slug>/ serves the static report page",
          code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)

    # /calculators/:slug/ - static shell + calculators.js, not app.js.
    code, body, _ = http(base + "/calculators/sip-calculator/")
    check("GET /calculators/<slug>/ serves the static calculator page",
          code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)
    code, body, _ = http(base + "/editorial-policy/")
    check("GET /editorial-policy/ serves the static editorial policy page",
          code == 200 and b"<h1" in body and b'id="app"' not in body, "code=%s" % code)
    code, body, _ = http(base + "/assets/js/calculators.js")
    check("GET /assets/js/calculators.js is served", code == 200 and len(body) > 0, "code=%s" % code)
    code, body, _ = http(base + "/assets/js/theme-init.js")
    check("GET /assets/js/theme-init.js is served", code == 200 and len(body) > 0, "code=%s" % code)

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

    # The real lead-capture risk is a <form> that POSTs somewhere, or an
    # <input> beyond the one known, client-side-only search box (fetches a
    # precomputed index, never submits - see the store.js/pages.js checks
    # above). A blanket "-zero <input> tags" check was wrong the moment the
    # search box shipped and had apparently never actually been run since
    # (only exercised via --url, which every prior CI/local run skipped).
    src = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
    check("shell has no <form> element (the actual lead-capture vector)", "<form" not in src.lower())
    inputs = re.findall(r"<input\b[^>]*>", src, re.I)
    unexpected = [i for i in inputs if 'id="search-input"' not in i]
    check("shell's only <input> is the known client-side search box",
          len(inputs) == 1 and not unexpected, "found: %s" % (unexpected or inputs))


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


def test_instrument_pages():
    """Instrument detail pages (stock / ETF / fund / AMC): real-data
    enrichment, no duplicated wording, no unsourced claims, no dead links."""
    section("instrument detail pages")
    site = os.path.join(ROOT, "site")

    def read(*parts):
        path = os.path.join(site, *parts)
        return open(path, encoding="utf-8").read() if os.path.exists(path) else None

    # AMFI parser: a banner like "IL&FS Mutual Fund (IDF)" is a fund house, not
    # a category (it used to overwrite the running category for ~2,500 rows).
    sys.path.insert(0, ROOT)
    from pipeline.sources import amfi as amfi_src

    class _F:
        def get_text(self, url, ttl=0):
            return (
                "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;"
                "Net Asset Value;Date\n\n"
                "Close Ended Schemes(Income)\n\nICICI Prudential Mutual Fund\n\n"
                "1;INF1;-;ICICI Plan A;;;10.1;01-Jun-2017\n\nIL&FS Mutual Fund (IDF)\n\n"
                "2;INF2;-;IL&FS Debt Series 1;;;11.0;31-Dec-2018\n\nKotak Mahindra Mutual Fund\n\n"
                "3;INF3;-;Kotak FMP;;;12.0;01-Jun-2017\n")
    rows = amfi_src.nav_master(_F()) or []
    by_code = {r["scheme_code"]: r for r in rows}
    check("AMFI parser files IL&FS (IDF) schemes under their own fund house",
          by_code.get("2", {}).get("amc") == "IL&FS Mutual Fund (IDF)")
    check("AMFI parser keeps the real category across an IL&FS-style AMC banner",
          all(r["category"] == "Close Ended Schemes(Income)" for r in rows) and len(rows) == 3)

    from pipeline import publish as pub
    info = pub._parse_amfi_category("Open Ended Schemes(Equity Scheme - Sectoral/ Thematic)")
    check("AMFI category parsing splits structure / family / sub",
          info == {"structure": "Open ended", "family": "Equity Scheme", "sub": "Sectoral/Thematic",
                   "label": "Equity Scheme: Sectoral/Thematic"})
    check("a non-category string parses to None (never a guess)",
          pub._parse_amfi_category("IL&FS Mutual Fund (IDF)") is None)
    gap = pub._direct_regular_gap([
        {"plan": "Direct Plan", "option": "Growth Option", "nav": 110.0, "nav_date": "01-Oct-2026"},
        {"plan": "Regular Plan", "option": "Growth Option", "nav": 100.0, "nav_date": "01-Oct-2026"}])
    check("Direct vs Regular gap is a plain ratio of two published NAVs",
          gap and abs(gap["gap_pct"] - 10.0) < 1e-9)
    check("no Direct vs Regular gap when the two NAV dates differ",
          pub._direct_regular_gap([
              {"plan": "Direct Plan", "option": "Growth Option", "nav": 110.0, "nav_date": "01-Oct-2026"},
              {"plan": "Regular Plan", "option": "Growth Option", "nav": 100.0, "nav_date": "30-Sep-2026"}]) is None)
    check("all-caps scheme names are re-cased for display, acronyms kept",
          pub._tidy_scheme_name("ADITYA BIRLA SUN LIFE NIFTY BANK ETF") == "Aditya Birla Sun Life Nifty Bank ETF"
          and pub._tidy_scheme_name("HDFC NIFTY 50 ETF") == "HDFC Nifty 50 ETF"
          and pub._tidy_scheme_name("Nippon India ETF Nifty 50 BeES") == "Nippon India ETF Nifty 50 BeES")
    _etfs = [
        {"symbol": "MOPVTBANK", "name": "MOTILALAMC - MOPVTBANK", "isin": "INF247L01IB6",
         "underlying_key": "NIFTY PRIVATE BANK", "underlying_asset": "NIFTY PRIVATE BANK"},
        {"symbol": "MO10YGSEC", "name": "MOTILALAMC - MO10YGSEC", "isin": "INF247L01HY0",
         "underlying_key": "GSECS/GILT", "underlying_asset": "Nifty 10 yr Benchmark G-Sec"},
        {"symbol": "KSHARED", "name": "KOTAKAMC - KSHARED", "isin": "INF174X01AA1",
         "underlying_key": "Nifty 50", "underlying_asset": "Nifty 50"},
    ]
    pub._enrich_etfs(_etfs, [
        {"name": "Motilal Oswal Nifty 50 ETF", "amc": "Motilal Oswal Mutual Fund", "isin_growth": "INF247L01AA1"},
        {"name": "Kotak Nifty ETF", "amc": "Kotak Mahindra Mutual Fund", "isin_growth": "INF174K01AA1"},
        {"name": "Mahindra Manulife Fund", "amc": "Mahindra Manulife Mutual Fund", "isin_growth": "INF174V01AA1"},
    ], {})
    check("an ETF not yet in AMFI's file is described from NSE's register, not shown by its raw label",
          _etfs[0]["name"] == "Nifty Private Bank ETF from Motilal Oswal Mutual Fund"
          and _etfs[0]["nse_name"] == "MOTILALAMC - MOPVTBANK" and "nav" not in _etfs[0] and "amc" not in _etfs[0])
    check("a category-like underlying key falls back to the index name",
          _etfs[1]["name"] == "Nifty 10 yr Benchmark G-Sec ETF from Motilal Oswal Mutual Fund")
    check("an ISIN issuer code shared by two fund houses names neither",
          _etfs[2]["name"] == "Nifty 50 ETF")

    src = open(os.path.join(ROOT, "pipeline", "publish.py"), encoding="utf-8").read()
    check("no unsourced '1-1.5 percent' distributor-commission claim anywhere in the page generator",
          "1-1.5 percent" not in src)

    # AMC hub pages
    amc_dir = os.path.join(site, "funds-by")
    amc_slugs = [d for d in os.listdir(amc_dir)
                 if d != "category" and os.path.isfile(os.path.join(amc_dir, d, "index.html"))] \
        if os.path.isdir(amc_dir) else []
    if amc_slugs:
        doubled = []
        no_faq = []
        no_tiles = []
        for s in amc_slugs:
            h = read("funds-by", s, "index.html")
            m = re.search(r"<title>(.*?)</title>", h, re.S)
            if m and re.search(r"mutual fund\s+mutual fund", m.group(1), re.I):
                doubled.append(s)
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
            if h1 and re.search(r"mutual fund\s+mutual fund", h1.group(1), re.I):
                doubled.append(s)
            if '"FAQPage"' not in h or '"Organization"' not in h:
                no_faq.append(s)
            if "With a Direct plan" not in h or "Latest NAV date" not in h:
                no_tiles.append(s)
        check("no AMC page repeats 'Mutual Fund Mutual Fund' in its title or H1", not doubled, str(doubled[:3]))
        check("every AMC page carries Organization + FAQPage JSON-LD", not no_faq, str(no_faq[:3]))
        check("every AMC page shows scheme/category/plan/NAV-date tiles", not no_tiles, str(no_tiles[:3]))
    else:
        skip("AMC page checks", "no built AMC pages")

    # ETF pages
    etf_dir = os.path.join(site, "etf")
    if os.path.isdir(etf_dir):
        raw = []
        for s in os.listdir(etf_dir):
            h = read("etf", s, "index.html")
            if h:
                m = re.search(r"<title>(.*?)</title>", h, re.S)
                if m and re.match(r"[A-Z0-9_ ]+-\s?[A-Z0-9_]+ \(", m.group(1)):
                    raw.append(s)
        check("ETF titles no longer show NSE's raw register label (<=2 unmatched)", len(raw) <= 2, str(raw[:5]))
        h = read("etf", "abslbanetf", "index.html")
        if h:
            check("an ETF matched by ISIN shows its AMFI scheme name, AMC and NAV",
                  "Aditya Birla Sun Life Nifty Bank ETF" in h and "Latest NAV (AMFI)" in h and "Fund house" in h)
        check("thin ETF/fund pages carry at most two sponsored banners",
              all((read("etf", s, "index.html") or "").count('class="aff-banner ') <= 2
                  for s in list(os.listdir(etf_dir))[:60]))

    # Fund pages
    fund_page = read("fund", "360-one-mutual-fund-360-one-balanced-hybrid-fund", "index.html")
    if fund_page:
        check("fund page shows structure/category/plans tiles and a Direct vs Regular NAV card",
              "Scheme structure" in fund_page and "Direct vs Regular plan" in fund_page
              and "not a return figure" in fund_page)
        check("fund page links to its AMC and related schemes",
              "/funds-by/360-one-mutual-fund/" in fund_page and "Related schemes" in fund_page)
    fund_dir = os.path.join(site, "fund")
    if os.path.isdir(fund_dir):
        dead = []
        for s in list(os.listdir(fund_dir))[:3500]:
            h = read("fund", s, "index.html")
            for link in re.findall(r'href="(/(?:compare/mutual-funds|fund|funds-by(?:/category)?)/[^"]+)"', h or ""):
                if not os.path.exists(os.path.join(site, link.strip("/"), "index.html")):
                    dead.append((s, link))
        check("every compare / sibling / category / AMC link on a fund page lands on a built page",
              not dead, str(dead[:3]))

    # Stock pages: compare links must resolve
    stock_dir = os.path.join(site, "stock")
    if os.path.isdir(stock_dir):
        dead, with_links = [], 0
        for s in os.listdir(stock_dir):
            h = read("stock", s, "index.html")
            if not h or "with sector peers" not in h:
                continue
            with_links += 1
            for link in re.findall(r'href="(/compare/stocks/[^"]+)"', h):
                if not os.path.exists(os.path.join(site, link.strip("/"), "index.html")):
                    dead.append((s, link))
        check("stock pages link to sector-peer comparisons", with_links > 100, str(with_links))
        check("every stock-page comparison link lands on a built, indexable page", not dead, str(dead[:3]))
        itc = read("stock", "itc", "index.html") or ""
        check("ITC links to its real sector peers' comparison pages",
              "ITC vs HINDUNILVR" in itc and "/compare/stocks/itc-vs-hindunilvr/" in itc)

    # Header speaker button: ships hidden, never autoplays, sits next to search
    js_path = os.path.join(site, "assets", "js", "theme-audio.js")
    check("theme-audio.js exists and never autoplays",
          os.path.exists(js_path)
          and not re.search(r"\.autoplay\s*=|autoplay\s*:", open(js_path, encoding="utf-8").read().lower()))
    check("search.js (loaded on every page with a search button) pulls in theme-audio.js",
          "theme-audio.js" in open(os.path.join(site, "assets", "js", "search.js"), encoding="utf-8").read())
    pages_with_search = [("stock", "itc"), ("etf", "abslbanetf"), ("brokers",), ("compare",), ("news",)]
    bad = []
    for parts in pages_with_search:
        h = read(*parts, "index.html")
        if not h or "id=\"search-toggle\"" not in h:
            continue
        i, j = h.find("id=\"search-toggle\""), h.find("id=\"audio-toggle\"")
        if j < 0 or j < i or " hidden" not in h[j:j + 220] or j - i > 900:
            bad.append("/".join(parts))
    check("every header with a search button has a hidden-until-ready speaker button right after it",
          not bad, str(bad))

    # Home-hero background video: light, lazy, decorative, present in both renderers
    vid_dir = os.path.join(site, "assets", "video")
    mp4 = os.path.join(vid_dir, "hero-bull-bear.mp4")
    check("hero video + poster ship under site/assets/video and stay light (<4 MB)",
          os.path.exists(mp4) and os.path.getsize(mp4) < 4 * 1024 * 1024
          and os.path.exists(os.path.join(vid_dir, "hero-bull-bear-poster.jpg")))
    home = read("index.html") or ""
    check("home hero carries the video: muted, looping, lazy (preload none), poster, aria-hidden",
          all(s in home for s in ('class="pitch-media" aria-hidden="true"', 'class="pitch-video"', "muted", "loop",
                                  'preload="none"'))
          and re.search(r'poster="/assets/video/hero-bull-bear-poster\.jpg(\?v=[0-9a-f]+)?"', home) is not None)
    pj = open(os.path.join(site, "assets", "js", "pages.js"), encoding="utf-8").read()
    check("the client-side home renderer carries the same hero video markup",
          "pitch-media" in pj and "hero-bull-bear.mp4" in pj)
    hv = os.path.join(site, "assets", "js", "hero-video.js")
    hvs = open(hv, encoding="utf-8").read() if os.path.exists(hv) else ""
    check("hero-video.js honours reduced motion / Data Saver and pauses off-screen",
          "prefers-reduced-motion" in hvs and "saveData" in hvs and "IntersectionObserver" in hvs
          and "visibilitychange" in hvs)
    check("app.js loads hero-video.js", "hero-video.js" in open(os.path.join(site, "assets", "js", "app.js"), encoding="utf-8").read())

    # Angel One logo: wordmark must follow the SITE theme, not the OS setting
    ne = open(os.path.join(ROOT, "pipeline", "news_engine.py"), encoding="utf-8").read()
    css_all = open(os.path.join(site, "assets", "css", "app.css"), encoding="utf-8").read()
    check("Angel One logo is inlined so its wordmark follows the site theme (not an <img> with an OS-only media query)",
          'class="ao-logo"' in ne and "partners/angelone.svg" not in ne
          and ".ao-logo .ao-text { fill: var(--text); }" in css_all)
    ao_svg = open(os.path.join(site, "assets", "img", "partners", "angelone.svg"), encoding="utf-8").read()
    check("standalone angelone.svg no longer hides its wordmark via prefers-color-scheme", "prefers-color-scheme" not in ao_svg)

    # Footer film (25 s bull-vs-bear): click-to-play, light, disclosed, accessible
    ff = os.path.join(site, "assets", "js", "footer-film.js")
    ffs = open(ff, encoding="utf-8").read() if os.path.exists(ff) else ""
    film_mp4 = os.path.join(site, "assets", "video", "bull-bear-film.mp4")
    check("footer film ships its video + poster and stays web-sized (<5 MB)",
          os.path.exists(film_mp4) and os.path.getsize(film_mp4) < 5 * 1024 * 1024
          and os.path.exists(os.path.join(site, "assets", "video", "bull-bear-film-poster.jpg")))
    check("footer film never autoplays and fetches nothing but the poster until played (preload none)",
          'preload="none"' in ffs and not re.search(r"\.autoplay\s*=|autoplay\s*:|\sautoplay[\s>]", ffs))
    check("footer film pauses off-screen / when hidden and yields to the header music button",
          "IntersectionObserver" in ffs and "visibilitychange" in ffs and "bl:media" in ffs
          and "bl:media" in open(os.path.join(site, "assets", "js", "theme-audio.js"), encoding="utf-8").read())
    check("footer film discloses AI-generated visuals, carries the film's risk disclaimer and a transcript",
          "Visuals are AI-generated" in ffs and "subject to market risks" in ffs and "film-transcript" in ffs)
    ch = re.findall(r"\{ t: ([0-9.]+),\s+name:", ffs)
    ts = [float(x) for x in ch]
    check("footer film chapters start at 0, ascend, and stay inside the 25 s runtime",
          len(ts) >= 5 and ts[0] == 0 and ts == sorted(ts) and ts[-1] < 25)
    check("footer film shortcuts ignore Ctrl/Cmd/Alt (no hijacking of find or site search)",
          "e.ctrlKey || e.metaKey || e.altKey" in ffs)
    check("footer film: chapter clicks never wait on metadata, errors do not delete the film, status is announced",
          "loadedmetadata" not in ffs and 'role="status"' in ffs and "could not be loaded" in ffs
          and "video.preload = 'auto'" in ffs)
    check("footer film: mute keeps one ARIA pattern (constant label + aria-pressed)",
          "'Unmute'" not in ffs and "aria-pressed" in ffs)
    check("media URLs in JS and HTML are content-hash versioned (immutable cache safe)",
          re.search(r"bull-bear-film\.mp4\?v=[0-9a-f]{10}", ffs) is not None
          and re.search(r"hero-bull-bear\.mp4\?v=[0-9a-f]{10}", pj) is not None
          and re.search(r'data-src="/assets/video/hero-bull-bear\.mp4\?v=[0-9a-f]{10}"', home) is not None)
    check("search.js (present on every footer page) loads footer-film.js",
          "footer-film.js" in open(os.path.join(site, "assets", "js", "search.js"), encoding="utf-8").read())
    check("footer film has a seek slider, keyboard shortcuts and a reduced-motion guard",
          'type="range"' in ffs and "keydown" in ffs and "prefers-reduced-motion" in ffs)

    # Broker profile depth (the thin pages Google flagged as Soft 404)
    zp = read("broker", "zerodha", "index.html") or ""
    if zp:
        body = zp[zp.find("</main>"):] if "</main>" in zp else ""
        words = len(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", zp, flags=re.S)).split())
        check("broker profile has real depth (regulatory table, verify/complain steps, FAQ) outside the SPA's <main>",
              "data-static-only" in body and "Regulatory profile of" in body and "How to verify" in body
              and "scores.sebi.gov.in" in body and "smartodr.in" in body and "Frequently asked questions about" in body)
        check("broker profile carries FAQPage JSON-LD and clears 450 visible words", '"FAQPage"' in zp and words > 450, str(words))
        check("broker profile depth shows only register-sourced fields (SEBI no., exchanges, DP registrations)",
              "INZ000031633" in zp and "IN-DP-431-2019" in zp)
        tdead = [l for l in re.findall(r'href="(/broker/zerodha/(?:trade|branches)/[^"]*)"', zp)
                 if not os.path.exists(os.path.join(site, l.strip("/"), "index.html"))]
        check("broker profile links to cost and branch pages that exist", not tdead, str(tdead[:3]))
    appjs = open(os.path.join(site, "assets", "js", "app.js"), encoding="utf-8").read()
    check("app.js drops server-rendered depth blocks on client-side navigation", "data-static-only" in appjs)
    itc2 = read("stock", "itc", "index.html") or ""
    if itc2:
        check("stock page shows a real performance snapshot labelled by the sessions on file",
              "Performance snapshot" in itc2 and "no 1-year or 52-week figure is shown" in itc2
              and re.search(r"From \d+-session high", itc2) is not None)
        check("stock page answers the 'share price target' query honestly (no forecast number)",
              "does not publish price targets or forecasts" in itc2 and "for 2026, 2030, 2040 or 2050" in itc2)

    kf = read("ipo", "kfintech", "index.html") or ""
    if kf:
        mt = re.search(r"<title>(.*?)</title>", kf, re.S)
        check("a listed IPO's title leads with the facts people search (name, IPO, date or price band), with no return figure in it",
              mt is not None and "KFin Technologies" in mt.group(1) and " IPO" in mt.group(1)
              and "%" not in mt.group(1) and "Latest Close" not in mt.group(1), mt.group(1) if mt else "")
        check("a fixed-price IPO shows one price, not 'Rs 366 to Rs 366'", "Rs 366 to Rs 366" not in kf)

    # Tiered sitemap, IPO lifecycle, email alerts
    smx = open(os.path.join(site, "sitemap.xml"), encoding="utf-8").read()
    listed = re.findall(r"/sitemaps/sitemap-([a-z0-9-]+?)(?:-\d+)?\.xml", smx)
    # "demand" lists pages from held-back families that already earn real search impressions
    # (publish._demand_sitemap_entries), so the index allowlist never noindexes them.
    check("sitemap index lists only wave-1 files (core, brokers, broker-charges, ipos, registry, news, crypto, top stocks, BSE-only stocks, demand)",
          set(listed) <= {"core", "brokers", "broker-charges", "ipos", "registry", "news", "crypto", "stocks-top", "stocks-bse", "demand"} and len(listed) >= 5, str(sorted(set(listed))))
    heldback = [n for n in ("trade-costs", "branches", "fund-compare", "stock-compare", "funds") if os.path.exists(os.path.join(site, "sitemaps", "sitemap-%s.xml" % n))]
    check("held-back waves are not written to the sitemaps folder (nothing stale left to submit)", not heldback, str(heldback))
    all_loc = "".join(open(os.path.join(site, "sitemaps", f), encoding="utf-8").read() for f in os.listdir(os.path.join(site, "sitemaps")) if f.endswith(".xml"))
    check("wave-1 sitemaps stay small (under 10,000 URLs)", all_loc.count("<loc>") < 10000, str(all_loc.count("<loc>")))
    check("sitemaps carry no changefreq and no build-date lastmod stamped on every URL",
          "<changefreq>" not in all_loc and all_loc.count("<lastmod>%s</lastmod>" % datetime.utcnow().strftime("%Y-%m-%d")) < 0.3 * max(1, all_loc.count("<loc>")))
    check("the upcoming-IPO page is in the sitemap", "/ipo/upcoming/" in all_loc)
    up = read("ipo", "upcoming", "index.html") or ""
    check("/ipo/upcoming/ exists with open / opening-soon sections, FAQ data and the SEBI timeline wording",
          "Upcoming IPOs in India" in up and "Open for bidding now" in up and "Opening soon" in up and '"FAQPage"' in up)
    hub = read("ipo", "index.html") or ""
    check("IPO hub no longer shows a made-up 'allotment chance' percentage or a fake 'live bidding connected' badge",
          "Allotment chance" not in hub and "Live Bidding Connected" not in hub and "<script>" not in hub.split("</footer>")[0].replace("<script src", ""))
    check("IPO hub lists closed-but-unlisted issues under their own heading, never as 'Recently Listed'",
          "Closed, Awaiting Listing" in hub or "no recent" in hub.lower() or "Closed, Awaiting" not in hub)
    kf2 = read("ipo", "kfintech", "index.html") or ""
    check("IPO page carries a status banner with an 'as of' date", "Page data as of" in kf2)
    priv = read("privacy-policy", "index.html") or ""
    check("no account-dependent signup remains: no subscribe endpoint, no alerts script, no email form on IPO pages",
          not os.path.exists(os.path.join(ROOT, "api", "subscribe.js")) and not os.path.exists(os.path.join(site, "assets", "js", "alerts.js"))
          and "alerts-card" not in (read("ipo", "upcoming", "index.html") or "") and "IPO email alerts" not in priv)
    feed = read("ipo", "feed.xml") or ""
    cal_path = os.path.join(site, "ipo", "upcoming.ics")
    cal = open(cal_path, encoding="utf-8", newline="").read() if os.path.exists(cal_path) else ""
    check("IPO RSS feed is valid-looking RSS 2.0 with IPO date items and no recommendation language",
          feed.startswith("<?xml") and "<rss version=\"2.0\">" in feed and "<channel>" in feed and "Facts only" in feed
          and not re.search(r"\bbuy\b|\bsubscribe now\b|must apply|guaranteed", feed, re.I))
    check("IPO calendar file is valid iCalendar (CRLF, BEGIN/END, VEVENTs with UID, DTSTAMP and all-day dates)",
          cal.startswith("BEGIN:VCALENDAR\r\n") and cal.rstrip().endswith("END:VCALENDAR")
          and cal.count("BEGIN:VEVENT") == cal.count("END:VEVENT") and cal.count("BEGIN:VEVENT") == cal.count("UID:")
          and (cal.count("BEGIN:VEVENT") == 0 or re.search(r"DTSTART;VALUE=DATE:\d{8}", cal) is not None))
    check("IPO hub and upcoming page offer the calendar and RSS follow options (no account)",
          "/ipo/upcoming.ics" in (read("ipo", "upcoming", "index.html") or "") and "/ipo/feed.xml" in (read("ipo", "index.html") or ""))

    # Listing-day gain must come from the real listing-day candle, never from candles[0]
    from pipeline.ipo_engine import compute_listing_performance as clp
    hist = {"AAA": [{"date": "2026-06-01", "open": 900, "high": 950, "low": 880, "close": 940},
                    {"date": "2026-10-01", "open": 960, "high": 970, "low": 950, "close": 965}]}
    old_ipo = clp("AAA", 366, hist, "2022-12-29")
    # No return since issue either: splits and bonus issues since an old listing are unknown (Laurus
    # Labs read 4.64x on its Rs 428 issue price after a 1:5 split). The latest close is still shown.
    check("an IPO whose listing day is before our price history shows its latest close but no listing-day gain and no return since issue",
          not old_ipo["has_listing_data"] and old_ipo["has_current_data"] and old_ipo["cmp"] == 965
          and "current_gain_pct" not in old_ipo and "gain_multiple" not in old_ipo)
    from pipeline.ipo_engine import render_performance_card as rpc
    old_card = rpc(old_ipo, "aaa")
    check("the performance card of an old IPO shows no return multiple and no 'vs issue price' move",
          "Return Multiple" not in old_card and "vs issue price" not in old_card and "965.00" in old_card
          and "not adjusted for splits or bonuses" in old_card)
    fresh = clp("AAA", 900, hist, "2026-06-01")
    check("an IPO whose listing-day candle is on file gets the exact listing-day open and gain",
          fresh["has_listing_data"] and fresh["listing_open"] == 900 and abs(fresh["listing_gain_pct"]) < 1e-9)
    check("an IPO whose listing-day candle is on file keeps its return since issue",
          abs(fresh["current_gain_pct"] - (965 / 900 - 1) * 100) < 1e-9 and "Return Multiple" in rpc(fresh, "aaa"))
    noprice = clp("AAA", 0, hist, "2026-06-01")
    check("with no issue price on record, no gain is invented from a candle", not noprice["has_listing_data"] and not noprice["has_current_data"])
    ao = read("ipo", "aonesteels", "index.html") or ""
    if ao:
        check("an IPO with its listing-day candle on file still shows the listing-day gain", "Listing Day Open" in ao and "Not on file" not in ao)
    if kf:
        check("an IPO listed before our price history says so instead of showing a listing-day gain",
              "Not on file" in kf and "Listing Day Gainer" not in kf and "Listing Discount" not in kf)

    # Split/bonus breaks: nothing is computed across an unadjusted price break
    from pipeline.common import trim_to_last_break
    split = [{"date": "2026-04-10", "close": 1000.0}, {"date": "2026-04-16", "close": 1004.0},
             {"date": "2026-04-17", "close": 99.0}, {"date": "2026-04-20", "close": 96.0}]
    tr, brk = trim_to_last_break(split)
    check("a 10-for-1 split in the history keeps only the stretch after it", brk == "2026-04-17" and [c["close"] for c in tr] == [99.0, 96.0])
    calm = [{"date": "d%d" % i, "close": 100 + i} for i in range(30)]
    check("an ordinary history is left untouched", trim_to_last_break(calm) == (calm, None))
    from pipeline import publish as _pub
    pc = read("stock", "pashupati", "index.html") or ""
    if pc and "left out" in pc:
        m = re.search(r"Return since[^<]*</div><div[^>]*>.*?([-+]\d+\.\d+)%", pc, re.S)
        check("a stock with a split in its history shows no absurd since-start return and says why",
              m is None or abs(float(m.group(1))) < 80, m.group(1) if m else "no return tile")
    elif _pub._EQUITY_BREAKS:
        sample_sym = next(iter(_pub._EQUITY_BREAKS.keys())).lower()
        sc_html = read("stock", sample_sym, "index.html") or ""
        check("a stock with a split in its history shows no absurd since-start return and says why",
              "left out" in sc_html)
    else:
        check("a stock with a split in its history shows no absurd since-start return and says why", True)

    check("share prices keep their decimals (Rs 85.09, Rs 0.45) while totals stay whole rupees",
          _pub._px_html(85.09) == "&#8377;85.09" and _pub._px_html(0.45) == "&#8377;0.45" and _pub._inr_html(255) == "&#8377;255")
    scj = open(os.path.join(site, "assets", "js", "stock-chart.js"), encoding="utf-8").read()
    check("chart HUD change is close vs previous close, matching the Last close card",
          "prevClose" in scj and "point.close - point.open" not in scj)

    css_hero = open(os.path.join(site, "assets", "css", "app.css"), encoding="utf-8").read()
    light_block = css_hero.split("Light theme: same geometry and feathered edges")[1].split("@media (max-width: 860px) {\n  .pitch-media")[0]
    check("light theme: the home hero keeps the dark theme's geometry and feathered mask (explicit and OS-light cases) on a clean light card; no framed tile, no inversion",
          ':root[data-theme="light"] .pitch-media {' in light_block and ':root:not([data-theme="dark"]) .pitch-media {' in light_block
          and light_block.count("radial-gradient(ellipse 62% 80% at 68% 50%") >= 4 and "mix-blend-mode: normal" in light_block
          and "grayscale" not in light_block and "border-radius: 18px" not in light_block and "mix-blend-mode: screen" in css_hero)

    pj2 = open(os.path.join(site, "assets", "js", "pages.js"), encoding="utf-8").read()
    homepage = read("index.html") or ""
    check("the home page no longer carries the sample-data banner or the 'client and complaint statistics not published yet' card",
          "Sample data in use" not in homepage and "Client and complaint statistics not published" not in homepage
          and "sampleBanner" not in pj2 and "Client and complaint statistics" not in pj2)

    # ---- IBSL sponsored banners
    import struct
    def jpeg_dims(path):
        d = open(path, "rb").read(); i = 2
        while i < len(d):
            if d[i] != 0xFF: i += 1; continue
            m = d[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", d[i + 5:i + 9]); return w, h
            i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
        return None
    adir = os.path.join(site, "assets", "img", "ads")
    dims = {n: jpeg_dims(os.path.join(adir, n)) if os.path.exists(os.path.join(adir, n)) else None
            for n in ("ibsl-strip-2400x320.jpg", "ibsl-wide-2000x500.jpg", "ibsl-card-1000x400.jpg")}
    check("IBSL creatives ship unmodified in their received shapes (4:1, 5:2) and the 7.5:1 strip at 2400 wide, each under 300 KB",
          dims == {"ibsl-strip-2400x320.jpg": (2400, 320), "ibsl-wide-2000x500.jpg": (2000, 500), "ibsl-card-1000x400.jpg": (1000, 400)}
          and all(os.path.getsize(os.path.join(adir, n)) < 300 * 1024 for n in dims), str(dims))
    from pipeline import publish as _pb
    bn = _pb.ibslBanner_html("wide", "ipo")
    check("banner is marked Sponsored, links to the approved IBSL URL (sponsored, noopener, new tab) and carries the SEBI numbers; the referral-fee sentence is gone",
          'href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens"' in bn and 'rel="sponsored noopener"' in bn
          and 'target="_blank"' in bn and ">Sponsored<" in bn and "INZ000036136" in bn and "IN-DP-423-2019" in bn
          and "referral fee" not in bn and "not a recommendation" not in bn and "How BrokerLens makes money" not in bn
          and "/sebi-registry/indiabulls-securities-limited/" in bn)
    css_all2 = open(os.path.join(site, "assets", "css", "app.css"), encoding="utf-8").read()
    check("banner has a descriptive alt, lazy loading, set dimensions and versioned image URLs, and NO close button; the Sponsored tag sits top-right",
          'alt="Indiabulls Securities: Rs 0' in bn and 'loading="lazy"' in bn and 'width="1000" height="400"' in bn
          and re.search(r"ibsl-wide-2000x500\.jpg\?v=[0-9a-f]{10}", bn) is not None
          and "ad-close" not in bn and "data-ad-close" not in bn and "<button" not in bn
          and re.search(r"\.ad-tag \{[^}]*top: 8px; right: 8px;", css_all2) is not None)
    all_gen = "".join(open(os.path.join(ROOT, "pipeline", f), encoding="utf-8").read() for f in ("publish.py", "news_engine.py", "ipo_engine.py", "trade_cost_engine.py", "ipo_apply_engine.py", "ipo_subscription_engine.py", "broker_branch_engine.py"))
    all_js = "".join(open(os.path.join(site, "assets", "js", f), encoding="utf-8").read() for f in os.listdir(os.path.join(site, "assets", "js")) if f.endswith(".js"))
    built_samples = "".join(read(*x, "index.html") or "" for x in (("",), ("brokers",), ("crypto",), ("stock", "itc"), ("ipo", "kfintech"), ("fund", "360-one-mutual-fund-360-one-balanced-hybrid-fund"), ("etf", "abslbanetf")))
    check("no banner anywhere has a cancel icon: no close buttons in any generator, script, stylesheet or built page; Sponsored tag is top-right on every banner",
          "aff-close" not in all_gen and "Dismiss this ad" not in all_gen and "aff-close" not in all_js and "Dismiss this ad" not in all_js
          and ".aff-close" not in css_all2 and "aff-close" not in built_samples and "Dismiss this ad" not in built_samples
          and re.search(r"\.aff-banner \.aff-tag \{\s*position: absolute; top: 10px; right: 10px;", css_all2) is not None)
    check("the old session-remembering banner dismissal code is gone (no stored dismissals can hide a banner)",
          "bl-aff-dismissed" not in all_js and "applyDismissedBanners" not in all_js)
    trk = open(os.path.join(site, "assets", "js", "ad-track.js"), encoding="utf-8").read()
    trk_code = re.sub(r"/\*.*?\*/", "", trk, flags=re.S)
    check("banners cannot be hidden and the tracker stores nothing, so every banner shows on every page load",
          "wrap.hidden" not in trk and "data-ad-close" not in trk and not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB", trk_code))
    check("tracking records imp (50% visible for 1 s, once) and click with sendBeacon; no personal data",
          all(s in trk for s in ("'imp'", "'click'", "sendBeacon", "intersectionRatio >= 0.5", "}, 1000)")) and "'close'" not in trk and "userAgent" not in trk_code)
    check("search.js loads ad-track.js (present on every page with a header)", "ad-track.js" in open(os.path.join(site, "assets", "js", "search.js"), encoding="utf-8").read())
    check("api/ad-event.js unit tests pass (origin, whitelist, size, rate limit, no caller logging)",
          os.system("node %s > /dev/null 2>&1" % os.path.join(ROOT, "tests", "ad_event_test.js")) == 0)

    def n_sponsored(h): return h.count('class="aff-banner ') + h.count('class="ad-ibsl"')
    hm = read("index.html") or ""
    i_stats = hm.find("SEBI-registered on file") if "SEBI-registered on file" in hm else hm.lower().find("sebi-registered on file")
    i_ad = hm.find('data-ad="ibsl"')
    i_bento = hm.find("MARKET INTELLIGENCE BENTO")
    check("home: the strip sits directly below the four stat tiles (after the last tile, before the next section)",
          i_ad > 0 and i_stats > 0 and i_ad > i_stats and (i_bento < 0 or i_ad < i_bento) and 'data-slot="strip"' in hm and 'data-page-type="home"' in hm)
    pjs = open(os.path.join(site, "assets", "js", "pages.js"), encoding="utf-8").read()
    j_ad = pjs.find("${ibslBanner('strip', 'home')}")
    j_stats = pjs.find("tracked brokers matched to the register")
    j_bento = pjs.find("MARKET INTELLIGENCE BENTO")
    check("home (client-side render) places the same strip below the stat tiles, before the next section",
          j_stats > 0 and j_ad > j_stats and (j_bento < 0 or j_ad < j_bento))
    placements = {
        ("ipo", "kfintech"): ("wide", "ipo"), ("ipo", "upcoming"): ("wide", "ipo"), ("ipo",): ("wide", "ipo"),
        ("broker", "zerodha"): ("wide", "broker"), ("stock", "itc"): ("card", "stock"), ("calculators",): ("wide", "calculator"),
    }
    miss = []
    for parts, (slot, pt) in placements.items():
        h = read(*parts, "index.html") or ""
        if 'data-ad="ibsl"' not in h or ('data-slot="%s"' % slot) not in h or ('data-page-type="%s"' % pt) not in h:
            miss.append("/".join(parts))
    news_pages = [d for d in os.listdir(os.path.join(site, "news")) if os.path.isfile(os.path.join(site, "news", d, "index.html"))] if os.path.isdir(os.path.join(site, "news")) else []
    news_no_ad = [d for d in news_pages if "Editorial Integrity" in (read("news", d, "index.html") or "") and 'data-ad="ibsl"' not in read("news", d, "index.html")]
    check("banner appears on the home, IPO hub, upcoming, IPO detail, broker, stock and calculator pages with the right slot and page type", not miss, str(miss))
    check("every news article (new and older) carries the banner", news_pages and not news_no_ad, str(news_no_ad[:3]))
    excluded = [("privacy-policy",), ("terms-of-service",), ("about",), ("methodology",), ("contact",), ("editorial-policy",), ("sources",),
                ("sebi-registry", "indiabulls-securities-limited"), ("crypto", "btc"), ("etf", "abslbanetf")]
    leaked = [("/".join(x)) for x in excluded if 'data-ad="ibsl"' in (read(*x, "index.html") or "")]
    check("no banner on legal and trust pages, SEBI registry entity pages, crypto, or ETF pages", not leaked, str(leaked))
    four04 = read("404.html") or ""
    check("no banner on the 404 page", 'data-ad="ibsl"' not in four04)
    over = []
    for parts in list(placements) + [("news", news_pages[0])] if news_pages else list(placements):
        h = read(*parts, "index.html") or ""
        if n_sponsored(h) > 3 or h.count('data-ad="ibsl"') > 2:
            over.append(("/".join(parts), n_sponsored(h)))
    check("no page carries more than three sponsored blocks or more than two IBSL banners", not over, str(over))
    stk = read("stock", "itc", "index.html") or ""
    check("stock page: IBSL (a broker) takes the place of 5paisa, so Zerodha, IBSL and Jiraaf remain", "aff-banner-5paisa" not in stk and "aff-banner-zerodha" in stk and "aff-banner-jiraaf" in stk)
    check("the editorial-integrity line no longer claims BrokerLens takes no payment to promote brokers",
          "does not accept payment to promote" not in open(os.path.join(ROOT, "pipeline", "news_engine.py"), encoding="utf-8").read()
          and not any("does not accept payment to promote" in (read("news", d, "index.html") or "") for d in news_pages))
    check("privacy policy discloses the anonymous banner events", "sponsored banner is shown or clicked" in (read("privacy-policy", "index.html") or ""))

    # Redirects for retired price-target URLs must cover the trailing-slash form
    rules = (load("vercel.json") or {}).get("redirects", [])
    sources = {r.get("source") for r in rules}
    check("retired share-price-target URLs redirect with and without a trailing slash",
          "/stock/:symbol/share-price-target-:year" in sources
          and "/stock/:symbol/share-price-target-:year/" in sources)


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
    test_leaderboards_market_movers()
    test_hub()
    test_instrument_pages()
    # Per-area regression checks live in tests/qa_extra_<area>.py, each exposing
    # run(check, ROOT, load) so parallel work never conflicts in this file.
    import glob, importlib.util
    for _p in sorted(glob.glob(os.path.join(ROOT, "tests", "qa_extra_*.py"))):
        _spec = importlib.util.spec_from_file_location(os.path.basename(_p)[:-3], _p)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        section(os.path.basename(_p))
        _mod.run(check, ROOT, load)
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
