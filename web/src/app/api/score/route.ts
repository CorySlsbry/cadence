import { NextResponse } from "next/server";
import { createHash } from "crypto";
import { createAdminClient } from "@/lib/supabase/admin";
import { clientIp } from "@/lib/ip";
import { scoreVideo, toTeaser, resolveVideoMeta, type ScoreInput } from "@/lib/score";

export const runtime = "nodejs";
export const maxDuration = 60;

// PUBLIC, no auth. The free Viral Score lead magnet (also the homepage demo + the engine the public
// MCP `score_video` tool calls). Rate-limited per IP; URL metadata resolved SSRF-safely (oEmbed only).
export async function POST(req: Request) {
  const admin = createAdminClient();

  // Reject oversized bodies up front (public endpoint, before buffering).
  const declared = Number(req.headers.get("content-length") || 0);
  if (declared && declared > 64 * 1024) {
    return NextResponse.json({ error: "Request too large." }, { status: 413 });
  }

  // Fail CLOSED: anything other than an explicit true (RPC error, missing fn) is treated as limited —
  // this is a paid Gemini call per request, so the limiter must never silently disable itself.
  const ip = clientIp(req);
  const { data: rlOk, error: rlErr } = await admin.rpc("rl_bump", { p_key: `score:${ip}`, p_limit: 15, p_window_sec: 60 });
  if (rlErr || rlOk !== true) {
    if (rlErr) console.error("[score] rl_bump error:", rlErr.message);
    return NextResponse.json({ error: "Too many scores in a row — give it a minute." }, { status: 429 });
  }

  let body: {
    url?: string;
    platform?: string;
    title?: string;
    topic?: string;
    hook?: string;
    transcript?: string;
    utm?: Record<string, string>;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }

  const clamp = (v: unknown, max: number) => (typeof v === "string" && v ? v.slice(0, max) : undefined);
  const url = (body.url || "").trim().slice(0, 2000);
  const meta = url ? await resolveVideoMeta(url) : {};
  const input: ScoreInput = {
    platform: clamp(body.platform || meta.platform, 60),
    title: clamp(meta.title || body.title, 500),
    topic: clamp(body.topic, 4000),
    hook: clamp(body.hook, 500),
    transcript: clamp(body.transcript, 6000),
    thumbnailUrl: meta.thumbnailUrl,
  };

  if (!url && !input.title && !input.topic && !input.hook && !input.transcript) {
    return NextResponse.json(
      { error: "Paste a video link, or describe the video (its topic + hook) so we can score it." },
      { status: 422 },
    );
  }

  let result;
  try {
    result = await scoreVideo(input);
  } catch (e) {
    return NextResponse.json(
      { error: `scoring failed: ${e instanceof Error ? e.message : "unknown"}` },
      { status: 502 },
    );
  }

  const ipHash = createHash("sha256").update(ip).digest("hex").slice(0, 32);
  const { data: row } = await admin
    .from("score_results")
    .insert({
      platform: input.platform ?? null,
      input: {
        url: url || null,
        title: input.title ?? null,
        topic: input.topic ?? null,
        hook: input.hook ?? null,
        has_transcript: !!input.transcript,
      },
      result, // full result (with fixes) stored server-side; only the teaser is returned pre-email
      score: result.score,
      ip_hash: ipHash,
      utm: body.utm ?? null,
    })
    .select("id")
    .single();

  return NextResponse.json({ id: row?.id ?? null, ...toTeaser(result) });
}
