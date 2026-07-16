import { createClient } from "@/lib/supabase/server";
import { LibraryGrid, type LibraryItem, type SocialConn } from "./library-grid";

// Every finished render lives here — in the app, not just a one-time download.
export const dynamic = "force-dynamic";

type JobRow = {
  id: string;
  output_path: string | null;
  created_at: string;
  customization: Record<string, unknown> | null;
  result: { width?: number; height?: number; duration?: number } | null;
  clips: { output_path: string; title?: string }[] | null;
};

function labelFor(job: JobRow): string {
  const faceless = (job.customization?.faceless ?? null) as { title?: string } | null;
  if (faceless?.title) return faceless.title;
  if (job.clips?.length) return `Auto-clips × ${job.clips.length}`;
  return "Studio render";
}

export default async function LibraryPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null; // (app) layout redirects unauthenticated visitors

  const { data: jobs } = await supabase
    .from("render_jobs")
    .select("id,output_path,created_at,customization,result,clips")
    .eq("user_id", user.id)
    .eq("status", "done")
    .not("output_path", "is", null)
    .order("created_at", { ascending: false })
    .limit(60);

  // Connected accounts (id + label + platform) power the per-video multi-account publisher.
  const { data: socialRows } = await supabase.rpc("my_social_connections");
  const connections: SocialConn[] = ((socialRows ?? []) as SocialConn[]).map((r) => ({
    id: r.id,
    platform: r.platform,
    username: r.username,
    label: r.label,
  }));

  const items: LibraryItem[] = [];
  for (const job of (jobs ?? []) as JobRow[]) {
    if (!job.output_path) continue;
    const { data: signed } = await supabase.storage
      .from("outputs")
      .createSignedUrl(job.output_path, 60 * 60 * 6);
    if (!signed?.signedUrl) continue;
    items.push({
      id: job.id,
      url: signed.signedUrl,
      title: labelFor(job),
      createdAt: job.created_at,
      width: job.result?.width ?? null,
      height: job.result?.height ?? null,
      duration: job.result?.duration ?? null,
      clipCount: job.clips?.length ?? 0,
    });
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <p className="text-sm font-semibold text-[var(--accent)]">Library</p>
      <h1 className="mt-1 text-3xl font-extrabold tracking-tight">Every video you&apos;ve shipped.</h1>
      <p className="mt-2 max-w-xl text-sm text-white/50">
        Finished renders live here — stream them, download them, or clear them out. Clips and
        social captions stay on each project&apos;s page.
      </p>
      <LibraryGrid items={items} connections={connections} />
    </div>
  );
}
