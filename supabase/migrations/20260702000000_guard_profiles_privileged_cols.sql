-- SECURITY (applied to prod 2026-07-02 via MCP; committed here for version control).
--
-- The profiles_update_own RLS policy authorizes an authenticated user to UPDATE ANY column
-- of their OWN row, and the default column grants expose every column — including `plan`
-- (the admin gate at admin/page.tsx + the unlimited-render gate in lib/limits.ts) and
-- `tokens` (the paid AI meter gated in api/render + api/faceless). That let any logged-in
-- user run, straight from the browser anon client:
--     supabase.from('profiles').update({ plan: 'admin', tokens: 1000000 }).eq('id', myId)
-- i.e. self-escalate to admin and grant themselves unlimited paid AI spend.
--
-- Postgres WITH CHECK cannot express per-column rules, so guard the privileged columns with
-- a BEFORE UPDATE trigger. Verified safe before shipping: spend_tokens, grant_extra_tokens,
-- claim_monthly_tokens, grant_monthly_tokens, claim_referral, record_affiliate_click are ALL
-- SECURITY DEFINER owned by postgres (so current_user = postgres inside them), and the Stripe
-- webhook uses the service_role key — none run as the 'authenticated'/'anon' roles blocked here.
-- Positive-tested: an authenticated benign write (full_name) and a definer/service token write
-- both still succeed; only a direct authenticated write to a guarded column is rejected.

create or replace function public.guard_profiles_privileged_cols()
returns trigger
language plpgsql
as $$
begin
  if current_user in ('authenticated', 'anon') then
    if new.plan is distinct from old.plan
       or new.tokens is distinct from old.tokens
       or new.token_period_start is distinct from old.token_period_start
       or new.monthly_render_limit is distinct from old.monthly_render_limit
       or new.referred_by is distinct from old.referred_by then
      raise exception 'not authorized to modify billing/plan columns'
        using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists guard_profiles_privileged_cols on public.profiles;
create trigger guard_profiles_privileged_cols
  before update on public.profiles
  for each row
  execute function public.guard_profiles_privileged_cols();
