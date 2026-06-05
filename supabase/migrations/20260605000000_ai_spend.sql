-- Durable AI-spend ledger. The worker runs on stateless, scale-to-zero Cloud Run
-- instances, so the old local JSON ledger could not enforce the $10 cap across
-- instances. This single-row table + an atomic guarded RPC make the cap hold no
-- matter how many worker instances exist.

create table if not exists public.ai_spend (
    id         int primary key default 1,
    spent_usd  numeric(12, 4) not null default 0,
    images     int            not null default 0,
    cap_usd    numeric(12, 4) not null default 10,
    updated_at timestamptz    not null default now(),
    constraint ai_spend_singleton check (id = 1)
);

insert into public.ai_spend (id) values (1) on conflict (id) do nothing;

-- RLS on, no policies -> only the service-role worker can read/charge it; anon and
-- authenticated users are fully denied.
alter table public.ai_spend enable row level security;

-- Atomically charge the ledger. The guarded UPDATE only commits when the new total
-- stays within the cap, so concurrent worker instances can never collectively exceed
-- it. Returns the new total, or raises when the charge would breach the cap.
create or replace function public.charge_ai_spend(p_cost numeric, p_cap numeric)
returns numeric language plpgsql security definer set search_path = public as $$
declare
    new_total numeric;
begin
    update public.ai_spend
    set spent_usd  = spent_usd + p_cost,
        images     = images + 1,
        cap_usd    = p_cap,
        updated_at = now()
    where id = 1
      and spent_usd + p_cost <= p_cap + 1e-9
    returning spent_usd into new_total;

    if new_total is null then
        raise exception 'AI budget cap reached (cap $%)', p_cap using errcode = 'check_violation';
    end if;
    return new_total;
end;
$$;

revoke all on function public.charge_ai_spend(numeric, numeric) from anon, authenticated;
