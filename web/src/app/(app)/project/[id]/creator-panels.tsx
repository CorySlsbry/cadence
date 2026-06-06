"use client";

import { useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui";
import type { RenderJob } from "@/lib/types";

function useCopy() {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = (key: string, value: string) => {
    void navigator.clipboard.writeText(value);
    setCopied(key);
    setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500);
  };
  return { copied, copy };
}

/** Multi-clip results: one signed video per clip + its title/hook + download. */
export function ClipsPanel({ job }: { job: RenderJob }) {
  const supabase = useMemo(() => createClient(), []);
  const [urls, setUrls] = useState<Record<number, string>>({});

  useEffect(() => {
    const clips = job.clips;
    if (!clips?.length) return;
    let active = true;
    (async () => {
      const next: Record<number, string> = {};
      for (const c of clips) {
        const { data } = await supabase.storage.from("outputs").createSignedUrl(c.output_path, 3600);
        if (data) next[c.index] = data.signedUrl;
      }
      if (active) setUrls(next);
    })();
    return () => { active = false; };
  }, [job.clips, supabase]);

  if (!job.clips?.length) return null;
  return (
    <div className="mx-auto max-w-2xl space-y-3 text-left">
      <h3 className="text-sm font-semibold">{job.clips.length} clips from your recording</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        {job.clips.map((c) => (
          <div key={c.index} className="space-y-2">
            {urls[c.index] ? (
              <video src={urls[c.index]} controls playsInline className="aspect-[9/16] w-full rounded-xl border border-white/10 bg-black" />
            ) : (
              <div className="aspect-[9/16] w-full animate-pulse rounded-xl bg-white/5" />
            )}
            <div className="text-xs"><span className="font-medium">{c.title || `Clip ${c.index + 1}`}</span> · {Math.round(c.duration)}s</div>
            {c.hook && <p className="text-xs text-white/45">{c.hook}</p>}
            {urls[c.index] && (
              <a href={urls[c.index]} download={`cadence-clip-${c.index + 1}.mp4`}>
                <Button variant="outline" className="w-full">Download</Button>
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Hook ideas + the suggested cold-open, each copyable. */
export function HooksPanel({ job }: { job: RenderJob }) {
  const { copied, copy } = useCopy();
  const h = job.hooks;
  if (!h?.hooks?.length) return null;
  return (
    <div className="mx-auto mt-4 max-w-md space-y-2 text-left">
      <h3 className="text-sm font-semibold">Hook ideas</h3>
      {h.cold_open?.line && (
        <p className="text-xs text-white/45">Cold open: &ldquo;{h.cold_open.line}&rdquo;{h.cold_open.why ? ` — ${h.cold_open.why}` : ""}</p>
      )}
      {h.hooks.map((hook, i) => (
        <div key={i} className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[0.02] p-2">
          <span className="text-sm">{hook}</span>
          <button onClick={() => copy(`h${i}`, hook)} className="shrink-0 text-xs font-medium text-[var(--accent)] hover:opacity-80">
            {copied === `h${i}` ? "Copied ✓" : "Copy"}
          </button>
        </div>
      ))}
    </div>
  );
}

/** Repurposed assets: carousel, thread, newsletter, quote cards. */
export function RepurposePanel({ job }: { job: RenderJob }) {
  const { copied, copy } = useCopy();
  const r = job.repurpose;
  if (!r) return null;
  const blocks: [string, string, string][] = [
    ["Carousel", (r.carousel ?? []).join("\n\n"), "car"],
    ["X / thread", (r.thread ?? []).join("\n\n"), "thr"],
    ["Newsletter", r.newsletter ?? "", "nl"],
    ["Quote cards", (r.quote_cards ?? []).join("\n"), "qc"],
  ];
  if (blocks.every(([, text]) => !text)) return null;
  return (
    <div className="mx-auto mt-4 max-w-md space-y-2 text-left">
      <h3 className="text-sm font-semibold">Repurpose this video</h3>
      {blocks.map(([label, text, key]) =>
        text ? (
          <div key={key} className="rounded-lg border border-white/10 bg-white/[0.02] p-2">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-white/45">{label}</span>
              <button onClick={() => copy(key, text)} className="text-xs font-medium text-[var(--accent)] hover:opacity-80">
                {copied === key ? "Copied ✓" : "Copy"}
              </button>
            </div>
            <p className="whitespace-pre-wrap text-sm text-white/80">{text}</p>
          </div>
        ) : null,
      )}
    </div>
  );
}
