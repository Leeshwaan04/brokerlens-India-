// Per-leg equity delivery charge math.
//
// Ported from (does not call, and must be kept in sync by hand with) the
// statutory rate constants in /Users/sumitbagewadi/Documents/Brokerlens-India
// /pipeline/trade_cost_engine.py. That file's calculate_trade_fees() computes
// a round trip (buy and sell at the SAME price, same day). Here, buy and sell
// legs settle on different calendar days at different real closing prices, so
// each leg is computed independently rather than reused as one round-trip
// total. Verified (see trade-costs.test.ts) that at the same price on both
// legs, the two independent totals sum back to the published round-trip
// figure to within a paisa or two, which is the amount of drift expected from
// rounding each leg separately instead of rounding one combined total.
//
// Equity delivery (CNC-equivalent) only. Intraday is explicitly out of scope
// for this MVP: EOD-only pricing cannot simulate a same-day square-off.

export const NSE_TURNOVER_RATE = 0.0000297; // 0.00297%
export const SEBI_TURNOVER_RATE = 0.000001; // Rs 10 per crore (0.0001%)
export const GST_RATE = 0.18; // 18% on brokerage + exchange charges + SEBI charges
export const STT_DELIVERY_RATE = 0.001; // 0.1%, charged on both the buy and the sell leg
export const STAMP_DUTY_DELIVERY_BUY_RATE = 0.00015; // 0.015%, buy leg only
const SEBI_CHARGE_FLOOR = 0.01;

// A brokerage plan encoded as (flat, pct) is only a genuine "lower of Rs flat
// or pct% of turnover" discount-broker cap when pct is at a discount-broker
// level. Above this threshold it is a full-service/regional percentage-of-
// turnover plan with no such cap. Mirrors CAP_RULE_MAX_PCT in
// pipeline/trade_cost_engine.py exactly, so the two engines can never
// disagree on which brokers get the capped formula.
export const CAP_RULE_MAX_PCT = 0.001;

export interface LegCharges {
  turnover: number;
  brokerage: number;
  stt: number;
  exchangeCharges: number;
  sebiCharges: number;
  stampDuty: number;
  gst: number;
  dpCharge: number;
  totalCharges: number;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

function brokerageForLeg(turnover: number, flat: number, pct: number): number {
  const p = pct || 0;
  const pctCost = turnover * p;
  if (!flat && !p) return 0;
  if (p > CAP_RULE_MAX_PCT) return pctCost; // uncapped ad-valorem plan, no flat-fee floor
  if (!flat) return pctCost;
  return pctCost > 0 ? Math.min(flat, pctCost) : flat;
}

/**
 * Charges for the BUY leg of an equity delivery order. No DP charge: that
 * applies only when shares are sold (see computeSellLegCharges).
 */
export function computeBuyLegCharges(
  fillPrice: number,
  qty: number,
  deliveryFlat: number,
  deliveryPct: number,
): LegCharges {
  const turnover = round2(fillPrice * qty);
  const brokerage = brokerageForLeg(turnover, deliveryFlat, deliveryPct);
  const stt = turnover * STT_DELIVERY_RATE;
  const exchangeCharges = turnover * NSE_TURNOVER_RATE;
  const sebiCharges = Math.max(turnover * SEBI_TURNOVER_RATE, SEBI_CHARGE_FLOOR);
  const stampDuty = turnover * STAMP_DUTY_DELIVERY_BUY_RATE;
  const gst = (brokerage + exchangeCharges + sebiCharges) * GST_RATE;
  const dpCharge = 0;
  const totalCharges = round2(brokerage + stt + exchangeCharges + sebiCharges + stampDuty + gst + dpCharge);
  return {
    turnover,
    brokerage: round2(brokerage),
    stt: round2(stt),
    exchangeCharges: round2(exchangeCharges),
    sebiCharges: round2(sebiCharges),
    stampDuty: round2(stampDuty),
    gst: round2(gst),
    dpCharge,
    totalCharges,
  };
}

/**
 * Charges for the SELL leg of an equity delivery order. No stamp duty: that
 * applies only on the buy leg. dpChargeRate comes from the account's
 * broker_catalog row (already GST-inclusive, matching how it is published on
 * brokerlens.in).
 */
export function computeSellLegCharges(
  fillPrice: number,
  qty: number,
  deliveryFlat: number,
  deliveryPct: number,
  dpChargeRate: number,
): LegCharges {
  const turnover = round2(fillPrice * qty);
  const brokerage = brokerageForLeg(turnover, deliveryFlat, deliveryPct);
  const stt = turnover * STT_DELIVERY_RATE;
  const exchangeCharges = turnover * NSE_TURNOVER_RATE;
  const sebiCharges = Math.max(turnover * SEBI_TURNOVER_RATE, SEBI_CHARGE_FLOOR);
  const stampDuty = 0;
  const gst = (brokerage + exchangeCharges + sebiCharges) * GST_RATE;
  const dpCharge = dpChargeRate;
  const totalCharges = round2(brokerage + stt + exchangeCharges + sebiCharges + stampDuty + gst + dpCharge);
  return {
    turnover,
    brokerage: round2(brokerage),
    stt: round2(stt),
    exchangeCharges: round2(exchangeCharges),
    sebiCharges: round2(sebiCharges),
    stampDuty: round2(stampDuty),
    gst: round2(gst),
    dpCharge: round2(dpCharge),
    totalCharges,
  };
}
