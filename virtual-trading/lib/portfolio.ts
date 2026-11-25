// Shared portfolio valuation helpers, used by the dashboard, portfolio and
// performance pages so they all compute holdings value and unrealized P&L
// the same way.

import { eq } from "drizzle-orm";
import { getDb } from "./db";
import { holdings, stockUniverse } from "./schema";
import { latestCloses } from "./prices";

export interface ValuedHolding {
  symbol: string;
  name: string;
  qty: number;
  avgCost: number;
  lastClose: number | null;
  lastCloseDate: string | null;
  marketValue: number;
  unrealizedPnl: number | null;
}

export async function getValuedHoldings(accountId: string, asOf?: string): Promise<ValuedHolding[]> {
  const db = getDb();
  const rows = await db
    .select({ symbol: holdings.symbol, qty: holdings.qty, avgCost: holdings.avgCost, name: stockUniverse.name })
    .from(holdings)
    .innerJoin(stockUniverse, eq(holdings.symbol, stockUniverse.symbol))
    .where(eq(holdings.accountId, accountId));
  const closes = await latestCloses(rows.map((r) => r.symbol), asOf);

  return rows
    .map((h) => {
      const avgCost = Number(h.avgCost);
      const c = closes.get(h.symbol) ?? null;
      const marketValue = c ? c.close * h.qty : avgCost * h.qty;
      const unrealizedPnl = c ? (c.close - avgCost) * h.qty : null;
      return {
        symbol: h.symbol,
        name: h.name,
        qty: h.qty,
        avgCost,
        lastClose: c?.close ?? null,
        lastCloseDate: c?.tradeDate ?? null,
        marketValue,
        unrealizedPnl,
      };
    })
    .sort((a, b) => b.marketValue - a.marketValue);
}

export function totalHoldingsValue(valued: ValuedHolding[]): number {
  return valued.reduce((sum, h) => sum + h.marketValue, 0);
}

export function totalUnrealizedPnl(valued: ValuedHolding[]): number {
  return valued.reduce((sum, h) => sum + (h.unrealizedPnl ?? 0), 0);
}

export function largestWeight(valued: ValuedHolding[]): number | null {
  const total = totalHoldingsValue(valued);
  if (total <= 0) return null;
  return valued.reduce((max, h) => Math.max(max, h.marketValue), 0) / total;
}
