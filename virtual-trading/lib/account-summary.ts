// Everything the dashboard, performance and cost-replay pages show about one
// account, computed once, the same way, from the account's own rows.

import { and, desc, eq } from "drizzle-orm";
import { getDb } from "./db";
import { brokerCatalog, orders, realizedPnlEvents, stockUniverse, type virtualAccounts } from "./schema";
import { getValuedHoldings, largestWeight, totalHoldingsValue, totalUnrealizedPnl, type ValuedHolding } from "./portfolio";
import { getReservations } from "./order-engine";
import { deliveryFeesFromRow, type DeliveryFees } from "./trade-costs";
import { computeConfidenceScore, MIN_TRADES_FOR_SCORE } from "./scoring";
import { readinessMilestones, readinessProgress, type Milestone } from "./readiness";
import type { ReplayFill } from "./cost-replay";

type AccountRow = typeof virtualAccounts.$inferSelect;
type BrokerRow = typeof brokerCatalog.$inferSelect;

export interface PendingOrderView {
  id: string;
  symbol: string;
  name: string;
  side: "BUY" | "SELL";
  qty: number;
  targetTradeDate: string;
}

export interface AccountSummary {
  account: AccountRow;
  broker: BrokerRow;
  fees: DeliveryFees;
  holdings: ValuedHolding[];
  cash: number;
  reservedCash: number;
  availableCash: number;
  holdingsValue: number;
  portfolioValue: number;
  startingBalance: number;
  totalReturnPct: number;
  unrealizedPnl: number;
  realizedPnl: number;
  closedTrades: number;
  winRate: number | null;
  chargesPaid: number;
  turnoverTraded: number;
  ordersPlaced: number;
  ordersFilled: number;
  pending: PendingOrderView[];
  fills: ReplayFill[];
  score: ReturnType<typeof computeConfidenceScore>;
  milestones: Milestone[];
  readiness: ReturnType<typeof readinessProgress>;
}

/** asOf values holdings at the close on or before that date (used for daily snapshots). */
export async function getAccountSummary(account: AccountRow, asOf?: string): Promise<AccountSummary | null> {
  const db = getDb();
  const [broker] = await db.select().from(brokerCatalog).where(eq(brokerCatalog.id, account.brokerId)).limit(1);
  if (!broker) return null;
  const fees = deliveryFeesFromRow(broker);

  const [holdingsList, allOrders, closed, reservations] = await Promise.all([
    getValuedHoldings(account.id, asOf),
    db
      .select({
        id: orders.id,
        symbol: orders.symbol,
        name: stockUniverse.name,
        side: orders.side,
        qty: orders.qty,
        status: orders.status,
        targetTradeDate: orders.targetTradeDate,
        fillPrice: orders.fillPrice,
        grossAmount: orders.grossAmount,
        totalCharges: orders.totalCharges,
      })
      .from(orders)
      .innerJoin(stockUniverse, eq(orders.symbol, stockUniverse.symbol))
      .where(eq(orders.accountId, account.id))
      .orderBy(desc(orders.requestedAt)),
    db.select({ realizedPnl: realizedPnlEvents.realizedPnl }).from(realizedPnlEvents).where(and(eq(realizedPnlEvents.accountId, account.id))),
    getReservations(account.id, fees),
  ]);

  const cash = Number(account.cashBalance);
  const holdingsValue = totalHoldingsValue(holdingsList);
  const portfolioValue = cash + holdingsValue;
  const startingBalance = Number(account.startingBalance);
  const totalReturnPct = startingBalance > 0 ? ((portfolioValue - startingBalance) / startingBalance) * 100 : 0;

  const filled = allOrders.filter((o) => o.status === "FILLED");
  const closedTrades = closed.length;
  const wins = closed.filter((c) => Number(c.realizedPnl) > 0).length;
  const winRate = closedTrades >= MIN_TRADES_FOR_SCORE ? wins / closedTrades : null;
  const largestHoldingValue = holdingsList.reduce((max, h) => Math.max(max, h.marketValue), 0);

  const score = computeConfidenceScore({ totalReturnPct, numClosedTrades: closedTrades, winRate, largestHoldingValue, portfolioValue });
  const milestones = readinessMilestones({
    ordersPlaced: allOrders.filter((o) => o.status !== "CANCELLED").length,
    ordersFilled: filled.length,
    closedTrades,
    holdingsCount: holdingsList.length,
    largestHoldingWeight: largestWeight(holdingsList),
  });

  return {
    account,
    broker,
    fees,
    holdings: holdingsList,
    cash,
    reservedCash: reservations.reservedCash,
    availableCash: Math.max(0, cash - reservations.reservedCash),
    holdingsValue,
    portfolioValue,
    startingBalance,
    totalReturnPct,
    unrealizedPnl: totalUnrealizedPnl(holdingsList),
    realizedPnl: closed.reduce((s, c) => s + Number(c.realizedPnl), 0),
    closedTrades,
    winRate,
    chargesPaid: filled.reduce((s, o) => s + Number(o.totalCharges ?? 0), 0),
    turnoverTraded: filled.reduce((s, o) => s + Number(o.grossAmount ?? 0), 0),
    ordersPlaced: allOrders.length,
    ordersFilled: filled.length,
    pending: allOrders
      .filter((o) => o.status === "PENDING")
      .map((o) => ({ id: o.id, symbol: o.symbol, name: o.name, side: o.side, qty: o.qty, targetTradeDate: o.targetTradeDate })),
    fills: filled.map((o) => ({ side: o.side, fillPrice: Number(o.fillPrice), qty: o.qty })),
    score,
    milestones,
    readiness: readinessProgress(milestones),
  };
}
