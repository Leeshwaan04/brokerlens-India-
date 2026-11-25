import { describe, it, expect } from "vitest";
import { shortDate, signedPct, signedInr } from "./format";

describe("format", () => {
  it("formats a Postgres date as a short Indian-style date", () => {
    expect(shortDate("2026-11-18")).toBe("18 Nov 2026");
    expect(shortDate(null)).toBe("");
  });

  it("signs percentages and never shows -0.00%", () => {
    expect(signedPct(1.234)).toBe("+1.23%");
    expect(signedPct(-0.001)).toBe("0.00%");
    expect(signedPct(-2.5)).toBe("-2.50%");
  });

  it("signs rupee amounts", () => {
    expect(signedInr(0)).not.toContain("-");
    expect(signedInr(-10).startsWith("-")).toBe(true);
    expect(signedInr(10).startsWith("+")).toBe(true);
  });
});
