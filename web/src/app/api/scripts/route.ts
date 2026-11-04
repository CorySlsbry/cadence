import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { geminiJson } from "@/lib/gemini";

// Personalized script generation — the bridge from "found a proven format" to
// "reading it on the teleprompter". Merges the outlier's format with the creator's
// Ikigai blueprint ("authentic, not original") using the 7-part hook formula:
// pattern interrupt → mirror the viewer → opportunity → gap → transformation →
// authority → transition. Output is teleprompter-ready spoken prose.

type GeneratedScript = {
  title: string;
  hook: string;
  body: string;
  broll_keywords: string[];
};

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { data } = await supabase
    .from("scripts").select("*")
    .eq("user_id", user.id).order("created_at", { ascending: false }).limit(20);
  return NextResponse.json({ scripts: data ?? [] });
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { outlierId?: string; topic?: string; lengthSec?: number };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }
  const lengthSec = Math.min(Math.max(body.lengthSec ?? 45, 20), 180);

  // Load the outlier (optional) + the blueprint (optional but strongly shaping).
  let outlier: { title: string; channel_title: string; outlier_score: number | null; analysis: Record<string, unknown> | null; id: string; video_id: string } | null = null;
  if (body.outlierId) {
    const { data } = await supabase
      .from("outlier_videos").select("id,video_id,title,channel_title,outlier_score,analysis")
      .eq("user_id", user.id).eq("id", body.outlierId).maybeSingle();
    outlier = data ?? null;
    if (!outlier) return NextResponse.json({ error: "outlier not found" }, { status: 404 });
  }
  const topic = (body.topic ?? "").trim().slice(0, 500);
  if (!outlier && !topic) return NextResponse.json({ error: "topic or outlierId required" }, { status: 422 });

  const { data: bp } = await supabase
    .from("brand_blueprints").select("icp,pillars,voice")
    .eq("user_id", user.id).maybeSingle();

  const wordsTarget = Math.round((lengthSec / 60) * 150); // ~150 wpm spoken
  const blueprintBlock = bp
    ? `CREATOR BLUEPRINT (write as THIS person, for THIS audience):
- Ideal viewer: ${JSON.stringify(bp.icp)}
- Content pillars: ${JSON.stringify(bp.pillars)}
- Voice: ${JSON.stringify(bp.voice)}`
    : "CREATOR BLUEPRINT: none on file — write in a clear, direct, conversational first-person voice.";

  const sourceBlock = outlier
    ? `PROVEN FORMAT TO REMIX (do NOT copy content — borrow the FORMAT/energy):
- Outlier title: ${outlier.title} (by ${outlier.channel_title}, scored ${Math.round(outlier.outlier_score ?? 0)} where 100 = channel normal)
- What made it work: ${JSON.stringify(outlier.analysis ?? "not analyzed — infer from the title")}`
    : `TOPIC: ${topic}`;

  let script: GeneratedScript;
  try {
    script = await geminiJson<GeneratedScript>({
      model: "gemini-2.5-pro",
      temperature: 0.8,
      prompt: `You are an elite short-form video scriptwriter. Write a ${lengthSec}-second (~${wordsTarget} words) 9:16 talking-head script.

${blueprintBlock}

${sourceBlock}

RULES
- Open with the 7-part hook stack compressed into the first ~8 seconds: pattern interrupt → mirror the viewer's pain → the opportunity → the gap (stakes, no fake urgency) → transformation promise → one authority anchor → transition into content.
- Spoken prose ONLY: no headings, no camera directions, no emoji, no "[pause]" markers — exactly what the creator reads off a teleprompter.
- Short punchy sentences. Contractions. First person. The creator's voice from the blueprint.
- End with ONE specific call-to-action sentence.
- The result must be authentic to the creator — a personalized take, never a copy of the source.

Return STRICT JSON:
{
  "title": "scroll-stopping video title (max 70 chars)",
  "hook": "the first 1-2 spoken sentences (the cold open)",
  "body": "the COMPLETE script including the hook, as one teleprompter-ready text",
  "broll_keywords": ["4-6 concrete b-roll search terms matching the script's moments"]
}`,
    });
  } catch (e) {
    return NextResponse.json({ error: `generation failed: ${e instanceof Error ? e.message : "unknown"}` }, { status: 502 });
  }

  const { data: saved, error } = await supabase
    .from("scripts")
    .insert({
      user_id: user.id,
      source_video_id: outlier?.video_id ?? null,
      topic: outlier ? outlier.title : topic,
      title: (script.title ?? "").slice(0, 200),
      hook: (script.hook ?? "").slice(0, 1000),
      body: script.body ?? "",
      broll_keywords: script.broll_keywords ?? [],
    })
    .select()
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ script: saved });
}
