import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { geminiJson } from "@/lib/gemini";

// Avatar from photos: the user uploads 1-3 photos of THEMSELVES and Gemini vision
// writes a reusable character sheet — a compact image-prompt fragment that keeps
// their look consistent across faceless scenes in any visual style.

const CreateBody = z.object({
  name: z.string().max(60).default("My avatar"),
  photos: z
    .array(z.object({
      mime: z.enum(["image/jpeg", "image/png", "image/webp"]),
      data: z.string().min(100).max(8_000_000), // base64, ~6MB decoded max
    }))
    .min(1)
    .max(3),
});

const SHEET_PROMPT = `These photos show the same person — the user of a video app
building an animated character of THEMSELVES for their own videos.

Write a reusable CHARACTER SHEET for image generation:
- One paragraph, 55-85 words, third person ("a man with…" / "a woman with…").
- Capture: apparent age range, build, skin tone, face shape, hair (color, length,
  texture, style), facial hair, eyebrows, eyes, glasses/piercings if present,
  signature clothing style visible in the photos, and 1-2 distinguishing features.
- Concrete visual vocabulary only — no names, no personality traits, no story,
  nothing that couldn't be drawn.
- It must read naturally when pasted into prompts like
  "claymation scene starring {sheet}" or "anime scene starring {sheet}".

Return JSON: {"sheet": "<the paragraph>"}`;

export async function POST(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: z.infer<typeof CreateBody>;
  try {
    body = CreateBody.parse(await req.json());
  } catch {
    return NextResponse.json({ error: "1-3 photos required (jpeg/png/webp)" }, { status: 422 });
  }

  let sheet: string;
  try {
    const out = await geminiJson<{ sheet?: string }>({
      prompt: SHEET_PROMPT,
      inlineImages: body.photos.map((p) => ({ mime: p.mime, data: p.data })),
      temperature: 0.4,
    });
    sheet = (out.sheet ?? "").trim();
  } catch (err) {
    return NextResponse.json(
      { error: `could not read the photos: ${err instanceof Error ? err.message : "unknown"}` },
      { status: 502 },
    );
  }
  if (sheet.length < 40) {
    return NextResponse.json({ error: "could not build a character sheet from these photos" }, { status: 422 });
  }

  // Keep the first photo so the avatar card can show it (user-scoped path under uploads).
  let photoPath: string | null = null;
  const first = body.photos[0];
  const ext = first.mime === "image/png" ? "png" : first.mime === "image/webp" ? "webp" : "jpg";
  photoPath = `${user.id}/avatar-${Date.now()}.${ext}`;
  const { error: upErr } = await supabase.storage
    .from("uploads")
    .upload(photoPath, Buffer.from(first.data, "base64"), { upsert: true, contentType: first.mime });
  if (upErr) photoPath = null; // the sheet is the product; the thumbnail is a nicety

  const { data: row, error } = await supabase
    .from("characters")
    .insert({ user_id: user.id, name: body.name.trim() || "My avatar", sheet, photo_path: photoPath })
    .select("id, name, sheet, photo_path, created_at")
    .single();
  if (error || !row) {
    return NextResponse.json({ error: error?.message ?? "could not save" }, { status: 500 });
  }
  return NextResponse.json({ character: row });
}

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { data, error } = await supabase
    .from("characters")
    .select("id, name, sheet, photo_path, created_at")
    .order("created_at", { ascending: false })
    .limit(12);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ characters: data ?? [] });
}

export async function DELETE(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const id = new URL(req.url).searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id required" }, { status: 422 });
  const { error } = await supabase.from("characters").delete().eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
