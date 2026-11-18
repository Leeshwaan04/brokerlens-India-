// Order placement and settlement. See the plan's "Order simulation" section
// for the full rules this implements.
//
// Equity delivery (CNC-equivalent) only, no intraday. An order never looks at
// a live price: it is always priced at whatever daily_prices row lands for
// its target_trade_date, resolved at placement time by market-calendar.ts
// and filled later by settlePendingOrders() once that close is published.

import { and, eq, asc, desc } from "drizzle-orm";
import { getDb } from "./db";
import {
  orders,
  holdings,
  virtualAccounts,
  dailyPrices,
  marketHolidays,
  realizedPnlEvents,
  brokerCatalog,
  type OrderSide,
} from "./schema";
import { targetTradeDateFor } from "./market-calendar";
import { computeBuyLegCharges, computeSellLegCharges } from "./trade-costs";

const AFFORDABILITY_BUFFER_PCT = 0.01; // rough charges estimate at placement time only

export class OrderPlacementError extends Error {}

async function loadHolidaySet(): Promise<Set<string>> {
  const db = getDb();
  const rows = await db.select({ holidayDate: marketHolidays.holidayDate }).from(marketHolidays);
  return new Set(rows.map((r) => r.holidayDate));
}

async function latestKnownClose(symbol: string): Promise<number | null> {
  const db = getDb();
  const [row] = await db
    .select({ close: dailyPrices.close })
    .from(dailyPrices)
    .where(eq(dailyPrices.symbol, symbol))
    .orderBy(desc(dailyPrices.tradeDate))
    .limit(1);
  return row ? Number(row.close) : null;
}

export interface PlaceOrderInput {
  userId: string;
  symbol: string;
  side: OrderSide;
  qty: number;
}

export interface PlaceOrderResult {
  orderId: string;
  targetTradeDate: string;
}

/**
 * Inserts a PENDING order after a best-effort affordability/holdings check
 * against the latest known close. No cash or holdings move yet: the real,
 * authoritative check happens again at settlement time, against whatever the
 * balance actually is on the day the order fills.
 */
export async function placeOrder(input: PlaceOrderInput): Promise<PlaceOrderResult> {
  if (!Number.isInteger(input.qty) || input.qty <= 0) {
    throw new OrderPlacementError("Quantity must be a positive whole number.");
  }

  const db = getDb();
  const [account] = await db
    .select()
    .from(virtualAccounts)
    .where(eq(virtualAccounts.userId, input.userId))
    .limit(1);
  if (!account) {
    throw new OrderPlacementError("No virtual account found. Select a broker first.");
  }

  const lastClose = await latestKnownClose(input.symbol);
  if (lastClose === null) {
    throw new OrderPlacementError("No price data on file for this symbol yet.");
  }

  if (input.side === "BUY") {
    const estimatedCost = lastClose * input.qty * (1 + AFFORDABILITY_BUFFER_PCT);
    if (estimatedCost > Number(account.cashBalance)) {
      throw new OrderPlacementError("Estimated order cost exceeds available virtual cash balance.");
    }
  } else {
    const [holding] = await db
      .select()
      .from(holdings)
      .where(and(eq(holdings.accountId, account.id), eq(holdings.symbol, input.symbol)))
      .limit(1);
    if (!holding || holding.qty < input.qty) {
      throw new OrderPlacementError("Not enough shares held to place this sell order.");
    }
  }

  const holidaySet = await loadHolidaySet();
  const targetTradeDate = targetTradeDateFor(new Date(), holidaySet);

  const [inserted] = await db
    .insert(orders)
    .values({
      accountId: account.id,
      symbol: input.symbol,
      side: input.side,
      qty: input.qty,
      targetTradeDate,
      status: "PENDING",
    })
    .returning({ id: orders.id });

  return { orderId: inserted.id, targetTradeDate };
}

/**
 * Settles every PENDING order whose target_trade_date is tradeDate, against
 * the daily_prices row for that date. Called from the EOD-sync cron route
 * (Slice 2) once a day's close is ingested; also safe to call directly (e.g.
 * from a test, or a manual trigger) against whatever daily_prices already
 * holds for that date, which is how Slice 1 exercises the full loop before
 * the real bhavcopy feed exists.
 */
export async function settlePendingOrders(tradeDate: string): Promise<{ settled: number; rejected: number }> {
  const db = getDb();
  let settled = 0;
  let rejected = 0;

  const pending = await db
    .select()
    .from(orders)
    .where(and(eq(orders.status, "PENDING"), eq(orders.targetTradeDate, tradeDate)))
    .orderBy(asc(orders.requestedAt));

  for (const order of pending) {
    await db.transaction(async (tx) => {
      const [priceRow] = await tx
        .select({ close: dailyPrices.close })
        .from(dailyPrices)
        .where(and(eq(dailyPrices.symbol, order.symbol), eq(dailyPrices.tradeDate, tradeDate)))
        .limit(1);
      if (!priceRow) {
        // Close for this date isn't ingested yet; leave PENDING for the next run.
        return;
      }
      const fillPrice = Number(priceRow.close);

      const [account] = await tx
        .select()
        .from(virtualAccounts)
        .where(eq(virtualAccounts.id, order.accountId))
        .limit(1);
      if (!account) return;

      const [broker] = await tx
        .select()
        .from(brokerCatalog)
        .where(eq(brokerCatalog.id, account.brokerId))
        .limit(1);
      if (!broker) return;

      const deliveryFlat = Number(broker.deliveryFlat);
      const deliveryPct = Number(broker.deliveryPct);

      if (order.side === "BUY") {
        const charges = computeBuyLegCharges(fillPrice, order.qty, deliveryFlat, deliveryPct);
        const netAmount = charges.turnover + charges.totalCharges;

        const currentCash = Number(account.cashBalance);
        if (netAmount > currentCash) {
          await tx
            .update(orders)
            .set({ status: "REJECTED", rejectionReason: "insufficient_funds_at_settlement" })
            .where(eq(orders.id, order.id));
          rejected++;
          return;
        }

        await tx
          .update(virtualAccounts)
          .set({ cashBalance: String(currentCash - netAmount) })
          .where(eq(virtualAccounts.id, account.id));

        const [existing] = await tx
          .select()
          .from(holdings)
          .where(and(eq(holdings.accountId, account.id), eq(holdings.symbol, order.symbol)))
          .limit(1);

        const buyAllInCost = charges.turnover + charges.totalCharges;
        if (existing) {
          const newQty = existing.qty + order.qty;
          const newAvgCost =
            (existing.qty * Number(existing.avgCost) + buyAllInCost) / newQty;
          await tx
            .update(holdings)
            .set({ qty: newQty, avgCost: String(newAvgCost) })
            .where(eq(holdings.id, existing.id));
        } else {
          await tx.insert(holdings).values({
            accountId: account.id,
            symbol: order.symbol,
            qty: order.qty,
            avgCost: String(buyAllInCost / order.qty),
          });
        }

        await tx
          .update(orders)
          .set({
            status: "FILLED",
            fillPrice: String(fillPrice),
            grossAmount: String(charges.turnover),
            brokerage: String(charges.brokerage),
            stt: String(charges.stt),
            exchangeCharges: String(charges.exchangeCharges),
            sebiCharges: String(charges.sebiCharges),
            stampDuty: String(charges.stampDuty),
            gst: String(charges.gst),
            dpCharge: String(charges.dpCharge),
            totalCharges: String(charges.totalCharges),
            netAmount: String(netAmount),
            filledAt: new Date(),
          })
          .where(eq(orders.id, order.id));
        settled++;
        return;
      }

      // SELL
      const [existing] = await tx
        .select()
        .from(holdings)
        .where(and(eq(holdings.accountId, account.id), eq(holdings.symbol, order.symbol)))
        .limit(1);
      if (!existing || existing.qty < order.qty) {
        await tx
          .update(orders)
          .set({ status: "REJECTED", rejectionReason: "insufficient_holdings_at_settlement" })
          .where(eq(orders.id, order.id));
        rejected++;
        return;
      }

      const charges = computeSellLegCharges(fillPrice, order.qty, deliveryFlat, deliveryPct, Number(broker.dpCharge));
      const netAmount = charges.turnover - charges.totalCharges;
      const sellNetPricePerShare = netAmount / order.qty;
      const buyAvgCost = Number(existing.avgCost);
      const realizedPnl = (sellNetPricePerShare - buyAvgCost) * order.qty;

      const currentCash = Number(account.cashBalance);
      await tx
        .update(virtualAccounts)
        .set({ cashBalance: String(currentCash + netAmount) })
        .where(eq(virtualAccounts.id, account.id));

      const remainingQty = existing.qty - order.qty;
      if (remainingQty === 0) {
        await tx.delete(holdings).where(eq(holdings.id, existing.id));
      } else {
        await tx.update(holdings).set({ qty: remainingQty }).where(eq(holdings.id, existing.id));
      }

      await tx.insert(realizedPnlEvents).values({
        accountId: account.id,
        orderId: order.id,
        symbol: order.symbol,
        qty: order.qty,
        buyAvgCost: String(buyAvgCost),
        sellNetPrice: String(sellNetPricePerShare),
        realizedPnl: String(realizedPnl),
      });

      await tx
        .update(orders)
        .set({
          status: "FILLED",
          fillPrice: String(fillPrice),
          grossAmount: String(charges.turnover),
          brokerage: String(charges.brokerage),
          stt: String(charges.stt),
          exchangeCharges: String(charges.exchangeCharges),
          sebiCharges: String(charges.sebiCharges),
          stampDuty: String(charges.stampDuty),
          gst: String(charges.gst),
          dpCharge: String(charges.dpCharge),
          totalCharges: String(charges.totalCharges),
          netAmount: String(netAmount),
          filledAt: new Date(),
        })
        .where(eq(orders.id, order.id));
      settled++;
    });
  }

  return { settled, rejected };
}
