import { describe, it, expect, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined }) }));
vi.mock("./db", () => ({ getDb: () => ({}) }));

const { encodeCampaign, valueBucket } = await import("./events");

describe("valueBucket", () => {
  it("never returns an exact amount", () => {
    expect(valueBucket(67550)).toBe("50k_1l");
    expect(valueBucket(999)).toBe("under_10k");
    expect(valueBucket(10_00_000)).toBe("5l_plus");
  });
});

describe("encodeCampaign", () => {
  it("keeps clean utm tags", () => {
    expect(encodeCampaign(new URLSearchParams("utm_source=brokerlens&utm_medium=nav&utm_campaign=home"))).toBe(
      "brokerlens|nav|home",
    );
  });
  it("ignores visits without a source", () => {
    expect(encodeCampaign(new URLSearchParams("utm_medium=nav"))).toBeNull();
  });
  it("rejects anything that is not a plain tag, so no free text or personal data is stored", () => {
    expect(encodeCampaign(new URLSearchParams("utm_source=someone@example.com"))).toBeNull();
    expect(encodeCampaign(new URLSearchParams("utm_source=x&utm_campaign=<script>"))).toBeNull();
  });
});
