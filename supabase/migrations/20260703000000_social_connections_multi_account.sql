-- Multi-account: allow several accounts of the same platform per user (2 IG, 3 TikTok, ...).
-- (Applied to prod 2026-07-03 via MCP; committed for version control.)
-- Additive + zero-downtime: adds the composite-unique + label but KEEPS the old
-- unique(user_id, platform) so the currently-deployed OAuth callback (onConflict user_id,platform)
-- keeps working. The old constraint is dropped in 20260703000200 when the new callback deploys.
update public.social_connections set platform_user_id = '' where platform_user_id is null;
alter table public.social_connections alter column platform_user_id set default '';
alter table public.social_connections alter column platform_user_id set not null;
alter table public.social_connections add column if not exists label text;
alter table public.social_connections
  add constraint social_connections_user_platform_account_key unique (user_id, platform, platform_user_id);

-- Read RPC now exposes id + platform_user_id + label so callers can address a specific account.
drop function if exists public.my_social_connections();
create function public.my_social_connections()
returns table (id uuid, platform text, platform_user_id text, username text, label text, expires_at timestamptz)
language sql stable security definer set search_path = public as $$
  select id, platform::text, platform_user_id, username, label, expires_at
  from public.social_connections
  where user_id = auth.uid()
  order by platform, created_at;
$$;
grant execute on function public.my_social_connections() to authenticated;