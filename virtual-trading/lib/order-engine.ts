// Order placement and settlement. See the plan's "Order simulation" section
// for the full rules this implements.
//
// Equity delivery (CNC-equivalent) only. An order never looks at a live
// price: it targets a session of the practice market (market-clock.ts) and
// is filled later by settlePendingOrders() against that session's official
// open, high, low and close, by the rules in fills.ts.

import { and, eq, asc, count, lte, sql } from "drizzle-orm";
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
import { isoDateOnly, nextTradingDay, targetTradeDateFor } from "./market-calendar";
import { marketMoment, marketNow } from "./market-clock";
import {
  buyLegFor,
  sellLegFor,
  deliveryFeesFromRow,
  intradayFeesFromRow,
  intradayLegFor,
  type DeliveryFees,
  type IntradayFees,
} from "./trade-costs";
import {
  buyReserve,
  misEntryReference,
  misReserve,
  misTermsError,
  MIS_MARGIN_PCT,
  PRODUCTS,
  resolveIntradayExit,
  type Product,
  GTT_DAYS,
  ORDER_TYPES,
  VALIDITIES,
  priceTermsError,
  resolveFill,
  type OrderType,
  type Validity,
} from "./fills";
import { latestClose, latestCloses } from "./prices";

export const MAX_ORDER_QTY = 1_000_000;
// Per-account caps on waiting orders. Each one is re-checked at every daily
// settlement (GTT orders for up to a year), so one account must not be able
// to load the shared run.
export const MAX_OPEN_ORDERS = 50;
export const MAX_OPEN_GTT = 20;

export class OrderPlacementError extends Error {
  constructor(
    message: string,
    // Stable machine-readable reason for analytics; the message is for people.
    readonly code: string = "other",
  ) {
    super(message);
  }
}

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
  orderType?: OrderType;
  limitPrice?: number | null;
  triggerPrice?: number | null;
  validity?: Validity;
  product?: Product;
  // Intraday only: optional exits within the session.
  stopLossPrice?: number | null;
  targetPrice?: number | null;
}


const CLIENT_ORDER_ID = /^[A-Za-z0-9-]{8,64}$/;

export interface PlaceOrderResult {
  orderId: string;
  targetTradeDate: string;
}

const num = (v: string | null) => (v === null ? null : Number(v));

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
type Reader = { select: ReturnType<typeof getDb>["select"] };

export async function getReservations(
  accountId: string,
  fees: DeliveryFees,
  intraday: IntradayFees,
  db: Reader = getDb(),
): Promise<Reservations> {
  const pending = await db
    .select({
      symbol: orders.symbol,
      side: orders.side,
      qty: orders.qty,
      orderType: orders.orderType,
      limitPrice: orders.limitPrice,
      triggerPrice: orders.triggerPrice,
      product: orders.product,
    })
    .from(orders)
    .where(and(eq(orders.accountId, accountId), eq(orders.status, "PENDING")));
  const closes = await latestCloses(pending.filter((o) => o.side === "BUY" || o.product === "MIS").map((o) => o.symbol));
  let reservedCash = 0;
  const pendingSellQty = new Map<string, number>();
  for (const o of pending) {
    if (o.product === "MIS") {
      // Intraday buys and short sells both block margin; neither touches holdings.
      const c = closes.get(o.symbol);
      if (c) reservedCash += misReserve(o.orderType, c.close, num(o.limitPrice), num(o.triggerPrice), o.qty, intraday);
    } else if (o.side === "BUY") {
      const c = closes.get(o.symbol);
      if (c) reservedCash += buyReserve(o.orderType, c.close, num(o.limitPrice), num(o.triggerPrice), o.qty, fees);
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
    throw new OrderPlacementError("Choose Buy or Sell.", "invalid_side");
  }
  if (!Number.isInteger(input.qty) || input.qty <= 0) {
    throw new OrderPlacementError("Quantity must be a positive whole number.", "invalid_qty");
  }
  if (input.qty > MAX_ORDER_QTY) {
    throw new OrderPlacementError("Quantity is larger than this simulator accepts in one order.", "qty_too_large");
  }
  const orderType: OrderType = input.orderType ?? "MARKET";
  const validity: Validity = input.validity ?? "DAY";
  if (!(ORDER_TYPES as readonly string[]).includes(orderType) || !(VALIDITIES as readonly string[]).includes(validity)) {
    throw new OrderPlacementError("Choose an order type and validity.", "invalid_terms");
  }
  if (validity === "GTT" && orderType === "MARKET") {
    throw new OrderPlacementError("A GTT order waits for a price, so give it a limit or a stop-loss trigger.", "invalid_terms");
  }
  const limitPrice = orderType === "LIMIT" ? (input.limitPrice ?? null) : null;
  const triggerPrice = orderType === "SL_M" ? (input.triggerPrice ?? null) : null;
  const product: Product = input.product ?? "CNC";
  if (!(PRODUCTS as readonly string[]).includes(product)) {
    throw new OrderPlacementError("Choose delivery or intraday.", "invalid_terms");
  }
  const stopLossPrice = product === "MIS" ? (input.stopLossPrice ?? null) : null;
  const targetPrice = product === "MIS" ? (input.targetPrice ?? null) : null;

  const db = getDb();
  const [account] = await db
    .select()
    .from(virtualAccounts)
    .where(eq(virtualAccounts.userId, input.userId))
    .limit(1);
  if (!account) {
    throw new OrderPlacementError("No virtual account found. Select a broker first.", "no_account");
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
    throw new OrderPlacementError("That stock is not available in this simulator.", "not_available");
  }

  const last = await latestClose(input.symbol);
  if (last === null) {
    throw new OrderPlacementError("No price data on file for this symbol yet.", "no_price");
  }
  const termsError = priceTermsError(input.side, orderType, limitPrice, triggerPrice, last.close);
  if (termsError) throw new OrderPlacementError(termsError, "invalid_price");
  const holidaySet = await loadHolidaySet();
  const now = new Date();
  const sessionOpen = marketMoment(holidaySet, now).phase === "open";
  if (product === "MIS") {
    const misError = misTermsError({
      side: input.side,
      type: orderType,
      validity,
      sessionOpen,
      entryRef: misEntryReference(orderType, last.close, limitPrice, triggerPrice),
      stopLoss: stopLossPrice,
      target: targetPrice,
    });
    if (misError) throw new OrderPlacementError(misError, "invalid_intraday");
  }

  const [broker] = await db.select().from(brokerCatalog).where(eq(brokerCatalog.id, account.brokerId)).limit(1);
  if (!broker) {
    throw new OrderPlacementError("Your selected broker is no longer available. Choose a broker again.", "broker_missing");
  }
  const fees = deliveryFeesFromRow(broker);
  const intraday = intradayFeesFromRow(broker);
  // The practice market's session, not the real calendar's (market-clock.ts).
  // An order is in before that session opens unless the market is open now.
  const targetTradeDate = targetTradeDateFor(marketNow(now), holidaySet);
  const beforeOpen = !sessionOpen;
  const expiresOn =
    validity === "GTT" ? isoDateOnly(new Date(new Date(`${targetTradeDate}T00:00:00Z`).getTime() + GTT_DAYS * 86_400_000)) : null;

  // Check and insert under a lock on the account row, so parallel requests
  // queue: each sees the orders the others placed, and none can spend the
  // same free cash or shares twice.
  return db.transaction(async (tx) => {
    const [locked] = await tx
      .select({ cashBalance: virtualAccounts.cashBalance })
      .from(virtualAccounts)
      .where(eq(virtualAccounts.id, account.id))
      .for("update");
    if (!locked) throw new OrderPlacementError("No virtual account found. Select a broker first.", "no_account");

    if (clientOrderId) {
      const [existing] = await tx
        .select({ id: orders.id, targetTradeDate: orders.targetTradeDate })
        .from(orders)
        .where(and(eq(orders.accountId, account.id), eq(orders.clientOrderId, clientOrderId)))
        .limit(1);
      if (existing) return { orderId: existing.id, targetTradeDate: existing.targetTradeDate };
    }

    const [open] = await tx
      .select({ all: count(), gtt: sql<number>`count(*) filter (where ${orders.validity} = 'GTT')` })
      .from(orders)
      .where(and(eq(orders.accountId, account.id), eq(orders.status, "PENDING")));
    if (Number(open?.all ?? 0) >= MAX_OPEN_ORDERS) {
      throw new OrderPlacementError(`You can have up to ${MAX_OPEN_ORDERS} open orders. Cancel some first.`, "too_many_orders");
    }
    if (validity === "GTT" && Number(open?.gtt ?? 0) >= MAX_OPEN_GTT) {
      throw new OrderPlacementError(`You can have up to ${MAX_OPEN_GTT} open GTT orders. Cancel some first.`, "too_many_orders");
    }

    const reservations = await getReservations(account.id, fees, intraday, tx);
    const available = Number(locked.cashBalance) - reservations.reservedCash;
    if (product === "MIS") {
      if (misReserve(orderType, last.close, limitPrice, triggerPrice, input.qty, intraday) > available) {
        throw new OrderPlacementError(
          "Not enough free virtual cash for the intraday margin, counting orders you already have pending.",
          "insufficient_cash",
        );
      }
    } else if (input.side === "BUY") {
      if (buyReserve(orderType, last.close, limitPrice, triggerPrice, input.qty, fees) > available) {
        throw new OrderPlacementError(
          "Not enough free virtual cash for this order, counting buys you already have pending.",
          "insufficient_cash",
        );
      }
    } else {
      const [holding] = await tx
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
          "insufficient_shares",
        );
      }
    }

    const [inserted] = await tx
      .insert(orders)
      .values({
        accountId: account.id,
        symbol: input.symbol,
        side: input.side,
        qty: input.qty,
        targetTradeDate,
        status: "PENDING",
        clientOrderId,
        orderType,
        limitPrice: limitPrice === null ? null : String(limitPrice),
        triggerPrice: triggerPrice === null ? null : String(triggerPrice),
        validity,
        beforeOpen,
        expiresOn,
        product,
        stopLossPrice: stopLossPrice === null ? null : String(stopLossPrice),
        targetPrice: targetPrice === null ? null : String(targetPrice),
      })
      .returning({ id: orders.id, targetTradeDate: orders.targetTradeDate });
    return { orderId: inserted.id, targetTradeDate: inserted.targetTradeDate };
  });
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
export async function settlePendingOrders(
  tradeDate: string,
): Promise<{ settled: number; rejected: number; expired: number; carried: number }> {
  const db = getDb();
  let settled = 0;
  let rejected = 0;
  let expired = 0;
  let carried = 0;
  const holidaySet = await loadHolidaySet();

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
        .where(and(eq(orders.id, order.id), eq(orders.status, "PENDING"), eq(orders.targetTradeDate, tradeDate)))
        .for("update", { skipLocked: true });
      if (!claimed) return;

      const [bar] = await tx
        .select({ open: dailyPrices.open, high: dailyPrices.high, low: dailyPrices.low, close: dailyPrices.close })
        .from(dailyPrices)
        .where(and(eq(dailyPrices.symbol, order.symbol), eq(dailyPrices.tradeDate, tradeDate)))
        .limit(1);
      if (!bar) {
        // Close for this date isn't ingested yet; leave PENDING for the next run.
        return;
      }
      const fillPrice = resolveFill(
        {
          side: order.side,
          type: order.orderType,
          limitPrice: num(order.limitPrice),
          triggerPrice: num(order.triggerPrice),
          beforeOpen: order.beforeOpen,
        },
        { open: num(bar.open), high: num(bar.high), low: num(bar.low), close: Number(bar.close) },
      );
      if (fillPrice === null) {
        // Its price was not reached. A day order ends with the session; a GTT
        // order waits for the next one, in before it opens, until it expires.
        const next = nextTradingDay(tradeDate, holidaySet);
        if (order.validity === "GTT" && order.expiresOn && next <= order.expiresOn) {
          await tx.update(orders).set({ targetTradeDate: next, beforeOpen: true }).where(eq(orders.id, order.id));
          carried++;
        } else {
          await tx
            .update(orders)
            .set({ status: "CANCELLED", rejectionReason: order.validity === "GTT" ? "gtt_expired" : "expired" })
            .where(eq(orders.id, order.id));
          expired++;
        }
        return;
      }

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

      if (order.product === "MIS") {
        // Opened and closed within this session (fills.ts): entry by the
        // order's own terms, exit at its stop-loss, target or the close.
        const intraday = intradayFeesFromRow(broker);
        const exit = resolveIntradayExit(
          order.side,
          fillPrice,
          num(order.stopLossPrice),
          num(order.targetPrice),
          { open: num(bar.open), high: num(bar.high), low: num(bar.low), close: Number(bar.close) },
        );
        const entryLeg = intradayLegFor(order.side, fillPrice, order.qty, intraday);
        const exitLeg = intradayLegFor(order.side === "BUY" ? "SELL" : "BUY", exit.price, order.qty, intraday);
        const charges = entryLeg.totalCharges + exitLeg.totalCharges;
        const gross = order.side === "BUY" ? exitLeg.turnover - entryLeg.turnover : entryLeg.turnover - exitLeg.turnover;
        const pnl = gross - charges;

        // Intraday positions in one session are open at the same time, so this
        // one's margin must fit beside the margin the account's other filled
        // intraday positions that session already used.
        const currentCash = Number(account.cashBalance);
        const [used] = await tx
          .select({ turnover: sql<string>`coalesce(sum(${orders.grossAmount}), 0)` })
          .from(orders)
          .where(
            and(
              eq(orders.accountId, account.id),
              eq(orders.product, "MIS"),
              eq(orders.status, "FILLED"),
              eq(orders.targetTradeDate, tradeDate),
            ),
          );
        const marginInUse = Number(used?.turnover ?? 0) * MIS_MARGIN_PCT;
        if (entryLeg.turnover * MIS_MARGIN_PCT + charges > currentCash - marginInUse) {
          await tx
            .update(orders)
            .set({ status: "REJECTED", rejectionReason: "insufficient_margin_at_settlement" })
            .where(eq(orders.id, order.id));
          rejected++;
          return;
        }
        await tx
          .update(virtualAccounts)
          .set({ cashBalance: String(currentCash + pnl) })
          .where(eq(virtualAccounts.id, account.id));

        const buyLeg = order.side === "BUY" ? entryLeg : exitLeg;
        const sellLeg = order.side === "BUY" ? exitLeg : entryLeg;
        await tx.insert(realizedPnlEvents).values({
          accountId: account.id,
          orderId: order.id,
          symbol: order.symbol,
          qty: order.qty,
          buyAvgCost: String((buyLeg.turnover + buyLeg.totalCharges) / order.qty),
          sellNetPrice: String((sellLeg.turnover - sellLeg.totalCharges) / order.qty),
          realizedPnl: String(pnl),
        });
        const sum = (k: "brokerage" | "stt" | "exchangeCharges" | "sebiCharges" | "stampDuty" | "gst") => String(entryLeg[k] + exitLeg[k]);
        await tx
          .update(orders)
          .set({
            status: "FILLED",
            fillPrice: String(fillPrice),
            exitPrice: String(exit.price),
            exitReason: exit.reason,
            grossAmount: String(entryLeg.turnover),
            brokerage: sum("brokerage"),
            stt: sum("stt"),
            exchangeCharges: sum("exchangeCharges"),
            sebiCharges: sum("sebiCharges"),
            stampDuty: sum("stampDuty"),
            gst: sum("gst"),
            dpCharge: "0",
            totalCharges: String(charges),
            netAmount: String(pnl),
            filledAt: new Date(),
          })
          .where(eq(orders.id, order.id));
        settled++;
        return;
      }

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

  return { settled, rejected, expired, carried };
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
