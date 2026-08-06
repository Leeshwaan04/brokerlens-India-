"""Derived metrics.

Everything in here is a pure function of ingested data plus an explicit formula.
No metric is published without (a) the inputs it came from and (b) an as_of
date, because the whole proposition of a comparison site is that the numbers
can be checked.

Editorial rule: we compute *facts and normalised ratios*, never advice. A
"reliability score" is defined and disclosed as arithmetic over SEBI complaint
disclosures - it is not a recommendation to use or avoid a broker.
"""
from __future__ import annotations

import math

# A typical retail month, used to make cost comparable across fee structures.
# Published on /methodology so users can see exactly what is being priced.
COST_BASKET = {
    "delivery_buy_value": 50000,
    "delivery_trades": 4,
    "intraday_turnover": 100000,
    "intraday_trades": 10,
    "fno_lots": 10,
    "fno_premium_turnover": 200000,
    "fno_trades": 10,
}


def pct_change(new, old):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / abs(old) * 100, 2)


def _last(series):
    return series[-1][1] if series else None


def _month_index(month):
    """'YYYY-MM' -> absolute month number, so date maths never counts positions."""
    try:
        y, m = str(month).split("-")[:2]
        return int(y) * 12 + int(m) - 1
    except (ValueError, AttributeError, IndexError):
        return None


def normalise_series(series):
    """Sort ascending by month and drop anything unparseable or duplicated.

    Callers hand us hand-maintained files. Trusting their order was a real
    defect: a newest-first file silently inverted the sign of every growth
    figure on the site.
    """
    seen, clean = {}, []
    for row in series or []:
        if not row or len(row) < 2:
            continue
        idx = _month_index(row[0])
        if idx is None:
            continue
        seen[idx] = [row[0], row[1]]          # last write wins on a duplicate month
    for idx in sorted(seen):
        clean.append(seen[idx])
    return clean


def _at(series, months_back):
    """Value exactly `months_back` calendar months before the latest point.

    Positional indexing (series[-1-n]) was wrong: with a gap in the data it
    silently compared non-adjacent months and published the result as
    "month-on-month". Returns None when that exact month is absent, so a gap
    produces an honest blank rather than a fabricated percentage.
    """
    if not series:
        return None
    target = _month_index(series[-1][0])
    if target is None:
        return None
    target -= months_back
    for month, value in reversed(series):
        idx = _month_index(month)
        if idx == target:
            return value
        if idx is not None and idx < target:
            break
    return None


def _month_at(series, months_back):
    """The 'YYYY-MM' label `months_back` before the latest, if it exists."""
    if not series:
        return None
    target = _month_index(series[-1][0])
    if target is None:
        return None
    target -= months_back
    for month, _ in reversed(series):
        if _month_index(month) == target:
            return month
    return None


def client_metrics(series, market_total_series):
    """series: [[YYYY-MM, count], ...]; order is normalised, not assumed."""
    series = normalise_series(series)
    latest = _last(series)
    out = {
        "active_clients": latest,
        "as_of": series[-1][0] if series else None,
        "mom_pct": pct_change(latest, _at(series, 1)),
        "qoq_pct": pct_change(latest, _at(series, 3)),
        "yoy_pct": pct_change(latest, _at(series, 12)),
        "net_adds_1m": (latest - _at(series, 1)) if latest is not None and _at(series, 1) is not None else None,
        "net_adds_12m": (latest - _at(series, 12)) if latest is not None and _at(series, 12) is not None else None,
        "market_share_pct": None,
        "market_share_change_1y_bps": None,
        "series": series,
    }
    mt = dict(market_total_series or {})
    if latest and series and mt.get(series[-1][0]):
        out["market_share_pct"] = round(latest / mt[series[-1][0]] * 100, 3)
        old_month = _month_at(series, 12)
        old_val = _at(series, 12)
        if old_month and old_val and mt.get(old_month):
            old_share = old_val / mt[old_month] * 100
            out["market_share_change_1y_bps"] = round((out["market_share_pct"] - old_share) * 100, 1)
    return out


def complaint_metrics(monthly, active_clients):
    """monthly: [{month, received, resolved, pending}, ...]; order normalised.

    A rate is only comparable if the window behind it is the same length, so a
    12-month figure is published only when 12 months exist. A broker with three
    months of disclosures previously published a third of the complaints as
    `received_12m` and scored ~4x better than an identical broker with a full
    year, on the metric that dominates the reliability score.
    """
    rows = {}
    for m in monthly or []:
        idx = _month_index(m.get("month"))
        if idx is not None:
            rows[idx] = m
    monthly = [rows[i] for i in sorted(rows)]
    if not monthly:
        return {"available": False}

    # Only count months that actually exist within the trailing 12-month window.
    latest_idx = _month_index(monthly[-1].get("month"))
    window = [m for m in monthly if latest_idx - 11 <= _month_index(m.get("month")) <= latest_idx]
    months_covered = len(window)
    full_year = months_covered >= 12

    received = sum(m.get("received") or 0 for m in window)
    resolved = sum(m.get("resolved") or 0 for m in window)
    pending = window[-1].get("pending") or 0

    # Rates are published only over a complete window; otherwise the field is
    # None and the UI shows a gap rather than a flattering partial number.
    per_10k = None
    if active_clients and full_year:
        per_10k = round(received / active_clients * 10000, 2)

    # Resolved can exceed received when a backlog is cleared. That is a real
    # and good thing, but it is not a ">100% resolution rate": cap the published
    # figure and expose the raw counts so the arithmetic stays checkable.
    resolution_rate = None
    if received:
        resolution_rate = round(min(resolved / received * 100, 100.0), 1)

    # Year-on-year needs two full, comparable windows.
    prev = [m for m in monthly if latest_idx - 23 <= _month_index(m.get("month")) <= latest_idx - 12]
    trend = None
    if full_year and len(prev) >= 12:
        prev_received = sum(m.get("received") or 0 for m in prev)
        trend = pct_change(received, prev_received) if prev_received else None

    return {
        "available": True,
        "as_of": monthly[-1].get("month"),
        "months_covered": months_covered,
        "full_year": full_year,
        "received_12m": received if full_year else None,
        "received_window": received,
        "resolved_12m": resolved if full_year else None,
        "pending_latest": pending,
        "per_10k_clients_12m": per_10k,
        "resolution_rate_pct": resolution_rate,
        "resolved_exceeds_received": bool(received and resolved > received),
        "trend_pct": trend,
        "series": [[m.get("month"), m.get("received") or 0] for m in monthly],
        "pending_series": [[m.get("month"), m.get("pending") or 0] for m in monthly],
    }


def cost_of_basket(charges):
    """Rupee cost of COST_BASKET/month under a broker's published charges.

    Brokerage only, plus AMC amortised monthly. Statutory charges (STT, stamp,
    exchange txn, SEBI turnover fee, GST) are identical across brokers for the
    same trade, so excluding them keeps the comparison about the broker's own
    pricing. Disclosed on /methodology.
    """
    if not charges:
        return None
    b = COST_BASKET
    out = {}

    def leg(plan, turnover, trades):
        """Cost of one leg under the Indian convention.

        Brokers price as "Rs20 or 0.03%, WHICHEVER IS LOWER". This function
        previously took the higher of the two, which overstated Zerodha's
        intraday cost by ~6.7x and, worse, made a flat-Rs20 broker and a
        0.03%-capped-at-Rs20 broker score identically when they differ several
        fold in reality. `pricing` may override the default per plan for the
        rare "whichever is higher" or "flat plus percentage" structures.
        """
        if plan is None:
            return None
        flat = plan.get("flat_per_order")
        pct = plan.get("pct_of_turnover")
        cap = plan.get("cap_per_order")
        mode = plan.get("pricing", "lower")     # lower | higher | sum
        if flat is None and pct is None:
            # A plan expressing only a cap is still priceable: the cap is the
            # per-order charge. Returning None here published "no data" for a
            # broker that does in fact disclose a price.
            if cap is None:
                return None
            return round(cap * trades, 2)

        pct_cost = turnover / max(trades, 1) * pct / 100 if pct is not None else None
        if flat is None:
            per_order = pct_cost
        elif pct_cost is None:
            per_order = float(flat)
        elif mode == "higher":
            per_order = max(pct_cost, flat)
        elif mode == "sum":
            per_order = pct_cost + flat
        else:                                   # the market default
            per_order = min(pct_cost, flat)

        if cap is not None:
            per_order = min(per_order, cap)
        return round(per_order * trades, 2)

    out["delivery"] = leg(charges.get("delivery"), b["delivery_buy_value"], b["delivery_trades"])
    out["intraday"] = leg(charges.get("intraday"), b["intraday_turnover"], b["intraday_trades"])
    out["fno"] = leg(charges.get("fno"), b["fno_premium_turnover"], b["fno_trades"])
    amc = charges.get("demat_amc_annual")
    out["amc_monthly"] = round(amc / 12, 2) if amc is not None else None

    parts = [v for v in (out["delivery"], out["intraday"], out["fno"], out["amc_monthly"]) if v is not None]
    out["monthly_total"] = round(sum(parts), 2) if parts else None
    out["complete"] = all(
        out[k] is not None for k in ("delivery", "intraday", "fno", "amc_monthly")
    )
    out["basket"] = b
    return out


# The full weight schedule. Coverage is measured against this, so a broker with
# only some inputs is reported as lower-confidence rather than silently scored as
# if everything were known. Published on /methodology.
RELIABILITY_WEIGHTS = {
    "complaint_rate": 0.40,
    "resolution": 0.20,
    "regulatory": 0.20,
    "backlog": 0.10,
    "tenure": 0.10,
}

# Named so /methodology can publish them instead of leaving magic numbers in code.
REGULATORY_CIRCULAR_PENALTY = 8     # points deducted per adverse circular
REGULATORY_CIRCULAR_CAP = 40        # ...capped, so one bad year is not terminal
BACKLOG_MONTHS_TO_ZERO = 4.0        # months of pending backlog that scores 0
MIN_RANKABLE_COVERAGE = 0.5         # below this a score exists but does not rank


def _current_year():
    """Tenure must not freeze on 1 Jan 2027, as a hardcoded year did."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).year


def _percentile(value, population, lower_is_better=False):
    vals = sorted(v for v in population if v is not None)
    if not vals or value is None:
        return None
    below = sum(1 for v in vals if v < value)
    p = below / len(vals) * 100
    return round(100 - p if lower_is_better else p, 1)


def reliability_score(broker, peers):
    """0-100 composite over SEBI/exchange disclosures only.

    Weights are published on /methodology. Missing components are dropped and
    the remaining weights renormalised, so a broker is never penalised for a
    dataset we have not ingested yet - it just gets a lower confidence flag.
    """
    comp = broker.get("complaints") or {}
    comps, weights = {}, {}

    per10k = comp.get("per_10k_clients_12m")
    if per10k is not None:
        comps["complaint_rate"] = _percentile(
            per10k, [(p.get("complaints") or {}).get("per_10k_clients_12m") for p in peers],
            lower_is_better=True,
        )
        weights["complaint_rate"] = RELIABILITY_WEIGHTS["complaint_rate"]

    rr = comp.get("resolution_rate_pct")
    if rr is not None:
        comps["resolution"] = min(100.0, rr)
        weights["resolution"] = RELIABILITY_WEIGHTS["resolution"]

    pend = comp.get("pending_latest")
    recv = comp.get("received_12m")
    if pend is not None and recv:
        backlog = pend / (recv / 12.0)  # months of backlog at current inflow
        comps["backlog"] = round(max(0.0, 100 - backlog * (100.0 / BACKLOG_MONTHS_TO_ZERO)), 1)
        weights["backlog"] = RELIABILITY_WEIGHTS["backlog"]

    # The regulatory component is only meaningful when we actually looked. It
    # used to be added unconditionally, which scored ABSENCE OF EVIDENCE as a
    # perfect record: a broker with no data at all came out at 100/100 and
    # topped the reliability leaderboard. It now requires that the regulatory
    # scan ran for this broker (`checked`), so an unexamined broker abstains.
    flags = broker.get("regulatory_flags") or {}
    if flags.get("checked"):
        penalty = 0
        if flags.get("defaulter"):
            penalty += 100
        penalty += min(REGULATORY_CIRCULAR_CAP,
                       REGULATORY_CIRCULAR_PENALTY * len(flags.get("circulars") or []))
        comps["regulatory"] = round(max(0.0, 100 - penalty), 1)
        weights["regulatory"] = RELIABILITY_WEIGHTS["regulatory"]

    founded = (broker.get("profile") or {}).get("founded")
    try:
        founded = int(founded) if founded else None
    except (TypeError, ValueError):
        founded = None                          # never abort a build on one bad field
    if founded:
        years = max(0, _current_year() - founded)
        comps["tenure"] = round(min(100.0, math.log1p(years) / math.log1p(35) * 100), 1)
        weights["tenure"] = RELIABILITY_WEIGHTS["tenure"]

    usable = {k: v for k, v in comps.items() if v is not None}
    if not usable:
        return {"score": None, "components": {}, "confidence": "none",
                "coverage": 0.0, "weights": {}, "rankable": False}
    wsum = sum(weights[k] for k in usable)
    score = sum(usable[k] * weights[k] for k in usable) / wsum

    # Coverage must be measured against the FULL weight schedule, not against the
    # weights that happened to be populated - otherwise it is always 1.0 and every
    # broker claims "high confidence" no matter how little data backs the score.
    coverage = wsum / sum(RELIABILITY_WEIGHTS.values())
    confidence = "high" if coverage >= 0.85 else "medium" if coverage >= 0.5 else "low"
    return {
        "score": round(score, 1),
        "components": usable,
        "weights": {k: weights[k] for k in usable},
        "coverage": round(coverage, 3),
        "confidence": confidence,
        # Ranking a thinly-evidenced score against a well-evidenced one is not a
        # like-for-like comparison, so leaderboards exclude anything below this.
        "rankable": coverage >= MIN_RANKABLE_COVERAGE,
    }


def market_aggregates(brokers, market_total_series):
    """HHI, concentration, and the discount-vs-full-service split."""
    shares = [
        (b["clients"]["market_share_pct"], b)
        for b in brokers
        if (b.get("clients") or {}).get("market_share_pct")
    ]
    shares.sort(reverse=True, key=lambda x: x[0])
    hhi = round(sum(s * s for s, _ in shares), 1) if shares else None

    by_type = {}
    for s, b in shares:
        t = (b.get("profile") or {}).get("type") or "unknown"
        by_type[t] = round(by_type.get(t, 0) + s, 2)

    months = sorted(market_total_series or {})
    total_series = [[m, market_total_series[m]] for m in months]
    latest_total = total_series[-1][1] if total_series else None
    prev_total = total_series[-13][1] if len(total_series) > 12 else None

    return {
        "total_active_clients": latest_total,
        "total_yoy_pct": pct_change(latest_total, prev_total),
        "total_series": total_series,
        "hhi": hhi,
        "concentration": {
            "top1_pct": round(shares[0][0], 2) if shares else None,
            "top3_pct": round(sum(s for s, _ in shares[:3]), 2) if shares else None,
            "top5_pct": round(sum(s for s, _ in shares[:5]), 2) if shares else None,
            "top10_pct": round(sum(s for s, _ in shares[:10]), 2) if shares else None,
        },
        "share_by_type": by_type,
        "broker_count_ranked": len(shares),
    }


def leaderboards(brokers):
    """Factual rankings only. Every board states the metric it sorts on."""

    def board(key, title, getter, reverse=True, need=None, unit="", note=""):
        rows = []
        for b in brokers:
            v = getter(b)
            if v is None:
                continue
            if need and not need(b):
                continue
            rows.append({"id": b["id"], "brand": b["profile"]["brand"], "value": v})
        rows.sort(key=lambda r: r["value"], reverse=reverse)
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        return {"key": key, "title": title, "unit": unit, "note": note, "rows": rows[:25]}

    c = lambda b: b.get("clients") or {}
    k = lambda b: b.get("complaints") or {}
    z = lambda b: b.get("cost") or {}

    return [
        board("most_clients", "Most active clients", lambda b: c(b).get("active_clients"), unit="clients",
              note="NSE active client count, latest available month."),
        board("fastest_growing", "Fastest growing (12 months)", lambda b: c(b).get("yoy_pct"), unit="%",
              note="Year-on-year change in active clients. Small bases move faster."),
        board("net_adds", "Most clients added (12 months)", lambda b: c(b).get("net_adds_12m"), unit="clients"),
        board("share_gainers", "Biggest market-share gainers", lambda b: c(b).get("market_share_change_1y_bps"),
              unit="bps", note="Change in share of the combined client base of the brokers tracked here, in basis points. This is not share of the entire NSE market."),
        board("fewest_complaints", "Fewest complaints per 10,000 clients",
              lambda b: k(b).get("per_10k_clients_12m"), reverse=False, unit="per 10k",
              need=lambda b: k(b).get("full_year"),
              note="SEBI-mandated monthly complaint disclosures over a full 12 months, normalised by client "
                   "base. Brokers with a shorter disclosure history are not ranked."),
        board("best_resolution", "Highest complaint resolution rate",
              lambda b: k(b).get("resolution_rate_pct"), unit="%",
              need=lambda b: k(b).get("full_year"),
              note="Resolved as a share of received over 12 months, capped at 100%."),
        # A partially-disclosed basket used to total to a small number and rank
        # FIRST as "cheapest", so every cost board now requires a complete one.
        board("cheapest_basket", "Lowest monthly cost, standard basket",
              lambda b: z(b).get("monthly_total"), reverse=False, unit="INR/month",
              need=lambda b: (z(b) or {}).get("complete"),
              note="Broker charges only for a fixed basket of trades, and only where every leg is disclosed. "
                   "Statutory charges excluded - they are identical everywhere."),
        board("cheapest_delivery", "Lowest delivery brokerage",
              lambda b: (z(b) or {}).get("delivery"), reverse=False, unit="INR/month",
              need=lambda b: (z(b) or {}).get("delivery") is not None),
        board("cheapest_fno", "Lowest F&O brokerage", lambda b: (z(b) or {}).get("fno"),
              reverse=False, unit="INR/month",
              need=lambda b: (z(b) or {}).get("fno") is not None),
        # Only scores with enough evidence behind them rank: otherwise the least
        # documented broker on the site came first.
        board("reliability", "Highest reliability score",
              lambda b: (b.get("reliability") or {}).get("score"), unit="/100",
              need=lambda b: (b.get("reliability") or {}).get("rankable"),
              note="Composite of complaint rate, resolution, backlog, regulatory flags and tenure. "
                   "Only brokers with at least half the inputs available are ranked. See methodology."),
    ]
