import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { geminiJson } from "@/lib/gemini";
import { checkRenderAllowance } from "@/lib/limits";

// Faceless videos: topic/script → blueprint-voiced narration → Gemini TTS → the worker
// turns it into AI scenes + karaoke captions. This route does everything up to "queued":
// script generation, speech synthesis, audio upload, job insert.

export const maxDuration = 300;

const TTS_MODEL = "gemini-3.1-flash-tts-preview";

// Curated Gemini prebuilt voices — names are the API values.
const VOICES = new Set(["Charon", "Kore", "Puck", "Aoede", "Fenrir", "Leda"]);

const SCENE_STYLES = new Set([
  "cinematic", "film", "clean", "claymation", "cartoon3d", "anime",
  "comic", "watercolor", "cyberpunk", "papercraft", "character",
]);

const Character = z.object({
  description: z.string().min(3).max(160),
  voiceProvider: z.enum(["gemini", "elevenlabs"]),
  voice: z.string().max(40).optional(),
  voiceId: z.string().max(64).optional(),
  voiceName: z.string().max(80).optional(),
});

const Body = z.object({
  topic: z.string().max(500).optional(),
  script: z.string().max(8000).optional(),
  voice: z.string().default("Charon"),
  voiceProvider: z.enum(["gemini", "elevenlabs"]).default("gemini"),
  voiceId: z.string().max(64).optional(), // ElevenLabs voice id when provider=elevenlabs
  mode: z.enum(["single", "dialogue"]).default("single"),
  characters: z.array(Character).length(2).optional(),
  lengthSec: z.number().min(20).max(180).default(60),
  style: z.enum(["cinematic", "cinematic_film", "clean_ugc"]).default("cinematic"),
  sceneStyle: z.string().max(24).default("cinematic"),
  sceneDirection: z.string().max(400).default(""),
  avatarSheet: z.string().max(900).default(""), // character sheet from /api/avatar
  animate: z.boolean().default(false),
  resolution: z.enum(["1080p", "4k"]).default("1080p"),
  projectId: z.string().uuid().nullable().optional(),
});

function pcmToWav(pcm: Buffer, rate: number): Buffer {
  const h = Buffer.alloc(44);
  h.write("RIFF", 0); h.writeUInt32LE(36 + pcm.length, 4); h.write("WAVE", 8);
  h.write("fmt ", 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20);
  h.writeUInt16LE(1, 22); h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28);
  h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write("data", 36);
  h.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([h, pcm]);
}

async function synthesizeSpeech(text: string, voice: string): Promise<Buffer> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error("GEMINI_API_KEY not configured");
  const style =
    "Read in a warm, confident, conversational voice, like an expert narrator speaking to one person:";
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${TTS_MODEL}:generateContent`,
    {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": key },
      body: JSON.stringify({
        contents: [{ parts: [{ text: `${style} ${text}` }] }],
        generationConfig: {
          responseModalities: ["AUDIO"],
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: voice } } },
        },
      }),
    },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`tts ${res.status}: ${detail.slice(0, 300)}`);
  }
  const data = (await res.json()) as {
    candidates?: { content?: { parts?: { inlineData?: { data?: string; mimeType?: string } }[] } }[];
  };
  const part = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData?.data)?.inlineData;
  if (!part?.data) throw new Error("tts returned no audio");
  let rate = 24000;
  const m = /rate=(\d+)/.exec(part.mimeType ?? "");
  if (m) rate = parseInt(m[1], 10);
  return pcmToWav(Buffer.from(part.data, "base64"), rate);
}

/** Two-speaker dialogue in ONE call — Gemini TTS multi-speaker keeps timing natural. */
async function synthesizeDialogueGemini(script: string, voiceA: string, voiceB: string): Promise<Buffer> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error("GEMINI_API_KEY not configured");
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${TTS_MODEL}:generateContent`,
    {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": key },
      body: JSON.stringify({
        contents: [{ parts: [{ text: `TTS this conversation naturally, with each speaker fully in character:\n${script}` }] }],
        generationConfig: {
          responseModalities: ["AUDIO"],
          speechConfig: {
            multiSpeakerVoiceConfig: {
              speakerVoiceConfigs: [
                { speaker: "A", voiceConfig: { prebuiltVoiceConfig: { voiceName: voiceA } } },
                { speaker: "B", voiceConfig: { prebuiltVoiceConfig: { voiceName: voiceB } } },
              ],
            },
          },
        },
      }),
    },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`dialogue tts ${res.status}: ${detail.slice(0, 300)}`);
  }
  const data = (await res.json()) as {
    candidates?: { content?: { parts?: { inlineData?: { data?: string; mimeType?: string } }[] } }[];
  };
  const part = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData?.data)?.inlineData;
  if (!part?.data) throw new Error("dialogue tts returned no audio");
  let rate = 24000;
  const m = /rate=(\d+)/.exec(part.mimeType ?? "");
  if (m) rate = parseInt(m[1], 10);
  return pcmToWav(Buffer.from(part.data, "base64"), rate);
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: z.infer<typeof Body>;
  try {
    body = Body.parse(await req.json());
  } catch {
    return NextResponse.json({ error: "invalid request body" }, { status: 422 });
  }
  if (!VOICES.has(body.voice)) body.voice = "Charon";

  // Dialogue mode: exactly two cast members, voices from ONE provider.
  const duo = body.mode === "dialogue" ? body.characters : undefined;
  if (body.mode === "dialogue") {
    if (!duo) return NextResponse.json({ error: "two characters required" }, { status: 422 });
    if (duo[0].voiceProvider !== duo[1].voiceProvider) {
      return NextResponse.json(
        { error: "Both characters need voices from the same provider." },
        { status: 422 },
      );
    }
    for (const c of duo) {
      if (c.voiceProvider === "gemini" && !VOICES.has(c.voice ?? "")) {
        return NextResponse.json({ error: "unknown studio voice" }, { status: 422 });
      }
      if (c.voiceProvider === "elevenlabs" && !c.voiceId) {
        return NextResponse.json({ error: "voiceId required for ElevenLabs cast" }, { status: 422 });
      }
    }
  }

  const topic = (body.topic ?? "").trim();
  let script = (body.script ?? "").trim();
  if (!topic && !script) {
    return NextResponse.json({ error: "topic or script required" }, { status: 422 });
  }

  // Same gate as /api/render — faceless burns one token per AI scene in the worker.
  const { data: profile } = await supabase
    .from("profiles").select("tokens").eq("id", user.id).single();
  if (((profile?.tokens as number) ?? 0) <= 0) {
    return NextResponse.json(
      { error: "You're out of tokens. Top up or upgrade on the Pricing page (tap your token badge)." },
      { status: 402 },
    );
  }

  // Pipeline-pressure guardrails BEFORE the expensive script+TTS work.
  const allowance = await checkRenderAllowance(user.id);
  if (!allowance.ok) {
    return NextResponse.json({ error: allowance.error }, { status: allowance.status });
  }

  // 1) Script — written for narration over visuals (not a talking head).
  let title = topic.slice(0, 70) || "Faceless video";
  if (!script) {
    const { data: bp } = await supabase
      .from("brand_blueprints").select("icp,pillars,voice")
      .eq("user_id", user.id).maybeSingle();
    const wordsTarget = Math.round((body.lengthSec / 60) * (duo ? 140 : 150));
    const blueprintBlock = bp
      ? `CREATOR BLUEPRINT (this channel's voice + audience):\n- Ideal viewer: ${JSON.stringify(bp.icp)}\n- Content pillars: ${JSON.stringify(bp.pillars)}\n- Voice: ${JSON.stringify(bp.voice)}`
      : "CREATOR BLUEPRINT: none on file — clear, confident, conversational narration.";
    const dialogueRules = duo
      ? `FORMAT — TWO-CHARACTER DIALOGUE
- Character A: ${duo[0].description}. Character B: ${duo[1].description}.
- EVERY line starts with exactly "A: " or "B: " — alternating naturally (A opens with the hook).
- The conversation TEACHES: A and B genuinely react to each other, disagree briefly, land the payoff together.
- 6-12 total lines, each speakable in 3-8 seconds.`
      : `FORMAT — SINGLE NARRATOR
- Spoken prose ONLY — no headings, no emoji, no stage directions.`;
    try {
      const out = await geminiJson<{ title: string; body: string }>({
        model: "gemini-2.5-pro",
        temperature: 0.8,
        prompt: `Write a ${body.lengthSec}-second (~${wordsTarget} words) FACELESS short-form video ${duo ? "dialogue" : "narration"} about: ${topic}

${blueprintBlock}

${dialogueRules}

RULES
- This is audio over AI-generated visuals — vivid, concrete, scene-paintable sentences (each beat should suggest an image).
- Open with the 7-part hook stack compressed into the first ~8 seconds: pattern interrupt → mirror the viewer → opportunity → gap → transformation → authority → transition.
- Short punchy sentences. Contractions. Second person where natural.
- End with ONE specific call-to-action sentence.

Return STRICT JSON: {"title": "scroll-stopping title (max 70 chars)", "body": "the complete ${duo ? "dialogue with A:/B: line prefixes" : "narration"}"}`,
      });
      script = out.body ?? "";
      title = (out.title ?? title).slice(0, 200);
    } catch (e) {
      return NextResponse.json(
        { error: `script generation failed: ${e instanceof Error ? e.message : "unknown"}` },
        { status: 502 },
      );
    }
    if (!script.trim()) return NextResponse.json({ error: "empty script generated" }, { status: 502 });
  }

  // 2) Narration audio — Gemini studio voices (included) or the user's ElevenLabs
  //    voice (BYOK; includes their in-app clones).
  let audio: Buffer;
  let ext = "wav";
  let mime = "audio/wav";
  let voiceLabel = body.voice;
  try {
    if (duo) {
      if (duo[0].voiceProvider === "gemini") {
        audio = await synthesizeDialogueGemini(script, duo[0].voice ?? "Charon", duo[1].voice ?? "Leda");
        voiceLabel = `duo:${duo[0].voice}+${duo[1].voice}`;
      } else {
        // ElevenLabs cast: per-line synthesis in each character's voice, stitched as PCM.
        const { resolveElevenLabsKey, ttsPcm24k } = await import("@/lib/elevenlabs");
        const { parseDialogueLines } = await import("@/lib/dialogue");
        const key = await resolveElevenLabsKey(user.id);
        if (!key) {
          return NextResponse.json(
            { error: "Connect your ElevenLabs key in Connections to use your own voices." },
            { status: 400 },
          );
        }
        const lines = parseDialogueLines(script);
        if (lines.length < 2) throw new Error("dialogue script did not parse into lines");
        const gap = Buffer.alloc(Math.round(24000 * 0.24) * 2); // 240ms beat between lines
        const chunks: Buffer[] = [];
        for (const line of lines) {
          const vid = line.speaker === "A" ? duo[0].voiceId! : duo[1].voiceId!;
          chunks.push(await ttsPcm24k(key, vid, line.text), gap);
        }
        audio = pcmToWav(Buffer.concat(chunks), 24000);
        voiceLabel = `duo-el:${duo[0].voiceName ?? duo[0].voiceId}+${duo[1].voiceName ?? duo[1].voiceId}`;
      }
    } else if (body.voiceProvider === "elevenlabs") {
      if (!body.voiceId) return NextResponse.json({ error: "voiceId required" }, { status: 422 });
      const { resolveElevenLabsKey, ttsMp3 } = await import("@/lib/elevenlabs");
      const key = await resolveElevenLabsKey(user.id);
      if (!key) {
        return NextResponse.json(
          { error: "Connect your ElevenLabs key in Connections to use your own voice." },
          { status: 400 },
        );
      }
      audio = await ttsMp3(key, body.voiceId, script);
      ext = "mp3";
      mime = "audio/mpeg";
      voiceLabel = `el:${body.voiceId}`;
    } else {
      audio = await synthesizeSpeech(script, body.voice);
    }
  } catch (e) {
    return NextResponse.json(
      { error: `voice synthesis failed: ${e instanceof Error ? e.message : "unknown"}` },
      { status: 502 },
    );
  }

  // Cast members appear in every scene: fold their descriptions into the direction.
  let sceneDirection = body.sceneDirection.trim();
  const avatarSheet = body.avatarSheet.trim();
  if (avatarSheet && !duo) {
    sceneDirection =
      `Every scene stars this exact recurring character (same person each time): ${avatarSheet}` +
      (sceneDirection ? ` ${sceneDirection}` : "");
  }
  if (duo) {
    const { buildCastDirection } = await import("@/lib/dialogue");
    sceneDirection = buildCastDirection(
      { description: duo[0].description },
      { description: duo[1].description },
      sceneDirection,
    );
  }

  // 3) Upload the narration as the job's "recording" (user-scoped path under uploads).
  const recordingPath = `${user.id}/faceless-${Date.now()}.${ext}`;
  const { error: upErr } = await supabase.storage
    .from("uploads")
    .upload(recordingPath, audio, { upsert: true, contentType: mime });
  if (upErr) return NextResponse.json({ error: `audio upload failed: ${upErr.message}` }, { status: 500 });

  // 4) Queue the render. The worker's faceless branch takes it from here.
  const { data: job, error } = await supabase
    .from("render_jobs")
    .insert({
      user_id: user.id,
      project_id: body.projectId ?? null,
      recording_path: recordingPath,
      customization: {
        faceless: {
          voice: voiceLabel,
          topic: title,
          scene_style: SCENE_STYLES.has(body.sceneStyle) ? body.sceneStyle : "cinematic",
          scene_direction: sceneDirection,
          animate: body.animate,
          ...(duo
            ? { cast: duo.map((c) => ({ description: c.description, voice: c.voiceName ?? c.voice ?? c.voiceId })) }
            : {}),
        },
        preset: body.style,
        resolution: body.resolution,
        captions: true,
        caption_mode: "karaoke",
        broll_mode: "ai",
        broll_quality: body.resolution === "4k" ? "ultra" : "standard",
        watermark: false,
      },
      status: "queued",
    })
    .select("id")
    .single();
  if (error || !job) {
    return NextResponse.json({ error: error?.message ?? "could not enqueue" }, { status: 500 });
  }
  return NextResponse.json({ jobId: job.id, title, script });
}
