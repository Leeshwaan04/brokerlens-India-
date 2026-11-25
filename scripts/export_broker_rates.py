#!/usr/bin/env python3
"""Exports pipeline.trade_cost_engine.BROKER_RATES to a JSON file for the
Virtual Trading MVP (virtual-trading/), per
/Users/sumitbagewadi/.claude/plans/graceful-painting-neumann.md section 6.

Run from the repo root so `import pipeline.trade_cost_engine` resolves:
    python3 scripts/export_broker_rates.py

Read-only against the pipeline: never writes back to pipeline/ or site/.
The output is committed, so a fee-data change shows up as a reviewable
git diff, not a silent runtime dependency between the two apps.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    # A script invoked as `python3 scripts/export_broker_rates.py` puts only
    # scripts/ on sys.path, not the repo root, so `import pipeline` fails
    # regardless of cwd. Insert the repo root explicitly instead of relying
    # on PYTHONPATH or `-m` invocation.
    sys.path.insert(0, ROOT)

import pipeline.broker_charges_engine as bce
import pipeline.trade_cost_engine as tce

FIELDS = (
    "brand",
    "tagline",
    "delivery_flat",
    "delivery_pct",
    "intraday_flat",
    "intraday_pct",
    "dp_charge",
    "demat_amc",
    "account_open",
    "cta_url",
    "partner_badge",
    # Without this, a broker whose real pricing page confirms a "lower of Rs
    # flat or pct%" cap above CAP_RULE_MAX_PCT (Choice Broking) would be
    # costed as an uncapped percentage in the app, ten times its real
    # brokerage on a Rs 1 lakh order.
    "cap_verified_asof",
)


def main():
    # The same "full fee schedule on file" test brokerlens.in applies before it
    # publishes a broker's charges page; the app ranks brokers by cost only
    # within this set.
    complete = set(bce.eligible_keys())
    out = []
    for broker_id, rates in tce.BROKER_RATES.items():
        entry = {"id": broker_id}
        for field in FIELDS:
            entry[field] = rates.get(field)
        entry["fee_schedule_complete"] = broker_id in complete
        out.append(entry)

    out_path = os.path.join(ROOT, "virtual-trading", "seed", "broker-rates.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Exported {len(out)} brokers from BROKER_RATES to {out_path}")


if __name__ == "__main__":
    main()
