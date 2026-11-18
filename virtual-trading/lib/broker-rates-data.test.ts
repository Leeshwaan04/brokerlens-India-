import { describe, it, expect } from "vitest";
import brokerRates from "../seed/broker-rates.json";

// Parse-only check for the real, committed seed/broker-rates.json (exported
// by scripts/export_broker_rates.py from pipeline.trade_cost_engine.
// BROKER_RATES). This does NOT exercise scripts/sync-broker-rates.ts's
// actual database write, since no real Neon database exists yet; it only
// proves the file sync-broker-rates.ts reads is well-formed and matches the
// shape that script and broker_catalog's schema expect.
describe("seed/broker-rates.json", () => {
  it("has a real, non-empty broker list", () => {
    expect(Array.isArray(brokerRates)).toBe(true);
    expect(brokerRates.length).toBeGreaterThan(0);
  });

  it("every entry has the fields broker_catalog requires, with a real cta_url", () => {
    for (const b of brokerRates as Record<string, unknown>[]) {
      expect(typeof b.id).toBe("string");
      expect(typeof b.brand).toBe("string");
      expect(typeof b.delivery_flat).toBe("number");
      expect(typeof b.delivery_pct).toBe("number");
      expect(typeof b.intraday_flat).toBe("number");
      expect(typeof b.intraday_pct).toBe("number");
      expect(typeof b.dp_charge).toBe("number");
      expect(typeof b.cta_url).toBe("string");
      expect((b.cta_url as string).startsWith("https://")).toBe(true);
    }
  });

  it("has no duplicate broker ids", () => {
    const ids = (brokerRates as { id: string }[]).map((b) => b.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
