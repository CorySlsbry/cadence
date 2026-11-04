-- Security hardening for the phone-record handoff (from the adversarial review):
--   1. Allow the transient 'uploading' status so the upload route can CLAIM the single-use lock
--      BEFORE buffering the body (bounds concurrent-upload memory/bandwidth DoS).
--   2. Drop the owner UPDATE policy: every real write goes through the service role, and the
--      desktop owner only needs SELECT to poll — so the owner can no longer reset their own row
--      to defeat single-use or extend the TTL.
alter table public.phone_link_sessions drop constraint if exists phone_link_sessions_status_check;
alter table public.phone_link_sessions add constraint phone_link_sessions_status_check
  check (status in ('pending', 'uploading', 'uploaded', 'consumed', 'expired'));

drop policy if exists phone_link_sessions_owner_update on public.phone_link_sessions;
