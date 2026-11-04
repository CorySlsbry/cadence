import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { cloneVoice, resolveElevenLabsKey } from "@/lib/elevenlabs";

export const maxDuration = 120;

/**
 * In-app instant voice clone: a mic recording (or uploaded sample) → the user's own
 * ElevenLabs voice library → immediately usable for faceless narration. BYOK only —
 * cloning runs on the customer's ElevenLabs plan, never the platform's.
 */
export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const key = await resolveElevenLabsKey(user.id);
  if (!key) {
    return NextResponse.json(
      { error: "Connect your ElevenLabs key in Connections first — cloning runs on your ElevenLabs plan." },
      { status: 400 },
    );
  }

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return NextResponse.json({ error: "expected multipart form data" }, { status: 422 });
  }
  const name = String(form.get("name") ?? "").trim() || "My voice";
  const files = form.getAll("files").filter((f): f is File => f instanceof File && f.size > 0);
  if (files.length === 0) {
    return NextResponse.json({ error: "record or upload at least one sample" }, { status: 422 });
  }
  const total = files.reduce((s, f) => s + f.size, 0);
  if (total > 25 * 1024 * 1024) {
    return NextResponse.json({ error: "samples too large (25MB max)" }, { status: 413 });
  }

  try {
    const voiceId = await cloneVoice(key, name, files);
    return NextResponse.json({ voice_id: voiceId, name });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "clone failed";
    // ElevenLabs explains plan limitations clearly (e.g. cloning needs Starter+) — surface it.
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
