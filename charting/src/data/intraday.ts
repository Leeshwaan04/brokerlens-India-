import { resampleIntraday } from "../core/resample";
import { INTRADAY_TIMEFRAMES, NSE_EQUITY_SESSION, SessionSpec, Timeframe, type Bar } from "../core/types";
import type { DataAdapter } from "../studio";

export interface MinuteSource {
  symbol: string;
  /** One-minute bars for the instrument, oldest first, from a licensed source. */
  loadMinutes(): Promise<Bar[]>;
  session?: SessionSpec;
}

/**
 * Builds an adapter that offers 1m to 4H (and daily, weekly, monthly) from one
 * set of one-minute bars. The studio never invents intraday bars: this is the
 * only way intraday timeframes appear, and it needs a real minute source.
 * Minute bars are loaded once and rolled up per timeframe.
 */
export function minuteBarAdapter(src: MinuteSource): DataAdapter {
  const session = src.session ?? NSE_EQUITY_SESSION;
  let minutes: Promise<Bar[]> | null = null;
  const load = () => (minutes ??= src.loadMinutes());
  return {
    symbol: src.symbol,
    async loadDaily() {
      return resampleIntraday(await load(), "D", session);
    },
    intraday: {
      timeframes: [...INTRADAY_TIMEFRAMES] as Timeframe[],
      load: async (tf) => resampleIntraday(await load(), tf, session),
    },
  };
}
