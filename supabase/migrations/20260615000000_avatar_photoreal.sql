-- Photoreal talking-avatar (self-host) — data model.
-- DRAFT for review; apply at deploy time (not before). Extends the existing
-- `characters` table (keeps the stylized kind='sheet' rows valid) and adds an
-- append-only consent ledger that the render route checks FAIL-CLOSED.

-- 1) Extend characters: a photoreal avatar is a character with kind='photoreal'.
alter table characters
  add column if not exists kind            text not null default 'sheet',  -- 'sheet' | 'photoreal'
  add column if not exists source_kind     text,                           -- 'video' | 'photo'
  add column if not exists source_path     text,                           -- reference clip/frame (storage)
  add column if not exists voice_id        text,                           -- ElevenLabs voice id (IVC/PVC)
  add column if not exists provider        text,                           -- 'echomimic'|'latentsync'|'tavus'
  add column if not exists provider_ref    text,                           -- hosted replica_id, if any
  add column if not exists framing_default text default 'lower_third',     -- 'lower_third'|'full'|'corner'
  add column if not exists coherence_mode  text default 'photoreal';       -- 'photoreal'|'stylized'

-- 2) Consent ledger — required before any photoreal render (load-bearing safety control).
create table if not exists consent_records (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references auth.users(id) on delete cascade,
  character_id           uuid references characters(id) on delete cascade,
  -- the on-camera spoken consent clip MUST be the same continuous capture as the avatar
  -- source (liveness-bound); arbitrary uploaded source video is not allowed for photoreal.
  consent_video_path     text not null,
  consent_script_version text not null,
  checkbox_set           jsonb not null default '{}'::jsonb,   -- the affirmations the user ticked
  tos_version            text,
  ip                     text,
  created_at             timestamptz not null default now(),
  revoked_at             timestamptz                            -- set on revocation; render check is fail-closed
);

create index if not exists consent_records_character_idx on consent_records(character_id);
create index if not exists consent_records_user_idx on consent_records(user_id);

alter table consent_records enable row level security;

-- Owner-only (mirrors the per-user RLS used elsewhere). Service role (worker) bypasses RLS.
create policy "consent_owner_select" on consent_records
  for select using (auth.uid() = user_id);
create policy "consent_owner_insert" on consent_records
  for insert with check (auth.uid() = user_id);
create policy "consent_owner_update" on consent_records
  for update using (auth.uid() = user_id);
