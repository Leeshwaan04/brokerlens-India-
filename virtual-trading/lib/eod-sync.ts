// Daily EOD price sync: fetches NSE's real public bhavcopy (walking back a
// day at a time if the target date's close isn't published yet), upserts
// daily_prices, loads the history the delayed practice market needs, then
// moves the practice market forward and settles every order waiting on it.
//
// Runs as a plain Node script in GitHub Actions (scripts/eod-sync.mts, daily
// at 19:00 IST), not inside the Worker: unzipping and parsing a bhavcopy and
// settling orders takes far more than the 10 ms of CPU a request gets on
// Cloudflare's Free plan. The bearer-guarded route
// app/api/cron/sync-eod-prices calls the same function for hosts without
// that limit.
import { and, desc, eq, gt, lte, sql } from "drizzle-orm";
import { getDb } from "./db";
import {
  dailyPrices,
  indexCloses,
  stockUniverse,
  marketHolidays,
  priceSyncRuns,
} from "./schema";
import { fetchBhavcopy, type DailyPriceRow } from "./bhavcopy";
import { fetchIndexCloses, type IndexCloseRow } from "./index-closes";
import { recordHistoryDay, toHistoryRows, upsertPriceHistory } from "./history/store";
import {
  isoDateOnly,
  missingCloseAction,
  nextTradingDay,
  previousTradingDaysFrom,
  tradingDaysBetween,
} from "./market-calendar";
import { priceLagDays, publishCeiling } from "./market-clock";
import {
  pendingDatesMissingPrices,
  pendingDueDates,
  retargetPendingOrders,
  settlePendingOrders,
} from "./order-engine";
import {
  applyCorporateActionsFor,
  type AppliedAction,
  type UnrecognisedAdjustment,
} from "./corporate-actions";
import { writeSnapshotsFor } from "./snapshots";

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
// A stored day with fewer than this share of the universe's stocks is fetched again.
const THIN_DAY_FRACTION = 0.85;

const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));
const utcDate = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
const shiftDays = (iso: string, days: number) =>
  isoDateOnly(new Date(utcDate(iso).getTime() + days * 86_400_000));

// One statement per session (about 100 rows) rather than one per stock: the
// sync runs far from the database (GitHub's runners to Mumbai), where every
// round trip costs a few hundred milliseconds.
async function upsertDailyPrices(tradeDate: string, rows: DailyPriceRow[]) {
  if (rows.length === 0) return;
  // The charting studio's long history gets the same day (lib/history/store.ts).
  const hist = toHistoryRows(tradeDate, rows);
  await upsertPriceHistory(hist);
  await recordHistoryDay(tradeDate, "new", hist.length, "ok");
  const num = (v: number | null) => (v !== null ? String(v) : null);
  await getDb()
    .insert(dailyPrices)
    .values(
      rows.map((row) => ({
        symbol: row.symbol,
        tradeDate,
        open: num(row.open),
        high: num(row.high),
        low: num(row.low),
        close: String(row.close),
        volume: num(row.volume),
        prevClose: num(row.prevClose),
      })),
    )
    .onConflictDoUpdate({
      target: [dailyPrices.symbol, dailyPrices.tradeDate],
      set: {
        open: sql`excluded.open`,
        high: sql`excluded.high`,
        low: sql`excluded.low`,
        close: sql`excluded.close`,
        volume: sql`excluded.volume`,
        prevClose: sql`excluded.prev_close`,
      },
    });
}

async function upsertIndexCloses(tradeDate: string, rows: IndexCloseRow[]) {
  if (rows.length === 0) return;
  const num = (v: number | null) => (v !== null ? String(v) : null);
  await getDb()
    .insert(indexCloses)
    .values(rows.map((r) => ({ indexKey: r.indexKey, tradeDate, open: num(r.open), high: num(r.high), low: num(r.low), close: String(r.close), changePct: num(r.changePct) })))
    .onConflictDoUpdate({
      target: [indexCloses.indexKey, indexCloses.tradeDate],
      set: { open: sql`excluded.open`, high: sql`excluded.high`, low: sql`excluded.low`, close: sql`excluded.close`, changePct: sql`excluded.change_pct` },
    });
}

/** Index closes for one session. Context only: a miss never fails the sync. */
async function ingestIndexCloses(day: string): Promise<boolean> {
  const res = await fetchIndexCloses(utcDate(day));
  if (res.status !== "ok") return false;
  await upsertIndexCloses(day, res.rows);
  return true;
}

export interface EodSyncOptions {
  /** Real date to start looking for the newest close from (YYYY-MM-DD); today by default. */
  date?: string;
  /** Most missing history days to fetch this run (default 5, at most 60). */
  history?: number;
}

export interface EodSyncResult {
  status: number;
  body: Record<string, unknown>;
}

export async function runEodSync(
  opts: EodSyncOptions = {},
): Promise<EodSyncResult> {
  const db = getDb();
  const startIso = opts.date ?? isoDateOnly(new Date());

  const [holidayRows, universeRows] = await Promise.all([
    db.select({ holidayDate: marketHolidays.holidayDate }).from(marketHolidays),
    db.select({ symbol: stockUniverse.symbol }).from(stockUniverse),
  ]);
  const holidaySet = new Set(holidayRows.map((r) => r.holidayDate));
  const allowedSymbols = new Set(universeRows.map((r) => r.symbol));

  if (allowedSymbols.size === 0) {
    return {
      status: 503,
      body: {
        error:
          "stock_universe is empty; run scripts/sync-stock-universe.ts first",
      },
    };
  }

  const lag = priceLagDays();
  const ceiling = publishCeiling(new Date(), lag);

  // 1. Ingest the newest close NSE has published (walking back over days it
  // has not published yet). With a lag this only stocks up for later: the
  // practice market will not reach these closes for another `lag` days.
  const candidates = previousTradingDaysFrom(
    startIso,
    holidaySet,
    MAX_WALK_BACK_ATTEMPTS,
  );
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
    await ingestIndexCloses(iso).catch(() => false);
    await db
      .insert(priceSyncRuns)
      .values({
        tradeDate: iso,
        rowsIngested: result.rows.length,
        status: "ok",
      });
    ingested = { tradeDate: iso, rows: result.rows.length };
    break;
  }
  if (!ingested) {
    const errorMessage = `No published bhavcopy found among candidate trading day(s): ${candidates.join(", ") || "none"}.${
      errors.length ? ` Fetch errors: ${errors.join("; ")}` : ""
    }`;
    await db
      .insert(priceSyncRuns)
      .values({
        tradeDate: startIso,
        rowsIngested: 0,
        status: "failed",
        error: errorMessage,
      });
    // Without a lag there is nothing new to settle against. With one, the
    // practice market runs on closes ingested weeks ago, so carry on.
    if (lag === 0) return { status: 502, body: { error: errorMessage } };
  }

  // 2. History the delayed market needs, oldest first, a few days per run.
  const historyFetched: string[] = [];
  if (ceiling) {
    const requested = Number(opts.history);
    const budget =
      Number.isInteger(requested) && requested > 0
        ? Math.min(requested, MAX_HISTORY_FETCHES)
        : DEFAULT_HISTORY_FETCHES;
    const have = new Set(
      (
        await db
          .selectDistinct({ d: dailyPrices.tradeDate })
          .from(dailyPrices)
          .where(
            gt(
              dailyPrices.tradeDate,
              shiftDays(ceiling, -HISTORY_LEAD_DAYS - 1),
            ),
          )
      ).map((r) => r.d),
    );
    const missingDays = tradingDaysBetween(shiftDays(ceiling, -HISTORY_LEAD_DAYS), ingested?.tradeDate ?? startIso, holidaySet).filter(
      (d) => !have.has(d),
    );
    // Days stored when the universe was smaller (100 stocks, now 500): fetched
    // again so every stock has its history. The upsert is idempotent.
    const perDay = await db
      .select({ d: dailyPrices.tradeDate, n: sql<number>`count(*)::int` })
      .from(dailyPrices)
      .where(gt(dailyPrices.tradeDate, shiftDays(ceiling, -HISTORY_LEAD_DAYS - 1)))
      .groupBy(dailyPrices.tradeDate);
    const thinDays = perDay.filter((r) => r.n < allowedSymbols.size * THIN_DAY_FRACTION).map((r) => r.d);
    const wanted = [...new Set([...missingDays, ...thinDays])].sort();
    for (const day of wanted.slice(0, budget)) {
      await pause(NSE_PAUSE_MS);
      const back = await fetchBhavcopy(utcDate(day), allowedSymbols);
      if (back.status === "ok" && back.rows.length > 0) {
        await upsertDailyPrices(day, back.rows);
        await ingestIndexCloses(day).catch(() => false);
        await db
          .insert(priceSyncRuns)
          .values({
            tradeDate: day,
            rowsIngested: back.rows.length,
            status: "ok",
          });
        historyFetched.push(day);
      }
    }
  }

  // 2b. Index closes for stored sessions that lack them (the first run after
  // the table was added, or a day whose index file was late). A few per run
  // is plenty once caught up.
  const indexFetched: string[] = [];
  {
    const haveIndex = new Set((await db.selectDistinct({ d: indexCloses.tradeDate }).from(indexCloses)).map((r) => r.d));
    const priced = (
      await db.selectDistinct({ d: dailyPrices.tradeDate }).from(dailyPrices).where(gt(dailyPrices.tradeDate, shiftDays(startIso, -200)))
    ).map((r) => r.d);
    for (const day of priced.filter((d) => !haveIndex.has(d)).sort().slice(0, MAX_HISTORY_FETCHES)) {
      await pause(NSE_PAUSE_MS);
      if (await ingestIndexCloses(day).catch(() => false)) indexFetched.push(day);
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
    return {
      status: 503,
      body: {
        ingested,
        historyFetched,
        error:
          "No closes on file for the practice market's date yet; run again with a larger history budget",
      },
    };
  }

  // Every earlier day a PENDING order is still waiting on: backfill its
  // close, or, if NSE never published one while a later close exists, it
  // was a market holiday missing from the calendar, so move those orders to
  // the next trading day rather than leave them PENDING forever.
  const backfilled: string[] = [];
  const retargeted: { from: string; to: string; orders: number }[] = [];
  for (const missing of (await pendingDatesMissingPrices(through)).slice(
    0,
    MAX_BACKFILL_DATES,
  )) {
    const knownHoliday = holidaySet.has(missing);
    let status: "ok" | "not_published" | "error" = "not_published";
    if (!knownHoliday) {
      const back = await fetchBhavcopy(utcDate(missing), allowedSymbols);
      if (back.status === "ok" && back.rows.length > 0) {
        await upsertDailyPrices(missing, back.rows);
        await ingestIndexCloses(missing).catch(() => false);
        await db
          .insert(priceSyncRuns)
          .values({
            tradeDate: missing,
            rowsIngested: back.rows.length,
            status: "ok",
          });
        backfilled.push(missing);
        continue;
      }
      status = back.status === "error" ? "error" : "not_published";
    }
    // pendingDatesMissingPrices only returns dates on or before `through`
    // that lack a close, and `through` has one, so a later close exists.
    if (
      missingCloseAction(status, knownHoliday, missing < through) === "retarget"
    ) {
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
            .where(
              and(
                gt(dailyPrices.tradeDate, lastPublished.d),
                lte(dailyPrices.tradeDate, through),
              ),
            )
        ).map((r) => r.d)
      : [];
  const days = [
    ...new Set([
      ...skipped,
      ...backfilled,
      through,
      ...(await pendingDueDates(through)),
    ]),
  ].sort();
  const settlement = {
    settled: 0,
    rejected: 0,
    expired: 0,
    carried: 0,
    dates: [] as string[],
  };
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
      error: unrecognised
        .map(
          (u) =>
            `${u.symbol} ${u.exDate}: stored ${u.storedPrevClose} vs NSE ${u.nsePrevClose}`,
        )
        .join("; "),
    });
  }
  const snapshots = await writeSnapshotsFor(through);
  // Only now may pages show `through`: its orders are settled.
  await db
    .insert(priceSyncRuns)
    .values({ tradeDate: through, rowsIngested: 0, status: "published" });

  return {
    status: 200,
    body: {
      lagDays: lag,
      ingested,
      historyFetched,
      indexSessionsFetched: indexFetched.length,
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
    },
  };
}
