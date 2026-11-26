import { defineConfig } from "drizzle-kit";
import { pgSslFor } from "./lib/pg-ssl";

const url = process.env.DATABASE_URL ?? "postgresql://placeholder/placeholder";
// Supabase needs its root CA pinned (lib/pg-ssl.ts), which drizzle-kit only
// accepts with the connection given field by field.
const ssl = pgSslFor(url);
const parsed = new URL(url);

export default defineConfig({
  schema: "./lib/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: ssl
    ? {
        host: parsed.hostname,
        port: Number(parsed.port || 5432),
        user: decodeURIComponent(parsed.username),
        password: decodeURIComponent(parsed.password),
        database: parsed.pathname.slice(1) || "postgres",
        ssl,
      }
    : { url },
});
