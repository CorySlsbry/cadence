// Interop harness for the key-vault crypto. `enc <text>` prints the blob; `dec <blob>` prints
// the plaintext. Used to prove web (TS) and worker (Python) share one AES-256-GCM wire format.
import { decryptSecret, encryptSecret } from "../src/lib/crypto";

const [mode, value] = process.argv.slice(2);
if (mode === "enc") process.stdout.write(encryptSecret(value));
else if (mode === "dec") process.stdout.write(decryptSecret(value));
else throw new Error("usage: crypto_interop.ts enc|dec <value>");
