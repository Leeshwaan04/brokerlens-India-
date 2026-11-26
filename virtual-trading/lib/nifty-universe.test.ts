import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { mergeUniverse, parseNifty100Csv } from "./nifty-universe";

// lib/__fixtures__/nifty100-fixture.csv is the real header plus the first 5
// real constituent rows, taken verbatim from NSE's real, live
// ind_nifty100list.csv, fetched directly from
// https://nsearchives.nseindia.com during this task.
const FIXTURE = readFileSync(join(__dirname, "__fixtures__", "nifty100-fixture.csv"), "utf-8");

describe("parseNifty100Csv against a real Nifty 100 excerpt", () => {
  it("parses the real constituent rows", () => {
    const rows = parseNifty100Csv(FIXTURE);
    expect(rows).toHaveLength(5);
    expect(rows.map((r) => r.symbol)).toEqual(["ABB", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS"]);
  });

  it("carries the real company name and ISIN through unchanged", () => {
    const rows = parseNifty100Csv(FIXTURE);
    const adaniEnt = rows.find((r) => r.symbol === "ADANIENT");
    expect(adaniEnt).toEqual({
      symbol: "ADANIENT",
      name: "Adani Enterprises Ltd.",
      isin: "INE423A01024",
    });
  });

  it("returns an empty list for text with no rows", () => {
    expect(parseNifty100Csv("")).toEqual([]);
  });
});

describe("mergeUniverse", () => {
  const row = (symbol: string) => ({ symbol, name: symbol, isin: null });
  it("gives each symbol one entry listing every index it is in", () => {
    const merged = mergeUniverse([
      { membership: "NIFTY50", rows: [row("RELIANCE")] },
      { membership: "NIFTY100", rows: [row("RELIANCE"), row("DMART")] },
      { membership: "NIFTY500", rows: [row("RELIANCE"), row("DMART"), row("ZYDUSLIFE")] },
    ]);
    expect(merged.map((m) => m.symbol)).toEqual(["DMART", "RELIANCE", "ZYDUSLIFE"]);
    expect(merged.find((m) => m.symbol === "RELIANCE")?.indexMembership).toEqual(["NIFTY50", "NIFTY100", "NIFTY500"]);
    expect(merged.find((m) => m.symbol === "ZYDUSLIFE")?.indexMembership).toEqual(["NIFTY500"]);
  });
});
