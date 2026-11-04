import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { createProject } from "../actions";
import { Button, Badge } from "@/components/ui";
import type { Project, RenderJob } from "@/lib/types";

export default async function Dashboard() {
  const supabase = await createClient();
  const { data: projects } = await supabase
    .from("projects")
    .select("*")
    .order("created_at", { ascending: false });
  const { data: jobs } = await supabase
    .from("render_jobs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(6);

  const list = (projects ?? []) as Project[];
  const recent = (jobs ?? []) as RenderJob[];

  return (
    <div className="space-y-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Your projects</h1>
          <p className="mt-1 text-sm text-white/45">Each project pairs a reference style with your footage.</p>
        </div>
        <form action={createProject}>
          <Button type="submit" className="w-full sm:w-auto">+ New project</Button>
        </form>
      </div>

      {list.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 p-8 text-center sm:p-16">
          <p className="text-white/50">No projects yet.</p>
          <form action={createProject} className="mt-4">
            <Button type="submit">Create your first project</Button>
          </form>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((p) => (
            <Link
              key={p.id}
              href={`/project/${p.id}`}
              className="group rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-4 transition hover:border-[var(--accent)]/40 sm:p-5"
            >
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">{p.name}</h3>
                <span className="text-white/20 transition group-hover:text-[var(--accent)]">→</span>
              </div>
              <p className="mt-2 text-xs text-white/40">
                {p.reference_analysis ? "Reference analyzed" : "No reference yet"}
              </p>
            </Link>
          ))}
        </div>
      )}

      {recent.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-white/60">Recent renders</h2>
          <div className="space-y-2">
            {recent.map((j) => (
              <div key={j.id} className="flex items-center justify-between rounded-xl border border-white/[0.06] px-4 py-3 text-sm">
                <span className="font-mono text-xs text-white/40">{j.id.slice(0, 8)}</span>
                <StatusBadge status={j.status} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: RenderJob["status"] }) {
  const map = {
    queued: { tone: "neutral", label: "Queued" },
    processing: { tone: "accent", label: "Processing" },
    done: { tone: "good", label: "Done" },
    error: { tone: "bad", label: "Failed" },
  } as const;
  const s = map[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}
