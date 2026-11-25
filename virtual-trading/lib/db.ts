// Lazy Drizzle client. Built lazily (not at module load time) so that
// `next build` never fails just because DATABASE_URL isn't set yet in an
// environment that is only running lint/typecheck/build, not a real request.
//
// Production uses Neon's Pool-based neon-serverless driver, not neon-http:
// order settlement (see order-engine.ts) reads a balance, decides FILLED vs
// REJECTED from it, then writes based on that decision, all inside one
// transaction, which needs real interactive transactions. A localhost
// DATABASE_URL uses node-postgres instead, so the whole app can run end to
// end against a plain local Postgres with no Neon account. Both drivers sit
// on Drizzle's same pg-core query builder and support interactive
// transactions, so the rest of the app cannot tell them apart.

import { Pool as NeonPool } from "@neondatabase/serverless";
import { drizzle as drizzleNeon } from "drizzle-orm/neon-serverless";
import { drizzle as drizzleNodePg } from "drizzle-orm/node-postgres";
import pg from "pg";
import * as schema from "./schema";

type Db = ReturnType<typeof drizzleNeon<typeof schema>>;

let cached: Db | null = null;

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

export function isLocalDatabaseUrl(url: string): boolean {
  try {
    return LOCAL_HOSTS.has(new URL(url).hostname);
  } catch {
    return false;
  }
}

export function getDb(): Db {
  if (cached) return cached;
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env.local and fill in a real Neon connection string.",
    );
  }
  if (isLocalDatabaseUrl(url)) {
    const pool = new pg.Pool({ connectionString: url });
    cached = drizzleNodePg(pool, { schema }) as unknown as Db;
  } else {
    const pool = new NeonPool({ connectionString: url });
    cached = drizzleNeon(pool, { schema });
  }
  return cached;
}
