// Split and bonus adjustment for chart history.
//
// NSE's bhavcopy does NOT print an adjusted previous close on an ex-date (checked
// on 27 Nov 2026 against Reliance's 1:1 bonus, Wipro's bonus, Bajaj Finance's
// split and Tata Steel's 10:1 split, in both file formats: the printed previous
// close is simply the unadjusted close of the day before). So a share action has
// to be recognised from the prices themselves.
//
// Rule, deliberately conservative: a session is treated as a split or bonus when
//  * the close fell by 44% or more from the previous session's close, and
//  * the previous close divided by TODAY'S OPEN (the exchange resets the opening
//    base price on an ex-date, so the open sits near the adjusted price) is
//    within 8% of one clean factor (2, 2.5, 3, 4, 5, 6, 8, 10, 12.5, 15, 20, 25,
//    40, 50), and the close agrees with that factor to within 20%.
// Every bar before it is then divided by the factor and its volume multiplied, so
// the chart shows the real day's move instead of a false crash.
//
// What it does NOT do, and says so instead of guessing:
//  * Bonus and split ratios below 2:1 (1:2 bonus is 3:2, 1:3 is 4:3 ...) look like
//    an ordinary 17% to 44% fall (a crash); they are listed in `unadjusted` so the
//    chart can say a drop on that date may be a corporate action.
//  * A fall that big but not a clean factor is listed the same way.
//  * A fall that is not a clean 44%+ share action is only reported when the stored previous
//    bar is the previous SESSION (a day we failed to fetch is not a crash).
//  * Dividends are not adjusted, matching how brokers' own charts behave.
// A proper corporate-actions source would remove these limits (docs roadmap).

export interface RawBar {
  date: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
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
  /** Dates of a large one-day fall (17% or more) that was not adjusted: a possible smaller bonus, or a real crash. */
  unadjusted: string[];
  /** Days with a big fall we did not trust because the previous session was missing from the data. */
  skippedGaps: string[];
}

const round2 = (n: number) => Math.round(n * 100) / 100;

const FACTORS = [2, 2.5, 3, 4, 5, 6, 8, 10, 12.5, 15, 20, 25, 40, 50];
const MIN_DROP_RATIO = 1.8; // previous close / close: a fall of 44% or more
const REPORT_DROP_RATIO = 1.2; // a fall of about 17% or more is worth a note
const OPEN_TOLERANCE = 0.08;
const CLOSE_TOLERANCE = 0.2;

function nearestFactor(openRatio: number, closeRatio: number): number | null {
  let best: number | null = null;
  let bestErr = Infinity;
  for (const f of FACTORS) {
    const err = Math.abs(openRatio / f - 1);
    if (err < bestErr) { best = f; bestErr = err; }
  }
  if (best === null || bestErr > OPEN_TOLERANCE) return null;
  return Math.abs(closeRatio / best - 1) <= CLOSE_TOLERANCE ? best : null;
}

/**
 * @param bars ascending by date
 * @param sessions every trading date known to the history (ascending); used to confirm adjacency
 */
export function adjustForShareActions(bars: RawBar[], sessions: readonly string[]): AdjustmentResult {
  const prevSession = new Map<string, string>();
  for (let i = 1; i < sessions.length; i++) prevSession.set(sessions[i], sessions[i - 1]);

  const applied: AppliedSplit[] = [];
  const unadjusted: string[] = [];
  const skippedGaps: string[] = [];
  const factorAt = new Array<number>(bars.length).fill(1);

  for (let i = 1; i < bars.length; i++) {
    const cur = bars[i];
    const prev = bars[i - 1];
    if (!(prev.close > 0) || !(cur.close > 0) || !(cur.open > 0)) continue;
    const closeRatio = prev.close / cur.close;
    if (closeRatio < REPORT_DROP_RATIO) continue; // an ordinary day (or a rise)
    // A fall of 44% or more that snaps to a clean factor is accepted even across missing sessions (a
    // stock can sit out several days, for example in trade-for-trade series, before its split). A
    // mid-sized fall across a gap is not reported at all: it may just be several days of movement.
    const adjacent = prevSession.get(cur.date) === prev.date;
    const factor = closeRatio >= MIN_DROP_RATIO ? nearestFactor(prev.close / cur.open, closeRatio) : null;
    if (!factor && !adjacent) {
      skippedGaps.push(cur.date);
      continue;
    }
    if (factor) {
      factorAt[i] = factor;
      applied.push({ date: cur.date, ratio: `${factor}:1`, factor });
    } else {
      unadjusted.push(cur.date);
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
  return { bars: out, applied, unadjusted, skippedGaps };
}
