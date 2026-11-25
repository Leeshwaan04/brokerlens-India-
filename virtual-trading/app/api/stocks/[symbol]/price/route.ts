import { NextResponse } from "next/server";
import { and, desc, eq, lte } from "drizzle-orm";
import { getSessionUserId } from "@/lib/session";
import { getDb } from "@/lib/db";
import { dailyPrices } from "@/lib/schema";
import { getMarketAsOf } from "@/lib/market-clock";

export async function GET(_request: Request, context: { params: Promise<{ symbol: string }> }) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { symbol } = await context.params;
  // Never later than the practice market's date (see market-clock.ts).
  const asOf = await getMarketAsOf();
  if (!asOf) return NextResponse.json({ error: "No price data on file for this symbol" }, { status: 404 });
  const db = getDb();
  const rows = await db
    .select({ tradeDate: dailyPrices.tradeDate, close: dailyPrices.close })
    .from(dailyPrices)
    .where(and(eq(dailyPrices.symbol, symbol.toUpperCase()), lte(dailyPrices.tradeDate, asOf)))
    .orderBy(desc(dailyPrices.tradeDate))
    .limit(30);

  if (rows.length === 0) {
    return NextResponse.json({ error: "No price data on file for this symbol" }, { status: 404 });
  }

  return NextResponse.json({
    symbol: symbol.toUpperCase(),
    lastClose: rows[0],
    history: rows,
  });
}
