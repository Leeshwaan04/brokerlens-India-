// Read-only numbers for the private /admin page. Every figure is a count over
// a period; nothing here returns an email, a name or a single user's activity.

import { count, countDistinct, desc, eq, gte, sql } from "drizzle-orm";
import { getDb } from "./db";
import { brokerCatalog, ctaClicks, events, orders, payments, priceSyncRuns, virtualAccounts } from "./schema";
import { istDate } from "./market-calendar";

/** Comma-separated user ids in ADMIN_USER_IDS. Nobody is an admin by default. */
export function isAdmin(userId: string | null, env: Record<string, string | undefined> = process.env): boolean {
  if (!userId) return false;
  const ids = (env.ADMIN_USER_IDS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return ids.includes(userId);
}

export const PERIODS = [7, 30, 90] as const;

const DAY_MS = 86_400_000;
const n = (v: unknown) => Number(v ?? 0);
const istDay = (col: unknown) => sql<string>`to_char(${col} at time zone 'Asia/Kolkata', 'YYYY-MM-DD')`;

export async function getAdminMetrics(days: number, now: Date = new Date()) {
  const db = getDb();
  const since = new Date(now.getTime() - days * DAY_MS);
  const today = istDate(now);
  const daysAgo = (d: number) => istDate(new Date(now.getTime() - d * DAY_MS));
  const trendSince = new Date(now.getTime() - 13 * DAY_MS);

  const [eventRows, [active], [orderStats], ctaTotals, byPlacement, byBroker, rejections, sources, trend, trendOrders, trendClicks, cronRuns] =
    await Promise.all([
      db
        .select({ name: events.name, total: count(), accounts: countDistinct(events.accountId) })
        .from(events)
        .where(gte(events.createdAt, since))
        .groupBy(events.name),
      db
        .select({
          total: count(),
          dau: sql<number>`count(*) filter (where ${virtualAccounts.lastActiveOn} = ${today})`,
          wau: sql<number>`count(*) filter (where ${virtualAccounts.lastActiveOn} >= ${daysAgo(6)})`,
          mau: sql<number>`count(*) filter (where ${virtualAccounts.lastActiveOn} >= ${daysAgo(29)})`,
        })
        .from(virtualAccounts),
      db
        .select({
          placed: count(),
          accounts: countDistinct(orders.accountId),
          filled: sql<number>`count(*) filter (where ${orders.status} = 'FILLED')`,
          pending: sql<number>`count(*) filter (where ${orders.status} = 'PENDING')`,
          rejected: sql<number>`count(*) filter (where ${orders.status} = 'REJECTED')`,
          cancelled: sql<number>`count(*) filter (where ${orders.status} = 'CANCELLED')`,
        })
        .from(orders)
        .where(gte(orders.requestedAt, since)),
      db
        .select({ total: count(), accounts: countDistinct(ctaClicks.accountId) })
        .from(ctaClicks)
        .where(gte(ctaClicks.createdAt, since)),
      db
        .select({ placement: ctaClicks.placement, clicks: count() })
        .from(ctaClicks)
        .where(gte(ctaClicks.createdAt, since))
        .groupBy(ctaClicks.placement)
        .orderBy(desc(count())),
      db
        .select({ brand: brokerCatalog.brand, clicks: count() })
        .from(ctaClicks)
        .innerJoin(brokerCatalog, eq(ctaClicks.brokerId, brokerCatalog.id))
        .where(gte(ctaClicks.createdAt, since))
        .groupBy(brokerCatalog.brand)
        .orderBy(desc(count()))
        .limit(10),
      db
        .select({ reason: sql<string>`${events.props}->>'reason'`, total: count() })
        .from(events)
        .where(sql`${events.name} = 'order_rejected' and ${events.createdAt} >= ${since}`)
        .groupBy(sql`1`)
        .orderBy(desc(count())),
      db
        .select({
          source: sql<string | null>`${events.props}->>'utm_source'`,
          landings: sql<number>`count(*) filter (where ${events.name} = 'landing_viewed')`,
          signups: sql<number>`count(*) filter (where ${events.name} = 'onboarding_completed')`,
        })
        .from(events)
        .where(sql`${events.name} in ('landing_viewed', 'onboarding_completed') and ${events.createdAt} >= ${since}`)
        .groupBy(sql`1`)
        .orderBy(desc(sql`3`), desc(sql`2`))
        .limit(15),
      db
        .select({ day: istDay(events.createdAt), name: events.name, total: count() })
        .from(events)
        .where(sql`${events.name} in ('landing_viewed', 'onboarding_completed') and ${events.createdAt} >= ${trendSince}`)
        .groupBy(sql`1`, events.name),
      db
        .select({ day: istDay(orders.requestedAt), total: count() })
        .from(orders)
        .where(gte(orders.requestedAt, trendSince))
        .groupBy(sql`1`),
      db
        .select({ day: istDay(ctaClicks.createdAt), total: count() })
        .from(ctaClicks)
        .where(gte(ctaClicks.createdAt, trendSince))
        .groupBy(sql`1`),
      db.select().from(priceSyncRuns).orderBy(desc(priceSyncRuns.runAt)).limit(8),
    ]);
  const revenue = await db
    .select({
      mode: payments.mode,
      paid: sql<number>`count(*) filter (where ${payments.status} = 'paid')`,
      started: count(),
      paise: sql<number>`coalesce(sum(${payments.amountPaise}) filter (where ${payments.status} = 'paid'), 0)`,
    })
    .from(payments)
    .where(gte(payments.createdAt, since))
    .groupBy(payments.mode);

  const ev = (name: string) => eventRows.find((r) => r.name === name);
  const funnel = [
    { step: "Landing page views", value: n(ev("landing_viewed")?.total), note: "Signed-out visits to the home page" },
    { step: "Sign-up page views", value: n(ev("signup_viewed")?.total) },
    { step: "Accounts created", value: n(ev("onboarding_completed")?.total), note: "Finished choosing a practice broker" },
    { step: "Accounts that placed an order", value: n(orderStats?.accounts) },
    { step: "Accounts that opened the cost replay", value: n(ev("replay_viewed")?.accounts) },
    {
      step: "Accounts that followed an account-opening link",
      value: n(ctaTotals[0]?.accounts),
      note: `${n(ctaTotals[0]?.total)} clicks in all, including signed-out visitors`,
    },
  ];

  const trendDays = Array.from({ length: 14 }, (_, i) => daysAgo(13 - i));
  const at = (rows: { day: string; total: number }[], day: string) => n(rows.find((r) => r.day === day)?.total);
  const daily = trendDays.map((day) => ({
    day,
    landings: at(
      trend.filter((r) => r.name === "landing_viewed"),
      day,
    ),
    signups: at(
      trend.filter((r) => r.name === "onboarding_completed"),
      day,
    ),
    orders: at(trendOrders, day),
    clicks: at(trendClicks, day),
  }));

  return {
    funnel,
    active: { total: n(active?.total), dau: n(active?.dau), wau: n(active?.wau), mau: n(active?.mau) },
    orders: {
      placed: n(orderStats?.placed),
      filled: n(orderStats?.filled),
      pending: n(orderStats?.pending),
      rejected: n(orderStats?.rejected),
      cancelled: n(orderStats?.cancelled),
    },
    ticketRejections: rejections.map((r) => ({ reason: r.reason ?? "unknown", total: n(r.total) })),
    accountActions: {
      brokerSwitches: n(ev("broker_switched")?.total),
      resets: n(ev("portfolio_reset")?.total),
      deletions: n(ev("account_deleted")?.total),
    },
    byPlacement: byPlacement.map((r) => ({ placement: r.placement, clicks: n(r.clicks) })),
    byBroker: byBroker.map((r) => ({ brand: r.brand, clicks: n(r.clicks) })),
    sources: sources.map((r) => ({ source: r.source, landings: n(r.landings), signups: n(r.signups) })),
    daily,
    cronRuns,
    revenue: revenue.map((r) => ({ mode: r.mode, paid: n(r.paid), started: n(r.started), rupees: n(r.paise) / 100 })),
    hoursSinceLastOkSync: (() => {
      const ok = cronRuns.find((r) => r.status === "ok");
      return ok ? (now.getTime() - ok.runAt.getTime()) / 3_600_000 : null;
    })(),
  };
}
