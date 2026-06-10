"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button, Card } from "@/components/ui";

// Faceless studio: topic/script → narrated, AI-scene short. The form queues a job
// (script gen + TTS happen in /api/faceless); this view then tells the truth about
// progress and ends in a 9:16 player.

const VOICES = [
  { id: "Charon", name: "Charon", vibe: "Deep & cinematic" },
  { id: "Kore", name: "Kore", vibe: "Confident & clear" },
  { id: "Puck", name: "Puck", vibe: "Upbeat & friendly" },
  { id: "Aoede", name: "Aoede", vibe: "Bright & energetic" },
  { id: "Fenrir", name: "Fenrir", vibe: "Bold & intense" },
  { id: "Leda", name: "Leda", vibe: "Calm & soothing" },
] as const;

const STYLES = [
  ["cinematic", "Cinematic"],
  ["cinematic_film", "Film"],
  ["clean_ugc", "Clean"],
] as const;

type JobRow = {
  status: "queued" | "processing" | "done" | "error";
  progress: number;
  output_path: string | null;
  error: string | null;
};

function Seg<T extends string>({
  value, options, onChange, label,
}: { value: T; options: readonly (readonly [T, string])[]; onChange: (v: T) => void; label: string }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-white/65">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([v, text]) => (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            aria-pressed={value === v}
            className={`press rounded-xl border px-3.5 py-2 text-sm font-medium transition-colors ${
              value === v
                ? "border-[var(--accent)]/60 bg-[var(--accent)]/15 text-white"
                : "border-white/10 bg-white/[0.03] text-white/60 hover:bg-white/5 hover:text-white/85"
            }`}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

function stageFor(p: number, status: string): string {
  if (status === "queued") return "Queued — a render slot opens in under a minute";
  if (p < 0.45) return "Transcribing the narration";
  if (p < 0.55) return "Planning the scenes";
  if (p < 0.82) return "Generating AI scenes";
  if (p < 0.95) return "Compositing video, captions, and sound";
  return "Finishing up";
}

export function FacelessClient() {
  const supabase = useMemo(() => createClient(), []);
  const [mode, setMode] = useState<"topic" | "script">("topic");
  const [topic, setTopic] = useState("");
  const [script, setScript] = useState("");
  const [voice, setVoice] = useState<string>("Charon");
  const [style, setStyle] = useState<(typeof STYLES)[number][0]>("cinematic");
  const [lengthSec, setLengthSec] = useState<"30" | "60" | "90">("60");
  const [resolution, setResolution] = useState<"1080p" | "4k">("1080p");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("");
  const [job, setJob] = useState<JobRow | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scenes = Math.max(3, Math.min(Math.round(Number(lengthSec) / 7), 16));

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  useEffect(() => {
    if (!jobId) return;
    pollRef.current = setInterval(async () => {
      const { data } = await supabase
        .from("render_jobs")
        .select("status,progress,output_path,error")
        .eq("id", jobId)
        .single<JobRow>();
      if (!data) return;
      setJob(data);
      if (data.status === "done" && data.output_path) {
        if (pollRef.current) clearInterval(pollRef.current);
        const { data: signed } = await supabase.storage
          .from("outputs")
          .createSignedUrl(data.output_path, 3600);
        if (signed) setVideoUrl(signed.signedUrl);
      }
      if (data.status === "error" && pollRef.current) clearInterval(pollRef.current);
    }, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [jobId, supabase]);

  async function generate() {
    setError(null);
    setBusy(true);
    try {
      const r = await fetch("/api/faceless", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic: mode === "topic" ? topic.trim() : undefined,
          script: mode === "script" ? script.trim() : undefined,
          voice,
          style,
          lengthSec: Number(lengthSec),
          resolution,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "generation failed");
      setJobId(data.jobId);
      setTitle(data.title ?? "");
      setJob({ status: "queued", progress: 0, output_path: null, error: null });
    } catch (e) {
      setError(e instanceof Error ? e.message : "generation failed");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    if (pollRef.current) clearInterval(pollRef.current);
    setJobId(null); setJob(null); setVideoUrl(null); setTitle(""); setError(null);
  }

  const inputOk = mode === "topic" ? topic.trim().length > 2 : script.trim().length > 20;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <p className="text-sm font-semibold text-[var(--accent)]">Faceless studio</p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">
        No camera. <span className="brand-grad-text">Still premium.</span>
      </h1>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-white/60">
        Give it a topic. It writes the narration in your blueprint voice, speaks it with a
        studio voice, paints every beat as an AI scene, and captions it karaoke-style —
        a finished 9:16 short with zero filming.
      </p>

      {!jobId && (
        <Card className="mt-7 space-y-5">
          <Seg label="Start from" value={mode}
            options={[["topic", "Give me a topic"], ["script", "I have a script"]] as const}
            onChange={setMode} />

          {mode === "topic" ? (
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              rows={2}
              placeholder="e.g. Why most creators burn out in 90 days — and the system that prevents it"
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none transition focus:border-[var(--accent)]/60 focus:ring-2 focus:ring-[var(--accent)]/25"
            />
          ) : (
            <textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              rows={6}
              placeholder="Paste the exact narration to speak…"
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none transition focus:border-[var(--accent)]/60 focus:ring-2 focus:ring-[var(--accent)]/25"
            />
          )}

          <div>
            <p className="mb-1.5 text-xs font-medium text-white/65">Voice</p>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
              {VOICES.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setVoice(v.id)}
                  aria-pressed={voice === v.id}
                  className={`press rounded-xl border px-3 py-2.5 text-left transition-colors ${
                    voice === v.id
                      ? "border-[var(--accent)]/60 bg-[var(--accent)]/15"
                      : "border-white/10 bg-white/[0.03] hover:bg-white/5"
                  }`}
                >
                  <span className="block text-sm font-semibold">{v.name}</span>
                  <span className="block text-xs text-white/55">{v.vibe}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Seg label="Look" value={style} options={STYLES} onChange={setStyle} />
            <Seg label="Length" value={lengthSec}
              options={[["30", "30s"], ["60", "60s"], ["90", "90s"]] as const}
              onChange={setLengthSec} />
            <Seg label="Quality" value={resolution}
              options={[["1080p", "1080p"], ["4k", "4K Ultra"]] as const}
              onChange={setResolution} />
          </div>

          {error && (
            <p className="rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          )}

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-white/45">≈ {scenes} AI scenes · {scenes} tokens</p>
            <Button onClick={generate} disabled={busy || !inputOk} className="min-w-44">
              {busy ? "Writing & voicing…" : "Generate video"}
            </Button>
          </div>
        </Card>
      )}

      {jobId && job && job.status !== "done" && job.status !== "error" && (
        <Card className="mt-7 space-y-4">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          <div>
            <div className="h-2 overflow-hidden rounded-full bg-white/5">
              <div
                className="h-full rounded-full transition-[width] duration-700"
                style={{ width: `${Math.max(4, Math.round(job.progress * 100))}%`, background: "var(--brand-grad)" }}
              />
            </div>
            <p className="mt-2 text-sm text-white/60">{stageFor(job.progress, job.status)}</p>
          </div>
          <p className="text-xs text-white/40">
            You can leave this page — the video keeps rendering and lands in your account.
          </p>
        </Card>
      )}

      {job?.status === "error" && (
        <Card className="mt-7 space-y-3 border-red-500/20">
          <h2 className="text-base font-semibold text-red-300">That render failed</h2>
          <p className="text-sm text-white/60">{job.error ?? "Unknown error."} Your tokens for unrendered scenes were not consumed.</p>
          <Button variant="outline" onClick={reset}>Try again</Button>
        </Card>
      )}

      {job?.status === "done" && videoUrl && (
        <div className="mt-7 space-y-4">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          <video
            src={videoUrl}
            controls
            playsInline
            className="mx-auto aspect-[9/16] w-full max-w-[320px] rounded-2xl border border-white/10 bg-black"
          />
          <div className="mx-auto flex max-w-[320px] gap-2">
            <a href={videoUrl} download="clouthook-faceless.mp4" className="flex-1">
              <Button className="w-full">Download</Button>
            </a>
            <Button variant="outline" onClick={reset}>Make another</Button>
          </div>
        </div>
      )}
    </div>
  );
}
