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


def _at(series, months_back):
    if not series or len(series) <= months_back:
        return None
    return series[-1 - months_back][1]


def client_metrics(series, market_total_series):
    """series: [[YYYY-MM, count], ...] ascending."""
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
        old_month = series[-1 - 12][0] if len(series) > 12 else None
        old_val = _at(series, 12)
        if old_month and old_val and mt.get(old_month):
            old_share = old_val / mt[old_month] * 100
            out["market_share_change_1y_bps"] = round((out["market_share_pct"] - old_share) * 100, 1)
    return out


def complaint_metrics(monthly, active_clients):
    """monthly: [{month, received, resolved, pending}, ...] ascending."""
    if not monthly:
        return {"available": False}
    last12 = monthly[-12:]
    received = sum(m.get("received") or 0 for m in last12)
    resolved = sum(m.get("resolved") or 0 for m in last12)
    pending = last12[-1].get("pending") or 0
    per_10k = None
    if active_clients:
        per_10k = round(received / active_clients * 10000, 2)
    resolution_rate = round(resolved / received * 100, 1) if received else None
    prev12 = monthly[-24:-12]
    prev_received = sum(m.get("received") or 0 for m in prev12) if prev12 else None
    return {
        "available": True,
        "as_of": last12[-1].get("month"),
        "received_12m": received,
        "resolved_12m": resolved,
        "pending_latest": pending,
        "per_10k_clients_12m": per_10k,
        "resolution_rate_pct": resolution_rate,
        "trend_pct": pct_change(received, prev_received) if prev_received else None,
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
        if plan is None:
            return None
        flat = plan.get("flat_per_order")
        pct = plan.get("pct_of_turnover")
        cap = plan.get("cap_per_order")
        if flat is None and pct is None:
            return None
        per_order = 0.0
        if pct is not None:
            per_order += turnover / max(trades, 1) * pct / 100
        if flat is not None:
            per_order = max(per_order, 0) + flat if pct is None else max(per_order, flat)
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
        comps["backlog"] = round(max(0.0, 100 - backlog * 25), 1)
        weights["backlog"] = RELIABILITY_WEIGHTS["backlog"]

    flags = broker.get("regulatory_flags") or {}
    penalty = 0
    if flags.get("defaulter"):
        penalty += 100
    penalty += min(40, 8 * len(flags.get("circulars") or []))
    comps["regulatory"] = round(max(0.0, 100 - penalty), 1)
    weights["regulatory"] = RELIABILITY_WEIGHTS["regulatory"]

    founded = (broker.get("profile") or {}).get("founded")
    if founded:
        years = max(0, 2026 - int(founded))
        comps["tenure"] = round(min(100.0, math.log1p(years) / math.log1p(35) * 100), 1)
        weights["tenure"] = RELIABILITY_WEIGHTS["tenure"]

    usable = {k: v for k, v in comps.items() if v is not None}
    if not usable:
        return {"score": None, "components": {}, "confidence": "none",
                "coverage": 0.0, "weights": {}}
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
              unit="bps", note="Change in share of total NSE active clients, in basis points."),
        board("fewest_complaints", "Fewest complaints per 10,000 clients",
              lambda b: k(b).get("per_10k_clients_12m"), reverse=False, unit="per 10k",
              note="SEBI-mandated monthly complaint disclosures over 12 months, normalised by client base."),
        board("best_resolution", "Highest complaint resolution rate",
              lambda b: k(b).get("resolution_rate_pct"), unit="%"),
        board("cheapest_basket", "Lowest monthly cost, standard basket",
              lambda b: z(b).get("monthly_total"), reverse=False, unit="INR/month",
              note="Broker charges only for a fixed basket of trades. Statutory charges excluded - they are identical everywhere."),
        board("cheapest_delivery", "Lowest delivery brokerage",
              lambda b: (z(b) or {}).get("delivery"), reverse=False, unit="INR/month"),
        board("cheapest_fno", "Lowest F&O brokerage", lambda b: (z(b) or {}).get("fno"),
              reverse=False, unit="INR/month"),
        board("reliability", "Highest reliability score",
              lambda b: (b.get("reliability") or {}).get("score"), unit="/100",
              note="Composite of complaint rate, resolution, backlog, regulatory flags and tenure. See methodology."),
    ]
