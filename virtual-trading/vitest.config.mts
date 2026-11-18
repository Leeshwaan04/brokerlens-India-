import { defineConfig } from "vitest/config";

// No "@/*" alias needed here: every current test file uses a relative import
// (lib/ testing lib/). Add one back with import.meta.dirname, not
// __dirname, if a future test needs it.
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
