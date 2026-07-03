-- Fire a Slack alert on every new signup (applied to prod 2026-07-02 via MCP; committed here
-- for version control). A profiles row is created for every auth method (email/password, Google
-- OAuth, magic-link) via the handle_new_user trigger, so this covers them all with zero client
-- change. pg_net makes the call async so it never slows a signup; any failure is swallowed.
--
-- SECRET: the x-signup-secret value lives in Vault under the name 'signup_hook_secret' and is set
-- out-of-band (NOT in this migration). To recreate in a fresh environment, run once:
--   select vault.create_secret('<SIGNUP_HOOK_SECRET>', 'signup_hook_secret',
--                              'x-signup-secret header value for POST /api/hooks/signup');
-- (must equal the SIGNUP_HOOK_SECRET env var on cadence-web).

create extension if not exists pg_net;

create or replace function public.notify_signup()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_secret text;
begin
  select decrypted_secret into v_secret from vault.decrypted_secrets where name = 'signup_hook_secret';
  perform net.http_post(
    url := 'https://clouthook.com/api/hooks/signup',
    body := jsonb_build_object(
      'type', 'INSERT',
      'table', 'profiles',
      'record', to_jsonb(new) || jsonb_build_object(
        'email', coalesce(new.email, (select u.email from auth.users u where u.id = new.id))
      )
    ),
    headers := jsonb_build_object('Content-Type', 'application/json', 'x-signup-secret', v_secret)
  );
  return new;
exception when others then
  return new; -- a webhook failure must never block a signup
end;
$$;

drop trigger if exists on_profile_created_notify on public.profiles;
create trigger on_profile_created_notify
  after insert on public.profiles
  for each row
  execute function public.notify_signup();
