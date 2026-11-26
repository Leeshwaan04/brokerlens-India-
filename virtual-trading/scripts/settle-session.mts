// Settles PENDING orders for the given practice-market sessions with the
// real settlement code, outside the daily sync. For local testing:
//   npx tsx scripts/settle-session.mts 2026-10-27 [2026-10-28 ...]
import { settlePendingOrders } from "../lib/order-engine";

for (const day of process.argv.slice(2)) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error(`Not a date: ${day}`);
  console.log(day, JSON.stringify(await settlePendingOrders(day)));
}
process.exit(0);
