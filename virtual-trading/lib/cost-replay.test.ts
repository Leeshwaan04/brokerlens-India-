import { describe, it, expect } from "vitest";
import { replayAtBroker, rankBrokersForFills, type ReplayBroker, type ReplayFill } from "./cost-replay";
import { roundTripCharges } from "./trade-costs";

// Real figures from pipeline/trade_cost_engine.py BROKER_RATES.
const FIVE_PAISA = { deliveryFlat: 20, deliveryPct: 0, dpCharge: 14.75, capVerified: false };
const ZERODHA = { deliveryFlat: 0, deliveryPct: 0, dpCharge: 15.34, capVerified: false };
const CHOICE = { deliveryFlat: 20, deliveryPct: 0.002, dpCharge: 11.8, capVerified: true };

const ROUND_TRIP: ReplayFill[] = [
  { side: "BUY", fillPrice: 1000, qty: 100 },
  { side: "SELL", fillPrice: 1000, qty: 100 },
];

describe("replayAtBroker", () => {
  it("matches roundTripCharges for a same-price round trip", () => {
    const r = replayAtBroker(ROUND_TRIP, FIVE_PAISA);
    expect(r.totalCharges).toBeCloseTo(roundTripCharges(100000, FIVE_PAISA), 2);
  });

  it("splits brokerage, DP and taxes so they sum to the total", () => {
    const r = replayAtBroker(ROUND_TRIP, FIVE_PAISA);
    expect(r.brokerage).toBe(40);
    expect(r.dpCharges).toBe(14.75);
    expect(r.brokerage + r.dpCharges + r.taxesAndFees).toBeCloseTo(r.totalCharges, 2);
  });

  it("costs nothing for no fills", () => {
    expect(replayAtBroker([], FIVE_PAISA).totalCharges).toBe(0);
  });
});

describe("rankBrokersForFills", () => {
  const brokers: ReplayBroker[] = [
    { id: "5paisa", brand: "5paisa", fees: FIVE_PAISA },
    { id: "zerodha", brand: "Zerodha", fees: ZERODHA },
    { id: "choice-broking", brand: "Choice", fees: CHOICE },
  ];

  it("ranks cheapest first and numbers ranks from 1", () => {
    const ranked = rankBrokersForFills(ROUND_TRIP, brokers);
    expect(ranked[0].id).toBe("zerodha"); // zero delivery brokerage
    expect(ranked.map((r) => r.rank)).toEqual([1, 2, 3]);
    for (let i = 1; i < ranked.length; i++) {
      expect(ranked[i].totalCharges).toBeGreaterThanOrEqual(ranked[i - 1].totalCharges);
    }
  });

  it("uses the verified cap for Choice, not the uncapped percentage", () => {
    const choice = rankBrokersForFills(ROUND_TRIP, brokers).find((r) => r.id === "choice-broking")!;
    expect(choice.brokerage).toBe(40); // Rs 20 each way, not Rs 200
  });

  it("lists ties alphabetically and gives them the same rank", () => {
    const tied: ReplayBroker[] = [
      { id: "b", brand: "Beta", fees: FIVE_PAISA },
      { id: "z", brand: "Zerodha", fees: ZERODHA },
      { id: "a", brand: "Alpha", fees: FIVE_PAISA },
    ];
    const ranked = rankBrokersForFills(ROUND_TRIP, tied);
    expect(ranked.map((r) => r.brand)).toEqual(["Zerodha", "Alpha", "Beta"]);
    expect(ranked.map((r) => r.rank)).toEqual([1, 2, 2]);
  });
});
