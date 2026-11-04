"use client";

import { useEffect, useRef, useState } from "react";

type Dim = { key: string; label: string; score: number; verdict: string };
type Teaser = {
  id: string | null;
  score: number;
  grade: string;
  summary: string;
  dimensions: Dim[];
  topFix: string | null;
  lockedFixes: number;
};
type FullDim = Dim & { fix: string };
type Full = { score: number; grade: string; summary: string; dimensions: FullDim[]; topFixes: string[] };

function utmParams(): Record<string, string> {
  if (typeof window === "undefined") return {};
  return Object.fromEntries(new URLSearchParams(window.location.search));
}

function barColor(s: number): string {
  if (s >= 7) return "var(--accent)";
  if (s >= 5) return "#d4a72c";
  return "#e0606b";
}
function tierWord(s: number): string {
  if (s >= 7) return "strong";
  if (s >= 5) return "needs work";
  return "weak";
}

export function ScoreClient({ headingLevel = "h2" }: { headingLevel?: "h2" | "h3" }) {
  const Heading = headingLevel;
  const [mode, setMode] = useState<"link" | "describe">("link");
  const [url, setUrl] = useState("");
  const [platform, setPlatform] = useState("");
  const [topic, setTopic] = useState("");
  const [hook, setHook] = useState("");
  const [phase, setPhase] = useState<"input" | "loading" | "result">("input");
  const [err, setErr] = useState("");
  const [teaser, setTeaser] = useState<Teaser | null>(null);
  const [email, setEmail] = useState("");
  const [unlocking, setUnlocking] = useState(false);
  const [full, setFull] = useState<Full | null>(null);
  const [copied, setCopied] = useState(false);
  const [status, setStatus] = useState(""); // persistent SR live-region text

  const resultRef = useRef<HTMLDivElement>(null);
  const urlRef = useRef<HTMLInputElement>(null);

  // Focus + announce the result when it renders (the live region below is always mounted, so the
  // announcement is reliable — a region injected together with its text is often missed).
  useEffect(() => {
    if (phase === "result" && teaser) {
      setStatus(`Your video scored ${teaser.score} out of 10, grade ${teaser.grade}.`);
      resultRef.current?.focus();
    }
  }, [phase, teaser]);
  useEffect(() => {
    if (full) setStatus("Your personalized fixes are ready below.");
  }, [full]);

  const submit = async () => {
    setErr("");
    if (mode === "link" && !url.trim()) {
      setErr("Paste a video link to score it.");
      urlRef.current?.focus();
      return;
    }
    if (mode === "describe" && !topic.trim() && !hook.trim()) {
      setErr("Tell us the topic, or paste your hook.");
      return;
    }
    setPhase("loading");
    try {
      const body = mode === "link" ? { url: url.trim(), utm: utmParams() } : { platform, topic, hook, utm: utmParams() };
      const r = await fetch("/api/score", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "Couldn't score that — try again.");
      setTeaser(j);
      setFull(null);
      setPhase("result");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
      setPhase("input");
    }
  };

  const unlock = async () => {
    if (!teaser?.id) return;
    setErr("");
    setUnlocking(true);
    try {
      const r = await fetch("/api/score/unlock", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: teaser.id, email: email.trim(), utm: utmParams() }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "Couldn't unlock — try again.");
      setFull(j.result as Full);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setUnlocking(false);
    }
  };

  const reset = () => {
    setPhase("input");
    setTeaser(null);
    setFull(null);
    setEmail("");
    setErr("");
    setStatus("");
  };

  const share = async () => {
    if (!teaser) return;
    const link = teaser.id ? `${window.location.origin}/score/${teaser.id}` : window.location.href;
    const text = `My video scored ${teaser.score}/10 on CloutHook's Viral Score. Score yours free:`;
    try {
      if (navigator.share) await navigator.share({ title: "My Viral Score", text, url: link });
      else {
        await navigator.clipboard.writeText(`${text} ${link}`);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      /* user dismissed share sheet */
    }
  };

  return (
    <div className="mt-8">
      {/* Persistent polite live region — always in the DOM so async results are announced. */}
      <div aria-live="polite" className="sr-only">
        {status}
      </div>

      {phase === "input" && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <div className="flex gap-2" role="group" aria-label="How to score">
            {(["link", "describe"] as const).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
                className={`min-h-11 rounded-lg px-4 text-sm font-medium transition ${
                  mode === m ? "bg-[var(--accent)] text-black" : "bg-white/5 text-white/70 hover:text-white"
                }`}
              >
                {m === "link" ? "Paste a link" : "Describe it"}
              </button>
            ))}
          </div>

          {mode === "link" ? (
            <div className="mt-5">
              <label htmlFor="vs-url" className="block text-sm text-white/70">
                Your video link (TikTok, YouTube, Reels, Shorts)
              </label>
              <input
                id="vs-url"
                ref={urlRef}
                className="input mt-2 w-full"
                placeholder="https://www.tiktok.com/@you/video/..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                inputMode="url"
                autoComplete="off"
                aria-invalid={!!err}
                aria-describedby={err ? "vs-error" : undefined}
              />
            </div>
          ) : (
            <div className="mt-5 space-y-4">
              <div>
                <label htmlFor="vs-platform" className="block text-sm text-white/70">Platform</label>
                <input id="vs-platform" className="input mt-2 w-full" placeholder="TikTok / YouTube Shorts / Reels" value={platform} onChange={(e) => setPlatform(e.target.value)} />
              </div>
              <div>
                <label htmlFor="vs-hook" className="block text-sm text-white/70">Your opening line (the first thing said/shown)</label>
                <input id="vs-hook" className="input mt-2 w-full" placeholder="e.g. 'Stop posting Reels until you watch this'" value={hook} onChange={(e) => setHook(e.target.value)} aria-invalid={!!err} aria-describedby={err ? "vs-error" : undefined} />
              </div>
              <div>
                <label htmlFor="vs-topic" className="block text-sm text-white/70">What the video is about</label>
                <textarea id="vs-topic" className="input mt-2 w-full" rows={3} placeholder="A 30s tip on editing faster with AI..." value={topic} onChange={(e) => setTopic(e.target.value)} aria-invalid={!!err} aria-describedby={err ? "vs-error" : undefined} />
              </div>
            </div>
          )}

          {err && <p id="vs-error" role="alert" className="mt-3 text-sm text-[#e0606b]">{err}</p>}

          <button onClick={submit} className="mt-5 min-h-12 w-full rounded-xl bg-[var(--accent)] px-6 font-semibold text-black transition active:scale-[0.99]">
            Score my video — free
          </button>
          <p className="mt-3 text-center text-xs text-white/50">No signup to see your score. ~15 seconds.</p>
        </div>
      )}

      {phase === "loading" && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-12 text-center" role="status" aria-live="polite">
          <div className="h-10 w-10 rounded-full border-2 border-[var(--accent)] border-t-transparent animate-spin" />
          <p className="text-white/70">Analyzing your hook, pacing, captions, and format…</p>
        </div>
      )}

      {phase === "result" && teaser && (
        <div ref={resultRef} tabIndex={-1} className="outline-none">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center">
            <div className="text-6xl font-bold text-white">
              {teaser.score}
              <span className="text-2xl text-white/50">/10</span>
            </div>
            <div className="mt-1 text-sm font-semibold text-[var(--accent)]">{teaser.grade}</div>
            {teaser.summary && <p className="mx-auto mt-3 max-w-xl text-[15px] leading-7 text-white/70">{teaser.summary}</p>}
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <button onClick={share} className="min-h-11 rounded-lg border border-white/15 px-4 text-sm font-medium text-white/80 transition hover:text-white">
                {copied ? "Link copied" : "Share my score"}
              </button>
              <button onClick={reset} className="min-h-11 rounded-lg border border-white/15 px-4 text-sm font-medium text-white/80 transition hover:text-white">
                Score another
              </button>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {teaser.dimensions.map((d) => {
              const fd = full?.dimensions.find((x) => x.key === d.key);
              return (
                <div key={d.key} className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-white">{d.label}</span>
                    <span className="text-sm font-semibold text-white/80">{d.score}/10</span>
                  </div>
                  <div
                    className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/10"
                    role="img"
                    aria-label={`${d.label}: ${d.score} out of 10 — ${tierWord(d.score)}`}
                  >
                    <div className="h-full rounded-full" style={{ width: `${d.score * 10}%`, background: barColor(d.score) }} />
                  </div>
                  <p className="mt-2 text-sm text-white/70">{d.verdict}</p>
                  {fd?.fix && <p className="mt-1 text-sm text-[var(--accent)]">Fix: {fd.fix}</p>}
                </div>
              );
            })}
          </div>

          {!full ? (
            <div className="mt-4 rounded-2xl border border-[var(--accent)]/30 bg-[var(--accent)]/10 p-6">
              <Heading className="text-lg font-semibold text-white">Unlock your {teaser.lockedFixes} personalized fixes</Heading>
              <p className="mt-1 text-sm text-white/70">
                {teaser.topFix ? `Starting with: ${teaser.topFix}` : "Get the specific, prioritized fixes for this exact video"} — emailed to you, plus a repaired preview.
              </p>
              <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                <label htmlFor="vs-email" className="sr-only">Email address</label>
                <input
                  id="vs-email"
                  type="email"
                  className="input w-full"
                  placeholder="person1@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  aria-invalid={!!err}
                  aria-describedby={err ? "vs-unlock-error" : undefined}
                />
                <button onClick={unlock} disabled={unlocking} className="min-h-12 shrink-0 rounded-xl bg-[var(--accent)] px-6 font-semibold text-black transition active:scale-[0.99] disabled:opacity-60">
                  {unlocking ? "Unlocking…" : "Email my fixes"}
                </button>
              </div>
              {err && <p id="vs-unlock-error" role="alert" className="mt-3 text-sm text-[#e0606b]">{err}</p>}
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-6">
              <Heading className="text-lg font-semibold text-white">Your top fixes</Heading>
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-[15px] leading-7 text-white/80">
                {full.topFixes.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ol>
              <a href="/signup" className="mt-5 inline-flex min-h-12 items-center rounded-xl bg-[var(--accent)] px-6 font-semibold text-black transition active:scale-[0.99]">
                Let CloutHook fix this video for you →
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
