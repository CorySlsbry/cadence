import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createAdminClient } from "@/lib/supabase/admin";
import type { ScoreResult } from "@/lib/score";

const SITE = "https://clouthook.com";

async function getResult(id: string): Promise<ScoreResult | null> {
  if (!/^[0-9a-f-]{36}$/i.test(id)) return null;
  try {
    const admin = createAdminClient();
    const { data } = await admin.from("score_results").select("result").eq("id", id).maybeSingle();
    return (data?.result as ScoreResult | undefined) ?? null;
  } catch {
    return null; // infra/env failure degrades to notFound(), not a 500
  }
}

function barColor(s: number): string {
  if (s >= 7) return "var(--accent)";
  if (s >= 5) return "#d4a72c";
  return "#e0606b";
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const r = await getResult(id);
  const title = r
    ? `This video scored ${r.score}/10 (${r.grade}) — CloutHook Viral Score`
    : "Viral Score — CloutHook";
  return {
    title,
    description: r?.summary || "Score your short-form video free with CloutHook's AI Viral Score.",
    alternates: { canonical: `${SITE}/score/${id}` },
  };
}

export default async function ScoreResultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await getResult(id);
  if (!r) notFound();

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-14">
      <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
        ← CloutHook
      </Link>
      <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-6 text-center">
        <p className="text-sm text-white/60">Viral Score</p>
        <div className="mt-1 text-6xl font-bold text-white">
          {r.score}
          <span className="text-2xl text-white/50">/10</span>
        </div>
        <div className="mt-1 text-sm font-semibold text-[var(--accent)]">{r.grade}</div>
        {r.summary && <p className="mx-auto mt-3 max-w-xl text-[15px] leading-7 text-white/70">{r.summary}</p>}
      </div>

      <div className="mt-4 space-y-3">
        {r.dimensions.map((d) => (
          <div key={d.key} className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-white">{d.label}</span>
              <span className="text-sm font-semibold text-white/80">{d.score}/10</span>
            </div>
            <div
              className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/10"
              role="img"
              aria-label={`${d.label}: ${d.score} out of 10`}
            >
              <div className="h-full rounded-full" style={{ width: `${d.score * 10}%`, background: barColor(d.score) }} />
            </div>
            <p className="mt-2 text-sm text-white/70">{d.verdict}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-2xl border border-[var(--accent)]/30 bg-[var(--accent)]/10 p-6 text-center">
        <h2 className="text-lg font-semibold text-white">Score your own video — free</h2>
        <p className="mt-1 text-sm text-white/70">Get your hook, pacing, captions, and format graded in ~15 seconds.</p>
        <Link
          href="/score"
          className="mt-4 inline-flex min-h-12 items-center rounded-xl bg-[var(--accent)] px-6 font-semibold text-black transition active:scale-[0.99]"
        >
          Get my Viral Score
        </Link>
      </div>
    </main>
  );
}
