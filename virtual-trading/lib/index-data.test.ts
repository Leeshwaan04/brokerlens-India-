import { describe, expect, it } from "vitest";
import { benchmarkPoints } from "./index-data";

const series = [
  { date: "2026-10-20", close: 20000 },
  { date: "2026-10-22", close: 20400 },
  { date: "2026-10-26", close: 19600 },
];

describe("benchmarkPoints", () => {
  it("scales the index's move onto the starting balance", () => {
    const pts = benchmarkPoints(["2026-10-20", "2026-10-22", "2026-10-26"], series, 1_000_000);
    expect(pts?.map((p) => Math.round(p.value))).toEqual([1_000_000, 1_020_000, 980_000]);
  });

  it("uses the latest close on or before a date with no session", () => {
    const pts = benchmarkPoints(["2026-10-21", "2026-10-23", "2026-10-26"], series, 1_000_000);
    // Base is the 20 Oct close (the latest on or before 21 Oct); 23 Oct falls back to 22 Oct.
    expect(pts?.map((p) => Math.round(p.value))).toEqual([1_000_000, 1_020_000, 980_000]);
  });

  it("has no benchmark when the index starts after the first date", () => {
    expect(benchmarkPoints(["2026-10-10", "2026-10-26"], series, 1_000_000)).toBeNull();
    expect(benchmarkPoints(["2026-10-20"], series, 1_000_000)).toBeNull();
    expect(benchmarkPoints(["2026-10-20", "2026-10-22"], [], 1_000_000)).toBeNull();
  });
});
