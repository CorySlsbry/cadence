import { createAdminClient } from "@/lib/supabase/admin";
import { decryptSecret } from "@/lib/crypto";

/**
 * ElevenLabs voice features are BYOK: each user's key lives encrypted in the
 * user_connections vault and is decrypted server-side at use. The platform's own
 * key (env) backs the admin/owner account only — regular users connect theirs in
 * /connections, which keeps third-party voice spend on the customer's plan.
 */

const API = "https://api.elevenlabs.io/v1";

export type ElVoice = {
  voice_id: string;
  name: string;
  category: string; // "cloned" | "premade" | "professional" | ...
  preview_url: string | null;
};

export async function resolveElevenLabsKey(userId: string): Promise<string | null> {
  const admin = createAdminClient();
  const { data: conn } = await admin
    .from("user_connections")
    .select("secret_enc,status")
    .eq("user_id", userId)
    .eq("provider", "elevenlabs")
    .maybeSingle();
  if (conn?.status === "active" && conn.secret_enc) {
    try {
      return decryptSecret(conn.secret_enc);
    } catch {
      /* corrupt blob → treat as not connected */
    }
  }
  const { data: profile } = await admin.from("profiles").select("plan").eq("id", userId).single();
  if (profile?.plan === "admin" && process.env.ELEVENLABS_API_KEY) {
    return process.env.ELEVENLABS_API_KEY; // owner convenience — never for regular users
  }
  return null;
}

export async function listVoices(key: string): Promise<ElVoice[]> {
  const res = await fetch(`${API}/voices`, { headers: { "xi-api-key": key } });
  if (!res.ok) throw new Error(`elevenlabs voices ${res.status}`);
  const data = (await res.json()) as { voices?: { voice_id: string; name: string; category?: string; preview_url?: string }[] };
  const voices = (data.voices ?? []).map((v) => ({
    voice_id: v.voice_id,
    name: v.name,
    category: v.category ?? "premade",
    preview_url: v.preview_url ?? null,
  }));
  // Cloned/professional voices first (the whole point), then a curated slice of premades.
  const own = voices.filter((v) => v.category !== "premade");
  const premade = voices.filter((v) => v.category === "premade").slice(0, 8);
  return [...own, ...premade];
}

/** Narration TTS → MP3 buffer (eleven_multilingual_v2 — the quality/stability sweet spot). */
export async function ttsMp3(key: string, voiceId: string, text: string): Promise<Buffer> {
  const res = await fetch(`${API}/text-to-speech/${voiceId}?output_format=mp3_44100_128`, {
    method: "POST",
    headers: { "xi-api-key": key, "content-type": "application/json" },
    body: JSON.stringify({
      text,
      model_id: "eleven_multilingual_v2",
      voice_settings: { stability: 0.5, similarity_boost: 0.75 },
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`elevenlabs tts ${res.status}: ${detail.slice(0, 300)}`);
  }
  return Buffer.from(await res.arrayBuffer());
}

/** Per-line dialogue TTS → raw 24kHz s16le PCM (concatenates cleanly across voices). */
export async function ttsPcm24k(key: string, voiceId: string, text: string): Promise<Buffer> {
  const res = await fetch(`${API}/text-to-speech/${voiceId}?output_format=pcm_24000`, {
    method: "POST",
    headers: { "xi-api-key": key, "content-type": "application/json" },
    body: JSON.stringify({
      text,
      model_id: "eleven_multilingual_v2",
      voice_settings: { stability: 0.5, similarity_boost: 0.75 },
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`elevenlabs tts ${res.status}: ${detail.slice(0, 300)}`);
  }
  return Buffer.from(await res.arrayBuffer());
}

/** Instant voice clone from one or more samples. Returns the new voice id. */
export async function cloneVoice(key: string, name: string, files: File[]): Promise<string> {
  const form = new FormData();
  form.append("name", name.slice(0, 80));
  form.append("remove_background_noise", "true");
  for (const f of files) form.append("files", f, f.name || "sample.webm");
  const res = await fetch(`${API}/voices/add`, {
    method: "POST",
    headers: { "xi-api-key": key },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`clone ${res.status}: ${detail.slice(0, 300)}`);
  }
  const data = (await res.json()) as { voice_id?: string };
  if (!data.voice_id) throw new Error("clone returned no voice id");
  return data.voice_id;
}

export async function deleteVoice(key: string, voiceId: string): Promise<void> {
  await fetch(`${API}/voices/${voiceId}`, { method: "DELETE", headers: { "xi-api-key": key } });
}
