import { NextResponse } from "next/server";
import { and, eq } from "drizzle-orm";
import { auth } from "@clerk/nextjs/server";
import { getDb } from "@/lib/db";
import { orders, virtualAccounts } from "@/lib/schema";

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
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await context.params;
  const order = await loadOwnedOrder(userId, id);
  if (!order) return NextResponse.json({ error: "Order not found" }, { status: 404 });

  return NextResponse.json({ order });
}

export async function DELETE(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await context.params;
  const order = await loadOwnedOrder(userId, id);
  if (!order) return NextResponse.json({ error: "Order not found" }, { status: 404 });
  if (order.status !== "PENDING") {
    return NextResponse.json({ error: "Only a PENDING order can be cancelled" }, { status: 409 });
  }

  const db = getDb();
  await db.update(orders).set({ status: "CANCELLED" }).where(eq(orders.id, id));
  return NextResponse.json({ ok: true });
}
