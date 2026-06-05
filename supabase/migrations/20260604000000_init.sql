-- Cadence SaaS schema: per-user isolation via RLS, storage buckets, render-job
-- queue with an atomic claim function, and monthly render quotas.

-- ---------------------------------------------------------------------------
-- profiles (1:1 with auth.users), auto-created on signup
-- ---------------------------------------------------------------------------
create table public.profiles (
    id                   uuid primary key references auth.users (id) on delete cascade,
    email                text,
    full_name            text,
    plan                 text not null default 'free',
    monthly_render_limit int  not null default 10,
    created_at           timestamptz not null default now()
);
alter table public.profiles enable row level security;

create policy "profiles_select_own" on public.profiles
    for select using (auth.uid() = id);
create policy "profiles_update_own" on public.profiles
    for update using (auth.uid() = id) with check (auth.uid() = id);

create function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into public.profiles (id, email, full_name)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name')
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- updated_at helper
-- ---------------------------------------------------------------------------
create function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- brand boards + assets
-- ---------------------------------------------------------------------------
create table public.brand_boards (
    id                uuid primary key default gen_random_uuid(),
    user_id           uuid not null references auth.users (id) on delete cascade,
    name              text not null,
    caption_primary   text,
    caption_outline   text,
    caption_font_path text,
    created_at        timestamptz not null default now()
);
alter table public.brand_boards enable row level security;
create policy "brand_boards_own" on public.brand_boards
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table public.brand_assets (
    id           uuid primary key default gen_random_uuid(),
    board_id     uuid not null references public.brand_boards (id) on delete cascade,
    user_id      uuid not null references auth.users (id) on delete cascade,
    kind         text not null,
    name         text not null,
    storage_path text not null,
    opacity      real not null default 1.0,
    anchor       text not null default 'bottom_right',
    scale        real not null default 0.18,
    meta         jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);
alter table public.brand_assets enable row level security;
create policy "brand_assets_own" on public.brand_assets
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------
create table public.projects (
    id                 uuid primary key default gen_random_uuid(),
    user_id            uuid not null references auth.users (id) on delete cascade,
    name               text not null default 'Untitled project',
    reference_path     text,
    reference_analysis jsonb,
    brand_board_id     uuid references public.brand_boards (id) on delete set null,
    created_at         timestamptz not null default now()
);
alter table public.projects enable row level security;
create policy "projects_own" on public.projects
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- render jobs (the worker queue)
-- ---------------------------------------------------------------------------
create type public.render_status as enum ('queued', 'processing', 'done', 'error');

create table public.render_jobs (
    id                 uuid primary key default gen_random_uuid(),
    user_id            uuid not null references auth.users (id) on delete cascade,
    project_id         uuid references public.projects (id) on delete cascade,
    recording_path     text not null,
    reference_path     text,
    transcript         jsonb,
    plan               jsonb,
    customization      jsonb,
    aggressive_fillers boolean not null default false,
    status             public.render_status not null default 'queued',
    progress           real not null default 0,
    output_path        text,
    result             jsonb,
    error              text,
    worker_id          text,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
alter table public.render_jobs enable row level security;
-- Users may read their own jobs and create jobs for themselves; the WORKER
-- (service-role key) updates job status and bypasses RLS.
create policy "render_jobs_select_own" on public.render_jobs
    for select using (auth.uid() = user_id);
create policy "render_jobs_insert_own" on public.render_jobs
    for insert with check (auth.uid() = user_id);

create trigger render_jobs_touch
    before update on public.render_jobs
    for each row execute function public.touch_updated_at();

create index render_jobs_queue_idx on public.render_jobs (status, created_at);
create index render_jobs_user_idx on public.render_jobs (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- quota: renders consumed this calendar month (anything not errored counts)
-- ---------------------------------------------------------------------------
create function public.renders_used_this_month(uid uuid)
returns int language sql stable security definer set search_path = public as $$
    select count(*)::int
    from public.render_jobs
    where user_id = uid
      and created_at >= date_trunc('month', now())
      and status <> 'error';
$$;

-- ---------------------------------------------------------------------------
-- atomic job claim for the worker (FOR UPDATE SKIP LOCKED -> no double-processing)
-- ---------------------------------------------------------------------------
create function public.claim_next_render_job(p_worker text)
returns public.render_jobs language plpgsql security definer set search_path = public as $$
declare
    j public.render_jobs;
begin
    select * into j
    from public.render_jobs
    where status = 'queued'
    order by created_at asc
    for update skip locked
    limit 1;

    if not found then
        return null;
    end if;

    update public.render_jobs
    set status = 'processing', worker_id = p_worker, progress = 0.05, updated_at = now()
    where id = j.id
    returning * into j;

    return j;
end;
$$;

-- ---------------------------------------------------------------------------
-- storage buckets (private) + per-user folder isolation (path = {uid}/...)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('uploads', 'uploads', false), ('outputs', 'outputs', false)
on conflict (id) do nothing;

create policy "uploads_read_own" on storage.objects
    for select using (bucket_id = 'uploads' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "uploads_write_own" on storage.objects
    for insert with check (bucket_id = 'uploads' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "uploads_delete_own" on storage.objects
    for delete using (bucket_id = 'uploads' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "outputs_read_own" on storage.objects
    for select using (bucket_id = 'outputs' and (storage.foldername(name))[1] = auth.uid()::text);
