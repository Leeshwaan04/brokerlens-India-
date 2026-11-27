import { describe, expect, it } from "vitest";
import { safeNextPath } from "./next-path";

describe("safeNextPath", () => {
  it("keeps in-app paths with their query", () => {
    expect(safeNextPath("/trade?symbol=INFY")).toBe("/trade?symbol=INFY");
  });
  it("refuses anything that could leave the app", () => {
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "trade", "javascript:alert(1)", "/a\nb", "/" + "x".repeat(300)]) {
      expect(safeNextPath(bad)).toBe("/dashboard");
    }
    expect(safeNextPath(undefined)).toBe("/dashboard");
  });
});
