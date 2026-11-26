import { describe, it, expect, vi } from "vitest";
import { createHmac } from "node:crypto";

vi.mock("./db", () => ({ getDb: () => ({}) }));
const { hmacSha256Hex, isPlanId, plusActive, razorpayConfig, safeEqual, verifyCheckoutSignature, verifyWebhookSignature } =
  await import("./billing");

describe("signatures", () => {
  it("match Node's HMAC-SHA256", async () => {
    expect(await hmacSha256Hex("secret", "order_1|pay_1")).toBe(createHmac("sha256", "secret").update("order_1|pay_1").digest("hex"));
  });
  it("accept Checkout's signature of order_id|payment_id and reject anything else", async () => {
    const good = createHmac("sha256", "k").update("order_A|pay_B").digest("hex");
    expect(await verifyCheckoutSignature("order_A", "pay_B", good, "k")).toBe(true);
    expect(await verifyCheckoutSignature("order_A", "pay_C", good, "k")).toBe(false);
    expect(await verifyCheckoutSignature("order_A", "pay_B", good, "other-secret")).toBe(false);
  });
  it("verify a webhook against its exact raw body", async () => {
    const body = '{"event":"payment.captured"}';
    const sig = createHmac("sha256", "wh").update(body).digest("hex");
    expect(await verifyWebhookSignature(body, sig, "wh")).toBe(true);
    expect(await verifyWebhookSignature(body + " ", sig, "wh")).toBe(false);
  });
  it("compare in constant time without length shortcuts going wrong", () => {
    expect(safeEqual("abc", "abc")).toBe(true);
    expect(safeEqual("abc", "abd")).toBe(false);
    expect(safeEqual("abc", "ab")).toBe(false);
  });
});

describe("config and plans", () => {
  it("is off without both keys, and knows test from live", () => {
    expect(razorpayConfig({})).toBeNull();
    expect(razorpayConfig({ RAZORPAY_KEY_ID: "rzp_test_x" })).toBeNull();
    expect(razorpayConfig({ RAZORPAY_KEY_ID: "rzp_test_x", RAZORPAY_KEY_SECRET: "s" })?.mode).toBe("test");
    expect(razorpayConfig({ RAZORPAY_KEY_ID: "rzp_live_x", RAZORPAY_KEY_SECRET: "s" })?.mode).toBe("live");
  });
  it("accepts only known plans", () => {
    expect(isPlanId("plus_year")).toBe(true);
    expect(isPlanId("toString")).toBe(false);
    expect(isPlanId("free")).toBe(false);
  });
  it("treats Plus as active only before its end", () => {
    const now = new Date("2026-11-25T00:00:00Z");
    expect(plusActive(new Date("2026-11-26T00:00:00Z"), now)).toBe(true);
    expect(plusActive(new Date("2026-11-24T00:00:00Z"), now)).toBe(false);
    expect(plusActive(null, now)).toBe(false);
  });
});
