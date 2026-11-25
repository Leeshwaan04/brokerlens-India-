ALTER TABLE "orders" ADD COLUMN "order_type" text DEFAULT 'MARKET' NOT NULL;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "limit_price" numeric;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "trigger_price" numeric;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "validity" text DEFAULT 'DAY' NOT NULL;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "before_open" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "expires_on" date;--> statement-breakpoint
ALTER TABLE "orders" ADD CONSTRAINT "orders_type_check" CHECK ("orders"."order_type" IN ('MARKET', 'LIMIT', 'SL_M'));--> statement-breakpoint
ALTER TABLE "orders" ADD CONSTRAINT "orders_validity_check" CHECK ("orders"."validity" IN ('DAY', 'GTT'));