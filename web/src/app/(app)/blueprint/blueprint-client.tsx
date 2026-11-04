"use client";

import { useState } from "react";
import { Button } from "@/components/ui";

type Blueprint = {
  love: string;
  great_at: string;
  world_needs: string;
  paid_for: string;
  icp: { who: string; pains: string[]; goals: string[]; watches: string } | null;
  pillars: { name: string; why: string }[] | null;
  voice: { tone: string; pov: string; phrases: string[] } | null;
} | null;

const QUESTIONS: { key: "love" | "great_at" | "world_needs" | "paid_for"; label: string; hint: string }[] = [
  { key: "love", label: "What do you love to do?", hint: "The work you'd do even unpaid — topics you can't shut up about." },
  { key: "great_at", label: "What are you great at?", hint: "Skills, reps, results. What do people ask you for help with?" },
  { key: "world_needs", label: "What does the world need right now?", hint: "The problem you see everywhere that you know how to fix." },
  { key: "paid_for", label: "What can you get paid for?", hint: "What have people actually paid you (or others like you) for?" },
];

export function BlueprintClient({ initial }: { initial: Blueprint }) {
  const [answers, setAnswers] = useState({
    love: initial?.love ?? "",
    great_at: initial?.great_at ?? "",
    world_needs: initial?.world_needs ?? "",
    paid_for: initial?.paid_for ?? "",
  });
  const [bp, setBp] = useState<Blueprint>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const complete = Object.values(answers).every((v) => v.trim().length > 0);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/blueprint", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(answers),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "generation failed");
      setBp(data.blueprint);
    } catch (e) {
      setError(e instanceof Error ? e.message : "generation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-8 space-y-8">
      <div className="grid gap-4 sm:grid-cols-2">
        {QUESTIONS.map((q) => (
          <div key={q.key} className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-4">
            <label className="text-sm font-semibold">{q.label}</label>
            <p className="mt-0.5 text-xs text-white/35">{q.hint}</p>
            <textarea
              value={answers[q.key]}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.key]: e.target.value }))}
              rows={4}
              className="mt-2 w-full resize-none rounded-xl border border-white/10 bg-black/30 p-3 text-sm text-white/85 outline-none placeholder:text-white/25 focus:border-[var(--accent)]/40"
              placeholder="Be specific — this shapes every script."
            />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={generate} disabled={!complete || busy}>
          {busy ? "Building your blueprint…" : bp?.icp ? "Regenerate blueprint" : "Generate my blueprint"}
        </Button>
        {error && <span className="text-sm text-red-400">{error}</span>}
      </div>

      {bp?.icp && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
            <div className="text-xs uppercase tracking-wide text-white/40">Ideal viewer</div>
            <p className="mt-2 text-sm font-medium">{bp.icp.who}</p>
            <div className="mt-3 text-xs uppercase tracking-wide text-white/40">Their pains</div>
            <ul className="mt-1 space-y-1 text-sm text-white/65">
              {bp.icp.pains?.map((p, i) => <li key={i}>• {p}</li>)}
            </ul>
            <div className="mt-3 text-xs uppercase tracking-wide text-white/40">They watch</div>
            <p className="mt-1 text-sm text-white/65">{bp.icp.watches}</p>
          </div>
          <div className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
            <div className="text-xs uppercase tracking-wide text-white/40">Content pillars</div>
            <ul className="mt-2 space-y-3">
              {bp.pillars?.map((p, i) => (
                <li key={i}>
                  <div className="text-sm font-semibold text-[var(--accent)]">{p.name}</div>
                  <div className="text-xs text-white/55">{p.why}</div>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
            <div className="text-xs uppercase tracking-wide text-white/40">Voice fingerprint</div>
            <p className="mt-2 text-sm"><span className="text-white/40">Tone:</span> {bp.voice?.tone}</p>
            <p className="mt-2 text-sm"><span className="text-white/40">POV:</span> {bp.voice?.pov}</p>
            <div className="mt-3 text-xs uppercase tracking-wide text-white/40">Signature phrasing</div>
            <ul className="mt-1 space-y-1 text-sm text-white/65">
              {bp.voice?.phrases?.map((p, i) => <li key={i}>“{p}”</li>)}
            </ul>
          </div>
        </div>
      )}

      {bp?.icp && (
        <p className="text-sm text-white/45">
          Done. Now head to <a href="/outliers" className="font-medium text-[var(--accent)] hover:opacity-80">Outliers</a> —
          find a proven format and we&apos;ll script it in this voice.
        </p>
      )}
    </div>
  );
}
