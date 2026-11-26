// BrokerLens Plus: a prepaid pass bought through Razorpay Checkout.
//
// Flow: the server creates a Razorpay order for a plan and records it; the
// browser opens Razorpay Checkout; on success the browser sends back the
// payment id and signature, which the server verifies (HMAC with the key
// secret), re-reads from Razorpay's API (status, order and amount must
// match), captures if it is only authorised, and only then grants Plus.
// The webhook grants the same way if the browser never comes back. Granting
// is idempotent: a payment row moves from "created" to "paid" once.
//
// Plain fetch and Web Crypto only, so this runs on Node and on Workers.

import { and, eq, sql } from "drizzle-orm";
import { getDb } from "./db";
import { payments, users } from "./schema";

export const PLANS = {
  plus_month: { label: "Plus, 1 month", amountPaise: 9_900, days: 30 },
  plus_year: { label: "Plus, 12 months", amountPaise: 79_900, days: 365 },
} as const;
export type PlanId = keyof typeof PLANS;

export function isPlanId(v: unknown): v is PlanId {
  return typeof v === "string" && Object.hasOwn(PLANS, v);
}

type Env = Record<string, string | undefined>;

export interface RazorpayConfig {
  keyId: string;
  keySecret: string;
  webhookSecret: string | null;
  mode: "test" | "live";
}

/** Razorpay keys from the environment, or null when payments are not configured. */
export function razorpayConfig(env: Env = process.env): RazorpayConfig | null {
  const keyId = env.RAZORPAY_KEY_ID?.trim();
  const keySecret = env.RAZORPAY_KEY_SECRET?.trim();
  if (!keyId || !keySecret) return null;
  const mode = keyId.startsWith("rzp_live_") ? "live" : "test";
  // Test keys on the production site would let anyone get Plus with test
  // cards, so production with test keys counts as payments off unless a
  // staging deploy opts in explicitly.
  if (mode === "test" && env.NODE_ENV === "production" && env.RAZORPAY_ALLOW_TEST_MODE !== "true") return null;
  return { keyId, keySecret, webhookSecret: env.RAZORPAY_WEBHOOK_SECRET?.trim() || null, mode };
}

export function plusActive(plusUntil: Date | null | undefined, now: Date = new Date()): boolean {
  return !!plusUntil && plusUntil.getTime() > now.getTime();
}

// ---------------------------------------------------------------------------
// Signatures

export async function hmacSha256Hex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
  return Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time comparison of two strings. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Checkout's success signature: HMAC-SHA256 of "order_id|payment_id" with the key secret. */
export async function verifyCheckoutSignature(orderId: string, paymentId: string, signature: string, keySecret: string) {
  return safeEqual(await hmacSha256Hex(keySecret, `${orderId}|${paymentId}`), signature);
}

/** A webhook's X-Razorpay-Signature: HMAC-SHA256 of the raw body with the webhook secret. */
export async function verifyWebhookSignature(rawBody: string, signature: string, webhookSecret: string) {
  return safeEqual(await hmacSha256Hex(webhookSecret, rawBody), signature);
}

// ---------------------------------------------------------------------------
// Razorpay API

const API = "https://api.razorpay.com/v1";

async function razorpay<T>(cfg: RazorpayConfig, path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: init?.method ?? "GET",
    headers: {
      Authorization: `Basic ${btoa(`${cfg.keyId}:${cfg.keySecret}`)}`,
      "Content-Type": "application/json",
    },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
  });
  const json = (await res.json().catch(() => ({}))) as T & { error?: { description?: string } };
  if (!res.ok) throw new Error(`Razorpay ${path} failed (${res.status}): ${json.error?.description ?? "no detail"}`);
  return json;
}

interface RazorpayOrder {
  id: string;
  amount: number;
  currency: string;
  status: string;
}

interface RazorpayPayment {
  id: string;
  order_id: string;
  amount: number;
  currency: string;
  status: "created" | "authorized" | "captured" | "refunded" | "failed";
}

/** Creates a Razorpay order for a plan and records it against the user. */
export async function createPlusOrder(cfg: RazorpayConfig, userId: string, plan: PlanId) {
  const p = PLANS[plan];
  const order = await razorpay<RazorpayOrder>(cfg, "/orders", {
    method: "POST",
    body: {
      amount: p.amountPaise,
      currency: "INR",
      receipt: `plus-${Date.now().toString(36)}`,
      notes: { plan, product: "brokerlens_plus" },
    },
  });
  await getDb().insert(payments).values({
    userId,
    plan,
    amountPaise: p.amountPaise,
    currency: "INR",
    mode: cfg.mode,
    razorpayOrderId: order.id,
  });
  return { orderId: order.id, amountPaise: p.amountPaise, currency: "INR", keyId: cfg.keyId, label: p.label };
}

export type ConfirmResult =
  | { ok: true; plusUntil: Date; alreadyGranted: boolean }
  | { ok: false; reason: "bad_signature" | "unknown_order" | "not_paid" | "mismatch" | "duplicate_payment" };

/**
 * Confirms a payment against Razorpay and grants Plus once. Used by the
 * checkout return (signature checked first) and by the webhook (signature
 * on the webhook body checked by the caller). userId, when given, must own
 * the order.
 */
export async function confirmPlusPayment(
  cfg: RazorpayConfig,
  orderId: string,
  paymentId: string,
  opts: { signature?: string; userId?: string },
): Promise<ConfirmResult> {
  if (opts.signature !== undefined && !(await verifyCheckoutSignature(orderId, paymentId, opts.signature, cfg.keySecret))) {
    return { ok: false, reason: "bad_signature" };
  }
  const db = getDb();
  const [row] = await db.select().from(payments).where(eq(payments.razorpayOrderId, orderId)).limit(1);
  if (!row || (opts.userId && row.userId !== opts.userId)) return { ok: false, reason: "unknown_order" };

  // Never trust the browser's word for what was paid: read it back.
  let payment = await razorpay<RazorpayPayment>(cfg, `/payments/${encodeURIComponent(paymentId)}`);
  if (payment.order_id !== orderId || payment.amount !== row.amountPaise || payment.currency !== row.currency) {
    return { ok: false, reason: "mismatch" };
  }
  // The order is already paid by a different payment (a retry, or a late UPI
  // authorisation): never capture this one. Razorpay refunds an authorised
  // payment that is not captured.
  if (row.status === "paid" && row.razorpayPaymentId && row.razorpayPaymentId !== paymentId) {
    return { ok: false, reason: "duplicate_payment" };
  }
  if (payment.status === "authorized") {
    payment = await razorpay<RazorpayPayment>(cfg, `/payments/${encodeURIComponent(paymentId)}/capture`, {
      method: "POST",
      body: { amount: row.amountPaise, currency: row.currency },
    });
  }
  if (payment.status !== "captured") return { ok: false, reason: "not_paid" };
  return grantPlus(orderId, paymentId);
}

/** Marks the order paid and extends the user's Plus, exactly once per order. */
async function grantPlus(orderId: string, paymentId: string): Promise<ConfirmResult> {
  return getDb().transaction(async (tx) => {
    const [paid] = await tx
      .update(payments)
      .set({ status: "paid", razorpayPaymentId: paymentId, paidAt: new Date() })
      .where(and(eq(payments.razorpayOrderId, orderId), eq(payments.status, "created")))
      .returning();
    const [row] = paid
      ? [paid]
      : await tx.select().from(payments).where(eq(payments.razorpayOrderId, orderId)).limit(1);
    if (!row?.userId) return { ok: false, reason: "unknown_order" } as const;
    if (!paid) {
      const [u] = await tx.select({ plusUntil: users.plusUntil }).from(users).where(eq(users.id, row.userId)).limit(1);
      return { ok: true, plusUntil: u?.plusUntil ?? new Date(), alreadyGranted: true } as const;
    }
    const days = isPlanId(row.plan) ? PLANS[row.plan].days : 0;
    // A renewal extends from the current end date, never from today.
    const [u] = await tx
      .update(users)
      .set({ plusUntil: sql`greatest(coalesce(${users.plusUntil}, now()), now()) + make_interval(days => ${days})` })
      .where(eq(users.id, row.userId))
      .returning({ plusUntil: users.plusUntil });
    return { ok: true, plusUntil: u?.plusUntil ?? new Date(), alreadyGranted: false } as const;
  });
}
