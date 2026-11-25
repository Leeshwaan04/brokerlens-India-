// How an order fills against one session's official open, high, low and close.
//
// The app has each day's OHLC, not the path prices took within the day, so
// these rules never assume a favourable order of events:
//
// - An order in before the session opened (placed the evening before, over a
//   weekend, or before 9:15) can fill at the open.
// - An order placed while the session was open is checked against the whole
//   day's range, and gets the worst price its own terms allow.
// - A limit fills only if the price traded through it, not merely touched it.

import { buyLegFor, estimateBuyCost, type DeliveryFees } from "./trade-costs";
import { inr, shortDate } from "./format";

export const ORDER_TYPES = ["MARKET", "LIMIT", "SL_M"] as const;
export type OrderType = (typeof ORDER_TYPES)[number];

export const VALIDITIES = ["DAY", "GTT"] as const;
export type Validity = (typeof VALIDITIES)[number];

export const ORDER_TYPE_LABEL: Record<OrderType, string> = { MARKET: "Market", LIMIT: "Limit", SL_M: "Stop-loss" };
export const VALIDITY_LABEL: Record<Validity, string> = { DAY: "Day", GTT: "GTT (1 year)" };

// A GTT order waits for its price for up to a year, as most brokers allow.
export const GTT_DAYS = 365;
// Limit and trigger prices must sit within this band of the last close. This
// is the simulator's own guard against typos, not an exchange rule.
export const PRICE_BAND_PCT = 0.2;

export interface Bar {
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
}

export interface FillTerms {
  side: "BUY" | "SELL";
  type: OrderType;
  limitPrice: number | null;
  triggerPrice: number | null;
  beforeOpen: boolean;
}

/** The fill price for this session, or null if the order's terms were not met. */
export function resolveFill(o: FillTerms, bar: Bar): number | null {
  const close = bar.close;
  const open = bar.open ?? close;
  const high = Math.max(bar.high ?? close, open, close);
  const low = Math.min(bar.low ?? close, open, close);
  const buy = o.side === "BUY";

  if (o.type === "MARKET") return o.beforeOpen ? open : close;

  if (o.type === "LIMIT") {
    const L = o.limitPrice;
    if (L === null || L <= 0) return null;
    if (o.beforeOpen) {
      if (buy ? open <= L : open >= L) return open;
      if (buy ? low < L : high > L) return L;
      return null;
    }
    // Placed mid-session: if the whole day was on the right side of the limit
    // it was executable whenever it arrived, so take the close; otherwise it
    // fills at the limit once the price traded through it.
    if (buy ? high <= L : low >= L) return close;
    if (buy ? low < L : high > L) return L;
    return null;
  }

  // SL_M: a stop that becomes a market order once the trigger trades.
  const T = o.triggerPrice;
  if (T === null || T <= 0) return null;
  if (o.beforeOpen) {
    // A gap through the trigger fills at the open, which is worse than T.
    if (buy ? open >= T : open <= T) return open;
    if (buy ? high >= T : low <= T) return T;
    return null;
  }
  if (buy ? low >= T : high <= T) return close;
  if (buy ? high >= T : low <= T) return T;
  return null;
}

/** Why the prices on an order are not acceptable, or null if they are. */
export function priceTermsError(
  side: "BUY" | "SELL",
  type: OrderType,
  limitPrice: number | null,
  triggerPrice: number | null,
  lastClose: number,
): string | null {
  const inBand = (p: number) => p >= lastClose * (1 - PRICE_BAND_PCT) && p <= lastClose * (1 + PRICE_BAND_PCT);
  const twoDecimals = (p: number) => Math.abs(Math.round(p * 100) - p * 100) < 1e-6;
  const pct = Math.round(PRICE_BAND_PCT * 100);

  if (type === "LIMIT") {
    if (limitPrice === null || !Number.isFinite(limitPrice) || limitPrice <= 0) return "Enter a limit price.";
    if (!twoDecimals(limitPrice)) return "Prices go to two decimal places at most.";
    if (!inBand(limitPrice)) return `Keep the limit price within ${pct}% of the last close.`;
    return null;
  }
  if (type === "SL_M") {
    if (triggerPrice === null || !Number.isFinite(triggerPrice) || triggerPrice <= 0) return "Enter a trigger price.";
    if (!twoDecimals(triggerPrice)) return "Prices go to two decimal places at most.";
    if (side === "SELL" && triggerPrice >= lastClose) return "A stop-loss sell needs a trigger below the last close.";
    if (side === "BUY" && triggerPrice <= lastClose) return "A stop-loss buy needs a trigger above the last close.";
    if (!inBand(triggerPrice)) return `Keep the trigger price within ${pct}% of the last close.`;
    return null;
  }
  return null;
}

/** The price a pending buy is reserved at: the most it can plausibly pay per share. */
export function reservePrice(type: OrderType, lastClose: number, limitPrice: number | null, triggerPrice: number | null): {
  price: number;
  addBuffer: boolean;
} {
  // A limit never pays more than its limit. Market and stop orders can fill
  // above the last close (or the trigger, on a gap), so they keep headroom.
  if (type === "LIMIT" && limitPrice) return { price: limitPrice, addBuffer: false };
  if (type === "SL_M" && triggerPrice) return { price: Math.max(triggerPrice, lastClose), addBuffer: true };
  return { price: lastClose, addBuffer: true };
}

/** Cash a buy needs reserved: turnover and buy-leg charges at the most it can plausibly pay. */
export function buyReserve(
  type: OrderType,
  lastClose: number,
  limitPrice: number | null,
  triggerPrice: number | null,
  qty: number,
  fees: DeliveryFees,
): number {
  const r = reservePrice(type, lastClose, limitPrice, triggerPrice);
  if (r.addBuffer) return estimateBuyCost(r.price, qty, fees);
  const leg = buyLegFor(r.price, qty, fees);
  return leg.turnover + leg.totalCharges;
}

/** Largest whole quantity whose reserve fits in freeCash (0 if none). */
export function maxBuyQty(
  type: OrderType,
  lastClose: number,
  limitPrice: number | null,
  triggerPrice: number | null,
  freeCash: number,
  fees: DeliveryFees,
): number {
  const unit = reservePrice(type, lastClose, limitPrice, triggerPrice).price;
  if (unit <= 0 || freeCash <= 0) return 0;
  let lo = 0;
  let hi = Math.floor(freeCash / unit) + 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (buyReserve(type, lastClose, limitPrice, triggerPrice, mid, fees) <= freeCash) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

export interface OrderTermsView {
  orderType: OrderType;
  limitPrice: string | null;
  triggerPrice: string | null;
  validity: Validity;
  beforeOpen: boolean;
  targetTradeDate: string;
  expiresOn: string | null;
}

/** "Limit ₹97.50", "Stop-loss ₹95.00" or "Market". */
export function orderTermsLabel(o: Pick<OrderTermsView, "orderType" | "limitPrice" | "triggerPrice">): string {
  if (o.orderType === "LIMIT" && o.limitPrice) return `Limit ${inr(Number(o.limitPrice))}`;
  if (o.orderType === "SL_M" && o.triggerPrice) return `Stop-loss ${inr(Number(o.triggerPrice))}`;
  return "Market";
}

/** When a pending order next gets a chance to fill, in a few words. */
export function nextChanceText(o: OrderTermsView): string {
  const day = shortDate(o.targetTradeDate);
  if (o.orderType === "MARKET") return o.beforeOpen ? `Fills at the ${day} open` : `Fills at the ${day} close`;
  const until = o.validity === "GTT" && o.expiresOn ? `, GTT until ${shortDate(o.expiresOn)}` : ", day order";
  return `Checked against the ${day} session${until}`;
}
