import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cache Components is off: every page here is per-user and DB-backed
  // (portfolio, orders, auth state), so there is nothing to statically cache.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
