// Split and bonus adjustment for chart history.
//
// NSE prints each day's previous close already adjusted on a split or bonus
// ex-date (a 1:5 split turns a 1,000 close into a printed 200), so comparing
// it with the close we stored for the previous session yields the share-count
// factor exactly (lib/corporate-actions.ts, which this reuses). Walking the
// series, every bar before an action is divided by its factor and its volume
// multiplied, so the chart shows no false 80% crash.
//
// Deliberately conservative:
//  * An action is only applied when the stored previous bar is the previous
//    SESSION (so a day we failed to fetch cannot masquerade as a split).
//  * A change that is not a clean share ratio (a rights issue, an
//    extraordinary dividend) is left alone and reported, never guessed at.
//  * Dividends are not adjusted, matching how brokers' own charts behave.
import { detectShareAdjustment } from "../corporate-actions";

export interface RawBar {
  date: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  /** NSE's printed previous close for this day, as published (adjusted on an ex-date). */
  prevClose: number | null;
}

export interface AdjustedBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface AppliedSplit {
  date: string;
  ratio: string; // "new:old"
  factor: number;
}

export interface AdjustmentResult {
  bars: AdjustedBar[];
  applied: AppliedSplit[];
  /** Days where the printed previous close differed but could not be explained as a share ratio. */
  unexplained: { date: string; storedPrevClose: number; nsePrevClose: number }[];
  /** Days with a difference we did not trust because the previous session was missing from the data. */
  skippedGaps: string[];
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/**
 * @param bars ascending by date
 * @param sessions every trading date known to the history (ascending); used to confirm adjacency
 */
export function adjustForShareActions(bars: RawBar[], sessions: readonly string[]): AdjustmentResult {
  const prevSession = new Map<string, string>();
  for (let i = 1; i < sessions.length; i++) prevSession.set(sessions[i], sessions[i - 1]);

  const applied: AppliedSplit[] = [];
  const unexplained: AdjustmentResult["unexplained"] = [];
  const skippedGaps: string[] = [];
  const factorAt = new Array<number>(bars.length).fill(1);

  for (let i = 1; i < bars.length; i++) {
    const cur = bars[i];
    const prev = bars[i - 1];
    if (cur.prevClose === null || cur.prevClose <= 0) continue;
    if (Math.abs(prev.close / cur.prevClose - 1) < 0.02) continue; // an ordinary day
    if (prevSession.get(cur.date) !== prev.date) {
      skippedGaps.push(cur.date);
      continue;
    }
    const adj = detectShareAdjustment(prev.close, cur.prevClose);
    if (adj) {
      factorAt[i] = adj.factor;
      applied.push({ date: cur.date, ratio: adj.ratio, factor: adj.factor });
    } else {
      unexplained.push({ date: cur.date, storedPrevClose: prev.close, nsePrevClose: cur.prevClose });
    }
  }

  // cumulative[i] = product of factors of every action strictly after bar i.
  const out: AdjustedBar[] = new Array(bars.length);
  let cumulative = 1;
  for (let i = bars.length - 1; i >= 0; i--) {
    const b = bars[i];
    out[i] = {
      date: b.date,
      open: round2(b.open / cumulative),
      high: round2(b.high / cumulative),
      low: round2(b.low / cumulative),
      close: round2(b.close / cumulative),
      volume: b.volume === null ? null : Math.round(b.volume * cumulative),
    };
    cumulative *= factorAt[i];
  }
  return { bars: out, applied, unexplained, skippedGaps };
}
