import { describe, it, expect } from "vitest";
import { devAuthUserId, isDevAuth } from "./session";

describe("dev auth", () => {
  it("is never honoured in production, even when the variable is set", () => {
    const env = { NODE_ENV: "production", VT_DEV_AUTH_USER_ID: "user_dev" };
    expect(isDevAuth(env)).toBe(false);
    expect(devAuthUserId(env)).toBeNull();
    expect(isDevAuth({ NODE_ENV: "production", VT_DEV_AUTH_USER_ID: "signed-out" })).toBe(false);
  });

  it("signs in as the given user in development", () => {
    const env = { NODE_ENV: "development", VT_DEV_AUTH_USER_ID: "user_dev" };
    expect(isDevAuth(env)).toBe(true);
    expect(devAuthUserId(env)).toBe("user_dev");
  });

  it("supports an anonymous visitor in development", () => {
    const env = { NODE_ENV: "development", VT_DEV_AUTH_USER_ID: "signed-out" };
    expect(isDevAuth(env)).toBe(true);
    expect(devAuthUserId(env)).toBeNull();
  });

  it("is off when the variable is missing or blank", () => {
    expect(isDevAuth({ NODE_ENV: "development" })).toBe(false);
    expect(isDevAuth({ NODE_ENV: "development", VT_DEV_AUTH_USER_ID: "   " })).toBe(false);
  });
});
