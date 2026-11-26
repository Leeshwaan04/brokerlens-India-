// Backup encryption: hybrid, so the nightly job needs only a PUBLIC key.
// A fresh AES-256-GCM key encrypts each backup; that key is wrapped with the
// owner's RSA public key (OAEP, SHA-256). Only the matching private key,
// which lives on the owner's Mac and never in GitHub, can unwrap it. So a
// backup stored where others can download it (a public repository's Actions
// artifacts) is unreadable to everyone else.
//
// File layout: "BLB1" | wrapped-key length (2 bytes) | wrapped key | IV (12) | tag (16) | ciphertext.
import { constants, createCipheriv, createDecipheriv, privateDecrypt, publicEncrypt, randomBytes } from "node:crypto";

const MAGIC = Buffer.from("BLB1");

export function encryptBackup(plain: Buffer, publicKeyPem: string): Buffer {
  const key = randomBytes(32);
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const body = Buffer.concat([cipher.update(plain), cipher.final()]);
  const tag = cipher.getAuthTag();
  const wrapped = publicEncrypt({ key: publicKeyPem, padding: constants.RSA_PKCS1_OAEP_PADDING, oaepHash: "sha256" }, key);
  const len = Buffer.alloc(2);
  len.writeUInt16BE(wrapped.length);
  return Buffer.concat([MAGIC, len, wrapped, iv, tag, body]);
}

export function decryptBackup(file: Buffer, privateKeyPem: string): Buffer {
  if (file.length < 4 + 2 + 12 + 16 || !file.subarray(0, 4).equals(MAGIC)) throw new Error("Not a BrokerLens backup file");
  const wrappedLen = file.readUInt16BE(4);
  let o = 6;
  const wrapped = file.subarray(o, (o += wrappedLen));
  const iv = file.subarray(o, (o += 12));
  const tag = file.subarray(o, (o += 16));
  const key = privateDecrypt({ key: privateKeyPem, padding: constants.RSA_PKCS1_OAEP_PADDING, oaepHash: "sha256" }, wrapped);
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(file.subarray(o)), decipher.final()]);
}
