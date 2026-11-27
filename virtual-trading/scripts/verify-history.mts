// Read-only audit of price_history: runs the split/bonus adjustment over every
// symbol and prints what it applied and what it could not explain. Use after a
// backfill. Needs DATABASE_URL (a direct or session-pooler URL), reads only.
//   npx tsx scripts/verify-history.mts [SYMBOL ...]
import pg from "pg";
import { adjustForShareActions, type RawBar } from "../lib/history/adjust";

const url = process.env.DATABASE_URL;
if (!url) throw new Error("DATABASE_URL is required");
const only = process.argv.slice(2).map((s) => s.toUpperCase());
const client = new pg.Client({ connectionString: url, ssl: url.includes("localhost") ? undefined : { rejectUnauthorized: false } });
await client.connect();

const days = (await client.query(`select to_char(trade_date,'YYYY-MM-DD') d from price_history_days where status='ok' order by trade_date`)).rows.map((r) => r.d as string);
const rows = (
  await client.query(
    `select symbol, to_char(trade_date,'YYYY-MM-DD') d, open_p, high_p, low_p, close_p, prev_close_p, volume
     from price_history ${only.length ? "where symbol = any($1)" : ""} order by symbol, trade_date`,
    only.length ? [only] : [],
  )
).rows;
await client.end();

const bySymbol = new Map<string, RawBar[]>();
for (const r of rows) {
  const list = bySymbol.get(r.symbol) ?? [];
  list.push({ date: r.d, open: r.open_p / 100, high: r.high_p / 100, low: r.low_p / 100, close: r.close_p / 100, volume: r.volume === null ? null : Number(r.volume), prevClose: r.prev_close_p === null ? null : r.prev_close_p / 100 });
  bySymbol.set(r.symbol, list);
}

let withActions = 0;
let withUnexplained = 0;
let worstJump = { symbol: "", date: "", pct: 0 };
for (const [symbol, bars] of bySymbol) {
  const res = adjustForShareActions(bars, days);
  if (res.applied.length) withActions++;
  if (res.unexplained.length) withUnexplained++;
  if (only.length || res.applied.length) console.log(symbol.padEnd(12), res.applied.map((a) => `${a.date} ${a.ratio}`).join(", ") || "-", res.unexplained.length ? `| unexplained ${res.unexplained.length}` : "");
  // After adjustment no single-day close-to-close move should look like an unadjusted split.
  for (let i = 1; i < res.bars.length; i++) {
    const pct = (res.bars[i].close / res.bars[i - 1].close - 1) * 100;
    if (Math.abs(pct) > Math.abs(worstJump.pct)) worstJump = { symbol, date: res.bars[i].date, pct };
  }
}
console.log(`\n${bySymbol.size} symbols: ${withActions} with share-count adjustments, ${withUnexplained} with unexplained previous-close differences`);
console.log(`largest remaining one-day move after adjustment: ${worstJump.symbol} ${worstJump.date} ${worstJump.pct.toFixed(1)}%`);
