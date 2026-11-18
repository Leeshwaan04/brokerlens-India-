// Lazy Neon + Drizzle client. Built lazily (not at module load time) so that
// `next build` never fails just because DATABASE_URL isn't set yet in an
// environment that is only running lint/typecheck/build, not a real request.
//
// Uses the Pool-based neon-serverless driver, not neon-http: order
// settlement (see order-engine.ts) reads a balance, decides FILLED vs
// REJECTED from it, then writes based on that decision, all inside one
// transaction. neon-http's transaction support only batches a fixed list of
// statements, it cannot branch on a value read earlier in the same
// transaction. The WebSocket-based Pool driver supports real interactive
// transactions, which this settlement logic actually needs.

import { Pool } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-serverless";
import * as schema from "./schema";

type Db = ReturnType<typeof drizzle<typeof schema>>;

let cached: Db | null = null;

export function getDb(): Db {
  if (cached) return cached;
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env.local and fill in a real Neon connection string.",
    );
  }
  const pool = new Pool({ connectionString: url });
  cached = drizzle(pool, { schema });
  return cached;
}
