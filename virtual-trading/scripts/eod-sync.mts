// The daily EOD price sync and order settlement (lib/eod-sync.ts) as a Node
// script, run by .github/workflows/virtual-trading-eod-sync.yml at 19:00 IST
// with DATABASE_URL set. Also for the first history load:
//   npx tsx scripts/eod-sync.mts --history 60      (run twice on a new database)
//   npx tsx scripts/eod-sync.mts --date 2026-11-20 (start from an earlier real date)
// Prints the result as JSON and exits non-zero when the sync failed.
import { parseArgs } from "node:util";
import { runEodSync } from "../lib/eod-sync";

const { values } = parseArgs({
  options: { history: { type: "string" }, date: { type: "string" } },
});
if (values.date !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(values.date)) throw new Error(`Not a date: ${values.date}`);
const history = values.history === undefined ? undefined : Number(values.history);
if (history !== undefined && !(Number.isInteger(history) && history > 0)) throw new Error(`--history must be a positive whole number`);

const { status, body } = await runEodSync({ date: values.date, history });
console.log(JSON.stringify({ status, ...body }, null, 2));
process.exit(status >= 400 ? 1 : 0);
