// Order placement and settlement. See the plan's "Order simulation" section
// for the full rules this implements.
//
// Equity delivery (CNC-equivalent) only, no intraday. An order never looks at
// a live price: it is always priced at whatever daily_prices row lands for
// its target_trade_date, resolved at placement time by market-calendar.ts
// and filled later by settlePendingOrders() once that close is published.

import { and, eq, asc, lte } from "drizzle-orm";
import { getDb } from "./db";
import {
  orders,
  holdings,
  virtualAccounts,
  dailyPrices,
  marketHolidays,
  realizedPnlEvents,
  brokerCatalog,
  stockUniverse,
  ORDER_SIDES,
  type OrderSide,
} from "./schema";
import { targetTradeDateFor } from "./market-calendar";
import { buyLegFor, sellLegFor, deliveryFeesFromRow, estimateBuyCost, type DeliveryFees } from "./trade-costs";
import { latestClose, latestCloses } from "./prices";

export const MAX_ORDER_QTY = 1_000_000;

export class OrderPlacementError extends Error {}

async function loadHolidaySet(): Promise<Set<string>> {
  const db = getDb();
  const rows = await db.select({ holidayDate: marketHolidays.holidayDate }).from(marketHolidays);
  return new Set(rows.map((r) => r.holidayDate));
}

export interface PlaceOrderInput {
  userId: string;
  symbol: string;
  side: OrderSide;
  qty: number;
  // Idempotency key from the order ticket; the same key never creates a
  // second order for the same account.
  clientOrderId?: string;
}

const CLIENT_ORDER_ID = /^[A-Za-z0-9-]{8,64}$/;

export interface PlaceOrderResult {
  orderId: string;
  targetTradeDate: string;
}

export interface Reservations {
  // Cash already spoken for by PENDING buys, at their estimated cost.
  reservedCash: number;
  // Shares already spoken for by PENDING sells, per symbol.
  pendingSellQty: Map<string, number>;
}

/**
 * What PENDING orders already hold back. Without this, placement only
 * compared each new order against the full balance, so ten pending Rs 9
 * lakh buys could all be accepted against a Rs 10 lakh balance and then all
 * but one rejected at settlement.
 */
export async function getReservations(accountId: string, fees: DeliveryFees): Promise<Reservations> {
  const db = getDb();
  const pending = await db
    .select({ symbol: orders.symbol, side: orders.side, qty: orders.qty })
    .from(orders)
    .where(and(eq(orders.accountId, accountId), eq(orders.status, "PENDING")));
  const closes = await latestCloses(pending.filter((o) => o.side === "BUY").map((o) => o.symbol));
  let reservedCash = 0;
  const pendingSellQty = new Map<string, number>();
  for (const o of pending) {
    if (o.side === "BUY") {
      const c = closes.get(o.symbol);
      if (c) reservedCash += estimateBuyCost(c.close, o.qty, fees);
    } else {
      pendingSellQty.set(o.symbol, (pendingSellQty.get(o.symbol) ?? 0) + o.qty);
    }
  }
  return { reservedCash, pendingSellQty };
}

/**
 * Inserts a PENDING order after checking it against what is actually free:
 * cash not already reserved by pending buys, and shares not already promised
 * to pending sells. No cash or holdings move yet: the authoritative check
 * happens again at settlement time, against the real balance on fill day.
 */
export async function placeOrder(input: PlaceOrderInput): Promise<PlaceOrderResult> {
  if (!(ORDER_SIDES as readonly string[]).includes(input.side)) {
    throw new OrderPlacementError("Choose Buy or Sell.");
  }
  if (!Number.isInteger(input.qty) || input.qty <= 0) {
    throw new OrderPlacementError("Quantity must be a positive whole number.");
  }
  if (input.qty > MAX_ORDER_QTY) {
    throw new OrderPlacementError("Quantity is larger than this simulator accepts in one order.");
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

  // A repeat of an order already placed (a double-click, a retried request)
  // returns that order instead of running the checks again, which would
  // otherwise count the first order's reservation against the repeat.
  const clientOrderId = input.clientOrderId && CLIENT_ORDER_ID.test(input.clientOrderId) ? input.clientOrderId : null;
  if (clientOrderId) {
    const [existing] = await db
      .select({ id: orders.id, targetTradeDate: orders.targetTradeDate })
      .from(orders)
      .where(and(eq(orders.accountId, account.id), eq(orders.clientOrderId, clientOrderId)))
      .limit(1);
    if (existing) return { orderId: existing.id, targetTradeDate: existing.targetTradeDate };
  }

  const [stock] = await db
    .select({ symbol: stockUniverse.symbol, isActive: stockUniverse.isActive })
    .from(stockUniverse)
    .where(eq(stockUniverse.symbol, input.symbol))
    .limit(1);
  if (!stock || !stock.isActive) {
    throw new OrderPlacementError("That stock is not available in this simulator.");
  }

  const last = await latestClose(input.symbol);
  if (last === null) {
    throw new OrderPlacementError("No price data on file for this symbol yet.");
  }

  const [broker] = await db.select().from(brokerCatalog).where(eq(brokerCatalog.id, account.brokerId)).limit(1);
  if (!broker) {
    throw new OrderPlacementError("Your selected broker is no longer available. Choose a broker again.");
  }
  const fees = deliveryFeesFromRow(broker);
  const reservations = await getReservations(account.id, fees);

  if (input.side === "BUY") {
    const available = Number(account.cashBalance) - reservations.reservedCash;
    if (estimateBuyCost(last.close, input.qty, fees) > available) {
      throw new OrderPlacementError(
        "Not enough free virtual cash for this order, counting buys you already have pending.",
      );
    }
  } else {
    const [holding] = await db
      .select()
      .from(holdings)
      .where(and(eq(holdings.accountId, account.id), eq(holdings.symbol, input.symbol)))
      .limit(1);
    const free = (holding?.qty ?? 0) - (reservations.pendingSellQty.get(input.symbol) ?? 0);
    if (free < input.qty) {
      throw new OrderPlacementError(
        free > 0
          ? `You can sell up to ${free} shares, counting sells you already have pending.`
          : "You do not hold any free shares of this stock to sell.",
      );
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
      clientOrderId,
    })
    .onConflictDoNothing({ target: [orders.accountId, orders.clientOrderId] })
    .returning({ id: orders.id, targetTradeDate: orders.targetTradeDate });
  if (inserted) return { orderId: inserted.id, targetTradeDate: inserted.targetTradeDate };

  // Lost a race with an identical request that inserted first.
  const [winner] = await db
    .select({ id: orders.id, targetTradeDate: orders.targetTradeDate })
    .from(orders)
    .where(and(eq(orders.accountId, account.id), eq(orders.clientOrderId, clientOrderId!)))
    .limit(1);
  return { orderId: winner.id, targetTradeDate: winner.targetTradeDate };
}

/** Cancels a PENDING order, only if it belongs to this user. Returns whether it did. */
export async function cancelPendingOrder(userId: string, orderId: string): Promise<boolean> {
  const db = getDb();
  const [account] = await db
    .select({ id: virtualAccounts.id })
    .from(virtualAccounts)
    .where(eq(virtualAccounts.userId, userId))
    .limit(1);
  if (!account) return false;
  const updated = await db
    .update(orders)
    .set({ status: "CANCELLED" })
    .where(and(eq(orders.id, orderId), eq(orders.accountId, account.id), eq(orders.status, "PENDING")))
    .returning({ id: orders.id });
  return updated.length > 0;
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
      // Claim the order. If another run is settling it right now, skip it;
      // if that run already finished, it is no longer PENDING. Either way it
      // can never be filled twice.
      const [claimed] = await tx
        .select({ id: orders.id })
        .from(orders)
        .where(and(eq(orders.id, order.id), eq(orders.status, "PENDING")))
        .for("update", { skipLocked: true });
      if (!claimed) return;

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

      // Lock the account so two orders settling at once cannot both read the
      // same cash balance and overwrite each other's update.
      const [account] = await tx
        .select()
        .from(virtualAccounts)
        .where(eq(virtualAccounts.id, order.accountId))
        .for("update");
      if (!account) return;

      const [broker] = await tx
        .select()
        .from(brokerCatalog)
        .where(eq(brokerCatalog.id, account.brokerId))
        .limit(1);
      if (!broker) return;

      const fees = deliveryFeesFromRow(broker);

      if (order.side === "BUY") {
        const charges = buyLegFor(fillPrice, order.qty, fees);
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

      const charges = sellLegFor(fillPrice, order.qty, fees);
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

/** Distinct target dates of PENDING orders on or before upToDate, oldest first. */
export async function pendingDueDates(upToDate: string): Promise<string[]> {
  const rows = await getDb()
    .selectDistinct({ targetTradeDate: orders.targetTradeDate })
    .from(orders)
    .where(and(eq(orders.status, "PENDING"), lte(orders.targetTradeDate, upToDate)))
    .orderBy(asc(orders.targetTradeDate));
  return rows.map((r) => r.targetTradeDate);
}

/** Distinct target dates of PENDING orders, on or before upToDate, that have no ingested close yet. */
export async function pendingDatesMissingPrices(upToDate: string): Promise<string[]> {
  const db = getDb();
  const due = await db
    .selectDistinct({ targetTradeDate: orders.targetTradeDate })
    .from(orders)
    .where(and(eq(orders.status, "PENDING"), lte(orders.targetTradeDate, upToDate)));
  const missing: string[] = [];
  for (const { targetTradeDate } of due) {
    const [row] = await db
      .select({ id: dailyPrices.id })
      .from(dailyPrices)
      .where(eq(dailyPrices.tradeDate, targetTradeDate))
      .limit(1);
    if (!row) missing.push(targetTradeDate);
  }
  return missing.sort();
}

/** Moves every PENDING order targeting fromDate to toDate. Returns how many moved. */
export async function retargetPendingOrders(fromDate: string, toDate: string): Promise<number> {
  const moved = await getDb()
    .update(orders)
    .set({ targetTradeDate: toDate })
    .where(and(eq(orders.status, "PENDING"), eq(orders.targetTradeDate, fromDate)))
    .returning({ id: orders.id });
  return moved.length;
}
