// Stock-universe sync: fetches NSE's live Nifty 50, 100 and 500 constituent
// lists and upserts stock_universe (the Nifty 500, each stock tagged with the
// lists it is in). Run with `npx tsx scripts/sync-stock-universe.ts` against a
// real DATABASE_URL, about quarterly when NSE reconstitutes the indices.
//
// A stock that has left the Nifty 500 is kept (so its history and any
// holdings still price) with an empty membership; nothing is deleted.
import { notInArray } from "drizzle-orm";
import { getDb } from "../lib/db";
import { stockUniverse } from "../lib/schema";
import { fetchUniverse } from "../lib/nifty-universe";

async function main() {
  const db = getDb();
  const rows = await fetchUniverse();
  if (rows.length < 400) {
    throw new Error(`Fetched only ${rows.length} constituents; refusing to change the universe on a partial list.`);
  }

  for (const r of rows) {
    await db
      .insert(stockUniverse)
      .values({ symbol: r.symbol, name: r.name, isin: r.isin, indexMembership: r.indexMembership })
      .onConflictDoUpdate({
        target: stockUniverse.symbol,
        set: { name: r.name, isin: r.isin, indexMembership: r.indexMembership },
      });
  }
  await db
    .update(stockUniverse)
    .set({ indexMembership: [] })
    .where(notInArray(stockUniverse.symbol, rows.map((r) => r.symbol)));

  const count = (m: string) => rows.filter((r) => r.indexMembership.includes(m)).length;
  console.log(`Synced ${rows.length} stocks (Nifty 50: ${count("NIFTY50")}, Nifty 100: ${count("NIFTY100")}, Nifty 500: ${count("NIFTY500")}).`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
