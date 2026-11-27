import { istMidnight } from "./time";
import type { Bar } from "./types";

/** Parallel arrays as the paper app's /api/history serves them (dates as YYYY-MM-DD). */
export interface DailyColumns {
  d: string[];
  o: number[];
  h: number[];
  l: number[];
  c: number[];
  v: (number | null)[];
}

export function barsFromColumns(cols: DailyColumns): Bar[] {
  const out: Bar[] = [];
  for (let i = 0; i < cols.d.length; i++) {
    const [o, h, l, c] = [cols.o[i], cols.h[i], cols.l[i], cols.c[i]];
    if (![o, h, l, c].every(Number.isFinite)) continue;
    out.push({ t: istMidnight(cols.d[i]), o, h, l, c, v: cols.v[i] ?? 0 });
  }
  return out;
}

/** The main site's per-stock file: { candles: [{ date, open, high, low, close, volume }] }. */
export interface CandleFile {
  candles: { date: string; open: number | null; high: number | null; low: number | null; close: number | null; volume?: number | null }[];
}

export function barsFromCandles(file: CandleFile): Bar[] {
  const out: Bar[] = [];
  for (const k of file.candles ?? []) {
    if (k.date == null || k.open == null || k.high == null || k.low == null || k.close == null) continue;
    out.push({ t: istMidnight(k.date), o: k.open, h: k.high, l: k.low, c: k.close, v: k.volume ?? 0 });
  }
  return out;
}
