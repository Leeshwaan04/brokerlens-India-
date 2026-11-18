import { describe, it, expect } from "vitest";
import { isTradingDay, previousTradingDaysFrom } from "./market-calendar";
import holidaysFile from "../seed/market-holidays.json";

// Real NSE CM-segment holidays for 2026 (see seed/market-holidays.json's
// "source" field: pulled from data/manual/nse_holidays.json, itself fetched
// live from NSE by pipeline/sources/nse_holidays.py).
const HOLIDAYS = new Set(holidaysFile.holidays.map((h) => h.date));

describe("isTradingDay against the real 2026 NSE holiday calendar", () => {
  it("treats a real trading day as a trading day", () => {
    expect(isTradingDay("2026-11-18", HOLIDAYS)).toBe(true); // Wednesday, not a holiday
  });

  it("treats a real weekday holiday (Diwali-Balipratipada) as a non-trading day", () => {
    expect(isTradingDay("2026-11-10", HOLIDAYS)).toBe(false); // Tuesday
  });

  it("treats a weekend as a non-trading day even though it's not in the holiday list", () => {
    expect(isTradingDay("2026-11-07", HOLIDAYS)).toBe(false); // Saturday
  });
});

describe("previousTradingDaysFrom against the real 2026 NSE holiday calendar", () => {
  it("walks back over a real holiday (Diwali-Balipratipada, Tue 2026-11-10) and the weekend around it", () => {
    // Starting Wed 2026-11-11 (a real trading day): 11-11 included, then
    // 11-10 (holiday) and 11-08/11-09 weekend skipped -> 11-09 (Mon) is
    // itself a real trading day, not a holiday, so it counts; continuing
    // back skips the 11-07/11-08 weekend to reach 11-06 (Fri).
    expect(previousTradingDaysFrom("2026-11-11", HOLIDAYS, 3)).toEqual([
      "2026-11-11",
      "2026-11-09",
      "2026-11-06",
    ]);
  });

  it("does not include the starting date when it is itself a holiday", () => {
    const result = previousTradingDaysFrom("2026-11-10", HOLIDAYS, 1);
    expect(result).toEqual(["2026-11-09"]);
  });
});
