"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button, Label } from "@/components/ui";
import type { PlatformCaption, RenderJob, SocialCaptions } from "@/lib/types";

type Platform = "tiktok" | "youtube" | "instagram";
const PLATFORMS: { id: Platform; label: string }[] = [
  { id: "tiktok", label: "TikTok" },
  { id: "instagram", label: "Instagram" },
  { id: "youtube", label: "YouTube" },
];

function assembled(p: Platform, b: PlatformCaption | undefined): string {
  if (!b) return "";
  if (p === "youtube") return [b.description, (b.hashtags ?? []).join(" ")].filter(Boolean).join("\n\n");
  return [b.caption, [...(b.mentions ?? []), ...(b.hashtags ?? [])].join(" ")].filter(Boolean).join("\n\n");
}

export function SocialPanel({ job }: { job: RenderJob }) {
  const supabase = useMemo(() => createClient(), []);
  const caps: SocialCaptions = job.social_captions ?? {};

  // Editable post text per platform (the final blob that gets posted), + YT title.
  const [text, setText] = useState<Record<Platform, string>>({
    tiktok: assembled("tiktok", caps.tiktok),
    instagram: assembled("instagram", caps.instagram),
    youtube: assembled("youtube", caps.youtube),
  });
  const [ytTitle, setYtTitle] = useState(caps.youtube?.title ?? "");
  const [copied, setCopied] = useState<Platform | null>(null);

  const [accounts, setAccounts] = useState<{ accountId: string; platform: string }[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; error?: string }>>({});
  const loaded = useRef(false);

  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    supabase
      .from("profiles")
      .select("blotato_accounts")
      .single()
      .then(({ data }) => setAccounts((data?.blotato_accounts ?? []) as { accountId: string; platform: string }[]));
  }, [supabase]);

  const connected = accounts.length > 0;
  const connectedPlatforms = new Set(accounts.map((a) => a.platform));

  async function connect() {
    setConnecting(true);
    setError(null);
    try {
      const res = await fetch("/api/social/connect", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ apiKey }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Could not connect");
      setAccounts(data.accounts ?? []);
      setApiKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect");
    } finally {
      setConnecting(false);
    }
  }

  async function copy(p: Platform) {
    const blob = p === "youtube" && ytTitle ? `${ytTitle}\n\n${text[p]}` : text[p];
    await navigator.clipboard.writeText(blob);
    setCopied(p);
    setTimeout(() => setCopied((c) => (c === p ? null : c)), 1500);
  }

  function block(p: Platform) {
    return p === "youtube"
      ? { title: ytTitle, description: text.youtube, hashtags: [] }
      : { caption: text[p], hashtags: [], mentions: [] };
  }

  async function post(platforms: Platform[]) {
    setPosting(true);
    setError(null);
    try {
      const captions = Object.fromEntries(platforms.map((p) => [p, block(p)]));
      const res = await fetch("/api/publish", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jobId: job.id, platforms, captions }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Publish failed");
      const next: Record<string, { ok: boolean; error?: string }> = {};
      for (const r of data.results as { platform: string; ok: boolean; error?: string }[]) {
        next[r.platform] = { ok: r.ok, error: r.error };
      }
      setResults((prev) => ({ ...prev, ...next }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPosting(false);
    }
  }

  if (!job.social_captions) return null;

  return (
    <div className="mx-auto mt-6 max-w-md space-y-4 text-left">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Ready to post</h3>
        {connected ? (
          <span className="text-xs text-emerald-400">Blotato connected · {accounts.length} account{accounts.length === 1 ? "" : "s"}</span>
        ) : (
          <span className="text-xs text-white/35">Copy now, or connect Blotato to auto-post</span>
        )}
      </div>

      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">{error}</div>}

      {PLATFORMS.map(({ id, label }) => (
        <div key={id} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">{label}</span>
            <div className="flex items-center gap-2">
              <button onClick={() => copy(id)} className="text-xs text-white/50 hover:text-white">
                {copied === id ? "Copied ✓" : "Copy"}
              </button>
              {connected && (
                <button
                  onClick={() => post([id])}
                  disabled={posting || !connectedPlatforms.has(id)}
                  className="rounded-md bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-black disabled:opacity-40"
                  title={connectedPlatforms.has(id) ? "" : `No ${label} account connected in Blotato`}
                >
                  Post
                </button>
              )}
            </div>
          </div>
          {id === "youtube" && (
            <input
              value={ytTitle}
              onChange={(e) => setYtTitle(e.target.value)}
              maxLength={100}
              placeholder="Title"
              className="mb-2 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-[var(--accent)]/40"
            />
          )}
          <textarea
            value={text[id]}
            onChange={(e) => setText((t) => ({ ...t, [id]: e.target.value }))}
            rows={id === "youtube" ? 5 : 4}
            className="w-full resize-none rounded-lg border border-white/10 bg-black/40 p-2.5 text-sm text-white/85 outline-none focus:border-[var(--accent)]/40"
          />
          {results[id] && (
            <p className={`mt-1.5 text-xs ${results[id].ok ? "text-emerald-400" : "text-red-300"}`}>
              {results[id].ok ? "Posted ✓" : results[id].error}
            </p>
          )}
        </div>
      ))}

      {connected ? (
        <Button className="w-full" disabled={posting} onClick={() => post(PLATFORMS.map((p) => p.id).filter((p) => connectedPlatforms.has(p)))}>
          {posting ? "Posting…" : "Post to all connected"}
        </Button>
      ) : (
        <div className="space-y-2 rounded-xl border border-white/10 p-3">
          <Label>Connect Blotato to auto-post</Label>
          <p className="text-xs text-white/40">
            Paste your Blotato API key (Settings → API in your Blotato dashboard). Blotato handles the TikTok/YouTube/Instagram
            connections — one key posts to all three.
          </p>
          <div className="flex gap-2">
            <input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="password"
              placeholder="blotato-api-key"
              className="flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-[var(--accent)]/40"
            />
            <Button variant="outline" disabled={connecting || apiKey.length < 10} onClick={connect}>
              {connecting ? "…" : "Connect"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
