import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { SOCIAL, isSocialPlatform, pkcePair, randomState, signState } from "@/lib/social-oauth";
import { publicOrigin } from "@/lib/request-origin";

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
  const origin = publicOrigin(request);
  if (!user) return NextResponse.redirect(new URL("/login", origin));
  if (!cfg.configured()) {
    return NextResponse.redirect(new URL(`/connections?social=${platform}&status=unconfigured`, origin));
  }

  // Account-cap enforcement (server-side; the UI also disables "Add another" at the cap).
  // Count this user's existing accounts for the platform and refuse a new connect once at cap.
  const admin = createAdminClient();
  const { data: prof } = await admin.from("profiles").select("plan").eq("id", user.id).maybeSingle();
  const planKey = (prof?.plan as string | null) ?? "free";
  const { data: planRow } = await admin
    .from("plans")
    .select("max_accounts_per_platform")
    .eq("key", planKey)
    .maybeSingle();
  const cap = (planRow?.max_accounts_per_platform as number | null) ?? 1;
  const { count } = await admin
    .from("social_connections")
    .select("id", { count: "exact", head: true })
    .eq("user_id", user.id)
    .eq("platform", platform);
  if ((count ?? 0) >= cap) {
    return NextResponse.redirect(new URL(`/connections?error=account_limit&social=${platform}`, request.url));
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
