-- Security audit 2026-07-03 (applied to prod via MCP; committed for version control).
-- Locks the RPC surface flagged by the Supabase security linter (lints 0011/0028/0029).
-- notify_signup is a TRIGGER function (fires on profiles INSERT) — never legitimately called via
-- /rest/v1/rpc. Revoke from both API roles.
revoke execute on function public.notify_signup() from anon, authenticated;
-- rl_bump is a rate-limit primitive. score/upload paths call it via the service role; only the
-- authenticated phone-session route uses the user client. Keep authenticated, drop anon (anon could
-- otherwise bump arbitrary keys to grief the limiter / lock out IPs+emails).
revoke execute on function public.rl_bump(text, integer, integer) from anon;
-- These SECURITY DEFINER readers already filter by auth.uid() (anon => empty rows), and only
-- signed-in users ever call them client-side. Drop anon EXECUTE to shrink the anonymous RPC surface.
revoke execute on function public.my_social_connections() from anon;
revoke execute on function public.my_connections() from anon;
-- Close the mutable-search_path warning on the privileged-column guard trigger.
alter function public.guard_profiles_privileged_cols() set search_path = public;
