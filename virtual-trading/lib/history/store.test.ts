import { describe, expect, it } from "vitest";
import { toHistoryRows, toPaise } from "./store";

describe("toPaise", () => {
  it("rounds to whole paise without float drift", () => {
    expect(toPaise(1234.56)).toBe(123456);
    expect(toPaise(0.1 + 0.2)).toBe(30);
    expect(toPaise(1.15)).toBe(115); // 1.15 * 100 is 114.99999999999999 in floating point
    expect(toPaise(2899.95)).toBe(289995);
  });
});

describe("toHistoryRows", () => {
  it("stores integers and keeps high and low consistent with open and close", () => {
    const [r] = toHistoryRows("2024-01-02", [{ symbol: "X", open: 100.5, high: 99, low: 101, close: 100, volume: 1500.4, prevClose: 99.5 }]);
    expect(r).toMatchObject({ open: 10050, close: 10000, prevClose: 9950, volume: 1500 });
    expect(r.high).toBeGreaterThanOrEqual(Math.max(r.open, r.close));
    expect(r.low).toBeLessThanOrEqual(Math.min(r.open, r.close));
  });
  it("builds a missing open, high or low from the close and drops unusable rows", () => {
    const rows = toHistoryRows("2024-01-02", [
      { symbol: "A", open: null, high: null, low: null, close: 50, volume: null, prevClose: null },
      { symbol: "B", open: 1, high: 1, low: 1, close: 0, volume: 1, prevClose: 1 },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ open: 5000, high: 5000, low: 5000, close: 5000, prevClose: null, volume: null });
  });
});
