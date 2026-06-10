import { createAdminClient } from "@/lib/supabase/admin";

/**
 * Multi-tenant render guardrails. Tokens meter AI spend; these meter PIPELINE
 * pressure, which tokens don't cover (clean renders are token-free):
 *  - at most MAX_ACTIVE jobs in flight per user (queued + processing)
 *  - a per-plan rolling-24h render allowance (plans.daily_renders; null = unlimited)
 * Both are friendly 429s, never silent failures.
 */
const MAX_ACTIVE = 2;

export type Allowance = { ok: true } | { ok: false; status: number; error: string };

export async function checkRenderAllowance(userId: string): Promise<Allowance> {
  const admin = createAdminClient();

  const { count: active } = await admin
    .from("render_jobs")
    .select("id", { count: "exact", head: true })
    .eq("user_id", userId)
    .in("status", ["queued", "processing"]);
  if ((active ?? 0) >= MAX_ACTIVE) {
    return {
      ok: false,
      status: 429,
      error: `You already have ${MAX_ACTIVE} videos in the pipeline — let one finish, then fire the next.`,
    };
  }

  const { data: profile } = await admin
    .from("profiles")
    .select("plan")
    .eq("id", userId)
    .single();
  const planKey = profile?.plan ?? "free";
  if (planKey === "admin") return { ok: true };

  const { data: plan } = await admin
    .from("plans")
    .select("daily_renders")
    .eq("key", planKey)
    .maybeSingle();
  const dailyCap = plan?.daily_renders ?? 3; // unknown plan → free allowance
  if (dailyCap === null) return { ok: true };

  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const { count: recent } = await admin
    .from("render_jobs")
    .select("id", { count: "exact", head: true })
    .eq("user_id", userId)
    .gte("created_at", since);
  if ((recent ?? 0) >= dailyCap) {
    return {
      ok: false,
      status: 429,
      error: `You've hit your plan's ${dailyCap} renders per day. Upgrade for a higher daily ceiling — or come back tomorrow.`,
    };
  }

  return { ok: true };
}
