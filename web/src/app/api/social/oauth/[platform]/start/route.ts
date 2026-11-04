import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { SOCIAL, isSocialPlatform, pkcePair, randomState, signState } from "@/lib/social-oauth";

// Kick off a platform OAuth connect: stash an HMAC-signed state cookie (CSRF + user_id + PKCE
// verifier) and redirect the user to the platform's consent screen.
export async function GET(request: Request, { params }: { params: Promise<{ platform: string }> }) {
  const { platform } = await params;
  if (!isSocialPlatform(platform)) return NextResponse.json({ error: "unknown platform" }, { status: 404 });
  const cfg = SOCIAL[platform];

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.redirect(new URL("/login", request.url));
  if (!cfg.configured()) {
    return NextResponse.redirect(new URL(`/connections?social=${platform}&status=unconfigured`, request.url));
  }

  const state = randomState();
  const { verifier, challenge } = pkcePair();
  const cookie = signState({ user_id: user.id, platform, state, verifier, exp: Date.now() + 600_000 });

  const res = NextResponse.redirect(cfg.authorizeUrl(state, challenge));
  res.cookies.set("cadence_social_oauth", cookie, {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 600,
  });
  return res;
}
