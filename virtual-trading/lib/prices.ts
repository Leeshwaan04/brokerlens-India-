// Latest ingested official close per symbol, in one query rather than one
// query per holding or pending order.

import { and, desc, inArray, lte } from "drizzle-orm";
import { getDb } from "./db";
import { dailyPrices } from "./schema";

export interface LatestClose {
  close: number;
  tradeDate: string;
}

/** Latest close per symbol, optionally as of a date (on or before asOf). */
export async function latestCloses(symbols: string[], asOf?: string): Promise<Map<string, LatestClose>> {
  const unique = [...new Set(symbols)];
  const out = new Map<string, LatestClose>();
  if (unique.length === 0) return out;
  const db = getDb();
  const rows = await db
    .selectDistinctOn([dailyPrices.symbol], {
      symbol: dailyPrices.symbol,
      close: dailyPrices.close,
      tradeDate: dailyPrices.tradeDate,
    })
    .from(dailyPrices)
    .where(asOf ? and(inArray(dailyPrices.symbol, unique), lte(dailyPrices.tradeDate, asOf)) : inArray(dailyPrices.symbol, unique))
    .orderBy(dailyPrices.symbol, desc(dailyPrices.tradeDate));
  for (const r of rows) out.set(r.symbol, { close: Number(r.close), tradeDate: r.tradeDate });
  return out;
}

export async function latestClose(symbol: string): Promise<LatestClose | null> {
  return (await latestCloses([symbol])).get(symbol) ?? null;
}

export interface CloseWithChange {
  close: number;
  tradeDate: string;
  prevClose: number | null;
}

/** The two most recent ingested trading dates, newest first. */
export async function latestTradeDates(limit = 2): Promise<string[]> {
  const rows = await getDb()
    .selectDistinct({ tradeDate: dailyPrices.tradeDate })
    .from(dailyPrices)
    .orderBy(desc(dailyPrices.tradeDate))
    .limit(limit);
  return rows.map((r) => r.tradeDate);
}

/**
 * Close on the latest ingested date and the one before it, for the day's
 * change. A symbol missing from the latest day falls back to its own latest
 * close with no change shown.
 */
export async function closesWithChange(symbols: string[]): Promise<Map<string, CloseWithChange>> {
  const unique = [...new Set(symbols)];
  const out = new Map<string, CloseWithChange>();
  if (unique.length === 0) return out;
  const dates = await latestTradeDates(2);
  if (dates.length === 0) return out;
  const rows = await getDb()
    .select({ symbol: dailyPrices.symbol, tradeDate: dailyPrices.tradeDate, close: dailyPrices.close })
    .from(dailyPrices)
    .where(and(inArray(dailyPrices.symbol, unique), inArray(dailyPrices.tradeDate, dates)));
  for (const s of unique) {
    const latest = rows.find((r) => r.symbol === s && r.tradeDate === dates[0]);
    const prev = dates[1] ? rows.find((r) => r.symbol === s && r.tradeDate === dates[1]) : undefined;
    if (latest) out.set(s, { close: Number(latest.close), tradeDate: latest.tradeDate, prevClose: prev ? Number(prev.close) : null });
  }
  const missing = unique.filter((s) => !out.has(s));
  if (missing.length) {
    for (const [s, c] of await latestCloses(missing)) out.set(s, { ...c, prevClose: null });
  }
  return out;
}
