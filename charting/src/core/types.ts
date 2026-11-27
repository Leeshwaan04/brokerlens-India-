/** One OHLCV bar. `t` is the instant the bar opens, in epoch seconds (UTC). */
export interface Bar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export type Timeframe = "1m" | "3m" | "5m" | "15m" | "30m" | "1H" | "4H" | "D" | "W" | "M";

export const INTRADAY_TIMEFRAMES: readonly Timeframe[] = ["1m", "3m", "5m", "15m", "30m", "1H", "4H"];
export const DAILY_TIMEFRAMES: readonly Timeframe[] = ["D", "W", "M"];

export const isIntraday = (tf: Timeframe): boolean => INTRADAY_TIMEFRAMES.includes(tf);

/** Minutes in each intraday timeframe. */
export const TIMEFRAME_MINUTES: Record<string, number> = { "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "4H": 240 };

export const TIMEFRAME_LABEL: Record<Timeframe, string> = {
  "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m", "1H": "1H", "4H": "4H", D: "1D", W: "1W", M: "1M",
};

/** A trading session as minutes after midnight, India time. */
export interface SessionSpec {
  openMin: number;
  closeMin: number;
}

/** NSE and BSE cash equities: 09:15 to 15:30. Other segments (commodities, currency) get their own spec. */
export const NSE_EQUITY_SESSION: SessionSpec = { openMin: 9 * 60 + 15, closeMin: 15 * 60 + 30 };
