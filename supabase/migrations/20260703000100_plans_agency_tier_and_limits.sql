-- Agency tier ($149/mo) + REAL per-plan entitlement columns. (Applied to prod 2026-07-03 via MCP.)
-- plans.features is display-only (never enforced); these columns are enforced server-side in
-- faceless/route.ts (length) and oauth/[platform]/start (account cap).
alter table public.plans add column if not exists max_accounts_per_platform int not null default 1;
alter table public.plans add column if not exists max_length_sec int not null default 90;

update public.plans set max_accounts_per_platform = 1, max_length_sec = 90  where key in ('free','base');
update public.plans set max_accounts_per_platform = 2, max_length_sec = 300 where key = 'creator';

insert into public.plans
  (key, name, price_usd, monthly_tokens, watermark, features, sort, active, daily_renders,
   max_accounts_per_platform, max_length_sec)
select 'agency', 'Agency', 149, 2000, false,
  '["Everything in Creator","2,000 AI scenes / mo","Videos up to 15 minutes","5 accounts per platform","Post to every account at once","Priority render queue"]'::jsonb,
  3, true, 80, 5, 900
where not exists (select 1 from public.plans where key = 'agency');