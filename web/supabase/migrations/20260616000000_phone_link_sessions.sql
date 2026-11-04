-- Phone-record handoff: a short-lived, account-scoped capability token that lets an
-- UNAUTHENTICATED phone upload ONE reference clip into the desktop user's account.
--
-- Security model (no cross-account mixing): the token is a 256-bit secret and the ONLY
-- capability; every row is bound to user_id at creation (from the desktop's authed
-- session). The phone routes validate the token + write to uploads/{user_id}/... via the
-- service role, so a token can only ever populate ITS OWN session for ITS OWN user.
-- Single-use (status flips pending->uploaded once) + 15-minute TTL.
create table if not exists public.phone_link_sessions (
  id uuid primary key default gen_random_uuid(),
  token text not null unique,                       -- 256-bit hex capability (NOT the id)
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'pending'
    check (status in ('pending', 'uploaded', 'consumed', 'expired')),
  recording_path text,                              -- uploads/{user_id}/avatar-phone-*.{webm,mp4}
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '15 minutes'),
  uploaded_at timestamptz,
  consumed_at timestamptz
);

create index if not exists phone_link_sessions_user_idx on public.phone_link_sessions (user_id);
create index if not exists phone_link_sessions_token_idx on public.phone_link_sessions (token);

alter table public.phone_link_sessions enable row level security;

-- Desktop owner (authed) manages only their own sessions. The phone upload + token
-- validation run via the service role (RLS-bypassing) and are gated by the capability
-- token in code — the phone is never authenticated and never sees user_id.
drop policy if exists phone_link_sessions_owner_select on public.phone_link_sessions;
create policy phone_link_sessions_owner_select on public.phone_link_sessions
  for select using (auth.uid() = user_id);

drop policy if exists phone_link_sessions_owner_insert on public.phone_link_sessions;
create policy phone_link_sessions_owner_insert on public.phone_link_sessions
  for insert with check (auth.uid() = user_id);

drop policy if exists phone_link_sessions_owner_update on public.phone_link_sessions;
create policy phone_link_sessions_owner_update on public.phone_link_sessions
  for update using (auth.uid() = user_id);
