CREATE TABLE "price_history" (
	"symbol" text NOT NULL,
	"trade_date" date NOT NULL,
	"open_p" integer NOT NULL,
	"high_p" integer NOT NULL,
	"low_p" integer NOT NULL,
	"close_p" integer NOT NULL,
	"prev_close_p" integer,
	"volume" bigint,
	CONSTRAINT "price_history_symbol_trade_date_pk" PRIMARY KEY("symbol","trade_date")
);
--> statement-breakpoint
CREATE TABLE "price_history_days" (
	"trade_date" date PRIMARY KEY NOT NULL,
	"source" text NOT NULL,
	"rows" integer NOT NULL,
	"status" text NOT NULL,
	"fetched_at" timestamp with time zone DEFAULT now() NOT NULL
);
