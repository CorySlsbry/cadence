-- Creator value-adds attached to a finished render (applied via MCP on 2026-06-06):
--   hooks:     {hooks:[...], cold_open:{line,why}}
--   repurpose: {carousel:[...], thread:[...], newsletter:"", quote_cards:[...]}
--   clips:     [{index, output_path, title, hook, start, end, duration, result, social_captions}]  (multi-clip mode)
alter table public.render_jobs add column if not exists hooks jsonb;
alter table public.render_jobs add column if not exists repurpose jsonb;
alter table public.render_jobs add column if not exists clips jsonb;
