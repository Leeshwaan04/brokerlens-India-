// Backfills about five years of daily history for the charting studio from
// NSE's public archive: equities (the stock universe) into price_history and
// the tracked indices into index_closes. Run from a machine NSE serves
// normally (the owner's Mac; NSE refuses GitHub's runners):
//
//   DATABASE_URL=... npx tsx scripts/backfill-history.mts [--years 5] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--pause 350]
//
// Resumable: finished days (price_history_days) are skipped, and a day with
// no published file (a market holiday) is remembered, so a rerun only does
// what is left. Plain requests, a pause between them, one day at a time.
import { parseArgs } from "node:util";
import { asc, sql } from "drizzle-orm";
import { getDb } from "../lib/db";
import { indexCloses, priceHistoryDays, stockUniverse } from "../lib/schema";
import { fetchBhavcopy } from "../lib/bhavcopy";
import { fetchOldBhavcopy, OLD_FORMAT_LAST_DATE } from "../lib/history/old-bhavcopy";
import { fetchIndexCloses } from "../lib/index-closes";
import { recordHistoryDay, toHistoryRows, upsertPriceHistory } from "../lib/history/store";

const { values } = parseArgs({ options: { years: { type: "string" }, from: { type: "string" }, to: { type: "string" }, pause: { type: "string" } } });
const iso = (d: Date) => d.toISOString().slice(0, 10);
const utc = (s: string) => new Date(`${s}T00:00:00Z`);
const to = values.to ?? iso(new Date());
const from = values.from ?? iso(new Date(utc(to).getTime() - Number(values.years ?? 5) * 365.25 * 86_400_000));
const pause = Number(values.pause ?? 350);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const db = getDb();
const universe = new Set((await db.select({ s: stockUniverse.symbol }).from(stockUniverse)).map((r) => r.s));
if (universe.size < 400) throw new Error(`Stock universe has only ${universe.size} symbols; run npm run sync:stock-universe first.`);
const done = new Set((await db.select({ d: priceHistoryDays.tradeDate }).from(priceHistoryDays).orderBy(asc(priceHistoryDays.tradeDate))).map((r) => r.d));

const days: string[] = [];
for (let t = utc(from).getTime(); t <= utc(to).getTime(); t += 86_400_000) {
  const d = new Date(t);
  // Weekends are tried too: NSE holds occasional special sessions (Budget Saturdays and Sundays,
  // Muhurat trading). Skipping them leaves a gap, and the next day's printed previous close (the special
  // session's close) would then look like a share-count change. A weekend with no file is remembered as none.
  if (!done.has(iso(d))) days.push(iso(d));
}
console.log(`Backfill ${from} to ${to}: ${days.length} days to do, ${done.size} already recorded, ${universe.size} symbols.`);

let ok = 0, none = 0, errors = 0, rowsTotal = 0, indexDays = 0;
const started = Date.now();
for (const [i, day] of days.entries()) {
  const useOld = day <= OLD_FORMAT_LAST_DATE;
  const when = utc(day);
  const res = useOld ? await fetchOldBhavcopy(when, universe) : await fetchBhavcopy(when, universe);
  if (res.status === "error") {
    errors++;
    console.log(`  ${day}: ${res.error} (will retry on the next run)`);
  } else if (res.status === "not_published" || res.rows.length === 0) {
    none++;
    await recordHistoryDay(day, useOld ? "old" : "new", 0, "none");
  } else {
    const rows = toHistoryRows(day, res.rows);
    await upsertPriceHistory(rows);
    await recordHistoryDay(day, useOld ? "old" : "new", rows.length, "ok");
    rowsTotal += rows.length;
    ok++;
    // Indices for the same session (best effort: a missing index file never fails the day).
    await sleep(pause);
    const idx = await fetchIndexCloses(when);
    if (idx.status === "ok") {
      await db
        .insert(indexCloses)
        .values(idx.rows.map((r) => ({ indexKey: r.indexKey, tradeDate: day, open: r.open === null ? null : String(r.open), high: r.high === null ? null : String(r.high), low: r.low === null ? null : String(r.low), close: String(r.close), changePct: r.changePct === null ? null : String(r.changePct) })))
        .onConflictDoUpdate({ target: [indexCloses.indexKey, indexCloses.tradeDate], set: { open: sql`excluded.open`, high: sql`excluded.high`, low: sql`excluded.low`, close: sql`excluded.close`, changePct: sql`excluded.change_pct` } });
      indexDays++;
    }
  }
  if ((i + 1) % 25 === 0 || i === days.length - 1) {
    const mins = ((Date.now() - started) / 60000).toFixed(1);
    console.log(`  ${i + 1}/${days.length} days (${day}): ${ok} loaded, ${none} holidays, ${errors} errors, ${rowsTotal} rows, ${indexDays} index days, ${mins} min`);
  }
  await sleep(pause);
}
console.log(`Done: ${ok} days loaded, ${none} without a file, ${errors} errors, ${rowsTotal} rows.`);
process.exit(errors > 0 ? 1 : 0);
