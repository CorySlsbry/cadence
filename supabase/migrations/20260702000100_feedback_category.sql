-- The public.feedback table was created live via MCP (schema drift — no prior migration
-- defines it). This is an additive backfill: add a category column so bug/feature/question
-- feedback can be classified and routed to Slack. Safe to re-run.

alter table public.feedback add column if not exists category text not null default 'other';

-- Constraint the category to known values. Guarded so re-running this migration won't error.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'feedback_category_check'
  ) then
    alter table public.feedback
      add constraint feedback_category_check
      check (category in ('bug', 'feature', 'question', 'other'));
  end if;
end $$;
