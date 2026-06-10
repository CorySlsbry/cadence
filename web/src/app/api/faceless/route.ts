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

const Body = z.object({
  topic: z.string().max(500).optional(),
  script: z.string().max(8000).optional(),
  voice: z.string().default("Charon"),
  lengthSec: z.number().min(20).max(180).default(60),
  style: z.enum(["cinematic", "cinematic_film", "clean_ugc"]).default("cinematic"),
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
    const wordsTarget = Math.round((body.lengthSec / 60) * 150);
    const blueprintBlock = bp
      ? `CREATOR BLUEPRINT (this channel's voice + audience):\n- Ideal viewer: ${JSON.stringify(bp.icp)}\n- Content pillars: ${JSON.stringify(bp.pillars)}\n- Voice: ${JSON.stringify(bp.voice)}`
      : "CREATOR BLUEPRINT: none on file — clear, confident, conversational narration.";
    try {
      const out = await geminiJson<{ title: string; body: string }>({
        model: "gemini-2.5-pro",
        temperature: 0.8,
        prompt: `Write a ${body.lengthSec}-second (~${wordsTarget} words) FACELESS short-form video narration about: ${topic}

${blueprintBlock}

RULES
- This is narration over AI-generated visuals — vivid, concrete, scene-paintable sentences (each beat should suggest an image).
- Open with the 7-part hook stack compressed into the first ~8 seconds: pattern interrupt → mirror the viewer → opportunity → gap → transformation → authority → transition.
- Spoken prose ONLY — no headings, no emoji, no stage directions.
- Short punchy sentences. Contractions. Second person where natural.
- End with ONE specific call-to-action sentence.

Return STRICT JSON: {"title": "scroll-stopping title (max 70 chars)", "body": "the complete narration"}`,
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

  // 2) Narration audio.
  let wav: Buffer;
  try {
    wav = await synthesizeSpeech(script, body.voice);
  } catch (e) {
    return NextResponse.json(
      { error: `voice synthesis failed: ${e instanceof Error ? e.message : "unknown"}` },
      { status: 502 },
    );
  }

  // 3) Upload the narration as the job's "recording" (user-scoped path under uploads).
  const recordingPath = `${user.id}/faceless-${Date.now()}.wav`;
  const { error: upErr } = await supabase.storage
    .from("uploads")
    .upload(recordingPath, wav, { upsert: true, contentType: "audio/wav" });
  if (upErr) return NextResponse.json({ error: `audio upload failed: ${upErr.message}` }, { status: 500 });

  // 4) Queue the render. The worker's faceless branch takes it from here.
  const { data: job, error } = await supabase
    .from("render_jobs")
    .insert({
      user_id: user.id,
      project_id: body.projectId ?? null,
      recording_path: recordingPath,
      customization: {
        faceless: { voice: body.voice, topic: title },
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
