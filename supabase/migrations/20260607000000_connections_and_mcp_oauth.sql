-- Per-user provider key vault (BYOK) + the remote-MCP OAuth 2.1 authorization-server state.
--
-- Every table here is SERVICE-ROLE-ONLY: RLS is enabled with NO anon/authenticated policies
-- (deny-all to clients). The web routes, the render worker, and the MCP service touch these
-- with the service-role key. The UI reads connection STATUS (never the ciphertext) via the
-- my_connections() SECURITY DEFINER RPC. Secrets are AES-256-GCM encrypted at the app layer
-- before they ever reach Postgres (secret_enc holds ciphertext, never plaintext).

-- ---------------------------------------------------------------------------
-- BYOK: per-user, encrypted provider API keys
-- ---------------------------------------------------------------------------
create type public.connection_provider as enum
    ('elevenlabs', 'gemini', 'anthropic', 'blotato');

create table public.user_connections (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references auth.users (id) on delete cascade,
    provider     public.connection_provider not null,
    secret_enc   text not null,           -- base64(nonce || AES-256-GCM ciphertext || tag); NEVER plaintext
    last4        text,                     -- non-secret display tail (e.g. "a1b2")
    status       text not null default 'active',   -- active | invalid | revoked
    validated_at timestamptz,
    meta         jsonb not null default '{}'::jsonb,  -- non-secret extras (e.g. blotato accounts)
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (user_id, provider)
);
alter table public.user_connections enable row level security;
-- (no policies on purpose -> deny-all to anon/authenticated; service-role bypasses RLS)
create trigger user_connections_touch
    before update on public.user_connections
    for each row execute function public.touch_updated_at();

-- UI-safe read: connection status only, never the secret. SECURITY DEFINER + auth.uid()
-- scopes it to the calling user.
create function public.my_connections()
returns table (provider text, last4 text, status text, validated_at timestamptz)
language sql stable security definer set search_path = public as $$
    select provider::text, last4, status, validated_at
    from public.user_connections
    where user_id = auth.uid();
$$;
revoke all on function public.my_connections() from public;
grant execute on function public.my_connections() to authenticated;

-- ---------------------------------------------------------------------------
-- Remote MCP server — OAuth 2.1 authorization-server state (service-role only)
-- ---------------------------------------------------------------------------
-- Dynamically-registered OAuth clients (RFC 7591). Claude registers itself here on first
-- connect. Public clients (PKCE) have a null client_secret.
create table public.oauth_clients (
    client_id      text primary key,
    client_secret  text,
    client_name    text,
    redirect_uris  jsonb not null default '[]'::jsonb,
    grant_types    jsonb not null default '["authorization_code","refresh_token"]'::jsonb,
    created_at     timestamptz not null default now()
);
alter table public.oauth_clients enable row level security;

-- Short-lived authorization codes (authorization-code grant + PKCE S256). Single-use:
-- deleted on exchange.
create table public.oauth_codes (
    code                  text primary key,
    client_id             text not null,
    user_id               uuid not null references auth.users (id) on delete cascade,
    redirect_uri          text not null,
    code_challenge        text not null,
    code_challenge_method text not null default 'S256',
    scope                 text,
    resource              text,          -- RFC 8707 audience the token will be bound to
    expires_at            timestamptz not null,
    created_at            timestamptz not null default now()
);
alter table public.oauth_codes enable row level security;
create index oauth_codes_expiry_idx on public.oauth_codes (expires_at);

-- Refresh tokens (opaque, stored hashed). Access tokens are stateless audience-bound JWTs.
create table public.oauth_refresh_tokens (
    id         uuid primary key default gen_random_uuid(),
    token_hash text not null unique,
    client_id  text not null,
    user_id    uuid not null references auth.users (id) on delete cascade,
    scope      text,
    expires_at timestamptz not null,
    revoked    boolean not null default false,
    created_at timestamptz not null default now()
);
alter table public.oauth_refresh_tokens enable row level security;
create index oauth_refresh_user_idx on public.oauth_refresh_tokens (user_id);
