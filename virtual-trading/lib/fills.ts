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

import { buyLegFor, estimateBuyCost, intradayRoundTrip, PRICE_MOVE_BUFFER_PCT, type DeliveryFees, type IntradayFees } from "./trade-costs";
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
export function nextChanceText(o: OrderTermsView & { product?: Product }): string {
  const day = shortDate(o.targetTradeDate);
  if (o.product === "MIS") return `Intraday on ${day}, squared off by the close`;
  if (o.orderType === "MARKET") return o.beforeOpen ? `Fills at the ${day} open` : `Fills at the ${day} close`;
  const until = o.validity === "GTT" && o.expiresOn ? `, GTT until ${shortDate(o.expiresOn)}` : ", day order";
  return `Checked against the ${day} session${until}`;
}

// ---------------------------------------------------------------------------
// Intraday (MIS)
//
// An intraday position opens and closes in the same session. The practice
// market has each session's open, high, low and close, not its ticks, so:
// - an intraday market order must be in before the session opens, and
//   enters at the open (mid-session there is no live price to enter at);
// - limit and stop-loss entries fill by the same rules as delivery orders;
// - an optional stop-loss and target exit the position if the day's range
//   reached them, and when both were reached the stop is assumed to have
//   come first; anything still open is squared off at the session's close.

export const PRODUCTS = ["CNC", "MIS"] as const;
export type Product = (typeof PRODUCTS)[number];
export const PRODUCT_LABEL: Record<Product, string> = { CNC: "Delivery", MIS: "Intraday" };

// Margin blocked for an intraday position: 20% of its value, i.e. up to 5x.
// The simulator's own simplification; each broker sets its own per stock.
export const MIS_MARGIN_PCT = 0.2;

export type ExitReason = "stop" | "target" | "square_off";
export const EXIT_REASON_LABEL: Record<ExitReason, string> = {
  stop: "Stop-loss hit",
  target: "Target hit",
  square_off: "Squared off at close",
};

/** Where an intraday position entered at `entry` was closed in this session. */
export function resolveIntradayExit(
  side: "BUY" | "SELL",
  entry: number,
  stopLoss: number | null,
  target: number | null,
  bar: Bar,
): { price: number; reason: ExitReason } {
  const close = bar.close;
  const open = bar.open ?? close;
  const high = Math.max(bar.high ?? close, open, close);
  const low = Math.min(bar.low ?? close, open, close);
  // Entered beyond its own stop (a gap past it): the stop triggers at once,
  // at about the entry price, never at the better stop price.
  if (stopLoss !== null && (side === "BUY" ? stopLoss >= entry : stopLoss <= entry)) return { price: entry, reason: "stop" };
  if (side === "BUY") {
    if (stopLoss !== null && low <= stopLoss) return { price: stopLoss, reason: "stop" };
    if (target !== null && high > target) return { price: target, reason: "target" };
  } else {
    if (stopLoss !== null && high >= stopLoss) return { price: stopLoss, reason: "stop" };
    if (target !== null && low < target) return { price: target, reason: "target" };
  }
  return { price: close, reason: "square_off" };
}

/** The price an intraday order is most likely to enter at, for margin and checks. */
export function misEntryReference(type: OrderType, lastClose: number, limitPrice: number | null, triggerPrice: number | null): number {
  if (type === "LIMIT" && limitPrice) return limitPrice;
  if (type === "SL_M" && triggerPrice) return triggerPrice;
  return lastClose;
}

/** Why an intraday order's terms are not acceptable, or null. */
export function misTermsError(o: {
  side: "BUY" | "SELL";
  type: OrderType;
  validity: Validity;
  sessionOpen: boolean;
  entryRef: number;
  stopLoss: number | null;
  target: number | null;
}): string | null {
  if (o.validity !== "DAY") return "Intraday orders last one session, so they are day orders.";
  if (o.type === "MARKET" && o.sessionOpen) {
    return "This practice market has no live price mid-session. Place an intraday market order before the session opens (it enters at the open), or use a limit or stop-loss entry.";
  }
  const twoDecimals = (p: number) => Math.abs(Math.round(p * 100) - p * 100) < 1e-6;
  const pct = Math.round(PRICE_BAND_PCT * 100);
  const inBand = (p: number) => p >= o.entryRef * (1 - PRICE_BAND_PCT) && p <= o.entryRef * (1 + PRICE_BAND_PCT);
  for (const [label, p] of [["stop-loss", o.stopLoss], ["target", o.target]] as const) {
    if (p === null) continue;
    if (!Number.isFinite(p) || p <= 0) return `Enter a valid ${label} price, or leave it empty.`;
    if (!twoDecimals(p)) return "Prices go to two decimal places at most.";
    if (!inBand(p)) return `Keep the ${label} within ${pct}% of the entry price.`;
  }
  const long = o.side === "BUY";
  if (o.stopLoss !== null && (long ? o.stopLoss >= o.entryRef : o.stopLoss <= o.entryRef)) {
    return long ? "For a buy, the stop-loss goes below the entry price." : "For a short sell, the stop-loss goes above the entry price.";
  }
  if (o.target !== null && (long ? o.target <= o.entryRef : o.target >= o.entryRef)) {
    return long ? "For a buy, the target goes above the entry price." : "For a short sell, the target goes below the entry price.";
  }
  return null;
}

/** Cash blocked for an intraday order: margin plus round-trip charges, with headroom on market and stop entries. */
export function misReserve(
  type: OrderType,
  lastClose: number,
  limitPrice: number | null,
  triggerPrice: number | null,
  qty: number,
  fees: IntradayFees,
): number {
  const entry = misEntryReference(type, lastClose, limitPrice, triggerPrice);
  const price = type === "LIMIT" ? entry : entry * (1 + PRICE_MOVE_BUFFER_PCT);
  return price * qty * MIS_MARGIN_PCT + intradayRoundTrip(price, qty, fees);
}

export function maxMisQty(
  type: OrderType,
  lastClose: number,
  limitPrice: number | null,
  triggerPrice: number | null,
  freeCash: number,
  fees: IntradayFees,
): number {
  const unit = misEntryReference(type, lastClose, limitPrice, triggerPrice) * MIS_MARGIN_PCT;
  if (unit <= 0 || freeCash <= 0) return 0;
  let lo = 0;
  let hi = Math.floor(freeCash / unit) + 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (misReserve(type, lastClose, limitPrice, triggerPrice, mid, fees) <= freeCash) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}
