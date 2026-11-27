import { describe, expect, it } from "vitest";
import { adjustForShareActions, type RawBar } from "./adjust";

const bar = (date: string, open: number, close: number, volume = 1000): RawBar => ({
  date, open, high: Math.max(open, close) * 1.01, low: Math.min(open, close) * 0.99, close, volume,
});
const sessions = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"];

describe("adjustForShareActions", () => {
  it("leaves a series with no action untouched", () => {
    const bars = [bar("2024-01-01", 100, 100), bar("2024-01-02", 100, 101), bar("2024-01-03", 101, 99)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([]);
    expect(r.unadjusted).toEqual([]);
    expect(r.bars.map((b) => b.close)).toEqual([100, 101, 99]);
    expect(r.bars[0].volume).toBe(1000);
  });

  it("adjusts a 1:5 split: earlier prices divided by 5, volumes multiplied, no false crash", () => {
    // 1,010 close, then the stock opens near 202 and closes at 205 on the ex-date.
    const bars = [bar("2024-01-01", 1000, 1000), bar("2024-01-02", 1000, 1010), bar("2024-01-03", 202, 205), bar("2024-01-04", 205, 210)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([{ date: "2024-01-03", ratio: "5:1", factor: 5 }]);
    expect(r.bars.map((b) => b.close)).toEqual([200, 202, 205, 210]);
    expect(r.bars.map((b) => b.volume)).toEqual([5000, 5000, 1000, 1000]);
    // day-on-day change across the ex-date is the real move (+1.49%), not -80%
    expect(r.bars[2].close / r.bars[1].close - 1).toBeCloseTo(205 / 202 - 1, 6);
  });

  it("adjusts Reliance's 1:1 bonus of 28 Oct 2024 (real NSE prices)", () => {
    const bars = [bar("2024-01-01", 2687, 2655.7), bar("2024-01-02", 1337, 1334.35)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toMatchObject([{ date: "2024-01-02", factor: 2 }]);
    expect(r.bars[0].close).toBeCloseTo(1327.85, 2); // the exchange's adjusted base price
  });

  it("adjusts Tata Steel's 10:1 split of 28 Jul 2022 (real NSE prices)", () => {
    const bars = [bar("2024-01-01", 951, 959.4), bar("2024-01-02", 98.1, 100.35)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toMatchObject([{ factor: 10 }]);
    expect(r.bars[0].close).toBeCloseTo(95.94, 2);
  });

  it("compounds two actions", () => {
    const bars = [bar("2024-01-01", 1000, 1000), bar("2024-01-02", 500, 500), bar("2024-01-03", 100, 100)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied.map((a) => a.factor)).toEqual([2, 5]);
    expect(r.bars.map((b) => b.close)).toEqual([100, 100, 100]);
    expect(r.bars[0].volume).toBe(10000);
  });

  it("does not report a mid-sized fall across a missing session (it may be days of movement)", () => {
    // 2024-01-02 is a known session but has no bar.
    const bars = [bar("2024-01-01", 100, 100), bar("2024-01-03", 80, 78)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([]);
    expect(r.unadjusted).toEqual([]);
    expect(r.skippedGaps).toEqual(["2024-01-03"]);
  });

  it("still adjusts a clean 50% split across a missing session (a stock that sat out some days)", () => {
    const bars = [bar("2024-01-01", 100, 100), bar("2024-01-03", 49, 50)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toMatchObject([{ factor: 2 }]);
    expect(r.bars[0].close).toBe(50);
  });

  it("reports, never adjusts, a mid-sized fall (a 1:2 bonus looks like a 33% crash)", () => {
    const bars = [bar("2024-01-01", 150, 150), bar("2024-01-02", 100, 100)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([]);
    expect(r.unadjusted).toEqual(["2024-01-02"]);
    expect(r.bars[0].close).toBe(150);
  });

  it("reports a huge fall that is not a clean factor", () => {
    const bars = [bar("2024-01-01", 100, 100), bar("2024-01-02", 33, 31)]; // 3.2x at the open: nearest factor 3 is 7% off, but the close is 3.2x
    const r = adjustForShareActions(bars, sessions);
    // 100/33 = 3.03 matches 3 at the open and the close ratio 3.2 is within 20%: this is accepted as 3:1.
    expect(r.applied).toMatchObject([{ factor: 3 }]);
    const odd = adjustForShareActions([bar("2024-01-01", 100, 100), bar("2024-01-02", 36, 35)], sessions);
    // 100/36 = 2.78 is 7.4% from 3 but 11% from 2.5; the open picks 3 (within 8%), close ratio 2.86 agrees: still a clean fit.
    expect(odd.applied).toHaveLength(1);
    const none = adjustForShareActions([bar("2024-01-01", 100, 100), bar("2024-01-02", 44, 40)], sessions);
    // 100/44 = 2.27 sits between 2 (13.6% off) and 2.5 (9% off): no clean factor, so it is reported.
    expect(none.applied).toEqual([]);
    expect(none.unadjusted).toEqual(["2024-01-02"]);
  });

  it("handles empty and single-bar input", () => {
    expect(adjustForShareActions([], sessions).bars).toEqual([]);
    expect(adjustForShareActions([bar("2024-01-01", 10, 10)], sessions).bars).toHaveLength(1);
  });
});
