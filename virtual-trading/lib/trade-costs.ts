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
export const STT_INTRADAY_SELL_RATE = 0.00025; // 0.025%, sell leg only
export const STAMP_DUTY_INTRADAY_BUY_RATE = 0.00003; // 0.003%, buy leg only
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

function brokerageForLeg(turnover: number, flat: number, pct: number, capVerified: boolean): number {
  const p = pct || 0;
  const pctCost = turnover * p;
  if (!flat && !p) return 0;
  // Uncapped ad-valorem plan, no flat-fee floor, unless the broker's own
  // current pricing page confirms a genuine whichever-is-lower cap
  // (cap_verified_asof, same exception as pipeline/trade_cost_engine.py).
  if (p > CAP_RULE_MAX_PCT && !capVerified) return pctCost;
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
  capVerified = false,
): LegCharges {
  const turnover = round2(fillPrice * qty);
  const brokerage = brokerageForLeg(turnover, deliveryFlat, deliveryPct, capVerified);
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
  capVerified = false,
): LegCharges {
  const turnover = round2(fillPrice * qty);
  const brokerage = brokerageForLeg(turnover, deliveryFlat, deliveryPct, capVerified);
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

/** The delivery-segment fee fields the leg calculators need, per broker. */
export interface DeliveryFees {
  deliveryFlat: number;
  deliveryPct: number;
  dpCharge: number;
  capVerified: boolean;
}

/** Converts a broker_catalog row (numerics arrive as strings) to DeliveryFees. */
export function deliveryFeesFromRow(row: {
  deliveryFlat: string;
  deliveryPct: string;
  dpCharge: string;
  capVerifiedAsof: string | null;
}): DeliveryFees {
  return {
    deliveryFlat: Number(row.deliveryFlat),
    deliveryPct: Number(row.deliveryPct),
    dpCharge: Number(row.dpCharge),
    capVerified: row.capVerifiedAsof !== null,
  };
}

export function buyLegFor(fillPrice: number, qty: number, fees: DeliveryFees): LegCharges {
  return computeBuyLegCharges(fillPrice, qty, fees.deliveryFlat, fees.deliveryPct, fees.capVerified);
}

export function sellLegFor(fillPrice: number, qty: number, fees: DeliveryFees): LegCharges {
  return computeSellLegCharges(fillPrice, qty, fees.deliveryFlat, fees.deliveryPct, fees.dpCharge, fees.capVerified);
}

/**
 * Charges for buying and later selling the same turnover (one order each
 * way), the same worked example brokerlens.in publishes on every broker's
 * charges page (e.g. 5paisa, Rs 1,00,000 each way: Rs 284.20).
 */
export function roundTripCharges(turnover: number, fees: DeliveryFees): number {
  return round2(buyLegFor(turnover, 1, fees).totalCharges + sellLegFor(turnover, 1, fees).totalCharges);
}

// An order fills at the NEXT official close, not the one shown when it is
// placed, so a buy reserves its estimated cost plus this much headroom for
// the price moving in between. Settlement still re-checks against the real
// balance on the day it fills.
export const PRICE_MOVE_BUFFER_PCT = 0.02;

/** Estimated cash a buy needs: turnover and real buy-leg charges at the last close, plus headroom. */
export function estimateBuyCost(lastClose: number, qty: number, fees: DeliveryFees): number {
  const leg = buyLegFor(lastClose, qty, fees);
  return leg.turnover + leg.totalCharges + leg.turnover * PRICE_MOVE_BUFFER_PCT;
}

/** Largest whole quantity whose estimated buy cost fits in freeCash (0 if none). */
export function maxAffordableQty(lastClose: number, freeCash: number, fees: DeliveryFees): number {
  if (lastClose <= 0 || freeCash <= 0) return 0;
  let lo = 0;
  let hi = Math.floor(freeCash / lastClose) + 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (estimateBuyCost(lastClose, mid, fees) <= freeCash) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** The intraday (MIS) fee fields, per broker. */
export interface IntradayFees {
  intradayFlat: number;
  intradayPct: number;
  capVerified: boolean;
}

export function intradayFeesFromRow(row: { intradayFlat: string; intradayPct: string; capVerifiedAsof: string | null }): IntradayFees {
  return { intradayFlat: Number(row.intradayFlat), intradayPct: Number(row.intradayPct), capVerified: row.capVerifiedAsof !== null };
}

/**
 * Charges for one leg of an intraday (MIS) trade, with the same statutory
 * rates as pipeline/trade_cost_engine.py: STT 0.025% on the sell leg only,
 * stamp duty 0.003% on the buy leg only, no DP charge (nothing reaches the
 * demat account). Each leg is rounded on its own, as each is billed.
 */
export function intradayLegFor(side: "BUY" | "SELL", fillPrice: number, qty: number, fees: IntradayFees): LegCharges {
  const turnover = round2(fillPrice * qty);
  const brokerage = brokerageForLeg(turnover, fees.intradayFlat, fees.intradayPct, fees.capVerified);
  const stt = side === "SELL" ? turnover * STT_INTRADAY_SELL_RATE : 0;
  const exchangeCharges = turnover * NSE_TURNOVER_RATE;
  const sebiCharges = Math.max(turnover * SEBI_TURNOVER_RATE, SEBI_CHARGE_FLOOR);
  const stampDuty = side === "BUY" ? turnover * STAMP_DUTY_INTRADAY_BUY_RATE : 0;
  const gst = (brokerage + exchangeCharges + sebiCharges) * GST_RATE;
  const totalCharges = round2(brokerage + stt + exchangeCharges + sebiCharges + stampDuty + gst);
  return {
    turnover,
    brokerage: round2(brokerage),
    stt: round2(stt),
    exchangeCharges: round2(exchangeCharges),
    sebiCharges: round2(sebiCharges),
    stampDuty: round2(stampDuty),
    gst: round2(gst),
    dpCharge: 0,
    totalCharges,
  };
}

/** Both legs of an intraday trade entered and exited at the same price. */
export function intradayRoundTrip(price: number, qty: number, fees: IntradayFees): number {
  return round2(intradayLegFor("BUY", price, qty, fees).totalCharges + intradayLegFor("SELL", price, qty, fees).totalCharges);
}
