import { describe, it, expect } from "vitest";
import { priceTermsError, resolveFill, type FillTerms } from "./fills";

// A day that opened at 100, traded 95 to 106 and closed at 103.
const bar = { open: 100, high: 106, low: 95, close: 103 };
const order = (o: Partial<FillTerms>): FillTerms => ({
  side: "BUY",
  type: "MARKET",
  limitPrice: null,
  triggerPrice: null,
  beforeOpen: false,
  ...o,
});

describe("market orders", () => {
  it("fill at the open when in before 9:15, otherwise at the close", () => {
    expect(resolveFill(order({ beforeOpen: true }), bar)).toBe(100);
    expect(resolveFill(order({}), bar)).toBe(103);
    expect(resolveFill(order({ side: "SELL", beforeOpen: true }), bar)).toBe(100);
  });
});

describe("limit buys", () => {
  it("take the open when it is at or below the limit, if in before the open", () => {
    expect(resolveFill(order({ type: "LIMIT", limitPrice: 101, beforeOpen: true }), bar)).toBe(100);
  });
  it("fill at the limit when the price traded through it", () => {
    expect(resolveFill(order({ type: "LIMIT", limitPrice: 97, beforeOpen: true }), bar)).toBe(97);
    expect(resolveFill(order({ type: "LIMIT", limitPrice: 97 }), bar)).toBe(97);
  });
  it("do not fill on a mere touch of the day's low", () => {
    expect(resolveFill(order({ type: "LIMIT", limitPrice: 95 }), bar)).toBeNull();
  });
  it("placed mid-session above the whole day's range, fill at the close, never above the limit", () => {
    expect(resolveFill(order({ type: "LIMIT", limitPrice: 110 }), bar)).toBe(103);
  });
  it("placed mid-session inside the range, fill at the limit, not the better open", () => {
    expect(resolveFill(order({ type: "LIMIT", limitPrice: 104 }), bar)).toBe(104);
  });
});

describe("limit sells", () => {
  it("mirror the buy rules", () => {
    expect(resolveFill(order({ side: "SELL", type: "LIMIT", limitPrice: 99, beforeOpen: true }), bar)).toBe(100);
    expect(resolveFill(order({ side: "SELL", type: "LIMIT", limitPrice: 105 }), bar)).toBe(105);
    expect(resolveFill(order({ side: "SELL", type: "LIMIT", limitPrice: 106 }), bar)).toBeNull();
    expect(resolveFill(order({ side: "SELL", type: "LIMIT", limitPrice: 90 }), bar)).toBe(103);
  });
});

describe("stop-loss (SL-M)", () => {
  it("a sell stop fills at the trigger when the low reaches it", () => {
    expect(resolveFill(order({ side: "SELL", type: "SL_M", triggerPrice: 96, beforeOpen: true }), bar)).toBe(96);
  });
  it("a sell stop gapped through fills at the worse open", () => {
    const gapDown = { open: 90, high: 94, low: 88, close: 92 };
    expect(resolveFill(order({ side: "SELL", type: "SL_M", triggerPrice: 96, beforeOpen: true }), gapDown)).toBe(90);
  });
  it("a sell stop the day never reached does not fill", () => {
    expect(resolveFill(order({ side: "SELL", type: "SL_M", triggerPrice: 94 }), bar)).toBeNull();
  });
  it("a buy stop fills at the trigger on a breakout", () => {
    expect(resolveFill(order({ type: "SL_M", triggerPrice: 105 }), bar)).toBe(105);
  });
});

describe("bars with only a close", () => {
  it("treat the close as the whole day", () => {
    expect(resolveFill(order({ beforeOpen: true }), { open: null, high: null, low: null, close: 50 })).toBe(50);
  });
});

describe("price terms", () => {
  it("need a price for limit and stop orders", () => {
    expect(priceTermsError("BUY", "LIMIT", null, null, 100)).toMatch(/limit price/);
    expect(priceTermsError("SELL", "SL_M", null, null, 100)).toMatch(/trigger price/);
  });
  it("keep prices within the band and to two decimals", () => {
    expect(priceTermsError("BUY", "LIMIT", 79, null, 100)).toMatch(/within 20%/);
    expect(priceTermsError("BUY", "LIMIT", 99.555, null, 100)).toMatch(/two decimal/);
    expect(priceTermsError("BUY", "LIMIT", 99.55, null, 100)).toBeNull();
  });
  it("need stop triggers on the right side of the last close", () => {
    expect(priceTermsError("SELL", "SL_M", null, 101, 100)).toMatch(/below the last close/);
    expect(priceTermsError("BUY", "SL_M", null, 99, 100)).toMatch(/above the last close/);
    expect(priceTermsError("SELL", "SL_M", null, 95, 100)).toBeNull();
  });
  it("ask nothing of market orders", () => {
    expect(priceTermsError("BUY", "MARKET", null, null, 100)).toBeNull();
  });
});

describe("intraday exits", async () => {
  const { resolveIntradayExit, misTermsError } = await import("./fills");
  it("square off at the close when neither stop nor target was reached", () => {
    expect(resolveIntradayExit("BUY", 100, 94, 107, bar)).toEqual({ price: 103, reason: "square_off" });
  });
  it("take the target when the high traded through it", () => {
    expect(resolveIntradayExit("BUY", 100, 94, 105, bar)).toEqual({ price: 105, reason: "target" });
  });
  it("assume the stop came first when the day reached both", () => {
    expect(resolveIntradayExit("BUY", 100, 96, 105, bar)).toEqual({ price: 96, reason: "stop" });
  });
  it("exit at the entry, not the better stop, when the entry was already past the stop", () => {
    expect(resolveIntradayExit("BUY", 95, 97, null, bar)).toEqual({ price: 95, reason: "stop" });
  });
  it("mirror the rules for a short sell", () => {
    expect(resolveIntradayExit("SELL", 100, 105, 96, bar)).toEqual({ price: 105, reason: "stop" });
    expect(resolveIntradayExit("SELL", 100, 107, 96, bar)).toEqual({ price: 96, reason: "target" });
    expect(resolveIntradayExit("SELL", 100, null, null, bar)).toEqual({ price: 103, reason: "square_off" });
  });
  const base = { side: "BUY" as const, type: "LIMIT" as const, validity: "DAY" as const, sessionOpen: true, entryRef: 100, stopLoss: null, target: null };
  it("refuse a mid-session intraday market order, which has no price to enter at", () => {
    expect(misTermsError({ ...base, type: "MARKET" })).toMatch(/no live price/);
    expect(misTermsError({ ...base, type: "MARKET", sessionOpen: false })).toBeNull();
  });
  it("keep stops and targets on the right side of the entry", () => {
    expect(misTermsError({ ...base, stopLoss: 101 })).toMatch(/below the entry/);
    expect(misTermsError({ ...base, target: 99 })).toMatch(/above the entry/);
    expect(misTermsError({ ...base, side: "SELL", stopLoss: 99 })).toMatch(/above the entry/);
    expect(misTermsError({ ...base, stopLoss: 97, target: 104 })).toBeNull();
  });
  it("are day orders only", () => {
    expect(misTermsError({ ...base, validity: "GTT" })).toMatch(/day orders/);
  });
});
