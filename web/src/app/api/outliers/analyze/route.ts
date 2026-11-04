import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { geminiJson } from "@/lib/gemini";

// "Why did this video pop?" — multimodal deconstruction of an outlier's title +
// thumbnail (image passed inline) + metadata. The Sandy Lee three: title pattern,
// thumbnail layout, hook hypothesis — plus remix angles to feed script generation.

type Analysis = {
  title_pattern: string;
  thumbnail_notes: string;
  hook_hypothesis: string;
  why_it_works: string;
  remix_angles: string[];
};

export async function POST(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }
  if (!body.id) return NextResponse.json({ error: "id required" }, { status: 422 });

  const { data: video } = await supabase
    .from("outlier_videos").select("*")
    .eq("user_id", user.id).eq("id", body.id).maybeSingle();
  if (!video) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (video.analysis) return NextResponse.json({ analysis: video.analysis }); // cached

  let analysis: Analysis;
  try {
    analysis = await geminiJson<Analysis>({
      model: "gemini-2.5-flash",
      temperature: 0.5,
      imageUrl: video.thumbnail_url ?? undefined,
      prompt: `You are a short-form/YouTube growth analyst. This video is an OUTLIER — it scored ${Math.round(video.outlier_score ?? 0)} (100 = the channel's typical video; this did ${((video.outlier_score ?? 0) / 100).toFixed(1)}× normal).

VIDEO
- Title: ${video.title}
- Channel: ${video.channel_title}
- Views: ${video.views} (channel median ${Math.round(video.channel_median_views ?? 0)})
- Published: ${video.published_at}
${video.thumbnail_url ? "- Thumbnail: attached image" : ""}

Deconstruct WHY it outperformed. Return STRICT JSON:
{
  "title_pattern": "the reusable title formula at work (name the curiosity trigger / promise)",
  "thumbnail_notes": "layout + visual choices doing the work (from the attached image if present)",
  "hook_hypothesis": "the likely first-30-seconds hook technique (pattern interrupt, bold claim, pain mirror...)",
  "why_it_works": "2-3 sentences tying it together — the psychological job this video does",
  "remix_angles": ["3 specific angles another creator could take on this exact format"]
}`,
    });
  } catch (e) {
    return NextResponse.json({ error: `analysis failed: ${e instanceof Error ? e.message : "unknown"}` }, { status: 502 });
  }

  await supabase.from("outlier_videos").update({ analysis }).eq("id", video.id).eq("user_id", user.id);
  return NextResponse.json({ analysis });
}
