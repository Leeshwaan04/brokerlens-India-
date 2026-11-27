import type { Bar } from "./types";

/** Heikin-Ashi candles. Smooths noise; the open uses the previous HA bar, so the whole series is needed. */
export function heikinAshi(bars: Bar[]): Bar[] {
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const c = (b.o + b.h + b.l + b.c) / 4;
    const prev = out[i - 1];
    const o = prev ? (prev.o + prev.c) / 2 : (b.o + b.c) / 2;
    out.push({ t: b.t, o, h: Math.max(b.h, o, c), l: Math.min(b.l, o, c), c, v: b.v });
  }
  return out;
}

/** Percentage change of each bar's close against the previous close; null for the first bar. */
export function changePct(bars: Bar[]): (number | null)[] {
  return bars.map((b, i) => (i === 0 || bars[i - 1].c === 0 ? null : (b.c / bars[i - 1].c - 1) * 100));
}
