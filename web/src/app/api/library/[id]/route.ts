import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";

/** Permanently delete one finished render: storage objects (main + clips) + the job row. */
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  // Ownership check through RLS (the user client only sees their own rows).
  const { data: job } = await supabase
    .from("render_jobs")
    .select("id,output_path,clips")
    .eq("id", id)
    .single();
  if (!job) return NextResponse.json({ error: "not found" }, { status: 404 });

  const paths = [
    ...(job.output_path ? [job.output_path as string] : []),
    ...(((job.clips as { output_path?: string }[] | null) ?? [])
      .map((c) => c.output_path)
      .filter((p): p is string => typeof p === "string" && p.length > 0)),
  ];

  const admin = createAdminClient();
  if (paths.length) {
    await admin.storage.from("outputs").remove(paths); // best-effort; row delete is the source of truth
  }
  const { error } = await supabase.from("render_jobs").delete().eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
