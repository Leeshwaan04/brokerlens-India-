// Trading-day and order-cutoff helpers. All times are IST (UTC+5:30), since
// NSE's own trading hours and close are defined in IST regardless of where
// this code runs.

const IST_OFFSET_MINUTES = 5 * 60 + 30;
const CUTOFF_HOUR_IST = 15;
const CUTOFF_MINUTE_IST = 30;

function toIst(date: Date): Date {
  return new Date(date.getTime() + IST_OFFSET_MINUTES * 60_000);
}

function dateOnlyIso(date: Date): string {
  // date must already be shifted to IST before calling this.
  return date.toISOString().slice(0, 10);
}

export function isWeekend(isoDate: string): boolean {
  // Treat the ISO date as a calendar date, independent of time zone, so a
  // plain "YYYY-MM-DD" lookup matches market_holidays rows reliably.
  const [y, m, d] = isoDate.split("-").map(Number);
  const day = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return day === 0 || day === 6;
}

export function isTradingDay(isoDate: string, holidaySet: ReadonlySet<string>): boolean {
  return !isWeekend(isoDate) && !holidaySet.has(isoDate);
}

export function nextTradingDay(isoDate: string, holidaySet: ReadonlySet<string>): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  let cursor = new Date(Date.UTC(y, m - 1, d));
  for (let i = 0; i < 14; i++) {
    cursor = new Date(cursor.getTime() + 86_400_000);
    const iso = cursor.toISOString().slice(0, 10);
    if (isTradingDay(iso, holidaySet)) return iso;
  }
  throw new Error(`No trading day found within 14 days after ${isoDate}`);
}

/**
 * UTC calendar date as "YYYY-MM-DD", independent of local timezone. For
 * walking over bhavcopy dates, which are already calendar dates in NSE's
 * own trading-day convention, not a timestamp needing the IST-shift
 * targetTradeDateFor() applies to "now".
 */
export function isoDateOnly(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** The calendar date in India (IST, UTC+5:30) at the given instant. */
export function istDate(now: Date = new Date()): string {
  return new Date(now.getTime() + 330 * 60_000).toISOString().slice(0, 10);
}

/**
 * Up to maxCount trading-day dates, most recent first, starting at isoDate
 * itself (included only if isoDate is a trading day) and walking backward
 * one calendar day at a time, skipping weekends and holidaySet. Used by the
 * EOD-sync cron route to find the latest bhavcopy actually published,
 * mirroring pipeline/sources/nse.py's _bhavcopy_day() walk-back pattern.
 * Never walks back more than 60 calendar days, as a safety bound.
 */
export function previousTradingDaysFrom(
  isoDate: string,
  holidaySet: ReadonlySet<string>,
  maxCount: number,
): string[] {
  const [y, m, d] = isoDate.split("-").map(Number);
  const start = Date.UTC(y, m - 1, d);
  let cursor = new Date(start);
  const out: string[] = [];
  if (isTradingDay(isoDate, holidaySet)) out.push(isoDate);
  while (out.length < maxCount && start - cursor.getTime() < 60 * 86_400_000) {
    cursor = new Date(cursor.getTime() - 86_400_000);
    const iso = cursor.toISOString().slice(0, 10);
    if (isTradingDay(iso, holidaySet)) out.push(iso);
  }
  return out;
}

/**
 * The trade date an order placed "now" should resolve against: today's close
 * if placed on a trading day before the 15:30 IST cutoff (once that close is
 * published), otherwise the next trading day's close.
 */
export function targetTradeDateFor(now: Date, holidaySet: ReadonlySet<string>): string {
  const ist = toIst(now);
  const todayIso = dateOnlyIso(ist);
  const hour = ist.getUTCHours();
  const minute = ist.getUTCMinutes();
  const beforeCutoff = hour < CUTOFF_HOUR_IST || (hour === CUTOFF_HOUR_IST && minute < CUTOFF_MINUTE_IST);

  if (isTradingDay(todayIso, holidaySet) && beforeCutoff) {
    return todayIso;
  }
  return nextTradingDay(todayIso, holidaySet);
}

export type MissingCloseAction = "ingest" | "retarget" | "wait";

/**
 * What to do about a past date that PENDING orders target but that has no
 * ingested close. NSE publishes a bhavcopy for every trading session, so a
 * date it never published, while a LATER date's close is already ingested,
 * had no session: a holiday the calendar did not list yet (the 2027 list,
 * say, before NSE publishes it). Those orders move to the next trading day
 * instead of waiting forever. A fetch error proves nothing, so on an error
 * the orders wait for the next run.
 */
export function missingCloseAction(
  fetchStatus: "ok" | "not_published" | "error",
  knownHoliday: boolean,
  laterCloseIngested: boolean,
): MissingCloseAction {
  if (knownHoliday) return laterCloseIngested ? "retarget" : "wait";
  if (fetchStatus === "ok") return "ingest";
  if (fetchStatus === "not_published" && laterCloseIngested) return "retarget";
  return "wait";
}
