import { describe, it, expect, vi } from "vitest";

vi.mock("./db", () => ({ getDb: () => ({}) }));
const { marketMoment, marketNow, priceLagDays, publishCeiling } = await import("./market-clock");

// 25 Nov 2026, 11:00 IST = 05:30 UTC
const at = (iso: string) => new Date(iso);
const NO_HOLIDAYS = new Set<string>();

describe("priceLagDays", () => {
  it("defaults to 30 and ignores nonsense", () => {
    expect(priceLagDays({})).toBe(30);
    expect(priceLagDays({ VT_PRICE_LAG_DAYS: "abc" })).toBe(30);
    expect(priceLagDays({ VT_PRICE_LAG_DAYS: "-1" })).toBe(30);
    expect(priceLagDays({ VT_PRICE_LAG_DAYS: "0" })).toBe(0);
    expect(priceLagDays({ VT_PRICE_LAG_DAYS: "45" })).toBe(45);
  });
});

describe("market clock with a 30-day lag", () => {
  it("is exactly 30 days behind", () => {
    expect(marketNow(at("2026-11-25T05:30:00Z"), 30).toISOString()).toBe("2026-10-26T05:30:00.000Z");
  });
  it("reports the session phase in practice-market time", () => {
    expect(marketMoment(NO_HOLIDAYS, at("2026-11-25T03:00:00Z"), 30)).toEqual({ date: "2026-10-26", phase: "pre_open", lagDays: 30 });
    expect(marketMoment(NO_HOLIDAYS, at("2026-11-25T05:30:00Z"), 30).phase).toBe("open");
    expect(marketMoment(NO_HOLIDAYS, at("2026-11-25T10:00:00Z"), 30).phase).toBe("closed");
    // 25 Oct 2026 was a Sunday
    expect(marketMoment(NO_HOLIDAYS, at("2026-11-24T05:30:00Z"), 30).phase).toBe("holiday");
  });
  it("never lets a close be shown before its session has closed, 30 days on", () => {
    expect(publishCeiling(at("2026-11-25T09:59:00Z"), 30)).toBe("2026-10-25"); // 15:29 IST
    expect(publishCeiling(at("2026-11-25T10:00:00Z"), 30)).toBe("2026-10-26"); // 15:30 IST
  });
  it("has no ceiling without a lag", () => {
    expect(publishCeiling(at("2026-11-25T10:00:00Z"), 0)).toBeNull();
  });
});

describe("longDate", async () => {
  const { longDate } = await import("./market-clock");
  it("reads like a dateline", () => {
    expect(longDate("2026-10-26")).toBe("Mon 26 Oct 2026");
  });
});
