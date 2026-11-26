import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { indexCloseUrl, parseIndexCloseCsv, TRACKED_INDICES } from "./index-closes";

const fixture = readFileSync(join(__dirname, "__fixtures__", "index-close-fixture.csv"), "utf8");

describe("indexCloseUrl", () => {
  it("uses NSE's DDMMYYYY file name", () => {
    expect(indexCloseUrl(new Date(Date.UTC(2026, 10, 5)))).toBe(
      "https://nsearchives.nseindia.com/content/indices/ind_close_all_05112026.csv",
    );
  });
});

describe("parseIndexCloseCsv", () => {
  const rows = parseIndexCloseCsv(fixture);
  const byKey = Object.fromEntries(rows.map((r) => [r.indexKey, r]));

  it("keeps only the tracked indices, matching NSE's names case-insensitively", () => {
    const keys = rows.map((r) => r.indexKey);
    expect(keys).not.toContain("Nifty IT");
    expect(new Set(keys).size).toBe(keys.length);
    for (const k of keys) expect(TRACKED_INDICES.map((t) => t.key)).toContain(k);
    expect(byKey.niftymidcap100).toBeDefined(); // NSE prints it "NIFTY Midcap 100"
  });

  it("reads the Nifty 50 row exactly as NSE printed it", () => {
    expect(byKey.nifty50).toEqual({
      indexKey: "nifty50",
      open: 25658.35,
      high: 25951.65,
      low: 25619,
      close: 25819.25,
      changePct: 1.85,
    });
  });

  it("reads a change printed without a leading zero", () => {
    expect(byKey.niftynext50.changePct).toBe(0.75);
  });

  it("returns nothing for an empty or unrecognised file", () => {
    expect(parseIndexCloseCsv("")).toEqual([]);
    expect(parseIndexCloseCsv("<html>Access Denied</html>")).toEqual([]);
  });
});
