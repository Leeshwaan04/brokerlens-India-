import { NextResponse } from "next/server";
import { eq, desc } from "drizzle-orm";
import { getSessionUserId } from "@/lib/session";
import { getDb } from "@/lib/db";
import { dailyPrices } from "@/lib/schema";

export async function GET(_request: Request, context: { params: Promise<{ symbol: string }> }) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { symbol } = await context.params;
  const db = getDb();
  const rows = await db
    .select({ tradeDate: dailyPrices.tradeDate, close: dailyPrices.close })
    .from(dailyPrices)
    .where(eq(dailyPrices.symbol, symbol.toUpperCase()))
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
