import { X509Certificate } from "node:crypto";
import { describe, expect, it } from "vitest";
import { SUPABASE_ROOT_CA_2021, isSupabaseUrl, pgSslFor } from "./pg-ssl";

describe("pgSslFor", () => {
  it("pins Supabase's root and verifies for Supabase hosts", () => {
    for (const url of [
      "postgresql://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres",
      "postgresql://postgres:pw@db.ref.supabase.co:5432/postgres",
    ]) {
      expect(isSupabaseUrl(url)).toBe(true);
      expect(pgSslFor(url)).toEqual({ ca: SUPABASE_ROOT_CA_2021, rejectUnauthorized: true });
    }
  });

  it("leaves every other host to its own connection string", () => {
    for (const url of [
      "postgresql://me@localhost:5432/dev",
      "postgresql://u:p@ep-x-pooler.ap-southeast-1.aws.neon.tech/db?sslmode=require",
      "postgresql://u:p@supabase.com.evil.example/db",
      "not a url",
    ]) {
      expect(pgSslFor(url)).toBeUndefined();
    }
  });

  it("carries the published Supabase Root 2021 CA", () => {
    const cert = new X509Certificate(SUPABASE_ROOT_CA_2021);
    expect(cert.subject).toContain("CN=Supabase Root 2021 CA");
    expect(cert.fingerprint256).toBe(
      "80:70:25:AD:50:D4:ED:21:9D:2C:9C:7D:29:9C:00:4F:82:4E:B0:0C:F7:F6:5A:FE:F6:07:D0:7B:72:E6:CA:FA",
    );
    expect(cert.ca).toBe(true);
  });
});
