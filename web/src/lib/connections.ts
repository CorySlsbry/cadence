// Per-user BYOK connections. ElevenLabs / Gemini / Anthropic have NO end-user OAuth in 2026
// (verified) — each is "paste your own API key", validated with a free GET before we ever store
// it. Validation + provider metadata live here; encryption + persistence live in the route.

export type Provider = "gemini" | "elevenlabs" | "anthropic";

export const PROVIDERS: readonly Provider[] = ["gemini", "elevenlabs", "anthropic"] as const;

export function isProvider(p: string): p is Provider {
  return (PROVIDERS as readonly string[]).includes(p);
}

export type ValidateResult = { ok: true; last4: string } | { ok: false; error: string };

/** Validate a pasted key with a free, no-spend call to the provider. Never stores anything. */
export async function validateKey(provider: Provider, rawKey: string): Promise<ValidateResult> {
  const key = rawKey.trim();
  if (key.length < 8) return { ok: false, error: "That key looks too short." };
  try {
    let res: Response;
    if (provider === "gemini") {
      res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`,
        { method: "GET" },
      );
    } else if (provider === "elevenlabs") {
      res = await fetch("https://api.elevenlabs.io/v1/user", { headers: { "xi-api-key": key } });
    } else {
      res = await fetch("https://api.anthropic.com/v1/models", {
        headers: { "x-api-key": key, "anthropic-version": "2023-06-01" },
      });
    }
    if (res.ok) return { ok: true, last4: key.slice(-4) };
    if (res.status === 401 || res.status === 403)
      return { ok: false, error: "That key is invalid or unauthorized (check it has the right scope)." };
    if (res.status === 429)
      return { ok: false, error: "That key is rate-limited or out of quota right now." };
    return { ok: false, error: `Provider rejected the key (HTTP ${res.status}).` };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "network error reaching provider" };
  }
}

export const PROVIDER_META: Record<
  Provider,
  { label: string; createUrl: string; createLabel: string; why: string }
> = {
  gemini: {
    label: "Google Gemini",
    createUrl: "https://aistudio.google.com/apikey",
    createLabel: "AI Studio → Get API key",
    why: "Captions, hooks, clip selection, repurposing, and AI b-roll run on your Gemini quota.",
  },
  elevenlabs: {
    label: "ElevenLabs",
    createUrl: "https://elevenlabs.io/app/developers/api-keys",
    createLabel: "Developers → API Keys",
    why: "Premium AI voiceover uses your ElevenLabs credits.",
  },
  anthropic: {
    label: "Anthropic (Claude)",
    createUrl: "https://platform.claude.com/settings/keys",
    createLabel: "Settings → API Keys",
    why: "Powers Claude-driven features and the tools the Cadence MCP server runs for you.",
  },
};
