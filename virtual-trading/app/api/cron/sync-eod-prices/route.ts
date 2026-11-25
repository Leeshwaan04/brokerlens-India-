// Daily EOD price sync: fetches NSE's real public bhavcopy (walking back a
// day at a time if the target date's close isn't published yet), upserts
// daily_prices, then settles every order waiting on that date. Triggered by
// scheduled workflow or Cloudflare Cron Trigger at ~19:00 IST on trading weekdays; also
// callable by hand with ?date=YYYY-MM-DD for backfill, same as the plan's
// "Verification" section describes.
import { NextRequest, NextResponse } from "next/server";
import { and, desc, eq, gt, lte } from "drizzle-orm";
import { getDb } from "@/lib/db";
import { dailyPrices, stockUniverse, marketHolidays, priceSyncRuns } from "@/lib/schema";
import { fetchBhavcopy, type DailyPriceRow } from "@/lib/bhavcopy";
import {
  isoDateOnly,
  missingCloseAction,
  nextTradingDay,
  previousTradingDaysFrom,
  tradingDaysBetween,
} from "@/lib/market-calendar";
import { priceLagDays, publishCeiling } from "@/lib/market-clock";
import { pendingDatesMissingPrices, pendingDueDates, retargetPendingOrders, settlePendingOrders } from "@/lib/order-engine";
import { applyCorporateActionsFor, type AppliedAction, type UnrecognisedAdjustment } from "@/lib/corporate-actions";
import { writeSnapshotsFor } from "@/lib/snapshots";

// Covers a long weekend plus a missed cron run or two; previousTradingDaysFrom
// itself also refuses to walk back more than 60 calendar days regardless.
const MAX_WALK_BACK_ATTEMPTS = 10;
// Most earlier days a single run will backfill for orders still waiting on
// a close that was never ingested (missed runs, a CI outage).
const MAX_BACKFILL_DATES = 15;
// History the delayed market needs: about three months of closes before the
// practice market's date (for day changes and price charts) up to the real
// latest. Missing days are fetched a few per run, or more with ?history=N on
// a first deploy.
const HISTORY_LEAD_DAYS = 90;
const DEFAULT_HISTORY_FETCHES = 5;
const MAX_HISTORY_FETCHES = 60;
const NSE_PAUSE_MS = 400;

const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));
const utcDate = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
const shiftDays = (iso: string, days: number) => isoDateOnly(new Date(utcDate(iso).getTime() + days * 86_400_000));

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
      prevClose: row.prevClose !== null ? String(row.prevClose) : null,
    };
    await db
      .insert(dailyPrices)
      .values(values)
      .onConflictDoUpdate({
        target: [dailyPrices.symbol, dailyPrices.tradeDate],
        set: {
          open: values.open,
          high: values.high,
          low: values.low,
          close: values.close,
          volume: values.volume,
          prevClose: values.prevClose,
        },
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

  const lag = priceLagDays();
  const ceiling = publishCeiling(new Date(), lag);

  // 1. Ingest the newest close NSE has published (walking back over days it
  // has not published yet). With a lag this only stocks up for later: the
  // practice market will not reach these closes for another `lag` days.
  const candidates = previousTradingDaysFrom(startIso, holidaySet, MAX_WALK_BACK_ATTEMPTS);
  const errors: string[] = [];
  let ingested: { tradeDate: string; rows: number } | null = null;
  for (const iso of candidates) {
    const result = await fetchBhavcopy(utcDate(iso), allowedSymbols);
    if (result.status === "error") {
      errors.push(`${iso}: ${result.error}`);
      continue;
    }
    if (result.status === "not_published" || result.rows.length === 0) continue;
    await upsertDailyPrices(iso, result.rows);
    await db.insert(priceSyncRuns).values({ tradeDate: iso, rowsIngested: result.rows.length, status: "ok" });
    ingested = { tradeDate: iso, rows: result.rows.length };
    break;
  }
  if (!ingested) {
    const errorMessage = `No published bhavcopy found among candidate trading day(s): ${candidates.join(", ") || "none"}.${
      errors.length ? ` Fetch errors: ${errors.join("; ")}` : ""
    }`;
    await db.insert(priceSyncRuns).values({ tradeDate: startIso, rowsIngested: 0, status: "failed", error: errorMessage });
    // Without a lag there is nothing new to settle against. With one, the
    // practice market runs on closes ingested weeks ago, so carry on.
    if (lag === 0) return NextResponse.json({ error: errorMessage }, { status: 502 });
  }

  // 2. History the delayed market needs, oldest first, a few days per run.
  const historyFetched: string[] = [];
  if (ceiling) {
    const requested = Number(request.nextUrl.searchParams.get("history"));
    const budget = Number.isInteger(requested) && requested > 0 ? Math.min(requested, MAX_HISTORY_FETCHES) : DEFAULT_HISTORY_FETCHES;
    const have = new Set(
      (await db.selectDistinct({ d: dailyPrices.tradeDate }).from(dailyPrices).where(gt(dailyPrices.tradeDate, shiftDays(ceiling, -HISTORY_LEAD_DAYS - 1)))).map(
        (r) => r.d,
      ),
    );
    const wanted = tradingDaysBetween(shiftDays(ceiling, -HISTORY_LEAD_DAYS), ingested?.tradeDate ?? startIso, holidaySet).filter(
      (d) => !have.has(d),
    );
    for (const day of wanted.slice(0, budget)) {
      await pause(NSE_PAUSE_MS);
      const back = await fetchBhavcopy(utcDate(day), allowedSymbols);
      if (back.status === "ok" && back.rows.length > 0) {
        await upsertDailyPrices(day, back.rows);
        await db.insert(priceSyncRuns).values({ tradeDate: day, rowsIngested: back.rows.length, status: "ok" });
        historyFetched.push(day);
      }
    }
  }

  // 3. Move the practice market forward: the newest ingested session it may
  // show (with no lag, the close just ingested).
  const [through] = ceiling
    ? await db
        .select({ d: dailyPrices.tradeDate })
        .from(dailyPrices)
        .where(lte(dailyPrices.tradeDate, ceiling))
        .orderBy(desc(dailyPrices.tradeDate))
        .limit(1)
        .then((r) => r.map((x) => x.d))
    : [ingested!.tradeDate];
  if (!through) {
    return NextResponse.json({ ingested, historyFetched, error: "No closes on file for the practice market's date yet; run with ?history=40" }, { status: 503 });
  }

  // Every earlier day a PENDING order is still waiting on: backfill its
  // close, or, if NSE never published one while a later close exists, it
  // was a market holiday missing from the calendar, so move those orders to
  // the next trading day rather than leave them PENDING forever.
  const backfilled: string[] = [];
  const retargeted: { from: string; to: string; orders: number }[] = [];
  for (const missing of (await pendingDatesMissingPrices(through)).slice(0, MAX_BACKFILL_DATES)) {
    const knownHoliday = holidaySet.has(missing);
    let status: "ok" | "not_published" | "error" = "not_published";
    if (!knownHoliday) {
      const back = await fetchBhavcopy(utcDate(missing), allowedSymbols);
      if (back.status === "ok" && back.rows.length > 0) {
        await upsertDailyPrices(missing, back.rows);
        await db.insert(priceSyncRuns).values({ tradeDate: missing, rowsIngested: back.rows.length, status: "ok" });
        backfilled.push(missing);
        continue;
      }
      status = back.status === "error" ? "error" : "not_published";
    }
    // pendingDatesMissingPrices only returns dates on or before `through`
    // that lack a close, and `through` has one, so a later close exists.
    if (missingCloseAction(status, knownHoliday, missing < through) === "retarget") {
      const to = nextTradingDay(missing, new Set([...holidaySet, missing]));
      const moved = await retargetPendingOrders(missing, to);
      await db.insert(priceSyncRuns).values({
        tradeDate: missing,
        rowsIngested: 0,
        status: "retargeted",
        error: `NSE published no close for ${missing}; ${moved} pending order(s) moved to ${to}.`,
      });
      retargeted.push({ from: missing, to, orders: moved });
    }
  }

  // Day by day in date order, including any session a missed run skipped:
  // a day's splits and bonuses are applied before that day's orders fill, so
  // an order is always settled against the share count of its own session.
  const [lastPublished] = await db
    .select({ d: priceSyncRuns.tradeDate })
    .from(priceSyncRuns)
    .where(eq(priceSyncRuns.status, "published"))
    .orderBy(desc(priceSyncRuns.tradeDate))
    .limit(1);
  const skipped =
    lastPublished?.d && lastPublished.d < through
      ? (
          await db
            .selectDistinct({ d: dailyPrices.tradeDate })
            .from(dailyPrices)
            .where(and(gt(dailyPrices.tradeDate, lastPublished.d), lte(dailyPrices.tradeDate, through)))
        ).map((r) => r.d)
      : [];
  const days = [...new Set([...skipped, ...backfilled, through, ...(await pendingDueDates(through))])].sort();
  const settlement = { settled: 0, rejected: 0, expired: 0, carried: 0, dates: [] as string[] };
  const corporateActions: AppliedAction[] = [];
  const unrecognised: UnrecognisedAdjustment[] = [];
  for (const day of days) {
    const ca = await applyCorporateActionsFor(day);
    corporateActions.push(...ca.applied);
    unrecognised.push(...ca.unrecognised);
    const r = await settlePendingOrders(day);
    settlement.settled += r.settled;
    settlement.rejected += r.rejected;
    settlement.expired += r.expired;
    settlement.carried += r.carried;
    if (r.settled + r.rejected > 0) settlement.dates.push(day);
  }
  if (unrecognised.length) {
    await db.insert(priceSyncRuns).values({
      tradeDate: through,
      rowsIngested: 0,
      status: "unrecognised_adjustment",
      error: unrecognised.map((u) => `${u.symbol} ${u.exDate}: stored ${u.storedPrevClose} vs NSE ${u.nsePrevClose}`).join("; "),
    });
  }
  const snapshots = await writeSnapshotsFor(through);
  // Only now may pages show `through`: its orders are settled.
  await db.insert(priceSyncRuns).values({ tradeDate: through, rowsIngested: 0, status: "published" });

  return NextResponse.json({
    lagDays: lag,
    ingested,
    historyFetched,
    marketDate: through,
    backfilled,
    retargeted,
    corporateActions,
    unrecognisedAdjustments: unrecognised,
    settled: settlement.settled,
    rejected: settlement.rejected,
    expired: settlement.expired,
    carriedToNextSession: settlement.carried,
    settledDates: settlement.dates,
    snapshots,
  });
}
