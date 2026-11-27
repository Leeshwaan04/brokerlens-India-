import { describe, expect, it } from "vitest";
import { adjustForShareActions, type RawBar } from "./adjust";

const bar = (date: string, close: number, prevClose: number | null, volume = 1000): RawBar => ({
  date, open: close, high: close * 1.01, low: close * 0.99, close, volume, prevClose,
});
const sessions = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"];

describe("adjustForShareActions", () => {
  it("leaves a series with no action untouched", () => {
    const bars = [bar("2024-01-01", 100, null), bar("2024-01-02", 101, 100), bar("2024-01-03", 99, 101)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([]);
    expect(r.bars.map((b) => b.close)).toEqual([100, 101, 99]);
    expect(r.bars[0].volume).toBe(1000);
  });

  it("adjusts a 1:5 split: earlier prices divided by 5, volumes multiplied, no false crash", () => {
    // 1,000 close, then NSE prints the previous close as 200 on the ex-date.
    const bars = [bar("2024-01-01", 1000, null), bar("2024-01-02", 1010, 1000), bar("2024-01-03", 205, 202), bar("2024-01-04", 210, 205)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([{ date: "2024-01-03", ratio: "5:1", factor: 5 }]);
    expect(r.bars.map((b) => b.close)).toEqual([200, 202, 205, 210]);
    expect(r.bars.map((b) => b.volume)).toEqual([5000, 5000, 1000, 1000]);
    // day-on-day change across the ex-date is the real move (+1.49%), not -80%
    expect(r.bars[2].close / r.bars[1].close - 1).toBeCloseTo(205 / 202 - 1, 6);
  });

  it("adjusts a 1:1 bonus (2:1)", () => {
    const bars = [bar("2024-01-01", 500, null), bar("2024-01-02", 252, 250)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied[0]).toMatchObject({ ratio: "2:1", factor: 2 });
    expect(r.bars[0].close).toBe(250);
  });

  it("compounds two actions", () => {
    const bars = [bar("2024-01-01", 1000, null), bar("2024-01-02", 500, 500), bar("2024-01-03", 100, 100)];
    // 2:1 on the 2nd (prev printed 500 vs stored 1000), then 5:1 on the 3rd (prev printed 100 vs stored 500).
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied.map((a) => a.factor)).toEqual([2, 5]);
    expect(r.bars.map((b) => b.close)).toEqual([100, 100, 100]);
    expect(r.bars[0].volume).toBe(10000);
  });

  it("does not adjust when the previous session is missing from the data (a gap is not a split)", () => {
    // 2024-01-02 is a known session but has no bar, so 01-03's printed previous close is 01-02's, not 01-01's.
    const bars = [bar("2024-01-01", 100, null), bar("2024-01-03", 85, 90)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([]);
    expect(r.skippedGaps).toEqual(["2024-01-03"]);
    expect(r.bars.map((b) => b.close)).toEqual([100, 85]);
  });

  it("reports, never guesses at, a change that is not a share ratio", () => {
    const bars = [bar("2024-01-01", 100, null), bar("2024-01-02", 90, 93.37)];
    const r = adjustForShareActions(bars, sessions);
    expect(r.applied).toEqual([]);
    expect(r.unexplained).toEqual([{ date: "2024-01-02", storedPrevClose: 100, nsePrevClose: 93.37 }]);
    expect(r.bars[0].close).toBe(100);
  });

  it("handles empty and single-bar input", () => {
    expect(adjustForShareActions([], sessions).bars).toEqual([]);
    expect(adjustForShareActions([bar("2024-01-01", 10, null)], sessions).bars).toHaveLength(1);
  });
});
