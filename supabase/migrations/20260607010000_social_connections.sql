-- Direct per-platform social OAuth connections (TikTok / YouTube / Instagram / ...), beyond
-- the Blotato broker. Each row holds a user's encrypted access + refresh tokens for one
-- platform. Service-role-only (deny-all RLS); the UI reads status via my_social_connections().
-- Tokens are AES-256-GCM encrypted at the app layer (same vault format as user_connections).

create type public.social_platform as enum
    ('youtube', 'tiktok', 'instagram', 'facebook', 'x', 'linkedin');

create table public.social_connections (
    id                uuid primary key default gen_random_uuid(),
    user_id           uuid not null references auth.users (id) on delete cascade,
    platform          public.social_platform not null,
    access_token_enc  text not null,         -- AES-256-GCM ciphertext
    refresh_token_enc text,                  -- AES-256-GCM ciphertext (if the platform issues one)
    platform_user_id  text,
    username          text,                  -- non-secret display handle
    scopes            text,
    expires_at        timestamptz,           -- access-token expiry (for refresh)
    meta              jsonb not null default '{}'::jsonb,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (user_id, platform)
);
alter table public.social_connections enable row level security;
create trigger social_connections_touch
    before update on public.social_connections
    for each row execute function public.touch_updated_at();

create function public.my_social_connections()
returns table (platform text, username text, expires_at timestamptz)
language sql stable security definer set search_path = public as $$
    select platform::text, username, expires_at
    from public.social_connections
    where user_id = auth.uid();
$$;
revoke all on function public.my_social_connections() from public;
grant execute on function public.my_social_connections() to authenticated;
