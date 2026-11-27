import { describe, expect, it } from "vitest";
import { istDate, istMidnight, istMinuteOfDay, mondayOf } from "../src/core/time";
import { resampleDaily, resampleIntraday } from "../src/core/resample";
import { heikinAshi } from "../src/core/transforms";
import { barsFromCandles, barsFromColumns } from "../src/core/series";
import type { Bar } from "../src/core/types";

const day = (date: string, o: number, h: number, l: number, c: number, v = 100): Bar => ({ t: istMidnight(date), o, h, l, c, v });
const minute = (date: string, hh: number, mm: number, p: number, v = 10): Bar => ({
  t: istMidnight(date) + (hh * 60 + mm) * 60, o: p, h: p + 0.5, l: p - 0.5, c: p, v,
});

describe("IST time", () => {
  it("round-trips a date through midnight and back", () => {
    expect(istDate(istMidnight("2026-10-27"))).toBe("2026-10-27");
    expect(istMinuteOfDay(istMidnight("2026-10-27") + 9 * 3600 + 15 * 60)).toBe(555);
  });
  it("keeps a late-evening UTC instant on the right Indian day", () => {
    // 20:00 UTC on the 26th is 01:30 IST on the 27th.
    expect(istDate(Date.UTC(2026, 9, 26, 20, 0) / 1000)).toBe("2026-10-27");
  });
  it("finds the Monday of a week, including month and year boundaries", () => {
    expect(mondayOf("2026-10-27")).toBe("2026-10-26"); // a Tuesday
    expect(mondayOf("2026-10-26")).toBe("2026-10-26");
    expect(mondayOf("2026-11-01")).toBe("2026-10-26"); // a Sunday belongs to the week before
    expect(mondayOf("2027-01-01")).toBe("2026-12-28"); // a Friday, across the year end
  });
});

describe("resampleDaily", () => {
  const week = [
    day("2026-10-26", 100, 105, 99, 104, 10), // Mon
    day("2026-10-27", 104, 110, 103, 108, 20),
    day("2026-10-28", 108, 109, 95, 96, 30),
    day("2026-10-29", 96, 101, 94, 100, 40),
    day("2026-10-30", 100, 102, 98, 101, 50), // Fri
    day("2026-11-02", 101, 103, 100, 102, 60), // next week, next month
  ];
  it("builds weekly OHLCV: first open, highest high, lowest low, last close, summed volume", () => {
    const w = resampleDaily(week, "W");
    expect(w).toHaveLength(2);
    expect(w[0]).toEqual({ t: istMidnight("2026-10-26"), o: 100, h: 110, l: 94, c: 101, v: 150 });
  });
  it("builds monthly bars and splits at the month change", () => {
    const m = resampleDaily(week, "M");
    expect(m.map((b) => b.c)).toEqual([101, 102]);
    expect(m[0].v).toBe(150);
  });
  it("keeps a short week (holiday) as one bar and does not mutate its input", () => {
    const copy = JSON.stringify(week);
    expect(resampleDaily(week.slice(0, 3), "W")).toHaveLength(1);
    expect(JSON.stringify(week)).toBe(copy);
    expect(resampleDaily(week, "D")).toEqual(week);
  });
});

describe("resampleIntraday", () => {
  const d = "2026-10-27";
  // 09:00 pre-open, then every minute 09:15 to 10:29, then 15:29, then 15:30 (after close).
  const minutes: Bar[] = [minute(d, 9, 0, 50)];
  for (let m = 9 * 60 + 15; m <= 10 * 60 + 29; m++) minutes.push(minute(d, Math.floor(m / 60), m % 60, 100 + (m - 555) * 0.1));
  minutes.push(minute(d, 15, 29, 200), minute(d, 15, 30, 999));

  it("drops pre-open and post-close minutes", () => {
    const m1 = resampleIntraday(minutes, "1m");
    expect(m1[0].o).toBeCloseTo(100);
    expect(m1.every((b) => istMinuteOfDay(b.t) >= 555 && istMinuteOfDay(b.t) < 930)).toBe(true);
  });
  it("aligns 15-minute bars to the 09:15 open", () => {
    const m15 = resampleIntraday(minutes, "15m");
    expect(istMinuteOfDay(m15[0].t)).toBe(555);
    expect(istMinuteOfDay(m15[1].t)).toBe(570);
    expect(m15[0].v).toBe(150); // 15 one-minute bars of volume 10
    expect(m15[0].o).toBeCloseTo(100);
    expect(m15[0].c).toBeCloseTo(100 + 14 * 0.1);
  });
  it("aligns 1H bars to 09:15 and 10:15, not to the clock hour", () => {
    const h1 = resampleIntraday(minutes, "1H");
    expect(h1.map((b) => istMinuteOfDay(b.t))).toEqual([555, 615, 929 - 14]); // 09:15, 10:15, 15:15
  });
  it("makes the two 4H bars 09:15 to 13:15 and 13:15 to the close", () => {
    const all: Bar[] = [];
    for (let m = 555; m < 930; m++) all.push(minute(d, Math.floor(m / 60), m % 60, 100));
    const h4 = resampleIntraday(all, "4H");
    expect(h4.map((b) => istMinuteOfDay(b.t))).toEqual([555, 795]);
    expect(h4[0].v).toBe(2400);
    expect(h4[1].v).toBe(1350);
  });
  it("rolls one-minute bars up to daily, weekly and monthly without losing volume", () => {
    const dayBars = resampleIntraday(minutes, "D");
    expect(dayBars).toHaveLength(1);
    expect(dayBars[0].v).toBe(minutes.filter((b) => istMinuteOfDay(b.t) >= 555 && istMinuteOfDay(b.t) < 930).reduce((s, b) => s + b.v, 0));
    expect(resampleIntraday(minutes, "W")).toHaveLength(1);
  });
  it("keeps two days apart", () => {
    const two = [...minutes, minute("2026-10-28", 9, 15, 300)];
    expect(resampleIntraday(two, "30m").filter((b) => istDate(b.t) === "2026-10-28")).toHaveLength(1);
  });
});

describe("heikinAshi", () => {
  it("follows the standard definition", () => {
    const bars = [day("2026-10-26", 10, 12, 9, 11), day("2026-10-27", 11, 13, 10, 12)];
    const ha = heikinAshi(bars);
    expect(ha[0]).toMatchObject({ o: 10.5, c: 10.5 });
    const c1 = (11 + 13 + 10 + 12) / 4;
    expect(ha[1].c).toBeCloseTo(c1);
    expect(ha[1].o).toBeCloseTo((ha[0].o + ha[0].c) / 2);
    expect(ha[1].h).toBeGreaterThanOrEqual(Math.max(ha[1].o, ha[1].c));
    expect(ha[1].l).toBeLessThanOrEqual(Math.min(ha[1].o, ha[1].c));
  });
});

describe("bar builders", () => {
  it("builds bars from the app's columnar history and skips broken rows", () => {
    const bars = barsFromColumns({ d: ["2026-10-26", "2026-10-27"], o: [1, NaN], h: [2, 2], l: [0.5, 0.5], c: [1.5, 1.5], v: [100, null] });
    expect(bars).toHaveLength(1);
    expect(bars[0]).toEqual({ t: istMidnight("2026-10-26"), o: 1, h: 2, l: 0.5, c: 1.5, v: 100 });
  });
  it("builds bars from the main site's candle file", () => {
    const bars = barsFromCandles({ candles: [{ date: "2026-10-26", open: 1, high: 2, low: 0.5, close: 1.5, volume: 7 }, { date: "2026-10-27", open: null, high: 2, low: 1, close: 1, volume: 1 }] });
    expect(bars).toHaveLength(1);
    expect(bars[0].v).toBe(7);
  });
});
