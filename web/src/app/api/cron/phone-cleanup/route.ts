import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

// Cloud Scheduler -> POST with x-payout-secret (the shared operator cron secret). Idempotent;
// safe at any cadence. (1) expires phone sessions past their TTL, (2) deletes abandoned phone
// clips (uploaded but never consumed within 2h) so biometric data isn't retained, (3) prunes
// old rate-limit buckets.
export async function POST(request: Request) {
  const secret = process.env.PAYOUT_RUN_SECRET;
  if (!secret || request.headers.get("x-payout-secret") !== secret) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const admin = createAdminClient();
  const now = Date.now();

  // 1) Expire pending/uploading sessions past their TTL.
  const { data: expired } = await admin
    .from("phone_link_sessions")
    .update({ status: "expired" })
    .in("status", ["pending", "uploading"])
    .lt("expires_at", new Date(now).toISOString())
    .select("id");

  // 2) Abandoned: uploaded but never consumed within 2h -> delete the clip + expire the row.
  const cutoff = new Date(now - 2 * 60 * 60 * 1000).toISOString();
  const { data: stale } = await admin
    .from("phone_link_sessions")
    .select("id, recording_path")
    .eq("status", "uploaded")
    .lt("uploaded_at", cutoff);
  const paths = (stale ?? []).map((r) => r.recording_path).filter(Boolean) as string[];
  if (paths.length) {
    try {
      await admin.storage.from("uploads").remove(paths);
    } catch {
      /* best-effort; the row is still expired below */
    }
    await admin
      .from("phone_link_sessions")
      .update({ status: "expired" })
      .in("id", (stale ?? []).map((r) => r.id));
  }

  // 3) Prune rate-limit buckets older than a day.
  await admin.from("rate_limits").delete().lt("window_start", new Date(now - 86_400_000).toISOString());

  return NextResponse.json({ expired: expired?.length ?? 0, purged_clips: paths.length });
}
