"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { brokerCatalog, virtualAccounts } from "@/lib/schema";
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

  try {
    const result = await placeOrder({ userId: current.userId, symbol, side: side as "BUY" | "SELL", qty });
    revalidateTradingPages();
    return {
      status: "ok",
      message: `${side === "BUY" ? "Buy" : "Sell"} order for ${qty} ${symbol} placed.`,
      orderId: result.orderId,
      targetTradeDate: result.targetTradeDate,
    };
  } catch (err) {
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
  // Header shows the practice broker, so refresh the whole layout, not one page.
  revalidatePath("/", "layout");
  redirect(`${returnTo}?switched=${encodeURIComponent(broker.id)}`);
}
