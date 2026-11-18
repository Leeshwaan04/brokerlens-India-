CREATE TABLE "broker_catalog" (
	"id" text PRIMARY KEY NOT NULL,
	"brand" text NOT NULL,
	"tagline" text,
	"delivery_flat" numeric NOT NULL,
	"delivery_pct" numeric NOT NULL,
	"intraday_flat" numeric NOT NULL,
	"intraday_pct" numeric NOT NULL,
	"dp_charge" numeric NOT NULL,
	"demat_amc" numeric,
	"account_open" numeric,
	"cta_url" text NOT NULL,
	"partner_badge" text,
	"synced_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
CREATE TABLE "daily_prices" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"symbol" text NOT NULL,
	"trade_date" date NOT NULL,
	"open" numeric,
	"high" numeric,
	"low" numeric,
	"close" numeric NOT NULL,
	"volume" numeric
);
--> statement-breakpoint
CREATE TABLE "holdings" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid NOT NULL,
	"symbol" text NOT NULL,
	"qty" integer NOT NULL,
	"avg_cost" numeric NOT NULL
);
--> statement-breakpoint
CREATE TABLE "market_holidays" (
	"holiday_date" date PRIMARY KEY NOT NULL,
	"description" text
);
--> statement-breakpoint
CREATE TABLE "orders" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid NOT NULL,
	"symbol" text NOT NULL,
	"side" text NOT NULL,
	"qty" integer NOT NULL,
	"requested_at" timestamp with time zone DEFAULT now() NOT NULL,
	"target_trade_date" date NOT NULL,
	"status" text DEFAULT 'PENDING' NOT NULL,
	"fill_price" numeric,
	"gross_amount" numeric,
	"brokerage" numeric,
	"stt" numeric,
	"exchange_charges" numeric,
	"sebi_charges" numeric,
	"stamp_duty" numeric,
	"gst" numeric,
	"dp_charge" numeric,
	"total_charges" numeric,
	"net_amount" numeric,
	"rejection_reason" text,
	"filled_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "performance_snapshots" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"account_id" uuid NOT NULL,
	"snapshot_date" date NOT NULL,
	"portfolio_value" numeric NOT NULL,
	"cash_balance" numeric NOT NULL,
	"holdings_value" numeric NOT NULL,
	"unrealized_pnl" numeric NOT NULL,
	"realized_pnl_cumulative" numeric NOT NULL,
	"total_return_pct" numeric NOT NULL,
	"num_closed_trades" integer NOT NULL,
	"win_rate" numeric,
	"confidence_score" numeric
);
--> statement-breakpoint
CREATE TABLE "price_sync_runs" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"run_at" timestamp with time zone DEFAULT now() NOT NULL,
	"trade_date" date,
	"rows_ingested" integer,
	"status" text NOT NULL,
	"error" text
);
--> statement-breakpoint
CREATE TABLE "realized_pnl_events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid NOT NULL,
	"order_id" uuid NOT NULL,
	"symbol" text NOT NULL,
	"qty" integer NOT NULL,
	"buy_avg_cost" numeric NOT NULL,
	"sell_net_price" numeric NOT NULL,
	"realized_pnl" numeric NOT NULL,
	"realized_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "stock_universe" (
	"symbol" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"isin" text,
	"index_membership" text[] DEFAULT '{}' NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" text PRIMARY KEY NOT NULL,
	"email" text NOT NULL,
	"display_name" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "virtual_accounts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"broker_id" text NOT NULL,
	"cash_balance" numeric NOT NULL,
	"starting_balance" numeric DEFAULT '1000000' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "virtual_accounts_user_id_unique" UNIQUE("user_id")
);
--> statement-breakpoint
ALTER TABLE "daily_prices" ADD CONSTRAINT "daily_prices_symbol_stock_universe_symbol_fk" FOREIGN KEY ("symbol") REFERENCES "public"."stock_universe"("symbol") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "holdings" ADD CONSTRAINT "holdings_account_id_virtual_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."virtual_accounts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "holdings" ADD CONSTRAINT "holdings_symbol_stock_universe_symbol_fk" FOREIGN KEY ("symbol") REFERENCES "public"."stock_universe"("symbol") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "orders" ADD CONSTRAINT "orders_account_id_virtual_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."virtual_accounts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "orders" ADD CONSTRAINT "orders_symbol_stock_universe_symbol_fk" FOREIGN KEY ("symbol") REFERENCES "public"."stock_universe"("symbol") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "performance_snapshots" ADD CONSTRAINT "performance_snapshots_account_id_virtual_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."virtual_accounts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "realized_pnl_events" ADD CONSTRAINT "realized_pnl_events_account_id_virtual_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."virtual_accounts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "realized_pnl_events" ADD CONSTRAINT "realized_pnl_events_order_id_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."orders"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "virtual_accounts" ADD CONSTRAINT "virtual_accounts_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "virtual_accounts" ADD CONSTRAINT "virtual_accounts_broker_id_broker_catalog_id_fk" FOREIGN KEY ("broker_id") REFERENCES "public"."broker_catalog"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "daily_prices_symbol_date_idx" ON "daily_prices" USING btree ("symbol","trade_date");--> statement-breakpoint
CREATE UNIQUE INDEX "holdings_account_symbol_idx" ON "holdings" USING btree ("account_id","symbol");--> statement-breakpoint
CREATE UNIQUE INDEX "performance_snapshots_account_date_idx" ON "performance_snapshots" USING btree ("account_id","snapshot_date");