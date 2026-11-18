// Shared portfolio valuation helpers, used by the dashboard, portfolio and
// performance pages so they all compute holdings value and unrealized P&L
// the same way.

import { eq, desc } from "drizzle-orm";
import { getDb } from "./db";
import { holdings, dailyPrices } from "./schema";

export interface ValuedHolding {
  symbol: string;
  qty: number;
  avgCost: number;
  lastClose: number | null;
  marketValue: number;
  unrealizedPnl: number | null;
}

async function latestClose(symbol: string): Promise<number | null> {
  const db = getDb();
  const [row] = await db
    .select({ close: dailyPrices.close })
    .from(dailyPrices)
    .where(eq(dailyPrices.symbol, symbol))
    .orderBy(desc(dailyPrices.tradeDate))
    .limit(1);
  return row ? Number(row.close) : null;
}

export async function getValuedHoldings(accountId: string): Promise<ValuedHolding[]> {
  const db = getDb();
  const rows = await db.select().from(holdings).where(eq(holdings.accountId, accountId));

  return Promise.all(
    rows.map(async (h) => {
      const avgCost = Number(h.avgCost);
      const lastClose = await latestClose(h.symbol);
      const marketValue = lastClose !== null ? lastClose * h.qty : avgCost * h.qty;
      const unrealizedPnl = lastClose !== null ? (lastClose - avgCost) * h.qty : null;
      return { symbol: h.symbol, qty: h.qty, avgCost, lastClose, marketValue, unrealizedPnl };
    }),
  );
}

export function totalHoldingsValue(valued: ValuedHolding[]): number {
  return valued.reduce((sum, h) => sum + h.marketValue, 0);
}

export function totalUnrealizedPnl(valued: ValuedHolding[]): number {
  return valued.reduce((sum, h) => sum + (h.unrealizedPnl ?? 0), 0);
}
