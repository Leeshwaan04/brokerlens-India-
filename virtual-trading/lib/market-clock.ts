// The practice market's clock. It runs VT_PRICE_LAG_DAYS behind the real
// calendar (default 30): with a 30-day lag, at 11:00 on 25 November the
// practice market is at 11:00 on 26 October, with that day's session, that
// day's holidays and, once that session has closed and been processed, that
// day's official closes. Every price the app shows is therefore at least
// that many days old. A lag of 0 runs on the real calendar.

import { cache } from "react";
import { and, desc, eq, lte, max } from "drizzle-orm";
import { getDb } from "./db";
import { dailyPrices, marketHolidays, priceSyncRuns } from "./schema";
import { istDate, isTradingDay } from "./market-calendar";

export const DEFAULT_PRICE_LAG_DAYS = 30;
const DAY_MS = 86_400_000;
const IST_MS = 330 * 60_000;
export const SESSION_OPEN_MINUTES = 9 * 60 + 15;
export const SESSION_CLOSE_MINUTES = 15 * 60 + 30;

type Env = Record<string, string | undefined>;

/** Whole days the practice market runs behind the real one. Anything unparseable means the default. */
export function priceLagDays(env: Env = process.env): number {
  const raw = env.VT_PRICE_LAG_DAYS?.trim();
  if (!raw) return DEFAULT_PRICE_LAG_DAYS;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 0 && n <= 365 ? n : DEFAULT_PRICE_LAG_DAYS;
}

/** The practice market's "now": the real instant moved back by the lag. */
export function marketNow(now: Date = new Date(), lag: number = priceLagDays()): Date {
  return new Date(now.getTime() - lag * DAY_MS);
}

/** Minutes after midnight IST at an instant. */
export function istMinutes(at: Date): number {
  const ist = new Date(at.getTime() + IST_MS);
  return ist.getUTCHours() * 60 + ist.getUTCMinutes();
}

export type SessionPhase = "pre_open" | "open" | "closed" | "holiday";

export interface MarketMoment {
  /** The practice market's calendar date. */
  date: string;
  phase: SessionPhase;
  lagDays: number;
}

export function marketMoment(holidays: ReadonlySet<string>, now: Date = new Date(), lag: number = priceLagDays()): MarketMoment {
  const m = marketNow(now, lag);
  const date = istDate(m);
  if (!isTradingDay(date, holidays)) return { date, phase: "holiday", lagDays: lag };
  const mins = istMinutes(m);
  const phase: SessionPhase = mins < SESSION_OPEN_MINUTES ? "pre_open" : mins < SESSION_CLOSE_MINUTES ? "open" : "closed";
  return { date, phase, lagDays: lag };
}

/**
 * The newest date whose close may be shown at this moment: the practice
 * market's date once its session has closed, otherwise the day before. With
 * a lag of 0 there is no ceiling beyond what has been ingested.
 */
export function publishCeiling(now: Date = new Date(), lag: number = priceLagDays()): string | null {
  if (lag === 0) return null;
  const m = marketNow(now, lag);
  const date = istDate(m);
  if (istMinutes(m) >= SESSION_CLOSE_MINUTES) return date;
  return istDate(new Date(m.getTime() - DAY_MS));
}

/**
 * The date every price on screen is "as of": the last session the price sync
 * has fully processed (corporate actions applied, orders settled), never
 * later than the publish ceiling. Before the first processed session it
 * falls back to the newest ingested close under the ceiling.
 */
export const getMarketAsOf = cache(async (): Promise<string | null> => {
  const db = getDb();
  const ceiling = publishCeiling();
  const [published] = await db
    .select({ d: max(priceSyncRuns.tradeDate) })
    .from(priceSyncRuns)
    .where(
      ceiling
        ? and(eq(priceSyncRuns.status, "published"), lte(priceSyncRuns.tradeDate, ceiling))
        : eq(priceSyncRuns.status, "published"),
    );
  if (published?.d) return published.d;
  const [latest] = await db
    .select({ d: dailyPrices.tradeDate })
    .from(dailyPrices)
    .where(ceiling ? lte(dailyPrices.tradeDate, ceiling) : undefined)
    .orderBy(desc(dailyPrices.tradeDate))
    .limit(1);
  return latest?.d ?? null;
});

/** NSE trading holidays on file, once per request. */
export const getHolidaySet = cache(async (): Promise<Set<string>> => {
  const rows = await getDb().select({ d: marketHolidays.holidayDate }).from(marketHolidays);
  return new Set(rows.map((r) => r.d));
});

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Mon 26 Oct 2026" for a YYYY-MM-DD date. */
export function longDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MONTHS[m - 1]} ${y}`;
}

export const PHASE_LABEL: Record<SessionPhase, string> = {
  pre_open: "opens 9:15",
  open: "open till 15:30",
  closed: "closed",
  holiday: "closed today",
};
