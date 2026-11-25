import { describe, it, expect } from "vitest";
import { isAdmin } from "./admin-metrics";

describe("isAdmin", () => {
  it("is nobody by default", () => {
    expect(isAdmin("user_1", {})).toBe(false);
    expect(isAdmin("user_1", { ADMIN_USER_IDS: "" })).toBe(false);
  });
  it("matches whole ids from the comma-separated list", () => {
    const env = { ADMIN_USER_IDS: " user_1 , user_2" };
    expect(isAdmin("user_2", env)).toBe(true);
    expect(isAdmin("user_", env)).toBe(false);
    expect(isAdmin(null, env)).toBe(false);
  });
});
