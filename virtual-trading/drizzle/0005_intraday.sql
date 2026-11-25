ALTER TABLE "orders" ADD COLUMN "product" text DEFAULT 'CNC' NOT NULL;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "stop_loss_price" numeric;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "target_price" numeric;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "exit_price" numeric;--> statement-breakpoint
ALTER TABLE "orders" ADD COLUMN "exit_reason" text;--> statement-breakpoint
ALTER TABLE "orders" ADD CONSTRAINT "orders_product_check" CHECK ("orders"."product" IN ('CNC', 'MIS'));