import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { geminiJson } from "@/lib/gemini";

// The Ikigai brand blueprint: 4 answers in → AI-generated ICP, content pillars and
// voice out. This is the personalization backbone — scripts, hooks and captions are
// written "authentic, not original" by merging proven formats with THIS identity.

type Generated = {
  icp: { who: string; pains: string[]; goals: string[]; watches: string };
  pillars: { name: string; why: string }[];
  voice: { tone: string; pov: string; phrases: string[] };
};

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { data } = await supabase.from("brand_blueprints").select("*").eq("user_id", user.id).maybeSingle();
  return NextResponse.json({ blueprint: data ?? null });
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { love?: string; great_at?: string; world_needs?: string; paid_for?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }
  const love = (body.love ?? "").trim().slice(0, 2000);
  const greatAt = (body.great_at ?? "").trim().slice(0, 2000);
  const worldNeeds = (body.world_needs ?? "").trim().slice(0, 2000);
  const paidFor = (body.paid_for ?? "").trim().slice(0, 2000);
  if (!love || !greatAt || !worldNeeds || !paidFor) {
    return NextResponse.json({ error: "answer all four questions" }, { status: 422 });
  }

  let generated: Generated;
  try {
    generated = await geminiJson<Generated>({
      model: "gemini-2.5-pro",
      temperature: 0.6,
      prompt: `You are a personal-brand strategist. From this creator's Ikigai answers, derive their content identity.

IKIGAI ANSWERS
1. What they love doing: ${love}
2. What they're great at: ${greatAt}
3. What the world needs right now: ${worldNeeds}
4. What they can get paid for: ${paidFor}

Return STRICT JSON:
{
  "icp": {
    "who": "one tight sentence describing the ideal viewer/customer",
    "pains": ["3-5 concrete pains in their words"],
    "goals": ["3-5 outcomes they want"],
    "watches": "what content they already watch and why"
  },
  "pillars": [{ "name": "pillar", "why": "why this creator wins this pillar" }],   // exactly 3-5 pillars
  "voice": {
    "tone": "3-6 word tone description",
    "pov": "the creator's distinct point of view in one sentence",
    "phrases": ["4-6 short signature phrasings that sound like them"]
  }
}`,
    });
  } catch (e) {
    return NextResponse.json({ error: `generation failed: ${e instanceof Error ? e.message : "unknown"}` }, { status: 502 });
  }

  const row = {
    user_id: user.id,
    love, great_at: greatAt, world_needs: worldNeeds, paid_for: paidFor,
    icp: generated.icp, pillars: generated.pillars, voice: generated.voice,
    updated_at: new Date().toISOString(),
  };
  const { data, error } = await supabase.from("brand_blueprints").upsert(row).select().single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ blueprint: data });
}
