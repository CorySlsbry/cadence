-- Self-heal retry counter for render_jobs. The worker's _fail_or_retry re-queues a job (up to
-- MAX_RENDER_ATTEMPTS) on transient failures and increments this column; the avatar billing gate
-- charges only when attempts = 0 so a retry never double-charges.
-- NOTE: already applied to the live DB out-of-band (via MCP) on 2026-06-22; this file exists so a
-- fresh database built from migrations matches production (the code review flagged the parity gap).
alter table public.render_jobs add column if not exists attempts int not null default 0;
