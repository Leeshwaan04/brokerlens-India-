import { describe, it, expect } from "vitest";
import { computeBuyLegCharges, computeSellLegCharges } from "./trade-costs";

// 5paisa's published equity-delivery round trip for a Rs 1,00,000 buy + Rs
// 1,00,000 sell, as computed by pipeline/trade_cost_engine.py's
// calculate_trade_fees() and already live on
// https://www.brokerlens.in/broker/5paisa/charges/: total_charges = 284.20.
// (5paisa: delivery_flat=20, delivery_pct=0, dp_charge=14.75.) Verified by
// hand against that function's exact source before writing this test:
// brokerage 40 (20 buy leg, 20 sell leg) + STT 200 + exchange charges 5.94 +
// SEBI charges 0.20 + stamp duty 15 (buy leg only) + GST 8.31 + DP charge
// 14.75 (sell leg only) = 284.20.
describe("computeBuyLegCharges / computeSellLegCharges against the published 5paisa round trip", () => {
  const PRICE = 1000;
  const QTY = 100; // turnover = 100,000 on each leg
  const DELIVERY_FLAT = 20;
  const DELIVERY_PCT = 0;
  const DP_CHARGE = 14.75;

  it("buy leg matches the real per-leg figures", () => {
    const buy = computeBuyLegCharges(PRICE, QTY, DELIVERY_FLAT, DELIVERY_PCT);
    expect(buy.turnover).toBe(100000);
    expect(buy.brokerage).toBe(20);
    expect(buy.stt).toBe(100); // 0.1% of buy turnover alone, not the round-trip total
    expect(buy.exchangeCharges).toBe(2.97);
    expect(buy.sebiCharges).toBe(0.1);
    expect(buy.stampDuty).toBe(15);
    expect(buy.dpCharge).toBe(0);
  });

  it("sell leg matches the real per-leg figures", () => {
    const sell = computeSellLegCharges(PRICE, QTY, DELIVERY_FLAT, DELIVERY_PCT, DP_CHARGE);
    expect(sell.turnover).toBe(100000);
    expect(sell.brokerage).toBe(20);
    expect(sell.stt).toBe(100);
    expect(sell.exchangeCharges).toBe(2.97);
    expect(sell.sebiCharges).toBe(0.1);
    expect(sell.stampDuty).toBe(0);
    expect(sell.dpCharge).toBe(14.75);
  });

  it("buy leg + sell leg total charges sum to the published round-trip total, within independent-rounding drift", () => {
    const buy = computeBuyLegCharges(PRICE, QTY, DELIVERY_FLAT, DELIVERY_PCT);
    const sell = computeSellLegCharges(PRICE, QTY, DELIVERY_FLAT, DELIVERY_PCT, DP_CHARGE);
    const combined = buy.totalCharges + sell.totalCharges;
    const PUBLISHED_ROUND_TRIP_TOTAL = 284.2;
    // Each leg rounds its own total independently (as it must: they settle on
    // different days and each is persisted on its own order row), whereas
    // the published figure rounds one combined round-trip total once. That
    // difference in rounding order can drift the sum by a paisa or two; it
    // must never drift by more.
    expect(Math.abs(combined - PUBLISHED_ROUND_TRIP_TOTAL)).toBeLessThanOrEqual(0.02);
  });
});

describe("brokerage cap rule", () => {
  it("applies the lower of flat fee or percentage for a discount-broker plan", () => {
    // Groww: delivery_flat=20, delivery_pct=0.001 (min of Rs 20 or 0.1%).
    // At a turnover of 10,000, 0.1% = 10, which is lower than the Rs 20 flat.
    const buy = computeBuyLegCharges(100, 100, 20, 0.001);
    expect(buy.brokerage).toBe(10);
  });

  it("charges the full percentage, uncapped, above the discount-broker threshold", () => {
    // ICICI Direct-shaped plan: delivery_pct=0.0055 (0.55%), no flat-fee cap
    // applies once pct exceeds CAP_RULE_MAX_PCT (0.1%).
    const buy = computeBuyLegCharges(1000, 100, 20, 0.0055);
    expect(buy.brokerage).toBe(100000 * 0.0055);
  });
});
