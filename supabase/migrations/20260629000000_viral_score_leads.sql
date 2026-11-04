-- Viral Score lead magnet: public score results + the first email-capture table CloutHook has.
-- Both are written/read ONLY by the service role (the public /api/score routes use the admin client);
-- RLS is enabled with no anon policies => anon/auth clients are denied, service role bypasses.

create table if not exists public.score_results (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  platform text,
  input jsonb,
  result jsonb not null,
  score numeric,
  email text,
  ip_hash text,
  utm jsonb
);
alter table public.score_results enable row level security;

create table if not exists public.leads (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  email text not null,
  source text,
  score_result_id uuid references public.score_results(id) on delete set null,
  utm jsonb,
  unsubscribed boolean not null default false,
  emailed_at timestamptz
);
create index if not exists leads_email_idx on public.leads (email);
create index if not exists leads_created_idx on public.leads (created_at desc);
alter table public.leads enable row level security;
