// Daily EOD price sync: fetches NSE's real public bhavcopy (walking back a
// day at a time if the target date's close isn't published yet), upserts
// daily_prices, then settles every order waiting on that date. Triggered by
// scheduled workflow or Cloudflare Cron Trigger at ~19:00 IST on trading weekdays; also
// callable by hand with ?date=YYYY-MM-DD for backfill, same as the plan's
// "Verification" section describes.
import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { dailyPrices, stockUniverse, marketHolidays, priceSyncRuns } from "@/lib/schema";
import { fetchBhavcopy, type DailyPriceRow } from "@/lib/bhavcopy";
import { isoDateOnly, previousTradingDaysFrom } from "@/lib/market-calendar";
import { settlePendingOrders } from "@/lib/order-engine";

// Covers a long weekend plus a missed cron run or two; previousTradingDaysFrom
// itself also refuses to walk back more than 60 calendar days regardless.
const MAX_WALK_BACK_ATTEMPTS = 10;

async function upsertDailyPrices(tradeDate: string, rows: DailyPriceRow[]) {
  const db = getDb();
  for (const row of rows) {
    const values = {
      symbol: row.symbol,
      tradeDate,
      open: row.open !== null ? String(row.open) : null,
      high: row.high !== null ? String(row.high) : null,
      low: row.low !== null ? String(row.low) : null,
      close: String(row.close),
      volume: row.volume !== null ? String(row.volume) : null,
    };
    await db
      .insert(dailyPrices)
      .values(values)
      .onConflictDoUpdate({
        target: [dailyPrices.symbol, dailyPrices.tradeDate],
        set: { open: values.open, high: values.high, low: values.low, close: values.close, volume: values.volume },
      });
  }
}

export async function GET(request: NextRequest) {
  const cronSecret = process.env.CRON_SECRET;
  const authHeader = request.headers.get("authorization");
  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const db = getDb();
  const dateParam = request.nextUrl.searchParams.get("date");
  const startIso = dateParam ?? isoDateOnly(new Date());

  const [holidayRows, universeRows] = await Promise.all([
    db.select({ holidayDate: marketHolidays.holidayDate }).from(marketHolidays),
    db.select({ symbol: stockUniverse.symbol }).from(stockUniverse),
  ]);
  const holidaySet = new Set(holidayRows.map((r) => r.holidayDate));
  const allowedSymbols = new Set(universeRows.map((r) => r.symbol));

  if (allowedSymbols.size === 0) {
    return NextResponse.json(
      { error: "stock_universe is empty; run scripts/sync-stock-universe.ts first" },
      { status: 503 },
    );
  }

  const candidates = previousTradingDaysFrom(startIso, holidaySet, MAX_WALK_BACK_ATTEMPTS);
  if (candidates.length === 0) {
    return NextResponse.json(
      { error: `${startIso} and the trading days before it are not trading days` },
      { status: 422 },
    );
  }

  const errors: string[] = [];
  for (const iso of candidates) {
    const [y, m, d] = iso.split("-").map(Number);
    const date = new Date(Date.UTC(y, m - 1, d));
    const result = await fetchBhavcopy(date, allowedSymbols);

    if (result.status === "error") {
      errors.push(`${iso}: ${result.error}`);
      continue;
    }
    if (result.status === "not_published" || result.rows.length === 0) {
      continue;
    }

    await upsertDailyPrices(iso, result.rows);
    const settlement = await settlePendingOrders(iso);
    await db.insert(priceSyncRuns).values({ tradeDate: iso, rowsIngested: result.rows.length, status: "ok" });

    return NextResponse.json({
      tradeDate: iso,
      rowsIngested: result.rows.length,
      settled: settlement.settled,
      rejected: settlement.rejected,
    });
  }

  const errorMessage = `No published bhavcopy found among candidate trading day(s): ${candidates.join(", ")}.${
    errors.length ? ` Fetch errors: ${errors.join("; ")}` : ""
  }`;
  await db.insert(priceSyncRuns).values({
    tradeDate: startIso,
    rowsIngested: 0,
    status: "failed",
    error: errorMessage,
  });
  return NextResponse.json({ error: errorMessage }, { status: 502 });
}
