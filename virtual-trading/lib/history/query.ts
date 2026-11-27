// Chart history for one symbol, adjusted, and never later than the practice
// market's date: a chart must not show prices the rest of the app is not
// allowed to (the 30-day lag, lib/market-clock.ts).
import { and, asc, eq, lte } from "drizzle-orm";
import { getDb } from "../db";
import { priceHistory, priceHistoryDays } from "../schema";
import { getMarketAsOf } from "../market-clock";
import { adjustForShareActions, type AdjustmentResult, type RawBar } from "./adjust";

export const SYMBOL_PATTERN = /^[A-Z0-9&_-]{1,20}$/;
/** Most sessions one request returns (about five years). */
export const MAX_BARS = 1500;

export interface HistoryPayload {
  symbol: string;
  asOf: string;
  adjusted: true;
  /** Share-count adjustments applied (split or bonus ex-dates) and anything left unexplained. */
  actions: { date: string; ratio: string }[];
  unexplained: number;
  /** Columnar: parallel arrays, oldest first. Prices in rupees, volume in shares. */
  d: string[];
  o: number[];
  h: number[];
  l: number[];
  c: number[];
  v: (number | null)[];
}

const rupees = (p: number) => p / 100;

/** Null when the symbol has no history on or before the practice date. */
export async function getHistory(symbol: string): Promise<HistoryPayload | null> {
  const asOf = await getMarketAsOf();
  if (!asOf) return null;
  const db = getDb();
  const [rows, days] = await Promise.all([
    db
      .select()
      .from(priceHistory)
      .where(and(eq(priceHistory.symbol, symbol), lte(priceHistory.tradeDate, asOf)))
      .orderBy(asc(priceHistory.tradeDate)),
    db
      .select({ d: priceHistoryDays.tradeDate })
      .from(priceHistoryDays)
      .where(and(eq(priceHistoryDays.status, "ok"), lte(priceHistoryDays.tradeDate, asOf)))
      .orderBy(asc(priceHistoryDays.tradeDate)),
  ]);
  if (rows.length === 0) return null;

  const raw: RawBar[] = rows.map((r) => ({
    date: r.tradeDate,
    open: rupees(r.open),
    high: rupees(r.high),
    low: rupees(r.low),
    close: rupees(r.close),
    volume: r.volume,
    prevClose: r.prevClose === null ? null : rupees(r.prevClose),
  }));
  const adj: AdjustmentResult = adjustForShareActions(raw, days.map((x) => x.d));
  const bars = adj.bars.slice(-MAX_BARS);
  return {
    symbol,
    asOf,
    adjusted: true,
    actions: adj.applied.map((a) => ({ date: a.date, ratio: a.ratio })),
    unexplained: adj.unexplained.length,
    d: bars.map((b) => b.date),
    o: bars.map((b) => b.open),
    h: bars.map((b) => b.high),
    l: bars.map((b) => b.low),
    c: bars.map((b) => b.close),
    v: bars.map((b) => b.volume),
  };
}
