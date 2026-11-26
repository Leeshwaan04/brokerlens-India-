// Lazy Drizzle client. Built lazily (not at module load time) so that
// `next build` never fails just because DATABASE_URL isn't set yet in an
// environment that is only running lint/typecheck/build, not a real request.
//
// Drivers, by where the app runs and what DATABASE_URL points at:
// - Cloudflare Workers with a HYPERDRIVE binding (production, wrangler.jsonc):
//   node-postgres to Hyperdrive, which pools connections to the database and
//   verifies its certificate. Workers cannot verify Supabase's private CA on a
//   direct socket, and Hyperdrive also keeps connection setup off the
//   Worker's CPU budget (10 ms a request on the Free plan).
// - A Neon URL: Neon's Pool-based neon-serverless driver (WebSockets).
// - Anything else (localhost, Supabase from Node): node-postgres over TCP,
//   with Supabase's root CA pinned (lib/pg-ssl.ts).
// All of them support interactive transactions, which order settlement needs
// (read a balance, decide FILLED vs REJECTED, write, in one transaction), and
// all sit on Drizzle's same pg-core query builder, so the rest of the app
// cannot tell them apart.
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
import { pgSslFor } from "./pg-ssl";
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

const NEON_HOST = /\.neon\.tech$/i;

function isNeonUrl(url: string): boolean {
  try {
    return NEON_HOST.test(new URL(url).hostname);
  } catch {
    return false;
  }
}

/** Hyperdrive's connection string inside a Worker request, when the binding exists. */
function hyperdriveConnectionString(): string | null {
  const env = getCloudflareContext().env as unknown as { HYPERDRIVE?: { connectionString?: string } };
  return env.HYPERDRIVE?.connectionString ?? null;
}

function nodePg(config: pg.PoolConfig): Db {
  return drizzleNodePg(new pg.Pool(config), { schema }) as unknown as Db;
}

function createDb(): Db {
  if (ON_WORKERS) {
    const hyperdrive = hyperdriveConnectionString();
    // A few connections at most per request: Promise.all reads run side by side.
    if (hyperdrive) return nodePg({ connectionString: hyperdrive, max: 5 });
  }
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Copy .env.example to .env.local and set a Postgres connection string.",
    );
  }
  if (isNeonUrl(url)) return drizzleNeon(new NeonPool({ connectionString: url }), { schema });
  return nodePg({ connectionString: url, ssl: isLocalDatabaseUrl(url) ? undefined : pgSslFor(url) });
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
