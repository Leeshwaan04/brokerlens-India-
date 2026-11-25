"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { and, eq } from "drizzle-orm";
import { clerkClient } from "@clerk/nextjs/server";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { brokerCatalog, stockUniverse, virtualAccounts, watchlistItems } from "@/lib/schema";
import { deleteUserData, resetPortfolio } from "@/lib/account-admin";
import { isDevAuth } from "@/lib/session";
import { track } from "@/lib/events";
import { ORDER_TYPE_LABEL, type OrderType, type Validity } from "@/lib/fills";
import { cancelPendingOrder, placeOrder, OrderPlacementError } from "@/lib/order-engine";

export interface OrderActionState {
  status: "idle" | "ok" | "error";
  message: string;
  orderId?: string;
  targetTradeDate?: string;
}

function revalidateTradingPages() {
  for (const p of ["/dashboard", "/trade", "/orders", "/portfolio", "/performance", "/costs"]) revalidatePath(p);
}

/**
 * The order ticket's form action. Returns state for useActionState rather
 * than redirecting with a message in the URL: the old version rendered
 * `?result=ok:<any text>` as a system notice, so a crafted link could show
 * arbitrary text styled as an official message.
 */
export async function placeOrderAction(_prev: OrderActionState, formData: FormData): Promise<OrderActionState> {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const symbol = String(formData.get("symbol") ?? "").trim().toUpperCase();
  const side = String(formData.get("side") ?? "");
  const qty = Number(formData.get("qty"));
  const clientOrderId = String(formData.get("clientOrderId") ?? "") || undefined;
  const orderType = String(formData.get("orderType") ?? "MARKET") as OrderType;
  const validity = String(formData.get("validity") ?? "DAY") as Validity;
  const price = (name: string) => {
    const raw = String(formData.get(name) ?? "").trim();
    return raw === "" ? null : Number(raw);
  };

  try {
    const result = await placeOrder({
      userId: current.userId,
      symbol,
      side: side as "BUY" | "SELL",
      qty,
      clientOrderId,
      orderType,
      validity,
      limitPrice: price("limitPrice"),
      triggerPrice: price("triggerPrice"),
      product: String(formData.get("product") ?? "CNC") === "MIS" ? "MIS" : "CNC",
      stopLossPrice: price("stopLossPrice"),
      targetPrice: price("targetPrice"),
    });
    revalidateTradingPages();
    return {
      status: "ok",
      message: `${String(formData.get("product")) === "MIS" ? "Intraday " : ""}${ORDER_TYPE_LABEL[orderType] ?? "Market"} ${side === "BUY" ? "buy" : "sell"} order for ${qty} ${symbol} placed.`,
      orderId: result.orderId,
      targetTradeDate: result.targetTradeDate,
    };
  } catch (err) {
    await track(
      "order_rejected",
      { reason: err instanceof OrderPlacementError ? err.code : "error", side, symbol, order_type: orderType },
      current.account.id,
    );
    return {
      status: "error",
      message: err instanceof OrderPlacementError ? err.message : "Could not place the order. Please try again.",
    };
  }
}

export async function cancelOrderAction(formData: FormData): Promise<void> {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  const orderId = String(formData.get("orderId") ?? "");
  if (orderId) await cancelPendingOrder(current.userId, orderId);
  revalidateTradingPages();
}

export async function switchBrokerAction(formData: FormData): Promise<void> {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const brokerId = String(formData.get("brokerId") ?? "");
  const returnTo = String(formData.get("returnTo") ?? "/broker") === "/costs" ? "/costs" : "/broker";
  if (!brokerId || brokerId === current.account.brokerId) redirect(returnTo);

  const db = getDb();
  const [broker] = await db.select({ id: brokerCatalog.id }).from(brokerCatalog).where(eq(brokerCatalog.id, brokerId)).limit(1);
  if (!broker) redirect(returnTo);

  await db.update(virtualAccounts).set({ brokerId: broker.id }).where(eq(virtualAccounts.id, current.account.id));
  await track("broker_switched", { from: current.account.brokerId, to: broker.id, via: returnTo.slice(1) }, current.account.id);
  // Header shows the practice broker, so refresh the whole layout, not one page.
  revalidatePath("/", "layout");
  redirect(`${returnTo}?switched=${encodeURIComponent(broker.id)}`);
}

export interface ConfirmActionState {
  status: "idle" | "error";
  message: string;
}

/** Clears holdings, orders and history and restores the starting cash. */
export async function resetPortfolioAction(_prev: ConfirmActionState, formData: FormData): Promise<ConfirmActionState> {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");
  if (String(formData.get("confirm") ?? "").trim().toUpperCase() !== "RESET") {
    return { status: "error", message: 'Type RESET to confirm. Nothing was changed.' };
  }
  await resetPortfolio(current.account.id);
  await track("portfolio_reset", {}, current.account.id);
  revalidatePath("/", "layout");
  redirect("/dashboard");
}

/** Deletes the practice account, its data and (in production) the sign-in identity. */
export async function deleteAccountAction(_prev: ConfirmActionState, formData: FormData): Promise<ConfirmActionState> {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (String(formData.get("confirm") ?? "").trim().toUpperCase() !== "DELETE") {
    return { status: "error", message: 'Type DELETE to confirm. Nothing was changed.' };
  }
  await deleteUserData(current.userId);
  await track("account_deleted"); // anonymous: the account no longer exists
  if (!isDevAuth()) {
    const clerk = await clerkClient();
    await clerk.users.deleteUser(current.userId);
  }
  redirect("/");
}

export async function toggleWatchlistAction(formData: FormData): Promise<void> {
  const current = await getCurrentAccount();
  if (!current?.account) redirect("/sign-in");
  const symbol = String(formData.get("symbol") ?? "").trim().toUpperCase();
  if (!symbol) return;
  const db = getDb();
  const removed = await db
    .delete(watchlistItems)
    .where(and(eq(watchlistItems.accountId, current.account.id), eq(watchlistItems.symbol, symbol)))
    .returning({ id: watchlistItems.id });
  if (removed.length === 0) {
    const [stock] = await db.select({ symbol: stockUniverse.symbol }).from(stockUniverse).where(eq(stockUniverse.symbol, symbol)).limit(1);
    if (stock) {
      await db.insert(watchlistItems).values({ accountId: current.account.id, symbol }).onConflictDoNothing();
    }
  }
  revalidatePath("/trade");
  revalidatePath("/dashboard");
}
