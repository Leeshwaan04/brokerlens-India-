import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { confirmPlusPayment, razorpayConfig, verifyWebhookSignature } from "@/lib/billing";
import { getDb } from "@/lib/db";
import { track } from "@/lib/events";
import { webhookEvents } from "@/lib/schema";

// Razorpay calls this for payment events (set up in the Razorpay dashboard:
// URL /api/webhooks/razorpay, events payment.captured and order.paid, with
// RAZORPAY_WEBHOOK_SECRET). It grants Plus if the browser never returned
// from Checkout. The signature covers the exact raw body, so read it as text.
export async function POST(request: Request) {
  const cfg = razorpayConfig();
  if (!cfg?.webhookSecret) return NextResponse.json({ error: "Webhook not configured" }, { status: 503 });

  const raw = await request.text();
  const signature = request.headers.get("x-razorpay-signature") ?? "";
  if (!(await verifyWebhookSignature(raw, signature, cfg.webhookSecret))) {
    return NextResponse.json({ error: "Bad signature" }, { status: 400 });
  }

  // A delivery already processed carries the same event id: acknowledge it.
  // The id is recorded only after processing succeeds, so a delivery that
  // failed half-way is retried by Razorpay instead of being dropped.
  const eventId = request.headers.get("x-razorpay-event-id");
  const db = getDb();
  if (eventId) {
    const [seen] = await db.select({ id: webhookEvents.id }).from(webhookEvents).where(eq(webhookEvents.id, eventId)).limit(1);
    if (seen) return NextResponse.json({ ok: true, duplicate: true });
  }

  let event: { event?: string; payload?: { payment?: { entity?: { id?: string; order_id?: string } } } };
  try {
    event = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "Bad body" }, { status: 400 });
  }
  const payment = event.payload?.payment?.entity;
  try {
    if ((event.event === "payment.captured" || event.event === "order.paid") && payment?.id && payment.order_id) {
      // Re-read from Razorpay and grant once, exactly as the Checkout return does.
      const result = await confirmPlusPayment(cfg, payment.order_id, payment.id, {});
      if (result.ok && !result.alreadyGranted) await track("payment_succeeded", { mode: cfg.mode, via: "webhook" });
    } else if (event.event === "payment.failed") {
      await track("payment_failed", { reason: "declined", mode: cfg.mode });
    }
  } catch (err) {
    console.error("razorpay webhook processing failed", err);
    return NextResponse.json({ error: "Processing failed; retry" }, { status: 500 });
  }
  if (eventId) await db.insert(webhookEvents).values({ id: eventId, source: "razorpay" }).onConflictDoNothing();
  return NextResponse.json({ ok: true });
}
