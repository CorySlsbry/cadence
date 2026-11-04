"""App-layer AES-256-GCM key vault — decrypt per-user provider API keys at use-time.

Wire format is shared verbatim with the web encrypter (`web/src/lib/crypto.ts`) and the MCP
service (`mcp/keyvault.py`):

    base64( nonce[12] || ciphertext || tag[16] )

The 32-byte master key is ``CADENCE_SECRET_ENC_KEY`` (base64) from Secret Manager. Python's
AESGCM appends the 16-byte tag to the ciphertext, so ``nonce + AESGCM.encrypt(...)`` already
yields ``nonce || ciphertext || tag`` — byte-identical to the Node ``createCipheriv`` output.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _master_key() -> bytes:
    b64 = os.environ.get("CADENCE_SECRET_ENC_KEY")
    if not b64:
        raise RuntimeError("CADENCE_SECRET_ENC_KEY is not set")
    key = base64.b64decode(b64)
    if len(key) != 32:
        raise RuntimeError("CADENCE_SECRET_ENC_KEY must decode to 32 bytes")
    return key


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret → base64(nonce || ciphertext || tag)."""
    nonce = os.urandom(12)
    ct = AESGCM(_master_key()).encrypt(nonce, plaintext.encode("utf-8"), None)  # ct ends with the tag
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(blob: str) -> str:
    """Decrypt a base64(nonce || ciphertext || tag) blob back to the secret string."""
    raw = base64.b64decode(blob)
    nonce, ct_and_tag = raw[:12], raw[12:]
    return AESGCM(_master_key()).decrypt(nonce, ct_and_tag, None).decode("utf-8")
