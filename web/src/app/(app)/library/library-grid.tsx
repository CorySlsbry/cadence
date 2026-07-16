"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

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

export type SocialConn = { id: string; platform: string; username: string | null; label: string | null };
type PublishResult = { ok: boolean; url?: string; error?: string; note?: string };

// Publish targets — connected accounts are grouped under these platforms.
const PLATFORM_ORDER = ["x", "tiktok", "instagram", "facebook", "linkedin", "youtube"] as const;
const PLATFORM_LABELS: Record<string, string> = {
  x: "X", tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn", youtube: "YouTube",
};

function resBadge(w: number | null, h: number | null): string | null {
  if (!w || !h) return null;
  return Math.max(w, h) >= 3840 ? "4K" : "1080p";
}

export function LibraryGrid({ items, connections }: { items: LibraryItem[]; connections: SocialConn[] }) {
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
            <PublishPanel jobId={v.id} caption={v.title} connections={connections} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Per-video multi-account publisher: pick connected accounts, post to all at once. */
function PublishPanel({ jobId, caption, connections }: { jobId: string; caption: string; connections: SocialConn[] }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Record<string, PublishResult>>({});
  const [msg, setMsg] = useState<string | null>(null);

  const byPlatform = useMemo(() => {
    const m: Record<string, SocialConn[]> = {};
    for (const c of connections) (m[c.platform] ??= []).push(c);
    return m;
  }, [connections]);
  const notes = useMemo(
    () => [...new Set(Object.values(results).map((r) => r.note).filter((n): n is string => !!n))],
    [results],
  );

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function post() {
    if (selected.size === 0) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch("/api/social/publish", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ connectionIds: [...selected], jobId, caption: caption.slice(0, 280) }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "publish failed");
      const map: Record<string, PublishResult> = {};
      for (const res of (d.results ?? []) as (PublishResult & { connectionId: string })[]) {
        map[res.connectionId] = { ok: res.ok, url: res.url, error: res.error, note: res.note };
      }
      setResults((prev) => ({ ...prev, ...map }));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "publish failed");
    } finally {
      setBusy(false);
    }
  }

  if (connections.length === 0) {
    return (
      <p className="text-xs text-white/35">
        <Link href="/connections" className="text-[var(--accent)] hover:underline">Connect an account</Link> to post directly.
      </p>
    );
  }

  return (
    <div className="border-t border-white/[0.06] pt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="press text-xs font-medium text-[var(--accent)] hover:opacity-80"
      >
        {open ? "Hide publish" : "Post to socials"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {PLATFORM_ORDER.filter((p) => byPlatform[p]?.length).map((p) => (
            <div key={p}>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">{PLATFORM_LABELS[p]}</p>
              <div className="space-y-1">
                {byPlatform[p].map((c) => {
                  const res = results[c.id];
                  const checked = selected.has(c.id);
                  return (
                    <label
                      key={c.id}
                      className={`flex cursor-pointer items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors ${
                        res?.ok
                          ? "border-emerald-400/40 bg-emerald-400/10"
                          : res?.error
                            ? "border-red-400/30 bg-red-400/5"
                            : checked
                              ? "border-[var(--accent)]/50 bg-[var(--accent)]/10"
                              : "border-white/10 bg-white/[0.03] hover:bg-white/5"
                      }`}
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggle(c.id)}
                          className="h-3.5 w-3.5 shrink-0 accent-[var(--accent)]"
                        />
                        <span className="truncate text-white/85">@{c.label || c.username || PLATFORM_LABELS[p]}</span>
                      </span>
                      {res?.ok && res.url ? (
                        <a
                          href={res.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="shrink-0 text-emerald-300 hover:underline"
                        >
                          View
                        </a>
                      ) : res?.error ? (
                        <span className="shrink-0 text-red-300" title={res.error}>Failed</span>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={post}
            disabled={busy || selected.size === 0}
            className="press w-full rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-black transition hover:brightness-95 disabled:opacity-40"
          >
            {busy ? "Posting…" : `Post to selected (${selected.size})`}
          </button>
          {notes.map((n) => (
            <p key={n} className="text-center text-[11px] text-white/50">{n}</p>
          ))}
          {msg && <p className="text-center text-[11px] text-white/55">{msg}</p>}
        </div>
      )}
    </div>
  );
}
