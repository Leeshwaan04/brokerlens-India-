// Quarterly stock-universe sync: fetches NSE's real, live Nifty 100
// constituent list and upserts stock_universe. Run with
// `npx tsx scripts/sync-stock-universe.ts` against a real DATABASE_URL.
// See the plan's "Stock universe" section: widening past Nifty 100 later
// is a filter change here, not a schema change.
import { getDb } from "../lib/db";
import { stockUniverse } from "../lib/schema";
import { fetchNifty100 } from "../lib/nifty-universe";

async function main() {
  const db = getDb();
  const rows = await fetchNifty100();
  if (rows.length === 0) {
    throw new Error("Fetched zero Nifty 100 constituents; refusing to upsert an empty universe.");
  }

  for (const r of rows) {
    await db
      .insert(stockUniverse)
      .values({ symbol: r.symbol, name: r.name, isin: r.isin, indexMembership: ["NIFTY100"] })
      .onConflictDoUpdate({
        target: stockUniverse.symbol,
        set: { name: r.name, isin: r.isin },
      });
  }

  console.log(`Synced ${rows.length} Nifty 100 constituents into stock_universe.`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
