CREATE TABLE "index_closes" (
	"index_key" text NOT NULL,
	"trade_date" date NOT NULL,
	"open" numeric,
	"high" numeric,
	"low" numeric,
	"close" numeric NOT NULL,
	"change_pct" numeric,
	CONSTRAINT "index_closes_index_key_trade_date_pk" PRIMARY KEY("index_key","trade_date")
);
