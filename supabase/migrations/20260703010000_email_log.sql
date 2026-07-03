-- Idempotency ledger for lifecycle emails (applied to prod 2026-07-03 via MCP). unique
-- (user_id, template) guarantees each template is sent at most once per user. Written only by the
-- service role (signup hook, Stripe webhook, nurture cron); RLS deny-all for anon/authenticated.
create table if not exists public.email_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  email text,
  template text not null,
  sent_at timestamptz not null default now(),
  unique (user_id, template)
);
alter table public.email_log enable row level security;
