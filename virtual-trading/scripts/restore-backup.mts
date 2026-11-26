// Decrypts a backup made by scripts/backup-db.mts, and optionally loads it
// into an EMPTY database whose tables already exist (run the migrations first).
//
//   npx tsx scripts/restore-backup.mts backup.bin --private-key backup-private.pem --out dump.ndjson
//   DATABASE_URL=<empty db> npx tsx scripts/restore-backup.mts backup.bin --private-key backup-private.pem --apply
import { readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { gunzipSync } from "node:zlib";
import pg from "pg";
import { decryptBackup } from "../lib/backup-crypto";
import { pgSslFor } from "../lib/pg-ssl";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: { "private-key": { type: "string" }, out: { type: "string" }, apply: { type: "boolean" } },
});
const [file] = positionals;
if (!file || !values["private-key"] || (!values.out && !values.apply)) {
  console.error("Usage: restore-backup.mts <backup.bin> --private-key <pem> (--out <dump.ndjson> | --apply with DATABASE_URL set)");
  process.exit(2);
}

const ndjson = gunzipSync(decryptBackup(readFileSync(file), readFileSync(values["private-key"], "utf8"))).toString("utf8");
if (values.out) {
  writeFileSync(values.out, ndjson, { mode: 0o600 });
  console.log(`Decrypted to ${values.out}`);
}

if (values.apply) {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  // table -> raw JSON row texts. Rows are never parsed, so numerics keep every digit.
  const byTable = new Map<string, string[]>();
  for (const line of ndjson.split("\n")) {
    if (!line) continue;
    const m = /^\{"t":("(?:[^"\\]|\\.)*"),"r":/.exec(line);
    if (!m) throw new Error(`Unrecognised backup line: ${line.slice(0, 80)}`);
    const t = JSON.parse(m[1]) as string;
    (byTable.get(t) ?? byTable.set(t, []).get(t)!).push(line.slice(m[0].length, -1));
  }

  const client = new pg.Client({ connectionString: url, ssl: pgSslFor(url) });
  await client.connect();
  try {
    // Parents before children, from the foreign keys.
    const { rows: fks } = await client.query<{ child: string; parent: string }>(
      `select tc.table_name child, ccu.table_name parent
         from information_schema.table_constraints tc
         join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'public' and tc.table_name <> ccu.table_name`,
    );
    const order: string[] = [];
    const visit = (t: string, seen: Set<string>) => {
      if (order.includes(t) || seen.has(t)) return;
      seen.add(t);
      for (const f of fks.filter((x) => x.child === t)) if (byTable.has(f.parent)) visit(f.parent, seen);
      order.push(t);
    };
    for (const t of byTable.keys()) visit(t, new Set());

    await client.query("begin");
    for (const t of order) {
      const { rows } = await client.query<{ n: string }>(`select count(*) n from "${t}"`);
      if (Number(rows[0].n) > 0) throw new Error(`Table ${t} is not empty; restore only into an empty database.`);
    }
    for (const t of order) {
      const rows = byTable.get(t)!;
      for (let i = 0; i < rows.length; i += 500) {
        const batch = `[${rows.slice(i, i + 500).join(",")}]`;
        await client.query(`insert into "${t}" select * from json_populate_recordset(null::"${t}", $1::json)`, [batch]);
      }
      // Serial columns: continue numbering after the restored rows.
      const { rows: serials } = await client.query<{ col: string; seq: string }>(
        `select column_name col, pg_get_serial_sequence('"${t}"', column_name) seq from information_schema.columns where table_schema = 'public' and table_name = $1`,
        [t],
      );
      for (const s of serials.filter((x) => x.seq)) await client.query(`select setval($1, coalesce((select max("${s.col}") from "${t}"), 1))`, [s.seq]);
      console.log(`${t}: ${rows.length} rows`);
    }
    await client.query("commit");
    console.log("Restore complete.");
  } catch (err) {
    await client.query("rollback").catch(() => undefined);
    throw err;
  } finally {
    await client.end();
  }
}
