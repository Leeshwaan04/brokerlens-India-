CREATE TABLE "corporate_action_events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"symbol" text NOT NULL,
	"ex_date" date NOT NULL,
	"factor" numeric NOT NULL,
	"ratio" text NOT NULL,
	"holdings_adjusted" integer NOT NULL,
	"orders_cancelled" integer NOT NULL,
	"detected_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "watchlist_items" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid NOT NULL,
	"symbol" text NOT NULL,
	"added_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "daily_prices" ADD COLUMN "prev_close" numeric;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "client_order_id" text;--> statement-breakpoint
ALTER TABLE "corporate_action_events" ADD CONSTRAINT "corporate_action_events_symbol_stock_universe_symbol_fk" FOREIGN KEY ("symbol") REFERENCES "public"."stock_universe"("symbol") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "watchlist_items" ADD CONSTRAINT "watchlist_items_account_id_virtual_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."virtual_accounts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "watchlist_items" ADD CONSTRAINT "watchlist_items_symbol_stock_universe_symbol_fk" FOREIGN KEY ("symbol") REFERENCES "public"."stock_universe"("symbol") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "corporate_action_symbol_date_idx" ON "corporate_action_events" USING btree ("symbol","ex_date");--> statement-breakpoint
CREATE UNIQUE INDEX "watchlist_account_symbol_idx" ON "watchlist_items" USING btree ("account_id","symbol");--> statement-breakpoint
CREATE UNIQUE INDEX "orders_account_client_order_idx" ON "orders" USING btree ("account_id","client_order_id");