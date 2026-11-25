CREATE TABLE "cta_clicks" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid,
	"broker_id" text NOT NULL,
	"placement" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "broker_catalog" ADD COLUMN "cap_verified_asof" date;--> statement-breakpoint
ALTER TABLE "broker_catalog" ADD COLUMN "fee_schedule_complete" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "cta_clicks" ADD CONSTRAINT "cta_clicks_account_id_virtual_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."virtual_accounts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "cta_clicks" ADD CONSTRAINT "cta_clicks_broker_id_broker_catalog_id_fk" FOREIGN KEY ("broker_id") REFERENCES "public"."broker_catalog"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "cta_clicks_broker_created_idx" ON "cta_clicks" USING btree ("broker_id","created_at");--> statement-breakpoint
CREATE INDEX "orders_account_status_idx" ON "orders" USING btree ("account_id","status");--> statement-breakpoint
ALTER TABLE "orders" ADD CONSTRAINT "orders_side_check" CHECK ("orders"."side" IN ('BUY', 'SELL'));--> statement-breakpoint
ALTER TABLE "orders" ADD CONSTRAINT "orders_qty_positive" CHECK ("orders"."qty" > 0);