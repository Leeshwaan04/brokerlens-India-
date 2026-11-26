// Encrypted backup of everything in the database that cannot be re-fetched
// from NSE (users, accounts, orders, holdings, payments, ...). Prices and
// index closes are skipped: the daily sync rebuilds them.
//
//   DATABASE_URL=... BACKUP_PUBLIC_KEY="$(cat backup-public.pem)" \
//     npx tsx scripts/backup-db.mts out.bin
//
// Encrypted to a public key (lib/backup-crypto.ts); the private key stays on
// the owner's Mac. Restore with scripts/restore-backup.mts.
import { writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import pg from "pg";
import { encryptBackup } from "../lib/backup-crypto";
import { pgSslFor } from "../lib/pg-ssl";

const SKIP = new Set(["daily_prices", "index_closes"]);

const out = process.argv[2];
const url = process.env.DATABASE_URL;
const publicKey = process.env.BACKUP_PUBLIC_KEY;
if (!out || !url || !publicKey) {
  console.error("Usage: DATABASE_URL=... BACKUP_PUBLIC_KEY=<pem> npx tsx scripts/backup-db.mts <out.bin>");
  process.exit(2);
}

const client = new pg.Client({ connectionString: url, ssl: pgSslFor(url) });
await client.connect();
try {
  // One snapshot for every table, so the backup is consistent.
  await client.query("begin isolation level repeatable read read only");
  const { rows: tables } = await client.query<{ t: string }>(
    `select table_name t from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE'`,
  );
  const names = tables.map((r) => r.t).filter((t) => !SKIP.has(t));

  const lines: string[] = [];
  const counts: Record<string, number> = {};
  for (const t of names) {
    // JSON text straight from Postgres: values (numerics, timestamps) are not
    // re-parsed here, so nothing is rounded or re-formatted.
    const { rows } = await client.query<{ j: string }>(`select row_to_json(x)::text j from "${t}" x`);
    counts[t] = rows.length;
    for (const r of rows) lines.push(`{"t":${JSON.stringify(t)},"r":${r.j}}`);
  }
  await client.query("commit");

  const gz = gzipSync(Buffer.from(lines.join("\n") + "\n"), { level: 9 });
  const file = encryptBackup(gz, publicKey);
  writeFileSync(out, file, { mode: 0o600 });
  console.log(`Backed up ${lines.length} rows from ${names.length} tables to ${out} (${file.length} bytes, encrypted).`);
  console.log(JSON.stringify(counts));
} finally {
  await client.end();
}
