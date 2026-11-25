CREATE TABLE "events" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"account_id" uuid,
	"name" text NOT NULL,
	"props" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "virtual_accounts" ADD COLUMN "last_active_on" date;--> statement-breakpoint
ALTER TABLE "events" ADD CONSTRAINT "events_account_id_virtual_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."virtual_accounts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "events_name_created_idx" ON "events" USING btree ("name","created_at");