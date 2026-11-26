import pg from "pg";
import { loadLocalEnv } from "./env";

loadLocalEnv();
export const E2E_USER = "user_e2e";

export async function sql<T = Record<string, unknown>>(text: string, params: unknown[] = []): Promise<T[]> {
  const client = new pg.Client({ connectionString: process.env.DATABASE_URL });
  await client.connect();
  try {
    return (await client.query(text, params)).rows as T[];
  } finally {
    await client.end();
  }
}

/** Removes every row the e2e user owns, children first (as deleteUserData does). */
export async function purgeE2eUser() {
  const steps = [
    `update events set account_id = null where account_id in (select id from virtual_accounts where user_id = $1)`,
    `update cta_clicks set account_id = null where account_id in (select id from virtual_accounts where user_id = $1)`,
    `delete from watchlist_items where account_id in (select id from virtual_accounts where user_id = $1)`,
    `delete from realized_pnl_events where account_id in (select id from virtual_accounts where user_id = $1)`,
    `delete from performance_snapshots where account_id in (select id from virtual_accounts where user_id = $1)`,
    `delete from holdings where account_id in (select id from virtual_accounts where user_id = $1)`,
    `delete from orders where account_id in (select id from virtual_accounts where user_id = $1)`,
    `delete from virtual_accounts where user_id = $1`,
    `delete from payments where user_id = $1`,
    `delete from users where id = $1`,
  ];
  for (const s of steps) await sql(s, [E2E_USER]);
}
