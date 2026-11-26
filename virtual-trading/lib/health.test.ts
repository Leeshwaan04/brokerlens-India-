import { describe, expect, it } from "vitest";
import { MIN_PRICE_RUNWAY_DAYS, priceRunwayDays, priceSupplyStatus } from "./health";

describe("priceRunwayDays", () => {
  it("counts the days before the practice market reaches the newest close", () => {
    // Launch day: closes to 25 Nov, today 26 Nov, 30-day lag.
    expect(priceRunwayDays("2026-11-25", "2026-11-26", 30)).toBe(29);
    expect(priceRunwayDays("2026-11-25", "2026-12-25", 30)).toBe(0);
    expect(priceRunwayDays("2026-11-25", "2027-01-04", 30)).toBe(-10);
  });

  it("crosses month and year ends", () => {
    expect(priceRunwayDays("2026-12-31", "2027-01-02", 30)).toBe(28);
  });
});

describe("priceSupplyStatus", () => {
  it("warns below the minimum runway and when nothing is stored", () => {
    expect(priceSupplyStatus(MIN_PRICE_RUNWAY_DAYS)).toBe("ok");
    expect(priceSupplyStatus(MIN_PRICE_RUNWAY_DAYS - 1)).toBe("low");
    expect(priceSupplyStatus(null)).toBe("low");
  });
});
