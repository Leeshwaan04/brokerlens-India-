import { describe, expect, it } from "vitest";
import { bollinger, ema, rsi, sma, swingZones } from "../src/indicators";
import type { Bar } from "../src/core/types";

// The classic Wilder RSI worked example (StockCharts "RSI" spreadsheet), 14 periods.
const WILDER = [
  44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.1, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.0, 46.03, 46.41, 46.22, 45.64,
  46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13,
];
const WILDER_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42, 39.99, 41.46, 41.87, 45.46, 37.3, 33.08, 37.77];

describe("sma", () => {
  it("is null until the period is filled, then the plain average", () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4]);
  });
  it("handles a series shorter than the period and a bad period", () => {
    expect(sma([1, 2], 5)).toEqual([null, null]);
    expect(sma([1, 2], 0)).toEqual([null, null]);
  });
});

describe("ema", () => {
  it("seeds with the simple average then applies 2/(n+1)", () => {
    const r = ema([10, 11, 12, 13, 14], 3);
    expect(r[1]).toBeNull();
    expect(r[2]).toBeCloseTo(11); // (10+11+12)/3
    expect(r[3]).toBeCloseTo(13 * 0.5 + 11 * 0.5); // k = 0.5
    expect(r[4]).toBeCloseTo(14 * 0.5 + (r[3] as number) * 0.5);
  });
  it("matches a published 10-period EMA", () => {
    // StockCharts moving-average worked example: closes and the 10-day EMA.
    const closes = [22.27, 22.19, 22.08, 22.17, 22.18, 22.13, 22.23, 22.43, 22.24, 22.29, 22.15, 22.39, 22.38, 22.61, 23.36, 24.05, 23.75, 23.83, 23.95, 23.63];
    const r = ema(closes, 10);
    expect(r[9]).toBeCloseTo(22.221, 2);
    expect(r[10]).toBeCloseTo(22.208, 2);
    expect(r[11]).toBeCloseTo(22.241, 2);
    expect(r[18]).toBeCloseTo(23.28, 2);
    expect(r[19]).toBeCloseTo(23.34, 2);
  });
});

describe("rsi (Wilder)", () => {
  it("is exact on a hand-worked first value", () => {
    // First 14 changes: gains sum 3.34, losses sum 1.40, so RS = 3.34 / 1.40 and RSI = 100 - 100 / (1 + RS).
    const exact = 100 - 100 / (1 + 3.34 / 1.4);
    expect((rsi(WILDER, 14)[14] as number)).toBeCloseTo(exact, 6);
    expect(exact).toBeCloseTo(70.4641, 3);
  });
  it("tracks the published worked example (which rounds its intermediate averages) within 0.1", () => {
    const r = rsi(WILDER, 14);
    expect(r.slice(0, 14).every((v) => v === null)).toBe(true);
    const got = r.slice(14) as number[];
    expect(got).toHaveLength(WILDER_RSI.length);
    got.forEach((v, i) => expect(Math.abs(v - WILDER_RSI[i])).toBeLessThan(0.1));
  });
  it("is 100 for a series that only rises, and stays within 0 to 100", () => {
    const up = Array.from({ length: 30 }, (_, i) => 100 + i);
    expect(rsi(up, 14).at(-1)).toBe(100);
    expect((rsi(WILDER, 14).filter((v) => v !== null) as number[]).every((v) => v >= 0 && v <= 100)).toBe(true);
  });
  it("needs more than `period` values", () => {
    expect(rsi([1, 2, 3], 14)).toEqual([null, null, null]);
  });
});

describe("bollinger", () => {
  it("is symmetric about the SMA, collapses to the price on a flat series, and widens with volatility", () => {
    const flat = bollinger(new Array(25).fill(100), 20, 2);
    expect(flat.upper[24]).toBe(100);
    expect(flat.lower[24]).toBe(100);
    const wavy = bollinger(Array.from({ length: 25 }, (_, i) => 100 + (i % 2 ? 5 : -5)), 20, 2);
    const mid = wavy.mid[24] as number;
    expect((wavy.upper[24] as number) - mid).toBeCloseTo(mid - (wavy.lower[24] as number), 9);
    expect((wavy.upper[24] as number) - mid).toBeCloseTo(10, 6); // population sd 5, times 2
  });
});

const bar = (i: number, h: number, l: number, c: number): Bar => ({ t: i * 86400, o: c, h, l, c, v: 1 });

describe("swingZones", () => {
  it("returns the nearest real swing high above and swing low below the last close", () => {
    // A hill at index 5 (high 120) and a valley at index 12 (low 80); last close 100.
    const bars: Bar[] = [];
    for (let i = 0; i < 20; i++) {
      const h = i === 5 ? 120 : 105 - Math.abs(i - 5) * 0.2;
      const l = i === 12 ? 80 : 95 + Math.abs(i - 12) * 0.2;
      bars.push(bar(i, h, l, 100));
    }
    const z = swingZones(bars);
    expect(z.resistance).toBe(120);
    expect(z.support).toBe(80);
  });
  it("returns null, not an invented band, when the price is at its highs with no swing above", () => {
    const bars = Array.from({ length: 20 }, (_, i) => bar(i, 100 + i, 99 + i, 100 + i));
    const z = swingZones(bars);
    expect(z.resistance).toBeNull();
  });
  it("needs a few bars", () => {
    expect(swingZones([bar(0, 1, 1, 1)])).toEqual({ resistance: null, support: null });
  });
});
