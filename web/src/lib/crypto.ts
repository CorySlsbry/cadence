import { createCipheriv, createDecipheriv, randomBytes } from "crypto";

/**
 * App-layer AES-256-GCM for the per-user key vault. Wire format (shared verbatim with the
 * Python worker + MCP `keyvault.py`):
 *
 *     base64( nonce[12] || ciphertext || tag[16] )
 *
 * The 32-byte master key is `CADENCE_SECRET_ENC_KEY` (base64) from Secret Manager. SERVER-ONLY
 * — never import this into client code. We encrypt on connect; the worker/MCP decrypt at use.
 */

function masterKey(): Buffer {
  const b64 = process.env.CADENCE_SECRET_ENC_KEY;
  if (!b64) throw new Error("CADENCE_SECRET_ENC_KEY is not set");
  const key = Buffer.from(b64, "base64");
  if (key.length !== 32) throw new Error("CADENCE_SECRET_ENC_KEY must decode to 32 bytes");
  return key;
}

/** Encrypt a secret string → base64(nonce ‖ ciphertext ‖ tag). */
export function encryptSecret(plaintext: string): string {
  const key = masterKey();
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  const ct = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([nonce, ct, tag]).toString("base64");
}

/** Decrypt a base64(nonce ‖ ciphertext ‖ tag) blob back to the secret string. */
export function decryptSecret(blob: string): string {
  const key = masterKey();
  const raw = Buffer.from(blob, "base64");
  const nonce = raw.subarray(0, 12);
  const tag = raw.subarray(raw.length - 16);
  const ct = raw.subarray(12, raw.length - 16);
  const decipher = createDecipheriv("aes-256-gcm", key, nonce);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ct), decipher.final()]).toString("utf8");
}

/** Non-secret display tail for "Connected …a1b2" — last 4 chars of the key. */
export function last4(secret: string): string {
  return secret.slice(-4);
}
