-- FINAL step of multi-account: drop the old unique(user_id, platform) so a user can hold
-- several accounts of the same platform. APPLY THIS ONLY WHEN the new OAuth callback
-- (onConflict "user_id,platform,platform_user_id") is deployed — until then the old constraint
-- must stay so the live callback keeps working. Multi-account is blocked until this runs.
alter table public.social_connections drop constraint if exists social_connections_user_id_platform_key;