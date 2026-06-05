import { createClient } from "@supabase/supabase-js";

/**
 * Service-role client — bypasses RLS. SERVER-ONLY. Use only for trusted operations
 * (signed URLs into a user's own folder, job bookkeeping). Never expose to the browser.
 */
export function createAdminClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false, autoRefreshToken: false } },
  );
}
