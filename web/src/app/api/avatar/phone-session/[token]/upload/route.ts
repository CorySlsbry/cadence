import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";
export const maxDuration = 120;

const MAX_BYTES = 80 * 1024 * 1024; // a reference clip is ~30-60s; 80MB is generous

// Trust the BYTES, not the client's Content-Type: sniff the container header.
function sniffVideoExt(buf: Buffer): "mp4" | "webm" | null {
  if (buf.length >= 4 && buf[0] === 0x1a && buf[1] === 0x45 && buf[2] === 0xdf && buf[3] === 0xa3) {
    return "webm"; // EBML / Matroska
  }
  if (buf.length >= 12 && buf.toString("ascii", 4, 8) === "ftyp") {
    return "mp4"; // ISO base media (MP4/MOV)
  }
  return null;
}

// PUBLIC (the phone is not logged in). Authorization is the capability token only: it must
// exist, be 'pending', and be unexpired. The file is written via the service role to
// uploads/{session.user_id}/... — a token can ONLY populate its own session for its own user.
// CLAIM-FIRST: the single-use lock (pending->uploading) happens BEFORE the body is read, so
// concurrent hits on one token can't each buffer a large payload.
export async function POST(req: Request, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  if (!token || !/^[0-9a-f]{64}$/.test(token)) {
    return NextResponse.json({ error: "bad link" }, { status: 400 });
  }
  const admin = createAdminClient();

  // Per-IP rate limit (defense vs a token holder flooding the public endpoint).
  const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "unknown";
  const { data: rlOk } = await admin.rpc("rl_bump", { p_key: `phup:${ip}`, p_limit: 30, p_window_sec: 60 });
  if (rlOk === false) {
    return NextResponse.json({ error: "too many uploads — slow down" }, { status: 429 });
  }

  const { data: s } = await admin
    .from("phone_link_sessions")
    .select("id, user_id, status, expires_at")
    .eq("token", token)
    .maybeSingle();
  if (!s) return NextResponse.json({ error: "invalid or expired link" }, { status: 404 });
  if (s.status !== "pending") {
    return NextResponse.json({ error: "this link was already used" }, { status: 409 });
  }
  if (new Date(s.expires_at).getTime() < Date.now()) {
    await admin.from("phone_link_sessions").update({ status: "expired" }).eq("id", s.id);
    return NextResponse.json({ error: "this link expired — generate a new QR" }, { status: 410 });
  }

  // Reject oversized uploads up front (before buffering).
  const declared = Number(req.headers.get("content-length") || 0);
  if (declared && declared > MAX_BYTES + 1024 * 1024) {
    return NextResponse.json({ error: "video too large (80MB max)" }, { status: 413 });
  }

  // Single-use lock BEFORE reading the body. Only the first claimer proceeds.
  const { data: claim } = await admin
    .from("phone_link_sessions")
    .update({ status: "uploading" })
    .eq("id", s.id)
    .eq("status", "pending")
    .select("id")
    .maybeSingle();
  if (!claim) return NextResponse.json({ error: "this link was already used" }, { status: 409 });

  const revert = () =>
    admin.from("phone_link_sessions").update({ status: "pending" }).eq("id", s.id).eq("status", "uploading");

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    await revert();
    return NextResponse.json({ error: "bad upload" }, { status: 400 });
  }
  const file = form.get("video");
  if (!(file instanceof File) || file.size <= 0 || file.size > MAX_BYTES) {
    await revert();
    return NextResponse.json({ error: "video missing or too large (80MB max)" }, { status: 413 });
  }
  const buf = Buffer.from(await file.arrayBuffer());
  const ext = sniffVideoExt(buf);
  if (!ext) {
    await revert();
    return NextResponse.json({ error: "must be an mp4 or webm video" }, { status: 415 });
  }
  const contentType = ext === "mp4" ? "video/mp4" : "video/webm";
  const path = `${s.user_id}/avatar-phone-${Date.now()}.${ext}`;
  const { error: upErr } = await admin.storage
    .from("uploads")
    .upload(path, buf, { contentType, upsert: false });
  if (upErr) {
    await revert();
    return NextResponse.json({ error: "upload failed" }, { status: 500 });
  }

  // Finalize: uploading -> uploaded with the path (the desktop poll waits for both).
  const { data: done } = await admin
    .from("phone_link_sessions")
    .update({ status: "uploaded", recording_path: path, uploaded_at: new Date().toISOString() })
    .eq("id", s.id)
    .eq("status", "uploading")
    .select("id")
    .maybeSingle();
  if (!done) {
    await admin.storage.from("uploads").remove([path]);
    return NextResponse.json({ error: "this link was already used" }, { status: 409 });
  }
  return NextResponse.json({ ok: true });
}
