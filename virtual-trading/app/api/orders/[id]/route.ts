import { NextResponse } from "next/server";
import { and, eq } from "drizzle-orm";
import { getSessionUserId } from "@/lib/session";
import { getDb } from "@/lib/db";
import { orders, virtualAccounts } from "@/lib/schema";
import { cancelPendingOrder } from "@/lib/order-engine";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function loadOwnedOrder(userId: string, orderId: string) {
  const db = getDb();
  const [row] = await db
    .select({ order: orders, accountUserId: virtualAccounts.userId })
    .from(orders)
    .innerJoin(virtualAccounts, eq(orders.accountId, virtualAccounts.id))
    .where(and(eq(orders.id, orderId), eq(virtualAccounts.userId, userId)))
    .limit(1);
  return row?.order ?? null;
}

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await context.params;
  if (!UUID.test(id)) return NextResponse.json({ error: "Order not found" }, { status: 404 });
  const order = await loadOwnedOrder(userId, id);
  if (!order) return NextResponse.json({ error: "Order not found" }, { status: 404 });

  return NextResponse.json({ order });
}

export async function DELETE(_request: Request, context: { params: Promise<{ id: string }> }) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await context.params;
  if (!UUID.test(id)) return NextResponse.json({ error: "Order not found" }, { status: 404 });
  const order = await loadOwnedOrder(userId, id);
  if (!order) return NextResponse.json({ error: "Order not found" }, { status: 404 });
  // Cancels only while still PENDING, in one statement, so a fill landing at
  // the same moment can never be overwritten as cancelled.
  if (!(await cancelPendingOrder(userId, id))) {
    return NextResponse.json({ error: "Only a PENDING order can be cancelled" }, { status: 409 });
  }
  return NextResponse.json({ ok: true });
}
