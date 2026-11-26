"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Script from "next/script";
import { buttonClass, cx, Notice } from "./ui";

interface RazorpayResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}
interface RazorpayInstance {
  open(): void;
  on(event: "payment.failed", cb: (e: { error?: { description?: string } }) => void): void;
}
declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => RazorpayInstance;
  }
}

type Status = { tone: "info" | "up" | "down"; text: string } | null;

// Opens Razorpay Checkout for a plan. Card, UPI and bank details are typed
// into Razorpay's own window and never reach BrokerLens. Plus is granted by
// the server only after it verifies the payment with Razorpay.
export function PlusCheckout({ plan, label, testMode }: { plan: string; label: string; testMode: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  async function start() {
    if (!window.Razorpay) {
      setStatus({ tone: "down", text: "The payment window did not load. Check your connection and try again." });
      return;
    }
    setBusy(true);
    setStatus(null);
    const res = await fetch("/api/billing/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    });
    const order = await res.json().catch(() => ({}));
    if (!res.ok) {
      setBusy(false);
      setStatus({ tone: "down", text: order.error ?? "Could not start the payment." });
      return;
    }
    const rzp = new window.Razorpay({
      key: order.keyId,
      order_id: order.orderId,
      amount: order.amountPaise,
      currency: order.currency,
      name: "BrokerLens Plus",
      description: order.label,
      prefill: { email: order.email, name: order.name },
      notes: { plan },
      theme: { color: "#6d7cf5" },
      modal: {
        ondismiss: () => {
          setBusy(false);
          setStatus({ tone: "info", text: "Payment window closed. Nothing was charged." });
        },
      },
      handler: async (response: RazorpayResponse) => {
        setStatus({ tone: "info", text: "Confirming your payment with Razorpay..." });
        const v = await fetch("/api/billing/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(response),
        });
        const out = await v.json().catch(() => ({}));
        setBusy(false);
        if (v.ok) {
          setStatus({ tone: "up", text: "Payment confirmed. Plus is active." });
          router.refresh();
        } else {
          setStatus({ tone: "down", text: out.error ?? "We could not confirm the payment." });
        }
      },
    });
    rzp.on("payment.failed", (e) => {
      setBusy(false);
      setStatus({ tone: "down", text: e.error?.description ?? "The payment did not go through. Nothing was charged." });
    });
    rzp.open();
  }

  return (
    <div className="flex flex-col gap-3">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />
      <button type="button" onClick={start} disabled={busy} className={cx(buttonClass("primary"), "w-full py-3")}>
        {busy ? "Opening payment" : `Pay for ${label}`}
      </button>
      {testMode && <p className="text-xs text-warn">Test mode: no real money moves. Use Razorpay&apos;s test payment options.</p>}
      {status && <Notice tone={status.tone}>{status.text}</Notice>}
    </div>
  );
}
