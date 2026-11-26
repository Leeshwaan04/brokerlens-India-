import { NextResponse } from "next/server";
import { crossSiteRejection } from "@/lib/request-guard";
import { and, count, eq, gte } from "drizzle-orm";
import { ensureUserRow } from "@/lib/auth";
import { createPlusOrder, isPlanId, razorpayConfig } from "@/lib/billing";
import { getDb } from "@/lib/db";
import { track } from "@/lib/events";
import { payments, users } from "@/lib/schema";
import { getSessionUserId } from "@/lib/session";

// Starts a Plus purchase: creates the Razorpay order and returns what
// Checkout needs. The amount comes from the server's plan list, never the browser.
export async function POST(request: Request) {
  const refused = crossSiteRejection(request);
  if (refused) return refused;
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Sign in first." }, { status: 401 });
  const cfg = razorpayConfig();
  if (!cfg) return NextResponse.json({ error: "Payments are not set up yet." }, { status: 503 });

  const body = await request.json().catch(() => null);
  const plan = body?.plan;
  if (!isPlanId(plan)) return NextResponse.json({ error: "Choose a plan." }, { status: 400 });

  // At most a handful of unpaid checkouts an hour per person: each one is a
  // real Razorpay order.
  const [recent] = await getDb()
    .select({ n: count() })
    .from(payments)
    .where(and(eq(payments.userId, userId), gte(payments.createdAt, new Date(Date.now() - 3_600_000))));
  if ((recent?.n ?? 0) >= 10) {
    return NextResponse.json({ error: "Too many payment attempts. Please try again in an hour." }, { status: 429 });
  }

  await ensureUserRow(userId);
  const [user] = await getDb().select({ email: users.email, name: users.displayName }).from(users).where(eq(users.id, userId)).limit(1);
  try {
    const order = await createPlusOrder(cfg, userId, plan);
    await track("checkout_started", { plan, mode: cfg.mode });
    return NextResponse.json({ ...order, email: user?.email ?? "", name: user?.name ?? "", mode: cfg.mode });
  } catch (err) {
    console.error("razorpay order failed", err);
    return NextResponse.json({ error: "Could not start the payment. Please try again." }, { status: 502 });
  }
}
