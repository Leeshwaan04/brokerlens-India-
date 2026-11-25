import { describe, it, expect } from "vitest";
import { readinessMilestones, readinessProgress } from "./readiness";

const fresh = { ordersPlaced: 0, ordersFilled: 0, closedTrades: 0, holdingsCount: 0, largestHoldingWeight: null };

describe("readinessMilestones", () => {
  it("starts with nothing done", () => {
    const p = readinessProgress(readinessMilestones(fresh));
    expect(p).toEqual({ done: 0, total: 5, ready: false });
  });

  it("does not count a concentrated portfolio as diversified", () => {
    const m = readinessMilestones({ ...fresh, holdingsCount: 3, largestHoldingWeight: 0.8 });
    expect(m.find((x) => x.id === "diversified")!.done).toBe(false);
  });

  it("counts 3 holdings with none above half as diversified", () => {
    const m = readinessMilestones({ ...fresh, holdingsCount: 3, largestHoldingWeight: 0.4 });
    expect(m.find((x) => x.id === "diversified")!.done).toBe(true);
  });

  it("is ready only when every milestone is done", () => {
    const all = { ordersPlaced: 12, ordersFilled: 12, closedTrades: 5, holdingsCount: 4, largestHoldingWeight: 0.3 };
    expect(readinessProgress(readinessMilestones(all)).ready).toBe(true);
    expect(readinessProgress(readinessMilestones({ ...all, closedTrades: 4 })).ready).toBe(false);
  });
});
