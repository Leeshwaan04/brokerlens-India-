import { generateKeyPairSync } from "node:crypto";
import { describe, expect, it } from "vitest";
import { decryptBackup, encryptBackup } from "./backup-crypto";

const pair = (bits = 2048) =>
  generateKeyPairSync("rsa", { modulusLength: bits, publicKeyEncoding: { type: "spki", format: "pem" }, privateKeyEncoding: { type: "pkcs8", format: "pem" } });

describe("backup encryption", () => {
  const a = pair();
  const plain = Buffer.from('{"t":"users","r":{"id":"user_1","email":"a@example.com"}}\n'.repeat(200));

  it("round-trips with the matching private key", () => {
    expect(decryptBackup(encryptBackup(plain, a.publicKey), a.privateKey).equals(plain)).toBe(true);
  });

  it("is unreadable without it: no plaintext in the file, and another key fails", () => {
    const file = encryptBackup(plain, a.publicKey);
    expect(file.includes("a@example.com")).toBe(false);
    expect(() => decryptBackup(file, pair().privateKey)).toThrow();
  });

  it("detects tampering and wrong files", () => {
    const file = encryptBackup(plain, a.publicKey);
    const bad = Buffer.from(file);
    bad[bad.length - 1] ^= 1;
    expect(() => decryptBackup(bad, a.privateKey)).toThrow();
    expect(() => decryptBackup(Buffer.from("not a backup at all, just text"), a.privateKey)).toThrow(/Not a BrokerLens backup/);
  });

  it("uses a fresh key every time", () => {
    expect(encryptBackup(plain, a.publicKey).equals(encryptBackup(plain, a.publicKey))).toBe(false);
  });
});
