-- Fixed-window rate limiter. rl_bump(key, limit, window_sec) atomically increments the current
-- window's counter and returns TRUE if still within limit. Used for per-user phone-session
-- minting and per-IP public uploads. SECURITY DEFINER so the authed + service-role clients can
-- call it; the table itself has RLS on with no policies (no direct client access).
create table if not exists public.rate_limits (
  key text not null,
  window_start timestamptz not null,
  count int not null default 0,
  primary key (key, window_start)
);
alter table public.rate_limits enable row level security;

create or replace function public.rl_bump(p_key text, p_limit int, p_window_sec int)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  w timestamptz := to_timestamp(floor(extract(epoch from now()) / p_window_sec) * p_window_sec);
  c int;
begin
  insert into public.rate_limits(key, window_start, count) values (p_key, w, 1)
    on conflict (key, window_start) do update set count = rate_limits.count + 1
    returning count into c;
  return c <= p_limit;
end;
$$;

grant execute on function public.rl_bump(text, int, int) to authenticated, service_role;
