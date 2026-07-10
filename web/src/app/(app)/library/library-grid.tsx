"use client";

import { useState } from "react";

export type LibraryItem = {
  id: string;
  url: string;
  title: string;
  createdAt: string;
  width: number | null;
  height: number | null;
  duration: number | null;
  clipCount: number;
};

// Display order + labels for the six platforms the publish route supports.
const PLATFORMS: { key: string; label: string }[] = [
  { key: "tiktok", label: "TikTok" },
  { key: "instagram", label: "Instagram" },
  { key: "youtube", label: "YouTube" },
  { key: "x", label: "X" },
  { key: "facebook", label: "Facebook" },
  { key: "linkedin", label: "LinkedIn" },
];

type PubState = "idle" | "busy" | "done" | "error";

function resBadge(w: number | null, h: number | null): string | null {
  if (!w || !h) return null;
  return Math.max(w, h) >= 3840 ? "4K" : "1080p";
}

export function LibraryGrid({ items, connected = [] }: { items: LibraryItem[]; connected?: string[] }) {
  const [gone, setGone] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  // Publish status + optional message, keyed by `${itemId}:${platform}`.
  const [pub, setPub] = useState<Record<string, { state: PubState; msg?: string }>>({});
  const visible = items.filter((i) => !gone.has(i.id));

  // Only show buttons for platforms the user has actually connected, in display order.
  const connectedPlatforms = PLATFORMS.filter((p) => connected.includes(p.key));

  async function remove(id: string) {
    if (!window.confirm("Delete this video permanently? This can't be undone.")) return;
    setBusy(id);
    try {
      const res = await fetch(`/api/library/${id}`, { method: "DELETE" });
      if (res.ok) setGone((g) => new Set(g).add(id));
    } finally {
      setBusy(null);
    }
  }

  async function publishTo(item: LibraryItem, platform: string) {
    const key = `${item.id}:${platform}`;
    setPub((p) => ({ ...p, [key]: { state: "busy" } }));
    try {
      const res = await fetch("/api/social/publish", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ platform, jobId: item.id, caption: item.title.slice(0, 280) }),
      });
      const data = (await res.json().catch(() => ({}))) as { url?: string; error?: string };
      if (res.ok) {
        setPub((p) => ({ ...p, [key]: { state: "done", msg: data.url } }));
      } else {
        setPub((p) => ({ ...p, [key]: { state: "error", msg: data.error ?? "Failed" } }));
      }
    } catch {
      setPub((p) => ({ ...p, [key]: { state: "error", msg: "Network error" } }));
    }
  }

  if (!visible.length) {
    return (
      <div className="mt-12 rounded-2xl border border-white/[0.07] bg-[var(--surface)]/40 p-12 text-center text-sm text-white/45">
        Nothing here yet — record a take or spin up a faceless video, and it lands here finished.
      </div>
    );
  }

  return (
    <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {visible.map((v) => (
        <div key={v.id} className="group overflow-hidden rounded-2xl border border-white/[0.07] bg-[var(--surface)]/50">
          <video src={v.url} controls playsInline preload="metadata" className="aspect-[9/16] w-full bg-black" />
          <div className="space-y-2 p-4">
            <div className="flex items-center gap-2">
              {resBadge(v.width, v.height) && (
                <span className="shrink-0 rounded-full bg-[var(--accent)]/15 px-2 py-0.5 text-[11px] font-semibold text-[var(--accent)]">
                  {resBadge(v.width, v.height)}
                </span>
              )}
              <span className="truncate text-sm font-medium">{v.title}</span>
            </div>
            <div className="flex items-center justify-between text-xs text-white/40">
              <span>
                {new Date(v.createdAt).toLocaleDateString()}
                {v.duration ? ` · ${Math.round(v.duration)}s` : ""}
                {v.clipCount ? ` · ${v.clipCount} clips` : ""}
              </span>
              <span className="flex items-center gap-3">
                <a href={v.url} download={`clouthook-${v.id.slice(0, 8)}.mp4`} className="press font-medium text-[var(--accent)] hover:opacity-80">
                  Download
                </a>
                <button
                  onClick={() => remove(v.id)}
                  disabled={busy === v.id}
                  className="press text-white/35 transition-colors hover:text-red-400 disabled:opacity-50"
                >
                  {busy === v.id ? "…" : "Delete"}
                </button>
              </span>
            </div>

            {/* Post directly to any connected social account — same route the faceless result screen uses. */}
            {connectedPlatforms.length > 0 ? (
              <div className="border-t border-white/[0.06] pt-3">
                <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-white/30">Post to</p>
                <div className="flex flex-wrap gap-1.5">
                  {connectedPlatforms.map((p) => {
                    const st = pub[`${v.id}:${p.key}`];
                    const state = st?.state ?? "idle";
                    return (
                      <button
                        key={p.key}
                        onClick={() => publishTo(v, p.key)}
                        disabled={state === "busy" || state === "done"}
                        title={state === "error" ? st?.msg : state === "done" ? "Posted — click the video on the platform" : `Post to ${p.label}`}
                        className={[
                          "press rounded-lg border px-2.5 py-1 text-xs font-medium transition",
                          state === "done"
                            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                            : state === "error"
                              ? "border-red-500/40 bg-red-500/10 text-red-300"
                              : "border-white/12 text-white/70 hover:border-[var(--accent)]/50 hover:text-white",
                          state === "busy" ? "opacity-60" : "",
                        ].join(" ")}
                      >
                        {state === "busy" ? `${p.label}…` : state === "done" ? `✓ ${p.label}` : state === "error" ? `${p.label} ✕` : p.label}
                      </button>
                    );
                  })}
                </div>
                {/* Surface the first live post link + any error for this card. */}
                {Object.entries(pub)
                  .filter(([k, s]) => k.startsWith(`${v.id}:`) && s.state === "done" && s.msg)
                  .slice(0, 1)
                  .map(([k, s]) => (
                    <a key={k} href={s.msg} target="_blank" rel="noopener noreferrer" className="mt-2 block truncate text-[11px] text-[var(--accent)] hover:opacity-80">
                      View live post →
                    </a>
                  ))}
                {Object.entries(pub)
                  .filter(([k, s]) => k.startsWith(`${v.id}:`) && s.state === "error")
                  .slice(0, 1)
                  .map(([k, s]) => (
                    <p key={k} className="mt-1.5 text-[11px] text-red-300/80">{s.msg}</p>
                  ))}
              </div>
            ) : (
              <div className="border-t border-white/[0.06] pt-3">
                <a href="/connections" className="press text-xs font-medium text-white/45 hover:text-[var(--accent)]">
                  Connect a social account to post →
                </a>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
