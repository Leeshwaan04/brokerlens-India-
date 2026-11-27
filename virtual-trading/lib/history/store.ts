// Writes daily rows into price_history (the charting studio's long history).
// Shared by the daily sync (one new day) and the backfill (about five years).
import { sql } from "drizzle-orm";
import { getDb } from "../db";
import { priceHistory, priceHistoryDays } from "../schema";
import type { DailyPriceRow } from "../bhavcopy";

/** Rupees to whole paise: stored as integers so nothing drifts. */
export const toPaise = (rupees: number): number => Math.round(rupees * 100);

export interface HistoryRow {
  symbol: string;
  tradeDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  prevClose: number | null;
  volume: number | null;
}

/** A day's rows as stored. A row missing its open, high or low is built from its close, never guessed higher. */
export function toHistoryRows(tradeDate: string, rows: DailyPriceRow[]): HistoryRow[] {
  return rows
    .filter((r) => Number.isFinite(r.close) && r.close > 0)
    .map((r) => {
      const close = toPaise(r.close);
      const open = r.open !== null && r.open > 0 ? toPaise(r.open) : close;
      const high = Math.max(r.high !== null && r.high > 0 ? toPaise(r.high) : close, open, close);
      const low = Math.min(r.low !== null && r.low > 0 ? toPaise(r.low) : close, open, close);
      return {
        symbol: r.symbol,
        tradeDate,
        open,
        high,
        low,
        close,
        prevClose: r.prevClose !== null && r.prevClose > 0 ? toPaise(r.prevClose) : null,
        volume: r.volume !== null && Number.isFinite(r.volume) ? Math.round(r.volume) : null,
      };
    });
}

/** One statement per 500 rows; safe to repeat for the same day. */
export async function upsertPriceHistory(rows: HistoryRow[]): Promise<void> {
  const db = getDb();
  for (let i = 0; i < rows.length; i += 500) {
    await db
      .insert(priceHistory)
      .values(rows.slice(i, i + 500))
      .onConflictDoUpdate({
        target: [priceHistory.symbol, priceHistory.tradeDate],
        set: {
          open: sql`excluded.open_p`,
          high: sql`excluded.high_p`,
          low: sql`excluded.low_p`,
          close: sql`excluded.close_p`,
          prevClose: sql`excluded.prev_close_p`,
          volume: sql`excluded.volume`,
        },
      });
  }
}

export async function recordHistoryDay(tradeDate: string, source: "old" | "new", rows: number, status: "ok" | "none"): Promise<void> {
  await getDb()
    .insert(priceHistoryDays)
    .values({ tradeDate, source, rows, status })
    .onConflictDoUpdate({ target: priceHistoryDays.tradeDate, set: { source, rows, status, fetchedAt: sql`now()` } });
}
