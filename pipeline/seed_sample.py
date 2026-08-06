"""Generates clearly-labelled SAMPLE data so the site is demonstrable before
the monthly regulator feeds have run.

Read this carefully: nothing produced here is a fact about any broker.

Every record written carries provenance:"sample". The publisher propagates that
flag, and the frontend renders a persistent amber banner plus a per-metric dot
for anything not sourced from a primary feed. Delete data/manual/*.json and
re-run the real pipeline to replace it.

Why sample data exists at all: two of the three headline datasets - NSE
member-wise active clients, and per-broker Annexure-B complaint disclosures -
have no confirmed machine-readable public endpoint (see docs/DATA_SOURCES.md).
They are real, published, free data; they just need either an India-egress
fetch or a per-broker disclosure crawl. Until then the shape of the product can
still be built and reviewed.
"""
from __future__ import annotations

import hashlib
import os

from .common import MANUAL, log, read_json, write_json, CONFIG

MONTHS = 24
END = (2026, 6)


def _months():
    y, m = END
    out = []
    for i in range(MONTHS):
        mm = m - (MONTHS - 1 - i)
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append("%04d-%02d" % (yy, mm))
    return out


def _rand(seed, i):
    """Deterministic pseudo-random in [0,1) - no Math.random, reproducible builds."""
    h = hashlib.sha256(("%s:%d" % (seed, i)).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def _series(bid, anchor, growth_pa, volatility=0.03):
    months = _months()
    out, val = [], anchor / ((1 + growth_pa) ** (MONTHS / 12.0))
    step = (1 + growth_pa) ** (1 / 12.0)
    for i, m in enumerate(months):
        val *= step * (1 + (_rand(bid, i) - 0.5) * volatility)
        out.append([m, int(round(val / 100.0) * 100)])
    out[-1][1] = anchor
    return out


# Anchor magnitudes only - order-of-magnitude plausible so charts and rankings
# render sensibly. NOT sourced, NOT verified, NOT to be published as fact.
SAMPLE_ANCHORS = {
    "groww": (13_500_000, 0.28), "zerodha": (7_900_000, 0.02), "angel-one": (7_600_000, 0.10),
    "upstox": (2_900_000, 0.06), "icici-direct": (1_950_000, 0.05), "kotak-securities": (1_450_000, 0.12),
    "hdfc-securities": (1_320_000, 0.09), "5paisa": (480_000, -0.06), "dhan": (1_100_000, 0.45),
    "motilal-oswal": (1_050_000, 0.14), "sbi-securities": (860_000, 0.18), "paytm-money": (620_000, -0.10),
    "iifl-securities": (540_000, 0.07), "sharekhan": (760_000, -0.03), "axis-direct": (640_000, 0.04),
    "fyers": (330_000, 0.16), "mstock": (410_000, 0.33), "nuvama": (215_000, 0.08),
    "geojit": (185_000, 0.03), "anand-rathi": (160_000, 0.11), "choice": (240_000, 0.22),
    "alice-blue": (205_000, 0.13), "smc": (145_000, 0.02), "religare": (95_000, -0.02),
    "master-trust": (130_000, 0.09), "samco": (88_000, -0.04), "shoonya": (175_000, 0.19),
    "bajaj-broking": (290_000, 0.38), "nirmal-bang": (72_000, 0.01), "ventura": (64_000, 0.05),
    "bonanza": (58_000, 0.03), "marwadi": (95_000, 0.07), "prabhudas-lilladher": (41_000, 0.02),
    "tradejini": (37_000, 0.06), "goodwill": (52_000, 0.08), "zebu": (29_000, 0.05),
    "trade-smart": (33_000, 0.04), "rupeezy": (46_000, 0.15), "profitmart": (26_000, 0.07),
    "ashika": (31_000, 0.03), "jainam": (44_000, 0.12), "swastika": (39_000, 0.06),
    "arihant": (57_000, 0.05), "indira": (35_000, 0.04), "wisdom-capital": (18_000, -0.05),
    "espresso": (68_000, 0.09), "stoxkart": (22_000, 0.03), "jio-blackrock": (310_000, 1.20),
}

# No sample broker is marked claimed, verified or featured: the site must not
# display monetisation signals (badges, sponsored slots, promoted rows) to end
# users. Every listing stays at the free/unclaimed default.
SAMPLE_CHARGES = {
    "zerodha":   {"delivery": {"flat_per_order": 0}, "intraday": {"flat_per_order": 20, "pct_of_turnover": 0.03, "cap_per_order": 20}, "fno": {"flat_per_order": 20}, "demat_amc_annual": 300, "account_opening": 200},
    "groww":     {"delivery": {"flat_per_order": 20, "pct_of_turnover": 0.1, "cap_per_order": 20}, "intraday": {"flat_per_order": 20, "pct_of_turnover": 0.1, "cap_per_order": 20}, "fno": {"flat_per_order": 20}, "demat_amc_annual": 0, "account_opening": 0},
    "dhan":      {"delivery": {"flat_per_order": 0}, "intraday": {"flat_per_order": 20, "pct_of_turnover": 0.03, "cap_per_order": 20}, "fno": {"flat_per_order": 20}, "demat_amc_annual": 0, "account_opening": 0},
    "angel-one": {"delivery": {"flat_per_order": 20, "pct_of_turnover": 0.1, "cap_per_order": 20}, "intraday": {"flat_per_order": 20, "pct_of_turnover": 0.03, "cap_per_order": 20}, "fno": {"flat_per_order": 20}, "demat_amc_annual": 240, "account_opening": 0},
}


def build():
    master = read_json(os.path.join(CONFIG, "brokers_master.json"), {})
    brokers = master.get("brokers", [])
    months = _months()

    clients = {"provenance": "sample", "unit": "active clients", "months": months,
               "source_note": "SAMPLE DATA - replace with NSE member-wise UCC ingest.", "brokers": {}}
    complaints = {"provenance": "sample", "months": months,
                  "source_note": "SAMPLE DATA - replace with per-broker SEBI Annexure-B disclosures.", "brokers": {}}
    charges = {"provenance": "sample", "as_of": "2026-06",
               "source_note": "SAMPLE pricing for a handful of demo brokers. Others stay null by design.",
               "brokers": {}}
    listings = {"provenance": "sample", "brokers": {}}

    for b in brokers:
        bid = b["id"]
        anchor, growth = SAMPLE_ANCHORS.get(bid, (25_000, 0.04))
        s = _series(bid, anchor, growth)
        clients["brokers"][bid] = s

        rows = []
        for i, (m, cnt) in enumerate(s):
            base = cnt / 10000.0 * (0.6 + _rand(bid + "c", i) * 2.2)
            recv = int(round(base))
            resolved = int(round(recv * (0.80 + _rand(bid + "r", i) * 0.19)))
            rows.append({"month": m, "received": recv, "resolved": resolved,
                         "pending": max(0, recv - resolved)})
        complaints["brokers"][bid] = rows

        if bid in SAMPLE_CHARGES:
            charges["brokers"][bid] = SAMPLE_CHARGES[bid]

    write_json(os.path.join(MANUAL, "active_clients.json"), clients)
    write_json(os.path.join(MANUAL, "complaints.json"), complaints)
    write_json(os.path.join(MANUAL, "charges.json"), charges)
    write_json(os.path.join(MANUAL, "listings.json"), listings)
    log("seeded SAMPLE data for %d brokers across %d months" % (len(brokers), MONTHS), "warn")


if __name__ == "__main__":
    build()
