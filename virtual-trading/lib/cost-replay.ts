// Broker Cost Replay: re-prices a user's own filled virtual orders under
// every broker's real, published delivery fee schedule, using the exact same
// per-leg math settlement uses (trade-costs.ts). Same fills, same prices,
// same quantities; only the broker's fee schedule changes. Nothing here is a
// forecast: it is arithmetic on trades that already happened in the
// simulator.

import { buyLegFor, sellLegFor, type DeliveryFees } from "./trade-costs";

export interface ReplayFill {
  side: "BUY" | "SELL";
  fillPrice: number;
  qty: number;
}

export interface ReplayTotals {
  totalCharges: number;
  brokerage: number;
  dpCharges: number;
  // STT, exchange transaction charges, SEBI fee, stamp duty and GST. These
  // are statutory, but GST is levied on brokerage too, so this still moves a
  // little between brokers.
  taxesAndFees: number;
}

export interface ReplayBroker {
  id: string;
  brand: string;
  fees: DeliveryFees;
}

export interface RankedBroker extends ReplayTotals {
  id: string;
  brand: string;
  rank: number;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

export function replayAtBroker(fills: ReplayFill[], fees: DeliveryFees): ReplayTotals {
  let totalCharges = 0;
  let brokerage = 0;
  let dpCharges = 0;
  for (const f of fills) {
    const leg = f.side === "BUY" ? buyLegFor(f.fillPrice, f.qty, fees) : sellLegFor(f.fillPrice, f.qty, fees);
    totalCharges += leg.totalCharges;
    brokerage += leg.brokerage;
    dpCharges += leg.dpCharge;
  }
  return {
    totalCharges: round2(totalCharges),
    brokerage: round2(brokerage),
    dpCharges: round2(dpCharges),
    taxesAndFees: round2(totalCharges - brokerage - dpCharges),
  };
}

/**
 * Ranks brokers by what the given fills would have cost at each, cheapest
 * first. Brokers with the same total share a rank ("1, 2, 2, 2, 5"), so a
 * tie is never presented as an order; within a tie, rows list alphabetically
 * by brand. Partner status plays no part, so the order is purely a function
 * of the published fees.
 */
export function rankBrokersForFills(fills: ReplayFill[], brokers: ReplayBroker[]): RankedBroker[] {
  const rows = brokers.map((b) => ({ id: b.id, brand: b.brand, ...replayAtBroker(fills, b.fees) }));
  rows.sort((a, b) => a.totalCharges - b.totalCharges || a.brand.localeCompare(b.brand));
  return rows.map((r) => ({
    ...r,
    rank: 1 + rows.filter((o) => o.totalCharges < r.totalCharges - 0.005).length,
  }));
}
