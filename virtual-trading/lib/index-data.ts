// Index closes for the app's screens, always capped at the practice market's
// date like every other price: an index level from after it would show a
// market the user's trades have not reached.
import { cache } from "react";
import { and, asc, eq, gte, inArray, lte, max } from "drizzle-orm";
import { getDb } from "./db";
import { indexCloses } from "./schema";
import { getMarketAsOf } from "./market-clock";
import { TRACKED_INDICES, type IndexKey } from "./index-closes";

/** The strip under the header, in display order. */
export const STRIP_KEYS: IndexKey[] = ["nifty50", "niftybank", "finnifty", "midcpnifty", "indiavix"];

export interface IndexStripItem {
  key: IndexKey;
  label: string;
  close: number;
  changePct: number | null;
}

export interface IndexStrip {
  date: string;
  items: IndexStripItem[];
}

/** The newest session at or before the practice market's date that has index closes. */
export const getIndexStrip = cache(async (): Promise<IndexStrip | null> => {
  const asOf = await getMarketAsOf();
  if (!asOf) return null;
  const db = getDb();
  const [latest] = await db.select({ d: max(indexCloses.tradeDate) }).from(indexCloses).where(lte(indexCloses.tradeDate, asOf));
  if (!latest?.d) return null;
  const rows = await db
    .select()
    .from(indexCloses)
    .where(and(eq(indexCloses.tradeDate, latest.d), inArray(indexCloses.indexKey, STRIP_KEYS)));
  const items = STRIP_KEYS.flatMap((key) => {
    const r = rows.find((x) => x.indexKey === key);
    const meta = TRACKED_INDICES.find((t) => t.key === key);
    return r && meta ? [{ key, label: meta.label, close: Number(r.close), changePct: r.changePct === null ? null : Number(r.changePct) }] : [];
  });
  return items.length > 0 ? { date: latest.d, items } : null;
});

/** One index's closes from `from` to the practice market's date, oldest first. */
export async function getIndexSeries(key: IndexKey, from: string): Promise<{ date: string; close: number }[]> {
  const asOf = await getMarketAsOf();
  if (!asOf) return [];
  const rows = await getDb()
    .select({ d: indexCloses.tradeDate, c: indexCloses.close })
    .from(indexCloses)
    .where(and(eq(indexCloses.indexKey, key), gte(indexCloses.tradeDate, from), lte(indexCloses.tradeDate, asOf)))
    .orderBy(asc(indexCloses.tradeDate));
  return rows.map((r) => ({ date: r.d, close: Number(r.c) }));
}

/**
 * A benchmark line on the same scale as the portfolio: the index's move since
 * the first date, applied to the starting balance. Each date takes the latest
 * index close on or before it, so a gap never invents a level. Null when the
 * index has no close on or before the first date.
 */
export function benchmarkPoints(
  dates: string[],
  series: { date: string; close: number }[],
  startingBalance: number,
): { date: string; value: number }[] | null {
  if (dates.length === 0 || series.length === 0) return null;
  const closeOnOrBefore = (d: string) => {
    let found: number | null = null;
    for (const s of series) {
      if (s.date <= d) found = s.close;
      else break;
    }
    return found;
  };
  const base = closeOnOrBefore(dates[0]);
  if (base === null || base <= 0) return null;
  const out: { date: string; value: number }[] = [];
  for (const d of dates) {
    const c = closeOnOrBefore(d);
    if (c !== null) out.push({ date: d, value: (startingBalance * c) / base });
  }
  return out.length >= 2 ? out : null;
}
