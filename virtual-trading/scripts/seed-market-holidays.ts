// One-off/idempotent load of seed/market-holidays.json (NSE's own real
// 2026 CM-segment holiday calendar, see that file's "source" field) into
// market_holidays. Run with `npx tsx scripts/seed-market-holidays.ts`
// against a real DATABASE_URL, and re-run whenever the source file is
// refreshed for a new year.
import { getDb } from "../lib/db";
import { marketHolidays } from "../lib/schema";
import holidaysFile from "../seed/market-holidays.json";

async function main() {
  const db = getDb();
  for (const h of holidaysFile.holidays) {
    await db
      .insert(marketHolidays)
      .values({ holidayDate: h.date, description: h.description })
      .onConflictDoUpdate({
        target: marketHolidays.holidayDate,
        set: { description: h.description },
      });
  }
  console.log(`Seeded ${holidaysFile.holidays.length} market holidays.`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
