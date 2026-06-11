import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { listVoices, resolveElevenLabsKey } from "@/lib/elevenlabs";

/** The user's ElevenLabs voices (cloned first) for the Faceless studio voice picker. */
export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const key = await resolveElevenLabsKey(user.id);
  if (!key) return NextResponse.json({ connected: false, voices: [] });

  try {
    const voices = await listVoices(key);
    return NextResponse.json({ connected: true, voices });
  } catch (e) {
    return NextResponse.json(
      { connected: true, voices: [], error: e instanceof Error ? e.message : "voices failed" },
      { status: 502 },
    );
  }
}
