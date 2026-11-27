import { describe, it, expect } from "vitest";
import { adjustHolding, detectShareAdjustment } from "./corporate-actions";

describe("detectShareAdjustment", () => {
  it("ignores a normal day, where NSE's previous close equals the stored one", () => {
    // Real: RELIANCE closed 1367.00 on 17 Nov 2026; the 18 Nov bhavcopy prints 1367.00.
    expect(detectShareAdjustment(1367, 1367)).toBeNull();
  });

  it("ignores rounding noise in the printed price", () => {
    expect(detectShareAdjustment(1367, 1366.95)).toBeNull();
  });

  it("recognises a 1:5 split", () => {
    expect(detectShareAdjustment(1000, 200)).toEqual({ factor: 5, ratio: "5:1" });
  });

  it("recognises a 1:1 bonus", () => {
    expect(detectShareAdjustment(1367, 683.5)).toEqual({ factor: 2, ratio: "2:1" });
  });

  it("recognises a 3:2 bonus (5 shares for every 2)", () => {
    expect(detectShareAdjustment(500, 200)).toEqual({ factor: 2.5, ratio: "5:2" });
  });

  it("recognises a 6:5 bonus (1:5), the smallest share action it will apply", () => {
    expect(detectShareAdjustment(120, 100)).toEqual({ factor: 1.2, ratio: "6:5" });
  });

  it("does not mistake a weekend special session's close for a share action", () => {
    // Printed previous close is the Saturday session's: 10%, 11% and 12.5% away from Friday's stored close.
    expect(detectShareAdjustment(110, 100)).toBeNull();
    expect(detectShareAdjustment(100, 90)).toBeNull();
    expect(detectShareAdjustment(100, 87.5)).toBeNull();
    expect(detectShareAdjustment(87.5, 100)).toBeNull();
  });

  it("recognises a 10:1 consolidation", () => {
    expect(detectShareAdjustment(12, 120)).toEqual({ factor: 0.1, ratio: "1:10" });
  });

  it("refuses to guess at an adjustment that is not a share ratio", () => {
    // A rights issue nudges the base price by an irregular amount.
    expect(detectShareAdjustment(1000, 961.37)).toBeNull();
  });

  it("returns null when NSE printed no previous close", () => {
    expect(detectShareAdjustment(1000, null)).toBeNull();
  });
});

describe("adjustHolding", () => {
  it("multiplies quantity and keeps total cost basis on a split", () => {
    const next = adjustHolding(50, 1369.09, 5);
    expect(next.qty).toBe(250);
    expect(next.qty * next.avgCost).toBeCloseTo(50 * 1369.09, 6);
  });

  it("drops a fractional entitlement but keeps the cost basis on the whole shares", () => {
    const next = adjustHolding(3, 100, 2.5); // 7.5 shares -> 7
    expect(next.qty).toBe(7);
    expect(next.qty * next.avgCost).toBeCloseTo(300, 6);
  });

  it("removes a holding a consolidation leaves below one share", () => {
    expect(adjustHolding(5, 12, 0.1)).toEqual({ qty: 0, avgCost: 0 });
  });
});
