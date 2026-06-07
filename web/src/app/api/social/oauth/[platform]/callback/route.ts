import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createAdminClient } from "@/lib/supabase/admin";
import { encryptSecret } from "@/lib/crypto";
import { SOCIAL, isSocialPlatform, verifyState } from "@/lib/social-oauth";

// OAuth redirect target. Verify the signed-state cookie (CSRF + user id + PKCE verifier),
// exchange the code for tokens, fetch the handle, encrypt + store, and bounce to /connections.
export async function GET(request: Request, { params }: { params: Promise<{ platform: string }> }) {
  const { platform } = await params;
  if (!isSocialPlatform(platform)) return NextResponse.json({ error: "unknown platform" }, { status: 404 });

  const url = new URL(request.url);
  const back = (status: string) =>
    NextResponse.redirect(new URL(`/connections?social=${platform}&status=${status}`, request.url));

  if (url.searchParams.get("error")) return back("denied");

  const jar = await cookies();
  const st = verifyState(jar.get("cadence_social_oauth")?.value);
  if (!st || st.platform !== platform || st.state !== url.searchParams.get("state")) return back("badstate");

  const code = url.searchParams.get("code");
  if (!code) return back("nocode");

  try {
    const tokens = await SOCIAL[platform].exchangeToken(code, String(st.verifier));
    const info: { id?: string; username?: string } = await SOCIAL[platform]
      .userInfo(tokens.access)
      .catch(() => ({}));
    const admin = createAdminClient();
    const { error } = await admin.from("social_connections").upsert(
      {
        user_id: String(st.user_id),
        platform,
        access_token_enc: encryptSecret(tokens.access),
        refresh_token_enc: tokens.refresh ? encryptSecret(tokens.refresh) : null,
        platform_user_id: info.id ?? null,
        username: info.username ?? null,
        scopes: tokens.scopes ?? null,
        expires_at: tokens.expiresIn ? new Date(Date.now() + tokens.expiresIn * 1000).toISOString() : null,
      },
      { onConflict: "user_id,platform" },
    );
    if (error) return back("storefailed");
    const res = back("connected");
    res.cookies.delete("cadence_social_oauth");
    return res;
  } catch {
    return back("exchangefailed");
  }
}
