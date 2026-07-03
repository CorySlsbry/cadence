// Fed by a Supabase Database Webhook on INSERT into public.profiles. A row is created for
// every new user regardless of method (email/password, Google OAuth, magic-link), so this
// fires for ALL signups with zero client-side change. Configure the webhook to POST here and
// send the shared secret in the `x-signup-secret` header (must equal SIGNUP_HOOK_SECRET).
import { NextResponse } from "next/server";
import { timingSafeEqual } from "crypto";
import { notifySlack } from "@/lib/notify-slack";

function secretMatches(provided: string | null): boolean {
  const expected = process.env.SIGNUP_HOOK_SECRET;
  if (!expected || !provided) return false;
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false; // timingSafeEqual throws on length mismatch
  return timingSafeEqual(a, b);
}

export async function POST(req: Request) {
  if (!secretMatches(req.headers.get("x-signup-secret"))) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  // Supabase DB webhooks POST { type, table, record: {...} }; also accept a flat { email, id }.
  type Rec = { email?: string; full_name?: string; id?: string };
  let body: { email?: string; id?: string; record?: Rec | null } = {};
  try {
    body = await req.json();
  } catch {
    // Tolerate empty/invalid body — the alert is best-effort.
  }
  const rec: Rec = (body.record ?? body) as Rec;

  await notifySlack({
    kind: "signup",
    title: rec.full_name ? `New signup — ${rec.full_name}` : "New signup",
    email: rec.email,
  });
  return NextResponse.json({ ok: true });
}
