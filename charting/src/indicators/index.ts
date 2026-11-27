// Technical indicators as pure functions over plain number arrays. Each result
// is the same length as its input, with null where the indicator is not yet
// defined (the first period-1 values), so results line up with bars by index.
// Full precision: rounding is for display, not for the maths.
import type { Bar } from "../core/types";

export type Series = (number | null)[];

export function sma(values: number[], period: number): Series {
  const out: Series = new Array(values.length).fill(null);
  if (period < 1 || values.length < period) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

/** Exponential moving average, seeded with the simple average of the first `period` values (the common convention). */
export function ema(values: number[], period: number): Series {
  const out: Series = new Array(values.length).fill(null);
  if (period < 1 || values.length < period) return out;
  const k = 2 / (period + 1);
  let prev = values.slice(0, period).reduce((s, v) => s + v, 0) / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

/** Bollinger Bands: middle = SMA, bands = middle plus or minus `mult` population standard deviations. */
export function bollinger(values: number[], period = 20, mult = 2): { mid: Series; upper: Series; lower: Series } {
  const mid = sma(values, period);
  const upper: Series = new Array(values.length).fill(null);
  const lower: Series = new Array(values.length).fill(null);
  for (let i = period - 1; i < values.length; i++) {
    const m = mid[i] as number;
    let ss = 0;
    for (let j = i - period + 1; j <= i; j++) ss += (values[j] - m) ** 2;
    const sd = Math.sqrt(ss / period);
    upper[i] = m + mult * sd;
    lower[i] = m - mult * sd;
  }
  return { mid, upper, lower };
}

/** Relative Strength Index with Wilder's smoothing. */
export function rsi(values: number[], period = 14): Series {
  const out: Series = new Array(values.length).fill(null);
  if (values.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = values[i] - values[i - 1];
    if (d >= 0) gain += d;
    else loss -= d;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  const toRsi = () => (avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss));
  out[period] = toRsi();
  for (let i = period + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    avgGain = (avgGain * (period - 1) + (d > 0 ? d : 0)) / period;
    avgLoss = (avgLoss * (period - 1) + (d < 0 ? -d : 0)) / period;
    out[i] = toRsi();
  }
  return out;
}

export interface Zones {
  /** The nearest swing high above the last close, or null when there is none. */
  resistance: number | null;
  /** The nearest swing low below the last close, or null when there is none. */
  support: number | null;
}

/**
 * Support and resistance from swing points: a bar whose high (low) is the
 * highest (lowest) within `lookback` bars either side. Tries a wide look-back
 * first and narrows it until a level exists on each side. Only levels that
 * really occurred in the data are returned: when there is none, null, never
 * an invented percentage band.
 */
export function swingZones(bars: Bar[]): Zones {
  if (bars.length < 5) return { resistance: null, support: null };
  const last = bars[bars.length - 1].c;
  let highs: number[] = [];
  let lows: number[] = [];
  for (const lb of [8, 4, 2]) {
    highs = [];
    lows = [];
    for (let i = lb; i < bars.length - lb; i++) {
      let isHigh = true;
      let isLow = true;
      for (let j = i - lb; j <= i + lb; j++) {
        if (j === i) continue;
        if (bars[j].h > bars[i].h) isHigh = false;
        if (bars[j].l < bars[i].l) isLow = false;
      }
      if (isHigh) highs.push(bars[i].h);
      if (isLow) lows.push(bars[i].l);
    }
    if (highs.some((p) => p > last) && lows.some((p) => p < last)) break;
  }
  const above = highs.filter((p) => p > last).sort((a, b) => a - b);
  const below = lows.filter((p) => p < last).sort((a, b) => b - a);
  return { resistance: above[0] ?? null, support: below[0] ?? null };
}
