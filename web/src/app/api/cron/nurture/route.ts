import { NextResponse } from "next/server";
import { timingSafeEqual } from "crypto";
import { createAdminClient } from "@/lib/supabase/admin";
import { sendFunnelEmail, type FunnelTemplate } from "@/lib/email";

// Daily lifecycle nurture. Hit by Cloud Scheduler (GET with an x-cron-secret header). Sends the
// day-N email to accounts created ~N days ago that are still on the free plan and haven't already
// received that template (email_log unique guard). Idempotent + safe to run repeatedly.

export const dynamic = "force-dynamic";

function secretOk(provided: string | null): boolean {
  const expected = process.env.CRON_SECRET;
  if (!expected || !provided) return false;
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

// [dayLo, dayHi) age window per step — a 1-day catch window so a daily run never misses anyone.
const STEPS: { template: FunnelTemplate; dayLo: number; dayHi: number }[] = [
  { template: "nurture_day2", dayLo: 2, dayHi: 3 },
  { template: "nurture_day5", dayLo: 5, dayHi: 6 },
  { template: "nurture_day12", dayLo: 12, dayHi: 13 },
];

const DAY = 86_400_000;

export async function GET(req: Request) {
  if (!secretOk(req.headers.get("x-cron-secret"))) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const admin = createAdminClient();
  const now = Date.now();
  const sent: Record<string, number> = {};

  for (const step of STEPS) {
    const loIso = new Date(now - step.dayHi * DAY).toISOString();
    const hiIso = new Date(now - step.dayLo * DAY).toISOString();
    const { data: candidates } = await admin
      .from("profiles")
      .select("id, email, full_name, created_at, plan")
      .gte("created_at", loIso)
      .lt("created_at", hiIso)
      .eq("plan", "free")
      .limit(500);

    let count = 0;
    for (const p of (candidates ?? []) as { id: string; email: string | null; full_name: string | null }[]) {
      if (!p.email) continue;
      // Reserve the send first — unique(user_id, template) makes it exactly-once across runs.
      const { error } = await admin
        .from("email_log")
        .insert({ user_id: p.id, email: p.email, template: step.template });
      if (error) continue; // already sent (or a transient error) → skip this run
      const ok = await sendFunnelEmail(p.email, step.template, p.full_name ?? undefined);
      if (ok) count++;
      else {
        // Relay not configured / send failed → release the reservation so a later run retries
        // (while the account is still inside the age window).
        await admin.from("email_log").delete().eq("user_id", p.id).eq("template", step.template);
      }
    }
    sent[step.template] = count;
  }

  return NextResponse.json({ ok: true, sent });
}
