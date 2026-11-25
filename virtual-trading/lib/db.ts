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
//
// On Cloudflare Workers (OpenNext build) a socket belongs to the request that
// opened it: reusing one from an earlier request fails with "Cannot perform
// I/O on behalf of a different request", and Neon's guidance is to create the
// Pool inside the request. So there the client is cached per request, keyed
// by OpenNext's per-request context object, and dropped with it. Everywhere
// else (next dev, next start, tests, scripts) one client per process.

import { Pool as NeonPool } from "@neondatabase/serverless";
import { drizzle as drizzleNeon } from "drizzle-orm/neon-serverless";
import { drizzle as drizzleNodePg } from "drizzle-orm/node-postgres";
import pg from "pg";
import { getCloudflareContext } from "@opennextjs/cloudflare/cloudflare-context";
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

const ON_WORKERS = typeof navigator !== "undefined" && navigator.userAgent === "Cloudflare-Workers";
const perRequest = new WeakMap<object, Db>();

function createDb(): Db {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env.local and fill in a real Neon connection string.",
    );
  }
  if (isLocalDatabaseUrl(url)) {
    const pool = new pg.Pool({ connectionString: url });
    return drizzleNodePg(pool, { schema }) as unknown as Db;
  }
  const pool = new NeonPool({ connectionString: url });
  return drizzleNeon(pool, { schema });
}

export function getDb(): Db {
  if (ON_WORKERS) {
    // Same object for the whole request, including after() callbacks, which
    // OpenNext runs inside that request's waitUntil.
    const scope = getCloudflareContext();
    let db = perRequest.get(scope);
    if (!db) {
      db = createDb();
      perRequest.set(scope, db);
    }
    return db;
  }
  if (cached) return cached;
  cached = createDb();
  return cached;
}
