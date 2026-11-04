"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui";

type Channel = { id: string; channel_id: string; title: string; handle: string | null; thumbnail_url: string | null; median_views: number | null };
type Analysis = { title_pattern: string; thumbnail_notes: string; hook_hypothesis: string; why_it_works: string; remix_angles: string[] };
type Outlier = {
  id: string; video_id: string; title: string; channel_title: string; thumbnail_url: string | null;
  published_at: string | null; views: number; channel_median_views: number | null;
  outlier_score: number | null; analysis: Analysis | null;
};
type Script = { id: string; title: string; hook: string; body: string; broll_keywords: string[] | null };

const fmtViews = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n));
const age = (iso: string | null) => {
  if (!iso) return "";
  const days = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 86400_000));
  return days === 0 ? "today" : days < 30 ? `${days}d ago` : `${Math.floor(days / 30)}mo ago`;
};

export function OutliersClient({
  initialChannels, initialOutliers, hasBlueprint,
}: { initialChannels: Channel[]; initialOutliers: Outlier[]; hasBlueprint: boolean }) {
  const [channels, setChannels] = useState(initialChannels);
  const [outliers, setOutliers] = useState(initialOutliers);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState<string | null>(null); // "add" | "refresh" | outlier id | `script:${id}`
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [script, setScript] = useState<Script | null>(null);
  const [sentToPrompter, setSentToPrompter] = useState(false);

  const top = useMemo(() => outliers.filter((o) => (o.outlier_score ?? 0) > 0), [outliers]);

  async function addChannel() {
    if (!input.trim()) return;
    setBusy("add"); setError(null);
    try {
      const r = await fetch("/api/channels", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ input }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "couldn't add channel");
      setChannels((c) => (c.some((x) => x.id === data.channel.id) ? c : [...c, data.channel]));
      setInput("");
      await refresh(); // populate the feed for the new channel right away
    } catch (e) {
      setError(e instanceof Error ? e.message : "couldn't add channel");
    } finally {
      setBusy(null);
    }
  }

  async function removeChannel(id: string) {
    setChannels((c) => c.filter((x) => x.id !== id));
    await fetch("/api/channels", {
      method: "DELETE", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const r = await fetch("/api/outliers");
    if (r.ok) setOutliers((await r.json()).outliers ?? []);
  }

  async function refresh() {
    setBusy("refresh"); setError(null);
    try {
      const r = await fetch("/api/outliers", { method: "POST" });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "refresh failed");
      setOutliers(data.outliers ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "refresh failed");
    } finally {
      setBusy(null);
    }
  }

  async function analyze(o: Outlier) {
    setOpenId(o.id);
    if (o.analysis) return;
    setBusy(o.id);
    try {
      const r = await fetch("/api/outliers/analyze", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: o.id }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "analysis failed");
      setOutliers((os) => os.map((x) => (x.id === o.id ? { ...x, analysis: data.analysis } : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "analysis failed");
    } finally {
      setBusy(null);
    }
  }

  async function writeScript(o: Outlier) {
    setBusy(`script:${o.id}`); setError(null); setScript(null); setSentToPrompter(false);
    try {
      const r = await fetch("/api/scripts", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ outlierId: o.id, lengthSec: 45 }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error ?? "script generation failed");
      setScript(data.script);
    } catch (e) {
      setError(e instanceof Error ? e.message : "script generation failed");
    } finally {
      setBusy(null);
    }
  }

  function sendToTeleprompter() {
    if (!script) return;
    try {
      localStorage.setItem("clouthook-script", script.body);
      localStorage.setItem("clouthook-script-title", script.title);
      setSentToPrompter(true);
    } catch { /* storage unavailable — the copy button still works */ }
  }

  return (
    <div className="mt-8 space-y-8">
      {!hasBlueprint && (
        <div className="rounded-2xl border border-[var(--accent)]/25 bg-[var(--accent)]/[0.06] p-4 text-sm">
          <strong>Make it yours:</strong> set up your{" "}
          <Link href="/blueprint" className="font-semibold text-[var(--accent)] hover:opacity-80">Brand Blueprint</Link>{" "}
          first — scripts get written in <em>your</em> voice, for <em>your</em> audience, instead of a generic one.
        </div>
      )}

      {/* Channel manager */}
      <div className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm font-semibold text-white/70">Watched channels <span className="text-white/35">({channels.length}/10)</span></div>
          <button onClick={refresh} disabled={busy === "refresh"} className="text-xs font-medium text-[var(--accent)] hover:opacity-80 disabled:opacity-40">
            {busy === "refresh" ? "Scanning uploads…" : "Refresh outliers"}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {channels.map((c) => (
            <span key={c.id} className="group flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] py-1 pl-1 pr-2.5 text-xs">
              {c.thumbnail_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={c.thumbnail_url} alt="" className="h-5 w-5 rounded-full" />
              ) : <span className="h-5 w-5 rounded-full bg-white/10" />}
              {c.title}
              <button onClick={() => removeChannel(c.id)} className="text-white/30 hover:text-white">×</button>
            </span>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addChannel()}
            placeholder="@handle or channel URL — the creators your audience already watches"
            className="flex-1 rounded-xl border border-white/10 bg-black/30 px-3 py-2.5 text-sm outline-none placeholder:text-white/25 focus:border-[var(--accent)]/40"
          />
          <Button onClick={addChannel} disabled={busy === "add" || !input.trim()}>
            {busy === "add" ? "Adding…" : "Watch"}
          </Button>
        </div>
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </div>

      {/* Outlier feed */}
      {top.length === 0 ? (
        <div className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-10 text-center text-white/40">
          {channels.length === 0
            ? "Add 3–5 channels in your niche. We'll find the videos that broke out of their baseline."
            : "No outliers scored yet — hit “Refresh outliers”."}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {top.map((o) => {
            const score = Math.round(o.outlier_score ?? 0);
            const hot = score >= 200;
            const open = openId === o.id;
            return (
              <div key={o.id} className={`flex flex-col overflow-hidden rounded-2xl border bg-[var(--surface)] ${hot ? "border-[var(--accent)]/30" : "border-white/[0.07]"}`}>
                <a href={`https://www.youtube.com/watch?v=${o.video_id}`} target="_blank" rel="noreferrer" className="relative block">
                  {o.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={o.thumbnail_url} alt="" className="aspect-video w-full object-cover" />
                  ) : <div className="aspect-video w-full bg-white/5" />}
                  <span className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-xs font-bold ${hot ? "bg-[var(--accent)] text-black" : "bg-black/70 text-white/80"}`}>
                    {score}
                  </span>
                </a>
                <div className="flex flex-1 flex-col gap-2 p-3">
                  <div className="line-clamp-2 text-sm font-semibold leading-snug">{o.title}</div>
                  <div className="text-xs text-white/40">
                    {o.channel_title} · {fmtViews(o.views)} views · {age(o.published_at)}
                    {o.channel_median_views ? ` · channel norm ${fmtViews(Math.round(o.channel_median_views))}` : ""}
                  </div>

                  {open && o.analysis && (
                    <div className="space-y-2 rounded-xl border border-white/[0.06] bg-black/25 p-3 text-xs leading-relaxed">
                      <p><span className="font-semibold text-[var(--accent)]">Title:</span> {o.analysis.title_pattern}</p>
                      <p><span className="font-semibold text-[var(--accent)]">Thumbnail:</span> {o.analysis.thumbnail_notes}</p>
                      <p><span className="font-semibold text-[var(--accent)]">Hook:</span> {o.analysis.hook_hypothesis}</p>
                      <p className="text-white/70">{o.analysis.why_it_works}</p>
                    </div>
                  )}

                  <div className="mt-auto flex gap-2 pt-1">
                    <button
                      onClick={() => (open ? setOpenId(null) : analyze(o))}
                      disabled={busy === o.id}
                      className="flex-1 rounded-lg border border-white/10 px-2 py-2 text-xs font-medium text-white/70 hover:text-white disabled:opacity-40"
                    >
                      {busy === o.id ? "Analyzing…" : open ? "Hide analysis" : "Why it popped"}
                    </button>
                    <button
                      onClick={() => writeScript(o)}
                      disabled={busy === `script:${o.id}`}
                      className="flex-1 rounded-lg bg-[var(--accent)] px-2 py-2 text-xs font-semibold text-black hover:opacity-90 disabled:opacity-40"
                    >
                      {busy === `script:${o.id}` ? "Writing…" : "Script my version"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Generated script panel */}
      {script && (
        <div className="rounded-2xl border border-[var(--accent)]/25 bg-[var(--surface)] p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-xs uppercase tracking-wide text-white/40">Your script — in your voice</div>
              <div className="mt-1 text-lg font-bold">{script.title}</div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => navigator.clipboard.writeText(script.body)}
                className="rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-white/70 hover:text-white"
              >
                Copy
              </button>
              <button
                onClick={sendToTeleprompter}
                className="rounded-lg bg-[var(--accent)] px-3 py-2 text-xs font-semibold text-black hover:opacity-90"
              >
                {sentToPrompter ? "On the teleprompter ✓" : "Send to teleprompter"}
              </button>
            </div>
          </div>
          <p className="mt-3 whitespace-pre-wrap rounded-xl bg-black/25 p-4 text-sm leading-relaxed text-white/85">{script.body}</p>
          {!!script.broll_keywords?.length && (
            <p className="mt-3 text-xs text-white/45">
              Suggested b-roll: {script.broll_keywords.join(" · ")}
            </p>
          )}
          {sentToPrompter && (
            <p className="mt-3 text-sm text-white/55">
              Loaded. Open a <Link href="/dashboard" className="font-medium text-[var(--accent)] hover:opacity-80">project</Link> —
              the teleprompter will offer this script. Hit Record and CloutHook finishes the rest: cleanup, captions, b-roll, clips.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
