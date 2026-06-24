import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { resolveElevenLabsKey, ttsMp3 } from "@/lib/elevenlabs";
import { geminiJson } from "@/lib/gemini";
import { pokeWorker } from "@/lib/worker";

export const maxDuration = 300;

// Avatar is a premium, GPU-heavy feature (~$0.40/video on the L4). Flat token cost gives
// ~65% margin at ~$0.141 retail/token; Creator-tier only; capped per calendar month so a
// single user can't run up unbounded GPU minutes.
const AVATAR_TOKEN_COST = 8;
const AVATAR_MONTHLY_CAP = 20;

// Render a photoreal talking-avatar video. Mirrors /api/faceless (token gate → narration
// in the user's cloned voice → upload as the job "recording" → enqueue), but stamps
// customization.avatar so the worker's avatar branch lip-syncs the reference + composites.
const FRAMINGS = new Set(["lower_third", "full", "corner"]);
const MODES = new Set(["standalone", "presenter"]);

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }
  const mode = MODES.has(String(body.mode)) ? String(body.mode) : "standalone";
  const framing = FRAMINGS.has(String(body.framing)) ? String(body.framing) : "lower_third";
  const look = String(body.look ?? "cinematic");
  let script = String(body.script ?? "").trim();
  const topic = String(body.topic ?? "").trim();
  if (!script && !topic) {
    return NextResponse.json({ error: "script or topic required" }, { status: 422 });
  }

  // 1) Load the avatar (RLS scopes it to the owner).
  const { data: ch } = await supabase
    .from("characters")
    .select("id, kind, voice_id")
    .eq("id", id).eq("user_id", user.id).maybeSingle();
  if (!ch || ch.kind !== "photoreal") {
    return NextResponse.json({ error: "photoreal avatar not found" }, { status: 404 });
  }

  // 2) Consent FAIL-CLOSED — never render a likeness without an active consent record.
  const { data: consent } = await supabase
    .from("consent_records")
    .select("id")
    .eq("character_id", id).is("revoked_at", null).limit(1).maybeSingle();
  if (!consent) {
    return NextResponse.json(
      { error: "consent on file is missing or revoked — re-create this avatar to continue" },
      { status: 403 },
    );
  }

  // 3) Premium gate + cost + monthly cap. Avatar is GPU-heavy, so it's Creator-tier only,
  //    bills a flat AVATAR_TOKEN_COST (prepaid below; the worker skips per-scene burn for
  //    avatar jobs), and is capped at AVATAR_MONTHLY_CAP renders per calendar month.
  const { data: profile } = await supabase
    .from("profiles")
    .select("plan, tokens")
    .eq("id", user.id)
    .single();
  const plan = String(profile?.plan ?? "free");
  if (plan !== "creator" && plan !== "admin") {
    return NextResponse.json(
      { error: "Photoreal avatars are a Creator-plan feature. Upgrade on the Pricing page to unlock." },
      { status: 403 },
    );
  }
  if (((profile?.tokens as number) ?? 0) < AVATAR_TOKEN_COST) {
    return NextResponse.json(
      { error: `Avatar videos cost ${AVATAR_TOKEN_COST} tokens. Top up or upgrade on the Pricing page.` },
      { status: 402 },
    );
  }
  const monthStart = new Date();
  monthStart.setUTCDate(1);
  monthStart.setUTCHours(0, 0, 0, 0);
  const { count: usedThisMonth } = await supabase
    .from("render_jobs")
    .select("id", { count: "exact", head: true })
    .eq("user_id", user.id)
    .not("customization->avatar", "is", null)
    .neq("status", "error")
    .gte("created_at", monthStart.toISOString());
  if ((usedThisMonth ?? 0) >= AVATAR_MONTHLY_CAP) {
    return NextResponse.json(
      { error: `You've reached this month's limit of ${AVATAR_MONTHLY_CAP} avatar videos.` },
      { status: 429 },
    );
  }

  // 4) Voice — the avatar speaks in the user's own cloned voice (ElevenLabs BYOK).
  if (!ch.voice_id) {
    return NextResponse.json(
      { error: "this avatar has no cloned voice — re-create it with a voice sample" },
      { status: 400 },
    );
  }
  const key = await resolveElevenLabsKey(user.id);
  if (!key) {
    return NextResponse.json(
      { error: "Connect your ElevenLabs key in Connections — narration runs on your plan." },
      { status: 400 },
    );
  }

  // 5) Script (provided, or generated from the topic).
  let title = topic.slice(0, 70) || "Avatar video";
  if (!script) {
    const lengthSec = Math.max(15, Math.min(Number(body.lengthSec) || 45, 90));
    try {
      const out = await geminiJson<{ title: string; body: string }>({
        model: "gemini-2.5-pro",
        temperature: 0.8,
        prompt: `Write a ${lengthSec}-second first-person short-form video script (the speaker is on camera talking to the viewer) about: ${topic}
RULES: spoken prose only — no stage directions, no emoji; contractions; open with a scroll-stopping hook; end with ONE clear CTA.
Return STRICT JSON: {"title":"<=70 chars","body":"the script"}`,
      });
      script = (out.body ?? "").trim();
      title = (out.title ?? title).slice(0, 200);
    } catch (e) {
      return NextResponse.json(
        { error: `script generation failed: ${e instanceof Error ? e.message : "unknown"}` },
        { status: 502 },
      );
    }
    if (!script) return NextResponse.json({ error: "empty script generated" }, { status: 502 });
  }

  // 6) Narration in the user's voice → upload as the job's "recording".
  let audio: Buffer;
  try {
    audio = await ttsMp3(key, ch.voice_id, script);
  } catch (e) {
    return NextResponse.json(
      { error: `voice synthesis failed: ${e instanceof Error ? e.message : "unknown"}` },
      { status: 502 },
    );
  }
  const recordingPath = `${user.id}/avatar-narration-${Date.now()}.mp3`;
  const { error: upErr } = await supabase.storage
    .from("uploads")
    .upload(recordingPath, audio, { upsert: true, contentType: "audio/mpeg" });
  if (upErr) {
    return NextResponse.json({ error: `audio upload failed: ${upErr.message}` }, { status: 500 });
  }

  // 7) Enqueue — the worker's avatar branch lip-syncs the reference + composites/standalone.
  const { data: job, error } = await supabase
    .from("render_jobs")
    .insert({
      user_id: user.id,
      project_id: (body.projectId as string) ?? null,
      recording_path: recordingPath,
      customization: {
        avatar: { character_id: id, mode, framing, coherence: String(body.coherence ?? "photoreal") },
        faceless: { topic: title, scene_style: look, scene_direction: "", animate: !!body.animate },
        preset: String(body.style ?? "clean"),
        resolution: String(body.resolution ?? "1080p"),
        captions: true,
        caption_mode: "karaoke",
        broll_mode: "ai",
      },
    })
    .select("id")
    .single();
  if (error || !job) {
    return NextResponse.json({ error: error?.message ?? "could not queue the render" }, { status: 500 });
  }
  // The AUTHORITATIVE Creator-gate + monthly cap + AVATAR_TOKEN_COST charge run in the WORKER
  // (the GPU choke point) — a render_jobs row can be inserted directly via RLS, so the checks
  // above are advisory UX only. Do NOT charge here (the worker would then double-bill).
  await pokeWorker(); // start now instead of waiting for the every-minute drain tick
  return NextResponse.json({ jobId: job.id, tokensCharged: AVATAR_TOKEN_COST });
}
