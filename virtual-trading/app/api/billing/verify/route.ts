import { NextResponse } from "next/server";
import { confirmPlusPayment, razorpayConfig } from "@/lib/billing";
import { track } from "@/lib/events";
import { getSessionUserId } from "@/lib/session";

const ID = /^[A-Za-z0-9_]{6,64}$/;
const SIG = /^[a-f0-9]{64}$/;

// Checkout's success handler posts here. Plus is granted only after the
// signature checks out and Razorpay itself confirms the payment was captured.
export async function POST(request: Request) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Sign in first." }, { status: 401 });
  const cfg = razorpayConfig();
  if (!cfg) return NextResponse.json({ error: "Payments are not set up yet." }, { status: 503 });

  const body = await request.json().catch(() => null);
  const orderId = body?.razorpay_order_id;
  const paymentId = body?.razorpay_payment_id;
  const signature = body?.razorpay_signature;
  if (![orderId, paymentId].every((v) => typeof v === "string" && ID.test(v)) || typeof signature !== "string" || !SIG.test(signature)) {
    return NextResponse.json({ error: "That payment response was incomplete." }, { status: 400 });
  }
  try {
    const result = await confirmPlusPayment(cfg, orderId, paymentId, { signature, userId });
    if (!result.ok) {
      await track("payment_failed", { reason: result.reason, mode: cfg.mode });
      return NextResponse.json({ error: "We could not confirm that payment. If money left your account, it will be refunded by Razorpay." }, { status: 400 });
    }
    if (!result.alreadyGranted) await track("payment_succeeded", { mode: cfg.mode });
    return NextResponse.json({ ok: true, plusUntil: result.plusUntil.toISOString() });
  } catch (err) {
    console.error("razorpay verify failed", err);
    return NextResponse.json({ error: "Could not reach Razorpay to confirm. Refresh in a minute; your payment is safe." }, { status: 502 });
  }
}
