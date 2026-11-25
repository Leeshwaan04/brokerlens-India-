// Drizzle schema for the Virtual Trading & Investing MVP.
// See /Users/sumitbagewadi/.claude/plans/graceful-painting-neumann.md section 2
// for the design rationale behind each table.

import {
  pgTable,
  text,
  timestamp,
  numeric,
  integer,
  bigserial,
  boolean,
  date,
  uuid,
  uniqueIndex,
  index,
  check,
  jsonb,
} from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

export const users = pgTable("users", {
  id: text("id").primaryKey(), // Clerk user id
  email: text("email").notNull(),
  displayName: text("display_name"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// Synced monthly from pipeline.trade_cost_engine.BROKER_RATES via
// scripts/export_broker_rates.py + scripts/sync-broker-rates.ts. Never
// written to from the app itself.
export const brokerCatalog = pgTable("broker_catalog", {
  id: text("id").primaryKey(), // e.g. 'zerodha', '5paisa'
  brand: text("brand").notNull(),
  tagline: text("tagline"),
  deliveryFlat: numeric("delivery_flat").notNull(),
  deliveryPct: numeric("delivery_pct").notNull(),
  intradayFlat: numeric("intraday_flat").notNull(),
  intradayPct: numeric("intraday_pct").notNull(),
  dpCharge: numeric("dp_charge").notNull(),
  dematAmc: numeric("demat_amc"),
  accountOpen: numeric("account_open"),
  ctaUrl: text("cta_url").notNull(),
  partnerBadge: text("partner_badge"),
  // Set when the broker's own current pricing page confirms a genuine "lower
  // of Rs flat or pct%" cap even though pct is above CAP_RULE_MAX_PCT (see
  // trade-costs.ts). Mirrors cap_verified_asof in pipeline/trade_cost_engine.py.
  capVerifiedAsof: date("cap_verified_asof"),
  // True only for brokers whose full fee schedule brokerlens.in has on file
  // (pipeline/broker_charges_engine.py eligible_keys()). Cost rankings use
  // only these, so no broker is ranked on an incomplete or indicative schedule.
  feeScheduleComplete: boolean("fee_schedule_complete").notNull().default(false),
  syncedAt: timestamp("synced_at", { withTimezone: true }).notNull(),
});

export const stockUniverse = pgTable("stock_universe", {
  symbol: text("symbol").primaryKey(), // NSE TckrSymb, e.g. 'RELIANCE'
  name: text("name").notNull(),
  isin: text("isin"),
  indexMembership: text("index_membership").array().notNull().default(sql`'{}'`),
  isActive: boolean("is_active").notNull().default(true),
});

export const dailyPrices = pgTable(
  "daily_prices",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    symbol: text("symbol")
      .notNull()
      .references(() => stockUniverse.symbol),
    tradeDate: date("trade_date").notNull(),
    open: numeric("open"),
    high: numeric("high"),
    low: numeric("low"),
    close: numeric("close").notNull(),
    volume: numeric("volume"),
    // NSE's previous close as printed in that day's bhavcopy (PrvsClsgPric).
    // NSE adjusts it for splits and bonuses on the ex-date, so comparing it
    // with the close actually stored for the previous session reveals the
    // ratio (see lib/corporate-actions.ts).
    prevClose: numeric("prev_close"),
  },
  (t) => [uniqueIndex("daily_prices_symbol_date_idx").on(t.symbol, t.tradeDate)],
);

export const marketHolidays = pgTable("market_holidays", {
  holidayDate: date("holiday_date").primaryKey(),
  description: text("description"),
});

export const virtualAccounts = pgTable("virtual_accounts", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id), // one account per user in the MVP
  brokerId: text("broker_id")
    .notNull()
    .references(() => brokerCatalog.id),
  cashBalance: numeric("cash_balance").notNull(),
  startingBalance: numeric("starting_balance").notNull().default("1000000"), // virtual Rs 10L
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  // A date, not a timestamp, written at most once a day: enough for daily and
  // weekly active users and retention without logging every visit.
  lastActiveOn: date("last_active_on"),
});

export const ORDER_SIDES = ["BUY", "SELL"] as const;
export type OrderSide = (typeof ORDER_SIDES)[number];

export const ORDER_STATUSES = ["PENDING", "FILLED", "REJECTED", "CANCELLED"] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const orders = pgTable(
  "orders",
  {
  id: uuid("id").primaryKey().defaultRandom(),
  accountId: uuid("account_id")
    .notNull()
    .references(() => virtualAccounts.id),
  symbol: text("symbol")
    .notNull()
    .references(() => stockUniverse.symbol),
  side: text("side").notNull().$type<OrderSide>(),
  qty: integer("qty").notNull(),
  requestedAt: timestamp("requested_at", { withTimezone: true }).notNull().defaultNow(),
  targetTradeDate: date("target_trade_date").notNull(), // the close this order resolves against
  status: text("status").notNull().$type<OrderStatus>().default("PENDING"),
  fillPrice: numeric("fill_price"),
  grossAmount: numeric("gross_amount"),
  brokerage: numeric("brokerage"),
  stt: numeric("stt"),
  exchangeCharges: numeric("exchange_charges"),
  sebiCharges: numeric("sebi_charges"),
  stampDuty: numeric("stamp_duty"),
  gst: numeric("gst"),
  dpCharge: numeric("dp_charge"),
  totalCharges: numeric("total_charges"),
  netAmount: numeric("net_amount"), // debit (BUY) or credit (SELL) to cash_balance
  rejectionReason: text("rejection_reason"),
  filledAt: timestamp("filled_at", { withTimezone: true }),
  // Generated by the order ticket when it renders, so a double-click or a
  // retried request cannot create the same order twice.
  clientOrderId: text("client_order_id"),
  },
  (t) => [
    check("orders_side_check", sql`${t.side} IN ('BUY', 'SELL')`),
    check("orders_qty_positive", sql`${t.qty} > 0`),
    index("orders_account_status_idx").on(t.accountId, t.status),
    uniqueIndex("orders_account_client_order_idx").on(t.accountId, t.clientOrderId),
  ],
);

export const holdings = pgTable(
  "holdings",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    accountId: uuid("account_id")
      .notNull()
      .references(() => virtualAccounts.id),
    symbol: text("symbol")
      .notNull()
      .references(() => stockUniverse.symbol),
    qty: integer("qty").notNull(),
    avgCost: numeric("avg_cost").notNull(), // per-share cost basis, charges-inclusive
  },
  (t) => [uniqueIndex("holdings_account_symbol_idx").on(t.accountId, t.symbol)],
);

export const realizedPnlEvents = pgTable("realized_pnl_events", {
  id: uuid("id").primaryKey().defaultRandom(),
  accountId: uuid("account_id")
    .notNull()
    .references(() => virtualAccounts.id),
  orderId: uuid("order_id")
    .notNull()
    .references(() => orders.id), // the SELL order that closed it
  symbol: text("symbol").notNull(),
  qty: integer("qty").notNull(),
  buyAvgCost: numeric("buy_avg_cost").notNull(),
  sellNetPrice: numeric("sell_net_price").notNull(), // per share, after sell-side charges
  realizedPnl: numeric("realized_pnl").notNull(),
  realizedAt: timestamp("realized_at", { withTimezone: true }).notNull().defaultNow(),
});

export const performanceSnapshots = pgTable(
  "performance_snapshots",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    accountId: uuid("account_id")
      .notNull()
      .references(() => virtualAccounts.id),
    snapshotDate: date("snapshot_date").notNull(),
    portfolioValue: numeric("portfolio_value").notNull(),
    cashBalance: numeric("cash_balance").notNull(),
    holdingsValue: numeric("holdings_value").notNull(),
    unrealizedPnl: numeric("unrealized_pnl").notNull(),
    realizedPnlCumulative: numeric("realized_pnl_cumulative").notNull(),
    totalReturnPct: numeric("total_return_pct").notNull(),
    numClosedTrades: integer("num_closed_trades").notNull(),
    winRate: numeric("win_rate"),
    confidenceScore: numeric("confidence_score"),
  },
  (t) => [uniqueIndex("performance_snapshots_account_date_idx").on(t.accountId, t.snapshotDate)],
);

// One row per split, bonus or consolidation detected and applied, so the
// daily job can never apply the same ex-date twice.
export const corporateActionEvents = pgTable(
  "corporate_action_events",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    symbol: text("symbol")
      .notNull()
      .references(() => stockUniverse.symbol),
    exDate: date("ex_date").notNull(),
    // New shares per old share: 5 for a 1:5 split, 2 for a 1:1 bonus.
    factor: numeric("factor").notNull(),
    ratio: text("ratio").notNull(), // e.g. "5:1"
    holdingsAdjusted: integer("holdings_adjusted").notNull(),
    ordersCancelled: integer("orders_cancelled").notNull(),
    detectedAt: timestamp("detected_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [uniqueIndex("corporate_action_symbol_date_idx").on(t.symbol, t.exDate)],
);

export const watchlistItems = pgTable(
  "watchlist_items",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    accountId: uuid("account_id")
      .notNull()
      .references(() => virtualAccounts.id),
    symbol: text("symbol")
      .notNull()
      .references(() => stockUniverse.symbol),
    addedAt: timestamp("added_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [uniqueIndex("watchlist_account_symbol_idx").on(t.accountId, t.symbol)],
);

// One row per click on an "open a real account" link, written by the
// /go/[brokerId] redirect route before it forwards to the broker's real
// cta_url. This is how conversion is measured: which placement (landing,
// cost replay, order ticket, ...) sent the click, and for which broker. No
// IP, user agent or other personal data is stored; account_id is null for
// signed-out visitors.
export const CTA_PLACEMENTS = [
  "landing",
  "replay",
  "ticket",
  "broker",
  "dashboard",
  "readiness",
  "onboarding",
  "other",
] as const;
export type CtaPlacement = (typeof CTA_PLACEMENTS)[number];

export const ctaClicks = pgTable(
  "cta_clicks",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    accountId: uuid("account_id").references(() => virtualAccounts.id),
    brokerId: text("broker_id")
      .notNull()
      .references(() => brokerCatalog.id),
    placement: text("placement").notNull().$type<CtaPlacement>(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("cta_clicks_broker_created_idx").on(t.brokerId, t.createdAt)],
);

// First-party product analytics, written on the server (route handlers,
// server actions, after() on page renders) so ad blockers cannot drop them.
// Properties never hold IP addresses, user agents, free text or exact money
// amounts (value buckets only). account_id is null for anonymous views.
export const EVENT_NAMES = [
  "landing_viewed",
  "signup_viewed",
  "onboarding_completed",
  "order_rejected",
  "replay_viewed",
  "broker_switched",
  "portfolio_reset",
  "account_deleted",
] as const;
export type EventName = (typeof EVENT_NAMES)[number];

export const events = pgTable(
  "events",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    accountId: uuid("account_id").references(() => virtualAccounts.id),
    name: text("name").notNull().$type<EventName>(),
    props: jsonb("props").$type<Record<string, string | number | boolean | null>>().notNull().default({}),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("events_name_created_idx").on(t.name, t.createdAt)],
);

// Observability for the daily EOD-sync cron job (Slice 2).
export const priceSyncRuns = pgTable("price_sync_runs", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  runAt: timestamp("run_at", { withTimezone: true }).notNull().defaultNow(),
  tradeDate: date("trade_date"),
  rowsIngested: integer("rows_ingested"),
  status: text("status").notNull(),
  error: text("error"),
});
