import { NextResponse } from "next/server";
import { randomBytes } from "node:crypto";
import QRCode from "qrcode";
import { createClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

// Start a phone-record handoff: mint a 256-bit capability token bound to THIS authed user,
// and return a QR (data URL) the desktop displays. The phone scans it to record + upload one
// reference clip into this user's account. The token is the only capability; it is unguessable
// and scoped to one user via the row's user_id (set here from the session, never from input).
export async function POST() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  // Cap session minting per user (defense vs unbounded session creation).
  const { data: allowed } = await supabase.rpc("rl_bump", {
    p_key: `phsess:${user.id}`,
    p_limit: 10,
    p_window_sec: 3600,
  });
  if (allowed === false) {
    return NextResponse.json({ error: "too many phone sessions — try again in a bit" }, { status: 429 });
  }

  const token = randomBytes(32).toString("hex"); // 256-bit, not guessable
  // Short TTL: a leaked QR/URL is only usable for ~5 min (and only to race a clip into the
  // owner's own folder before their real phone — no read, no cross-account).
  const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();
  const { data: session, error } = await supabase
    .from("phone_link_sessions")
    .insert({ token, user_id: user.id, expires_at: expiresAt })
    .select("token, expires_at")
    .single();
  if (error || !session) {
    return NextResponse.json({ error: "could not start a phone session" }, { status: 500 });
  }

  const base = (process.env.NEXT_PUBLIC_SITE_URL || "https://clouthook.com").replace(/\/$/, "");
  const url = `${base}/m/rec/${token}`;
  const qr = await QRCode.toDataURL(url, { width: 320, margin: 1, errorCorrectionLevel: "M" });
  return NextResponse.json({ token, url, qr, expires_at: session.expires_at });
}
