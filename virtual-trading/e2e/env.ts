import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Loads virtual-trading/.env.local into process.env (without overriding). */
export function loadLocalEnv() {
  // Playwright loads these files as CommonJS, so __dirname is available.
  const path = join(__dirname, "..", ".env.local");
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*"?([^"]*)"?\s*$/);
    if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2];
  }
  const url = process.env.DATABASE_URL ?? "";
  if (!/@(localhost|127\.0\.0\.1)[:/]/.test(url) && !url.includes("localhost")) {
    throw new Error("E2E tests run only against a local database (DATABASE_URL on localhost).");
  }
}
