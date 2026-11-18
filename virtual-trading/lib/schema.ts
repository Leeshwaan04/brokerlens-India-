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
});

export const ORDER_SIDES = ["BUY", "SELL"] as const;
export type OrderSide = (typeof ORDER_SIDES)[number];

export const ORDER_STATUSES = ["PENDING", "FILLED", "REJECTED", "CANCELLED"] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const orders = pgTable("orders", {
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
});

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

// Observability for the daily EOD-sync cron job (Slice 2).
export const priceSyncRuns = pgTable("price_sync_runs", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  runAt: timestamp("run_at", { withTimezone: true }).notNull().defaultNow(),
  tradeDate: date("trade_date"),
  rowsIngested: integer("rows_ingested"),
  status: text("status").notNull(),
  error: text("error"),
});
