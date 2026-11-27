import { describe, expect, it } from "vitest";
import { minuteBarAdapter } from "../src/data/intraday";
import { istMidnight } from "../src/core/time";
import type { Bar } from "../src/core/types";

// Synthetic one-minute bars for two sessions. No real market data is used.
function session(date: string, base: number): Bar[] {
  const out: Bar[] = [];
  const open = istMidnight(date);
  for (let m = 555; m < 930; m++) {
    const p = base + (m - 555) * 0.01;
    out.push({ t: open + m * 60, o: p, h: p + 0.05, l: p - 0.05, c: p + 0.01, v: 10 });
  }
  return out;
}

describe("minuteBarAdapter", () => {
  const minutes = [...session("2026-10-26", 100), ...session("2026-10-27", 104)];
  let loads = 0;
  const adapter = minuteBarAdapter({ symbol: "TEST", loadMinutes: async () => (loads++, minutes) });

  it("offers every intraday timeframe, rolled up from the same minutes", async () => {
    expect(adapter.intraday?.timeframes).toEqual(["1m", "3m", "5m", "15m", "30m", "1H", "4H"]);
    const m1 = await adapter.intraday!.load("1m");
    const h1 = await adapter.intraday!.load("1H");
    expect(m1).toHaveLength(375 * 2);
    expect(h1).toHaveLength(7 * 2); // 09:15 to 15:15 is six full hours plus the 15:15 half hour
    expect(h1.reduce((a, b) => a + b.v, 0)).toBe(10 * 375 * 2);
    expect(loads).toBe(1); // minutes fetched once
  });

  it("builds daily bars from the same minutes", async () => {
    const daily = await adapter.loadDaily();
    expect(daily).toHaveLength(2);
    expect(daily[0].o).toBeCloseTo(100);
    expect(daily[0].v).toBe(3750);
    expect(daily[1].c).toBeCloseTo(104 + 374 * 0.01 + 0.01);
  });
});
