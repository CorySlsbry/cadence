import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

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

  // Server-side quota enforcement — never trust the client.
  const { data: profile } = await supabase
    .from("profiles")
    .select("monthly_render_limit")
    .eq("id", user.id)
    .single();
  const { data: used } = await supabase.rpc("renders_used_this_month", { uid: user.id });
  const limit = profile?.monthly_render_limit ?? 10;
  if (((used as number) ?? 0) >= limit) {
    return NextResponse.json(
      { error: `Monthly render limit reached (${limit}). Upgrade to render more.` },
      { status: 429 },
    );
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
