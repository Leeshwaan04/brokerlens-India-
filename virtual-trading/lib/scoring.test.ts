import { describe, it, expect } from "vitest";
import { computeConfidenceScore, MIN_TRADES_FOR_SCORE } from "./scoring";

describe("computeConfidenceScore", () => {
  it("reports not enough trades below the minimum, regardless of return", () => {
    const result = computeConfidenceScore({
      totalReturnPct: 50,
      numClosedTrades: MIN_TRADES_FOR_SCORE - 1,
      winRate: null,
      largestHoldingValue: 0,
      portfolioValue: 100000,
    });
    expect(result.enoughTrades).toBe(false);
  });

  it("scores a flat, inexperienced account at the neutral midpoint", () => {
    const result = computeConfidenceScore({
      totalReturnPct: 0,
      numClosedTrades: 0,
      winRate: null,
      largestHoldingValue: 0,
      portfolioValue: 100000,
    });
    expect(result.score).toBe(50);
    expect(result.label).toBe("Developing"); // 40 <= 50 < 60
  });

  it("rewards positive return and a good win rate with enough trades", () => {
    const result = computeConfidenceScore({
      totalReturnPct: 25,
      numClosedTrades: 20,
      winRate: 0.75,
      largestHoldingValue: 20000,
      portfolioValue: 100000,
    });
    expect(result.enoughTrades).toBe(true);
    expect(result.score).toBeGreaterThan(80);
    expect(result.label).toBe("Strong");
  });

  it("penalizes concentration in a single holding", () => {
    const concentrated = computeConfidenceScore({
      totalReturnPct: 10,
      numClosedTrades: 10,
      winRate: 0.6,
      largestHoldingValue: 90000,
      portfolioValue: 100000,
    });
    const diversified = computeConfidenceScore({
      totalReturnPct: 10,
      numClosedTrades: 10,
      winRate: 0.6,
      largestHoldingValue: 20000,
      portfolioValue: 100000,
    });
    expect(concentrated.score).toBeLessThan(diversified.score);
  });

  it("never goes outside the 0 to 100 range at the extremes", () => {
    const worst = computeConfidenceScore({
      totalReturnPct: -90,
      numClosedTrades: 20,
      winRate: 0,
      largestHoldingValue: 100000,
      portfolioValue: 100000,
    });
    expect(worst.score).toBeGreaterThanOrEqual(0);

    const best = computeConfidenceScore({
      totalReturnPct: 200,
      numClosedTrades: 50,
      winRate: 1,
      largestHoldingValue: 0,
      portfolioValue: 100000,
    });
    expect(best.score).toBeLessThanOrEqual(100);
  });
});
