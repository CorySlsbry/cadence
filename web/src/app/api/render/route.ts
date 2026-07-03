import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { checkRenderAllowance } from "@/lib/limits";

const Body = z.object({
  projectId: z.string().uuid().nullable().optional(),
  recordingPath: z.string().min(1),
  referencePath: z.string().nullable().optional(),
  aggressiveFillers: z.boolean().optional().default(false),
  customization: z.record(z.string(), z.unknown()).nullable().optional(),
});

export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: z.infer<typeof Body>;
  try {
    body = Body.parse(await request.json());
  } catch {
    return NextResponse.json({ error: "invalid request body" }, { status: 422 });
  }

  // Tenant isolation (IDOR guard): the worker downloads these keys with the service role,
  // which BYPASSES storage RLS — so the paths MUST live in the caller's own folder. Without
  // this, an attacker could point recordingPath at another user's private upload.
  const ownsPath = (p: string | null | undefined) => !p || p.startsWith(`${user.id}/`);
  if (!ownsPath(body.recordingPath) || !ownsPath(body.referencePath)) {
    return NextResponse.json({ error: "storage path is outside your workspace" }, { status: 422 });
  }

  // Per-user token meter (1 token = 1 AI scene) — the real multi-tenant gate. Never
  // trust the client; the worker also burns tokens atomically per image. BYOK users
  // keep their tokens (the worker skips metering for them), so they pass this freely.
  const { data: profile } = await supabase
    .from("profiles")
    .select("tokens")
    .eq("id", user.id)
    .single();
  if (((profile?.tokens as number) ?? 0) <= 0) {
    return NextResponse.json(
      { error: "You're out of tokens. Top up or upgrade on the Pricing page (tap your token badge)." },
      { status: 402 },
    );
  }

  // Pipeline-pressure guardrails (active-job cap + per-plan daily allowance).
  const allowance = await checkRenderAllowance(user.id);
  if (!allowance.ok) {
    return NextResponse.json({ error: allowance.error }, { status: allowance.status });
  }

  // Insert via the user's client so RLS guarantees user_id = auth.uid().
  const { data, error } = await supabase
    .from("render_jobs")
    .insert({
      user_id: user.id,
      project_id: body.projectId ?? null,
      recording_path: body.recordingPath,
      reference_path: body.referencePath ?? null,
      aggressive_fillers: body.aggressiveFillers,
      customization: body.customization ?? null,
      status: "queued",
    })
    .select("id")
    .single();

  if (error || !data) {
    return NextResponse.json({ error: error?.message ?? "could not enqueue render" }, { status: 500 });
  }
  return NextResponse.json({ jobId: data.id });
}
