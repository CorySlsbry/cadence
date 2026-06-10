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

function resBadge(w: number | null, h: number | null): string | null {
  if (!w || !h) return null;
  return Math.max(w, h) >= 3840 ? "4K" : "1080p";
}

export function LibraryGrid({ items }: { items: LibraryItem[] }) {
  const [gone, setGone] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const visible = items.filter((i) => !gone.has(i.id));

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
          </div>
        </div>
      ))}
    </div>
  );
}
