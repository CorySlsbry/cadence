import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { geminiJson } from "@/lib/gemini";
import { cloneVoice, resolveElevenLabsKey } from "@/lib/elevenlabs";
import { createAdminClient } from "@/lib/supabase/admin";

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

  // Photoreal avatar = multipart (reference clip/frame + on-camera consent + optional voice
  // sample). The JSON path below stays the stylized "character sheet" (kind='sheet').
  if ((req.headers.get("content-type") || "").includes("multipart/form-data")) {
    return createPhotorealAvatar(req, supabase, user.id);
  }

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

// Photoreal avatar: store the reference + on-camera consent, clone the voice (BYOK),
// and write the character (kind='photoreal') + an append-only consent record. Consent is
// captured AT CREATION; the render route is fail-closed on it.
type SB = Awaited<ReturnType<typeof createClient>>;
async function createPhotorealAvatar(req: Request, supabase: SB, userId: string) {
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return NextResponse.json({ error: "expected multipart form data" }, { status: 422 });
  }
  const name = String(form.get("name") ?? "").trim() || "My avatar";
  const sourceKindRaw = String(form.get("source_kind") ?? "video");
  const source = form.get("source");
  const sourcePathInput = String(form.get("source_path") ?? "").trim(); // phone clip already in storage
  const consentVideo = form.get("consent_video");
  const voiceSample = form.get("voice_sample");
  const tosVersion = String(form.get("tos_version") ?? "").trim();
  let checkboxSet: Record<string, boolean> = {};
  try {
    checkboxSet = JSON.parse(String(form.get("checkbox_set") ?? "{}"));
  } catch {
    checkboxSet = {};
  }
  const framing = String(form.get("framing_default") ?? "lower_third");

  // Consent is required regardless of where the reference came from.
  if (!(consentVideo instanceof File) || consentVideo.size === 0) {
    return NextResponse.json({ error: "an on-camera consent clip is required" }, { status: 403 });
  }
  const affirmed =
    Object.keys(checkboxSet).length > 0 && Object.values(checkboxSet).every(Boolean) && !!tosVersion;
  if (!affirmed) {
    return NextResponse.json({ error: "you must affirm the consent checkboxes" }, { status: 403 });
  }

  const ts = Date.now();
  const consentPath = `${userId}/avatar-consent-${ts}.webm`;
  const put = async (path: string, file: File, mime: string) =>
    supabase.storage.from("uploads").upload(path, Buffer.from(await file.arrayBuffer()), {
      upsert: true,
      contentType: file.type || mime,
    });

  // Reference: either a phone-recorded clip already in the user's storage (source_path) or a
  // freshly uploaded File. A source_path MUST live inside the caller's OWN folder — this is the
  // control that stops one account referencing another's upload (no cross-user, no traversal).
  let sourceKind: "photo" | "video";
  let srcPath: string;
  if (sourcePathInput) {
    if (!sourcePathInput.startsWith(`${userId}/`) || sourcePathInput.includes("..")) {
      return NextResponse.json({ error: "invalid reference path" }, { status: 403 });
    }
    // Bind the clip to a real phone session of THIS user that hasn't been consumed, and consume
    // it once — so a phone clip is single-use at consumption (not just at upload) and can't be
    // replayed after its TTL. (The startsWith check already blocks cross-account paths.)
    const admin = createAdminClient();
    const { data: sess } = await admin
      .from("phone_link_sessions")
      .select("id, status")
      .eq("user_id", userId)
      .eq("recording_path", sourcePathInput)
      .maybeSingle();
    if (!sess || sess.status !== "uploaded") {
      return NextResponse.json({ error: "phone clip is invalid or already used — re-scan the QR" }, { status: 403 });
    }
    const { data: consumed } = await admin
      .from("phone_link_sessions")
      .update({ status: "consumed", consumed_at: new Date().toISOString() })
      .eq("id", sess.id)
      .eq("status", "uploaded")
      .select("id")
      .maybeSingle();
    if (!consumed) {
      return NextResponse.json({ error: "phone clip already used — re-scan the QR" }, { status: 409 });
    }
    sourceKind = "video";
    srcPath = sourcePathInput;
  } else {
    sourceKind = sourceKindRaw === "photo" ? "photo" : "video";
    if (!(source instanceof File) || source.size === 0) {
      return NextResponse.json({ error: "a reference recording or photo is required" }, { status: 422 });
    }
    if (source.size > 200 * 1024 * 1024) {
      return NextResponse.json({ error: "reference too large (200MB max)" }, { status: 413 });
    }
    srcPath = `${userId}/avatar-src-${ts}.${sourceKind === "photo" ? "png" : "webm"}`;
    if ((await put(srcPath, source, sourceKind === "photo" ? "image/png" : "video/webm")).error) {
      return NextResponse.json({ error: "reference upload failed" }, { status: 500 });
    }
  }
  if ((await put(consentPath, consentVideo, "video/webm")).error) {
    return NextResponse.json({ error: "consent upload failed" }, { status: 500 });
  }

  // Voice clone (ElevenLabs BYOK). Prefer the PHONE clip's audio when the reference came from a
  // phone (far better mic than a laptop webcam) — but only if it's small enough to handle safely
  // in this 512Mi web instance + ElevenLabs' sample limit; else fall back to the consent clip.
  let voiceId: string | null = null;
  const elKey = await resolveElevenLabsKey(userId);
  if (elKey) {
    let voiceFile: File | null =
      voiceSample instanceof File && voiceSample.size > 0 ? voiceSample : null;
    if (sourcePathInput) {
      try {
        const admin = createAdminClient();
        const slash = srcPath.lastIndexOf("/");
        const dir = srcPath.slice(0, slash);
        const base = srcPath.slice(slash + 1);
        const { data: items } = await admin.storage.from("uploads").list(dir, { search: base });
        const size = items?.find((i) => i.name === base)?.metadata?.size ?? 0;
        if (size > 0 && size <= 20 * 1024 * 1024) {
          const { data: blob } = await admin.storage.from("uploads").download(srcPath);
          if (blob && blob.size > 0) {
            voiceFile = new File([blob], "phone-voice", { type: blob.type || "video/mp4" });
          }
        }
      } catch {
        /* fall back to the consent clip */
      }
    }
    if (voiceFile) {
      try {
        voiceId = await cloneVoice(elKey, name, [voiceFile]);
      } catch {
        voiceId = null; // non-fatal: they can clone later in Connections
      }
    }
  }

  const { data: row, error } = await supabase
    .from("characters")
    .insert({
      user_id: userId,
      name,
      sheet: "",
      photo_path: sourceKind === "photo" ? srcPath : null,
      kind: "photoreal",
      source_kind: sourceKind,
      source_path: srcPath,
      voice_id: voiceId,
      provider: "selfhost",
      framing_default: framing,
      coherence_mode: "photoreal",
    })
    .select("id, name, kind, source_kind, voice_id, framing_default, photo_path, created_at")
    .single();
  if (error || !row) {
    return NextResponse.json({ error: error?.message ?? "could not save the avatar" }, { status: 500 });
  }

  const { error: cErr } = await supabase.from("consent_records").insert({
    user_id: userId,
    character_id: row.id,
    consent_video_path: consentPath,
    consent_script_version: String(form.get("consent_script_version") ?? "v1"),
    checkbox_set: checkboxSet,
    tos_version: tosVersion,
  });
  if (cErr) {
    // Consent is load-bearing — never leave a photoreal row without it.
    await supabase.from("characters").delete().eq("id", row.id);
    return NextResponse.json({ error: "could not record consent" }, { status: 500 });
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

  // Load for cleanup (RLS scopes to the owner).
  const { data: ch } = await supabase
    .from("characters").select("voice_id, source_path").eq("id", id).eq("user_id", user.id).maybeSingle();

  // Revoke consent (append-only ledger: stamp revoked_at, keep the proof) BEFORE deleting.
  await supabase.from("consent_records")
    .update({ revoked_at: new Date().toISOString() })
    .eq("character_id", id).is("revoked_at", null);

  // Delete the cloned voice on the user's ElevenLabs plan.
  if (ch?.voice_id) {
    const key = await resolveElevenLabsKey(user.id);
    if (key) {
      try {
        await fetch(`https://api.elevenlabs.io/v1/voices/${ch.voice_id}`, {
          method: "DELETE", headers: { "xi-api-key": key },
        });
      } catch { /* best-effort */ }
    }
  }

  // Purge biometric assets from storage (GDPR/BIPA require deletion, not just the row).
  const paths: string[] = [];
  if (ch?.source_path) paths.push(ch.source_path as string);
  const { data: crows } = await supabase
    .from("consent_records").select("consent_video_path").eq("character_id", id);
  for (const c of crows ?? []) if (c.consent_video_path) paths.push(c.consent_video_path as string);
  if (paths.length) {
    try { await supabase.storage.from("uploads").remove(paths); } catch { /* best-effort */ }
  }

  const { error } = await supabase.from("characters").delete().eq("id", id).eq("user_id", user.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
