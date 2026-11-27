// Drizzle schema for the Virtual Trading & Investing MVP.
// See /Users/sumitbagewadi/.claude/plans/graceful-painting-neumann.md section 2
// for the design rationale behind each table.

import type { ExitReason, OrderType, Product, Validity } from "./fills";
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
  primaryKey,
  bigint,
} from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

export const users = pgTable("users", {
  id: text("id").primaryKey(), // Clerk user id
  email: text("email").notNull(),
  displayName: text("display_name"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  // BrokerLens Plus is a prepaid pass: active while this is in the future.
  plusUntil: timestamp("plus_until", { withTimezone: true }),
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

// NSE's daily closes for a handful of indices (lib/index-closes.ts): market
// context and the Performance benchmark. Not tradable, so no link to orders.
export const indexCloses = pgTable(
  "index_closes",
  {
    indexKey: text("index_key").notNull(),
    tradeDate: date("trade_date").notNull(),
    open: numeric("open"),
    high: numeric("high"),
    low: numeric("low"),
    close: numeric("close").notNull(),
    changePct: numeric("change_pct"),
  },
  (t) => [primaryKey({ columns: [t.indexKey, t.tradeDate] })],
);

// Long daily history for the charting studio (about five years of the Nifty 500).
// Separate from daily_prices, which feeds order settlement and holds only the
// recent window. Raw prices as NSE printed them, in paise (whole numbers, no
// float drift), plus NSE's printed previous close: that previous close is
// adjusted on a split or bonus ex-date, which is how lib/history/adjust.ts
// finds the adjustments. Never served past the practice market's date.
export const priceHistory = pgTable(
  "price_history",
  {
    symbol: text("symbol").notNull(),
    tradeDate: date("trade_date").notNull(),
    open: integer("open_p").notNull(),
    high: integer("high_p").notNull(),
    low: integer("low_p").notNull(),
    close: integer("close_p").notNull(),
    prevClose: integer("prev_close_p"),
    volume: bigint("volume", { mode: "number" }),
  },
  (t) => [primaryKey({ columns: [t.symbol, t.tradeDate] })],
);

// One row per date the history backfill has looked at, so a rerun skips
// finished days and never re-asks for market holidays.
export const priceHistoryDays = pgTable("price_history_days", {
  tradeDate: date("trade_date").primaryKey(),
  source: text("source").notNull(), // "old" or "new" NSE file format
  rows: integer("rows").notNull(),
  status: text("status").notNull(), // "ok" or "none" (no file published: holiday)
  fetchedAt: timestamp("fetched_at", { withTimezone: true }).notNull().defaultNow(),
});

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
  // Order terms (see lib/fills.ts). MARKET orders fill at the open when in
  // before the session opened, otherwise at the close.
  orderType: text("order_type").notNull().$type<OrderType>().default("MARKET"),
  limitPrice: numeric("limit_price"),
  triggerPrice: numeric("trigger_price"),
  validity: text("validity").notNull().$type<Validity>().default("DAY"),
  // Whether the order was in before its target session opened. A GTT order
  // carried to a later session is, by definition.
  beforeOpen: boolean("before_open").notNull().default(false),
  // Last session a GTT order may fill in.
  expiresOn: date("expires_on"),
  // CNC (delivery) or MIS (intraday: opened and closed in one session, on
  // margin, with an optional stop-loss and target; see fills.ts). For MIS,
  // fill_price is the entry, exit_price where it closed, the charge columns
  // cover both legs and net_amount is the signed P&L credited to cash.
  product: text("product").notNull().$type<Product>().default("CNC"),
  stopLossPrice: numeric("stop_loss_price"),
  targetPrice: numeric("target_price"),
  exitPrice: numeric("exit_price"),
  exitReason: text("exit_reason").$type<ExitReason>(),
  },
  (t) => [
    check("orders_side_check", sql`${t.side} IN ('BUY', 'SELL')`),
    check("orders_qty_positive", sql`${t.qty} > 0`),
    check("orders_type_check", sql`${t.orderType} IN ('MARKET', 'LIMIT', 'SL_M')`),
    check("orders_validity_check", sql`${t.validity} IN ('DAY', 'GTT')`),
    check("orders_product_check", sql`${t.product} IN ('CNC', 'MIS')`),
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
  "plus_viewed",
  "checkout_started",
  "payment_succeeded",
  "payment_failed",
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

// One row per Razorpay order for a Plus pass. Kept after account deletion
// with user_id cleared, because payment records must be retained for tax.
// Card, UPI and bank details never reach BrokerLens: Razorpay handles them.
export const PAYMENT_STATUSES = ["created", "paid", "failed"] as const;
export type PaymentStatus = (typeof PAYMENT_STATUSES)[number];

export const payments = pgTable(
  "payments",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: text("user_id").references(() => users.id),
    plan: text("plan").notNull(),
    amountPaise: integer("amount_paise").notNull(),
    currency: text("currency").notNull().default("INR"),
    mode: text("mode").notNull().$type<"test" | "live">(),
    razorpayOrderId: text("razorpay_order_id").notNull(),
    razorpayPaymentId: text("razorpay_payment_id"),
    status: text("status").notNull().$type<PaymentStatus>().default("created"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    paidAt: timestamp("paid_at", { withTimezone: true }),
  },
  (t) => [
    uniqueIndex("payments_order_idx").on(t.razorpayOrderId),
    uniqueIndex("payments_payment_idx").on(t.razorpayPaymentId),
    check("payments_status_check", sql`${t.status} IN ('created', 'paid', 'failed')`),
    check("payments_amount_positive", sql`${t.amountPaise} > 0`),
  ],
);

// Razorpay webhook deliveries already processed, by their event id, so a
// retried delivery is acknowledged without being applied twice.
export const webhookEvents = pgTable("webhook_events", {
  id: text("id").primaryKey(),
  source: text("source").notNull(),
  receivedAt: timestamp("received_at", { withTimezone: true }).notNull().defaultNow(),
});
