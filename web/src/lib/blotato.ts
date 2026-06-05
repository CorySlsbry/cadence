// Thin Blotato REST client. Base: https://backend.blotato.com/v2, auth via the
// `blotato-api-key` header. Blotato owns the per-platform OAuth + app reviews under its
// own approved TikTok/Meta/Google apps, so a single key publishes to every connected
// social account — no per-platform app review on our side.
//
// Target field shapes follow help.blotato.com/api/publish-post; verify on the first live
// post since the response is surfaced to the user for debugging.

const BASE = "https://backend.blotato.com/v2";

export type Platform = "tiktok" | "youtube" | "instagram";
export type BlotatoAccount = { accountId: string; platform: string; name?: string };

async function req(apiKey: string, method: string, path: string, body?: unknown) {
  const res = await fetch(BASE + path, {
    method,
    headers: { "blotato-api-key": apiKey, "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Blotato ${method} ${path} → ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

// GET the accounts the user connected inside Blotato (one per platform we care about).
export async function listAccounts(apiKey: string): Promise<BlotatoAccount[]> {
  const data = await req(apiKey, "GET", "/users/me/accounts");
  const arr: unknown[] = Array.isArray(data) ? data : (data.accounts ?? data.items ?? []);
  return arr
    .map((raw) => {
      const a = raw as Record<string, unknown>;
      return {
        accountId: String(a.accountId ?? a.id ?? ""),
        platform: String(a.platform ?? a.type ?? "").toLowerCase(),
        name: (a.name ?? a.username ?? a.displayName) as string | undefined,
      };
    })
    .filter((a) => a.accountId && a.platform);
}

function target(platform: Platform, title: string) {
  switch (platform) {
    case "tiktok":
      // isAiGenerated=true is the compliant disclosure for AI-assisted video.
      return {
        targetType: "tiktok",
        privacyLevel: "PUBLIC_TO_EVERYONE",
        isAiGenerated: true,
        disabledComments: false,
        disabledDuet: false,
        disabledStitch: false,
        isBrandedContent: false,
        isYourBrand: false,
      };
    case "youtube":
      return { targetType: "youtube", title: title.slice(0, 100), privacyStatus: "public", shouldNotifySubscribers: true };
    case "instagram":
      return { targetType: "instagram", mediaType: "reel", shareToFeed: true };
  }
}

export async function publish(
  apiKey: string,
  opts: { accountId: string; platform: Platform; text: string; videoUrl: string; title?: string },
) {
  const body = {
    post: {
      accountId: opts.accountId,
      content: { text: opts.text, mediaUrls: [opts.videoUrl], platform: opts.platform },
      target: target(opts.platform, opts.title ?? ""),
    },
  };
  return req(apiKey, "POST", "/posts", body);
}
