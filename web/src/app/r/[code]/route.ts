import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { publicOrigin } from "@/lib/request-origin";

/**
 * Pretty affiliate link: clouthook.com/r/CODE
 * Counts the click, drops a 90-day attribution cookie, and lands on the homepage.
 * The (app) layout claims the cookie server-side after ANY signup path (email,
 * Google OAuth, magic link), so attribution survives every route into the app.
 */
export async function GET(request: Request, ctx: { params: Promise<{ code: string }> }) {
  const { code } = await ctx.params;
  const clean = (code || "").toLowerCase().trim().slice(0, 24);

  if (clean) {
    try {
      await createAdminClient().rpc("record_affiliate_click", { p_code: clean });
    } catch {
      /* a dead counter must never break the landing */
    }
  }

  const res = NextResponse.redirect(new URL(`/?ref=${encodeURIComponent(clean)}`, publicOrigin(request)), 302);
  res.cookies.set("ch_ref", clean, {
    maxAge: 60 * 60 * 24 * 90, // 90-day referral window
    path: "/",
    sameSite: "lax",
    httpOnly: false, // the signup form also reads it client-side
    secure: true,
  });
  return res;
}
