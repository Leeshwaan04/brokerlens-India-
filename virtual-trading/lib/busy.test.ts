import { describe, expect, it } from "vitest";
import { isBusyError } from "./busy";

describe("isBusyError", () => {
  it("recognises pool, lock and connection-limit failures, however deeply wrapped", () => {
    expect(isBusyError(new Error("timeout exceeded when trying to connect"))).toBe(true);
    expect(isBusyError(Object.assign(new Error("x"), { code: "55P03" }))).toBe(true);
    expect(isBusyError(new Error("Failed query", { cause: new Error("timeout exceeded when trying to connect") }))).toBe(true);
    expect(isBusyError(new Error("sorry, too many clients already"))).toBe(true);
  });
  it("does not call real failures busy", () => {
    expect(isBusyError(new Error("relation \"orders\" does not exist"))).toBe(false);
    expect(isBusyError(new Error("Failed query", { cause: new Error("syntax error") }))).toBe(false);
    expect(isBusyError(undefined)).toBe(false);
    expect(isBusyError("boom")).toBe(false);
  });
});
