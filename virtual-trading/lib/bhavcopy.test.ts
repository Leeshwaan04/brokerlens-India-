import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { bhavcopyUrl, parseBhavcopyCsv } from "./bhavcopy";

// lib/__fixtures__/bhavcopy-fixture.csv is a real excerpt (header plus 5
// real rows: RELIANCE, TCS, INFY, HDFCBANK, and one non-EQ row, SGBJUN28,
// a gold bond) taken verbatim from NSE's real bhavcopy for 2026-11-18,
// fetched directly from https://nsearchives.nseindia.com during this task.
// Figures are real closing prices from that real trading day, not invented.
const FIXTURE = readFileSync(join(__dirname, "__fixtures__", "bhavcopy-fixture.csv"), "utf-8");

describe("bhavcopyUrl", () => {
  it("builds the real NSE archive URL pattern", () => {
    const date = new Date(Date.UTC(2026, 10, 18)); // 2026-11-18
    expect(bhavcopyUrl(date)).toBe(
      "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261118_F_0000.csv.zip",
    );
  });
});

describe("parseBhavcopyCsv against a real bhavcopy excerpt", () => {
  it("filters to SctySrs=='EQ' only, dropping the gold-bond row", () => {
    const rows = parseBhavcopyCsv(FIXTURE);
    expect(rows).toHaveLength(4);
    expect(rows.map((r) => r.symbol).sort()).toEqual(["HDFCBANK", "INFY", "RELIANCE", "TCS"]);
  });

  it("carries the real OHLCV figures through unchanged", () => {
    const rows = parseBhavcopyCsv(FIXTURE);
    const reliance = rows.find((r) => r.symbol === "RELIANCE");
    expect(reliance).toMatchObject({
      open: 1370.0,
      high: 1376.5,
      low: 1354.0,
      close: 1363.0,
      volume: 18228940,
    });
  });

  it("restricts to an allowed-symbol set when given one", () => {
    const rows = parseBhavcopyCsv(FIXTURE, new Set(["RELIANCE", "TCS"]));
    expect(rows.map((r) => r.symbol).sort()).toEqual(["RELIANCE", "TCS"]);
  });

  it("returns an empty list for text with no rows", () => {
    expect(parseBhavcopyCsv("")).toEqual([]);
  });
});
