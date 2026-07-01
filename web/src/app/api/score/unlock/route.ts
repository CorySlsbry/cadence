import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { clientIp } from "@/lib/ip";
import { sendScoreReport } from "@/lib/email";
import type { ScoreResult } from "@/lib/score";

export const runtime = "nodejs";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Email gate: trades an email for the full fixes + a mailed report (jaredrhod: capture at the value
// moment). Captures the lead and sends the report from support@neuron-HQ.com (best-effort).
export async function POST(req: Request) {
  const admin = createAdminClient();
  const ip = clientIp(req);
  const { data: rlOk, error: rlErr } = await admin.rpc("rl_bump", { p_key: `unlock:${ip}`, p_limit: 20, p_window_sec: 60 });
  if (rlErr || rlOk !== true) return NextResponse.json({ error: "Slow down a moment." }, { status: 429 });

  let body: { id?: string; email?: string; utm?: Record<string, string> };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }
  const id = (body.id || "").trim();
  const email = (body.email || "").trim().toLowerCase();
  if (!EMAIL_RE.test(email) || email.length > 254) {
    return NextResponse.json({ error: "Enter a valid email." }, { status: 422 });
  }
  if (!id) return NextResponse.json({ error: "missing score id" }, { status: 422 });

  // Load + validate the score row FIRST, so a junk/guessed id can't burn a real email's send quota.
  const { data: row } = await admin
    .from("score_results")
    .select("id, result, score, platform, input")
    .eq("id", id)
    .maybeSingle();
  if (!row) return NextResponse.json({ error: "score not found" }, { status: 404 });

  // Per-recipient cap (only after the id is known-good): a public score id must not email-bomb an address.
  const { data: mailOk, error: mailErr } = await admin.rpc("rl_bump", { p_key: `unlockmail:${email}`, p_limit: 3, p_window_sec: 3600 });
  if (mailErr || mailOk !== true) {
    return NextResponse.json({ error: "We've already sent recent reports to that email — check your inbox." }, { status: 429 });
  }

  await admin.from("leads").insert({ email, source: "viral_score", score_result_id: id, utm: body.utm ?? null });
  // Stamp the email only once — don't let a later caller clobber the original captor's email.
  await admin.from("score_results").update({ email }).eq("id", id).is("email", null);

  // Best-effort report email from support@neuron-HQ.com — never block the unlock on mail delivery.
  try {
    await sendScoreReport(email, row.result as ScoreResult, id);
    await admin.from("leads").update({ emailed_at: new Date().toISOString() }).eq("email", email).eq("score_result_id", id);
  } catch (e) {
    console.error("[score] report email failed:", e instanceof Error ? e.message : e);
  }

  return NextResponse.json({ ok: true, result: row.result });
}
