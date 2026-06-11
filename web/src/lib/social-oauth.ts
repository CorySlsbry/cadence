// Direct per-platform social OAuth (YouTube / TikTok / Instagram), beyond the Blotato broker.
// Each platform differs (param names, PKCE, token-response shape, long-lived exchange), so the
// registry encapsulates that behind exchangeToken() + userInfo(). The connect flow:
//   /api/social/oauth/[platform]/start  -> signed-state cookie + redirect to the platform
//   /api/social/oauth/[platform]/callback -> verify state, exchange code, fetch handle, store
// Tokens are AES-256-GCM encrypted into social_connections (service-role only).
//
// SETUP (per platform, on its developer portal — see mcp/SOCIAL_OAUTH_SETUP.md):
//   redirect URI = https://<web>/api/social/oauth/<platform>/callback
//   secrets (Secret Manager / env): CADENCE_<PLATFORM>_CLIENT_ID / _CLIENT_SECRET
import { createHash, createHmac, randomBytes } from "crypto";

export type SocialPlatform = "youtube" | "tiktok" | "instagram" | "x";
export const SOCIAL_PLATFORMS: readonly SocialPlatform[] = ["youtube", "tiktok", "instagram", "x"] as const;
export function isSocialPlatform(p: string): p is SocialPlatform {
  return (SOCIAL_PLATFORMS as readonly string[]).includes(p);
}

const WEB_BASE = (process.env.CADENCE_WEB_BASE_URL || "https://cadence-web-840472456279.us-west1.run.app").replace(/\/$/, "");
export const redirectUri = (platform: string) => `${WEB_BASE}/api/social/oauth/${platform}/callback`;

export type TokenSet = {
  access: string;
  refresh?: string | null;
  expiresIn?: number | null; // seconds
  scopes?: string | null;
};

type PlatformCfg = {
  label: string;
  /** True once its client-id/secret env vars are present (so the UI can gate the button). */
  configured: () => boolean;
  /** Build the platform authorization URL the user is redirected to. */
  authorizeUrl: (state: string, challenge: string) => string;
  pkce: boolean;
  /** Exchange the callback code (+ PKCE verifier) for tokens. */
  exchangeToken: (code: string, verifier: string) => Promise<TokenSet>;
  /** Fetch the connected account's id + handle for display. */
  userInfo: (access: string) => Promise<{ id?: string; username?: string }>;
  /** Refresh an expired access token (platforms with short-lived tokens, e.g. X's 2h). */
  refreshToken?: (refresh: string) => Promise<TokenSet>;
};

function env(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`${name} is not configured`);
  return v;
}
const has = (...names: string[]) => names.every((n) => !!process.env[n]);

async function postForm(url: string, body: Record<string, string>, headers: Record<string, string> = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json", ...headers },
    body: new URLSearchParams(body).toString(),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`token exchange failed (${res.status}): ${JSON.stringify(json).slice(0, 200)}`);
  return json as Record<string, unknown>;
}

export const SOCIAL: Record<SocialPlatform, PlatformCfg> = {
  // --- YouTube (Google OAuth 2.0) — the reference; standard auth-code + refresh -------------
  youtube: {
    label: "YouTube",
    configured: () => has("CADENCE_YOUTUBE_CLIENT_ID", "CADENCE_YOUTUBE_CLIENT_SECRET"),
    pkce: false,
    authorizeUrl: (state) =>
      "https://accounts.google.com/o/oauth2/v2/auth?" +
      new URLSearchParams({
        client_id: env("CADENCE_YOUTUBE_CLIENT_ID"),
        redirect_uri: redirectUri("youtube"),
        response_type: "code",
        scope: "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        access_type: "offline",
        prompt: "consent",
        include_granted_scopes: "true",
        state,
      }).toString(),
    exchangeToken: async (code) => {
      const j = await postForm("https://oauth2.googleapis.com/token", {
        code, client_id: env("CADENCE_YOUTUBE_CLIENT_ID"), client_secret: env("CADENCE_YOUTUBE_CLIENT_SECRET"),
        redirect_uri: redirectUri("youtube"), grant_type: "authorization_code",
      });
      return { access: j.access_token as string, refresh: (j.refresh_token as string) ?? null,
               expiresIn: (j.expires_in as number) ?? null, scopes: (j.scope as string) ?? null };
    },
    userInfo: async (access) => {
      const r = await fetch("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
        { headers: { authorization: `Bearer ${access}` } });
      const j = await r.json().catch(() => ({}));
      const ch = (j.items && j.items[0]) || {};
      return { id: ch.id, username: ch?.snippet?.title };
    },
  },

  // --- TikTok (OAuth v2, PKCE required, client_key naming) ----------------------------------
  tiktok: {
    label: "TikTok",
    configured: () => has("CADENCE_TIKTOK_CLIENT_KEY", "CADENCE_TIKTOK_CLIENT_SECRET"),
    pkce: true,
    authorizeUrl: (state, challenge) =>
      "https://www.tiktok.com/v2/auth/authorize/?" +
      new URLSearchParams({
        client_key: env("CADENCE_TIKTOK_CLIENT_KEY"),
        redirect_uri: redirectUri("tiktok"),
        response_type: "code",
        scope: "user.info.basic,video.publish,video.upload",
        state,
        code_challenge: challenge,
        code_challenge_method: "S256",
      }).toString(),
    exchangeToken: async (code, verifier) => {
      const j = await postForm("https://open.tiktokapis.com/v2/oauth/token/", {
        client_key: env("CADENCE_TIKTOK_CLIENT_KEY"), client_secret: env("CADENCE_TIKTOK_CLIENT_SECRET"),
        code, grant_type: "authorization_code", redirect_uri: redirectUri("tiktok"), code_verifier: verifier,
      });
      return { access: j.access_token as string, refresh: (j.refresh_token as string) ?? null,
               expiresIn: (j.expires_in as number) ?? null, scopes: (j.scope as string) ?? null };
    },
    userInfo: async (access) => {
      const r = await fetch("https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name",
        { headers: { authorization: `Bearer ${access}` } });
      const j = await r.json().catch(() => ({}));
      return { id: j?.data?.user?.open_id, username: j?.data?.user?.display_name };
    },
  },

  // --- Instagram (Instagram API with Instagram Login; short -> long-lived token) -------------
  instagram: {
    label: "Instagram",
    configured: () => has("CADENCE_INSTAGRAM_CLIENT_ID", "CADENCE_INSTAGRAM_CLIENT_SECRET"),
    pkce: false,
    authorizeUrl: (state) =>
      "https://www.instagram.com/oauth/authorize?" +
      new URLSearchParams({
        client_id: env("CADENCE_INSTAGRAM_CLIENT_ID"),
        redirect_uri: redirectUri("instagram"),
        response_type: "code",
        scope: "instagram_business_basic,instagram_business_content_publish",
        state,
      }).toString(),
    exchangeToken: async (code) => {
      // 1) short-lived token
      const short = await postForm("https://api.instagram.com/oauth/access_token", {
        client_id: env("CADENCE_INSTAGRAM_CLIENT_ID"), client_secret: env("CADENCE_INSTAGRAM_CLIENT_SECRET"),
        grant_type: "authorization_code", redirect_uri: redirectUri("instagram"), code,
      });
      // 2) exchange for a long-lived (~60d) token
      const longRes = await fetch("https://graph.instagram.com/access_token?" + new URLSearchParams({
        grant_type: "ig_exchange_token", client_secret: env("CADENCE_INSTAGRAM_CLIENT_SECRET"),
        access_token: short.access_token as string,
      }).toString());
      const long = await longRes.json().catch(() => ({}));
      return { access: (long.access_token as string) || (short.access_token as string),
               refresh: null, expiresIn: (long.expires_in as number) ?? null, scopes: "instagram_business_content_publish" };
    },
    userInfo: async (access) => {
      const r = await fetch("https://graph.instagram.com/me?fields=user_id,username&access_token=" + encodeURIComponent(access));
      const j = await r.json().catch(() => ({}));
      return { id: j.user_id, username: j.username };
    },
  },

  // --- X (OAuth 2.0 + PKCE, confidential client: Basic auth on the token endpoint; ----------
  //     2h access tokens, refresh via offline.access)
  x: {
    label: "X",
    configured: () => has("CADENCE_X_CLIENT_ID", "CADENCE_X_CLIENT_SECRET"),
    pkce: true,
    authorizeUrl: (state, challenge) =>
      "https://x.com/i/oauth2/authorize?" +
      new URLSearchParams({
        client_id: env("CADENCE_X_CLIENT_ID"),
        redirect_uri: redirectUri("x"),
        response_type: "code",
        scope: "tweet.read tweet.write users.read media.write offline.access",
        state,
        code_challenge: challenge,
        code_challenge_method: "S256",
      }).toString(),
    exchangeToken: async (code, verifier) => {
      const basic = Buffer.from(`${env("CADENCE_X_CLIENT_ID")}:${env("CADENCE_X_CLIENT_SECRET")}`).toString("base64");
      const j = await postForm("https://api.x.com/2/oauth2/token", {
        code, grant_type: "authorization_code", redirect_uri: redirectUri("x"),
        code_verifier: verifier, client_id: env("CADENCE_X_CLIENT_ID"),
      }, { authorization: `Basic ${basic}` });
      return { access: j.access_token as string, refresh: (j.refresh_token as string) ?? null,
               expiresIn: (j.expires_in as number) ?? null, scopes: (j.scope as string) ?? null };
    },
    refreshToken: async (refresh) => {
      const basic = Buffer.from(`${env("CADENCE_X_CLIENT_ID")}:${env("CADENCE_X_CLIENT_SECRET")}`).toString("base64");
      const j = await postForm("https://api.x.com/2/oauth2/token", {
        refresh_token: refresh, grant_type: "refresh_token", client_id: env("CADENCE_X_CLIENT_ID"),
      }, { authorization: `Basic ${basic}` });
      return { access: j.access_token as string, refresh: (j.refresh_token as string) ?? refresh,
               expiresIn: (j.expires_in as number) ?? null, scopes: (j.scope as string) ?? null };
    },
    userInfo: async (access) => {
      const r = await fetch("https://api.x.com/2/users/me", { headers: { authorization: `Bearer ${access}` } });
      const j = await r.json().catch(() => ({}));
      return { id: j?.data?.id, username: j?.data?.username };
    },
  },
};

// --- HMAC-signed state cookie (CSRF + carries user_id/platform/PKCE verifier) ---------------
function hmacKey(): Buffer {
  return Buffer.from(env("CADENCE_SECRET_ENC_KEY"), "base64");
}
export function signState(payload: Record<string, unknown>): string {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = createHmac("sha256", hmacKey()).update(body).digest("base64url");
  return `${body}.${sig}`;
}
export function verifyState(token: string | undefined): Record<string, unknown> | null {
  if (!token || !token.includes(".")) return null;
  const [body, sig] = token.split(".");
  const expect = createHmac("sha256", hmacKey()).update(body).digest("base64url");
  if (sig !== expect) return null;
  try {
    const data = JSON.parse(Buffer.from(body, "base64url").toString());
    if (data.exp && Date.now() > data.exp) return null;
    return data;
  } catch {
    return null;
  }
}
export function pkcePair(): { verifier: string; challenge: string } {
  const verifier = randomBytes(48).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge };
}
export const randomState = () => randomBytes(16).toString("base64url");
