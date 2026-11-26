import { defineConfig, devices } from "@playwright/test";
import { loadLocalEnv } from "./e2e/env";

// Two runs against a local dev server and the local database, never a public
// host: E2E_MODE=signed-in (default) walks one throwaway user, user_e2e,
// from sign-up to account deletion; E2E_MODE=signed-out checks public pages
// and that everything private refuses. Stop any other `next dev` in this
// folder first (Next allows one per folder). Run: npm run e2e
loadLocalEnv();
const signedOut = process.env.E2E_MODE === "signed-out";
const PORT = 3200;

export default defineConfig({
  testDir: "./e2e",
  testMatch: signedOut ? "public.spec.ts" : "journey.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  globalSetup: signedOut ? undefined : "./e2e/global-setup.ts",
  globalTeardown: signedOut ? undefined : "./e2e/global-teardown.ts",
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: signedOut
    ? [{ name: "public", use: { ...devices["Desktop Chrome"] } }]
    : [{ name: "journey", use: { ...devices["Desktop Chrome"], viewport: { width: 1400, height: 900 } } }],
  webServer: {
    command: `npx next dev -p ${PORT}`,
    url: `http://localhost:${PORT}/privacy`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: { VT_DEV_AUTH_USER_ID: signedOut ? "signed-out" : "user_e2e", ADMIN_USER_IDS: "" },
  },
});
