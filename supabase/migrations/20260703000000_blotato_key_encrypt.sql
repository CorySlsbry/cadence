-- Encrypt the Blotato API key at rest (applied to prod 2026-07-03 via MCP; committed here for
-- version control). It was stored plaintext on profiles and readable by the owning browser client
-- (profiles_select_own grants row-wide SELECT). The connect route now writes AES-256-GCM ciphertext
-- into blotato_api_key_enc (web/src/lib/crypto.ts) and the publish route decrypts it server-side;
-- the plaintext column is cleared. Blotato is deprecated, so any existing plaintext key is nulled +
-- re-entered rather than migrated (encryption is app-side, not expressible in SQL).
alter table public.profiles add column if not exists blotato_api_key_enc text;
update public.profiles set blotato_api_key = null where blotato_api_key is not null;
