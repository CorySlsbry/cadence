"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button, Label } from "@/components/ui";
import type { RenderJob } from "@/lib/types";

type Platform = "tiktok" | "youtube" | "instagram";

const UPLOAD_URL: Record<Platform, string> = {
  tiktok: "https://www.tiktok.com/upload",
  youtube: "https://www.youtube.com/upload",
  instagram: "https://www.instagram.com/",
};
const NATIVE_CAP: Record<Platform, number> = { tiktok: 4000, youtube: 5000, instagram: 2200 };

function joinTags(mentions?: string[], hashtags?: string[]): string {
  return [...(mentions ?? []), ...(hashtags ?? [])].join(" ").trim();
}

export function SocialPanel({ job }: { job: RenderJob }) {
  const supabase = useMemo(() => createClient(), []);
  const caps = job.social_captions ?? {};

  // Native-upload fields, pre-filled per platform's real layout.
  const [tiktok, setTiktok] = useState(
    [caps.tiktok?.caption, joinTags(caps.tiktok?.mentions, caps.tiktok?.hashtags)].filter(Boolean).join("\n\n"),
  );
  const [ytTitle, setYtTitle] = useState(caps.youtube?.title ?? "");
  const [ytDesc, setYtDesc] = useState(
    [caps.youtube?.description, (caps.youtube?.hashtags ?? []).join(" ")].filter(Boolean).join("\n\n"),
  );
  const [ig, setIg] = useState(
    [caps.instagram?.caption, joinTags(caps.instagram?.mentions, caps.instagram?.hashtags)].filter(Boolean).join("\n\n"),
  );
  const igHashtags = (caps.instagram?.hashtags ?? []).join(" ");

  const [copied, setCopied] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<{ accountId: string; platform: string }[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [posting, setPosting] = useState<Platform | "all" | null>(null);
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
  const has = (p: Platform) => accounts.some((a) => a.platform === p);

  async function copy(key: string, value: string) {
    await navigator.clipboard.writeText(value);
    setCopied(key);
    setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500);
  }

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

  function blockFor(p: Platform) {
    if (p === "tiktok") return { caption: tiktok };
    if (p === "instagram") return { caption: ig };
    return { title: ytTitle, description: ytDesc };
  }

  async function post(platforms: Platform[], tag: Platform | "all") {
    setPosting(tag);
    setError(null);
    try {
      const captions = Object.fromEntries(platforms.map((p) => [p, blockFor(p)]));
      const res = await fetch("/api/publish", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jobId: job.id, platforms, captions }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Publish failed");
      const next: Record<string, { ok: boolean; error?: string }> = {};
      for (const r of data.results as { platform: string; ok: boolean; error?: string }[]) next[r.platform] = r;
      setResults((prev) => ({ ...prev, ...next }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPosting(null);
    }
  }

  if (!job.social_captions) return null;

  return (
    <div className="mx-auto mt-6 max-w-md space-y-3 text-left">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Ready to post</h3>
        <span className="text-xs text-white/35">
          {connected ? `Blotato · ${accounts.length} connected` : "Copy & post natively, or connect Blotato"}
        </span>
      </div>
      <p className="text-xs text-white/40">
        Tip: native uploads usually get more reach (trending sounds + the in-app boost). Download the video above, then copy the
        copy below for each platform. Or connect Blotato to post in one click.
      </p>
      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">{error}</div>}

      {/* TikTok */}
      <PlatformCard p="tiktok" label="TikTok" connected={connected} has={has("tiktok")} posting={posting}
        result={results.tiktok} onPost={() => post(["tiktok"], "tiktok")}>
        <Field label="Caption" value={tiktok} onChange={setTiktok} rows={4} cap={NATIVE_CAP.tiktok}
          copyKey="tt-cap" copied={copied} onCopy={() => copy("tt-cap", tiktok)} />
      </PlatformCard>

      {/* YouTube — Title + Description are separate native fields */}
      <PlatformCard p="youtube" label="YouTube Shorts" connected={connected} has={has("youtube")} posting={posting}
        result={results.youtube} onPost={() => post(["youtube"], "youtube")}>
        <Field label="Title" value={ytTitle} onChange={setYtTitle} rows={1} cap={100}
          copyKey="yt-title" copied={copied} onCopy={() => copy("yt-title", ytTitle)} />
        <Field label="Description" value={ytDesc} onChange={setYtDesc} rows={5} cap={NATIVE_CAP.youtube}
          copyKey="yt-desc" copied={copied} onCopy={() => copy("yt-desc", ytDesc)} />
      </PlatformCard>

      {/* Instagram — caption + hashtags-only (for first-comment posting) */}
      <PlatformCard p="instagram" label="Instagram Reels" connected={connected} has={has("instagram")} posting={posting}
        result={results.instagram} onPost={() => post(["instagram"], "instagram")}>
        <Field label="Caption" value={ig} onChange={setIg} rows={4} cap={NATIVE_CAP.instagram}
          copyKey="ig-cap" copied={copied} onCopy={() => copy("ig-cap", ig)} />
        {igHashtags && (
          <button onClick={() => copy("ig-tags", igHashtags)} className="text-xs text-white/45 hover:text-white">
            {copied === "ig-tags" ? "Hashtags copied ✓" : "Copy hashtags only (for first comment)"}
          </button>
        )}
      </PlatformCard>

      {connected ? (
        <Button className="w-full" disabled={posting !== null}
          onClick={() => post((["tiktok", "youtube", "instagram"] as Platform[]).filter(has), "all")}>
          {posting === "all" ? "Posting…" : "Post to all connected"}
        </Button>
      ) : (
        <div className="space-y-2 rounded-xl border border-white/10 p-3">
          <Label>Connect Blotato for one-click posting</Label>
          <p className="text-xs text-white/40">
            Paste your Blotato API key (Blotato dashboard → Settings → API). Blotato owns the TikTok/YouTube/Instagram
            connections — one key posts to all three.
          </p>
          <div className="flex gap-2">
            <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" placeholder="blotato-api-key"
              className="flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-[var(--accent)]/40" />
            <Button variant="outline" disabled={connecting || apiKey.length < 10} onClick={connect}>
              {connecting ? "…" : "Connect"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function PlatformCard({
  p, label, connected, has, posting, result, onPost, children,
}: {
  p: Platform; label: string; connected: boolean; has: boolean; posting: Platform | "all" | null;
  result?: { ok: boolean; error?: string }; onPost: () => void; children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <div className="flex items-center gap-3">
          <a href={UPLOAD_URL[p]} target="_blank" rel="noopener noreferrer" className="text-xs text-white/45 hover:text-white">
            Upload natively ↗
          </a>
          {connected && (
            <button onClick={onPost} disabled={posting !== null || !has}
              className="rounded-md bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-black disabled:opacity-40"
              title={has ? "" : `No ${label} account connected in Blotato`}>
              {posting === p ? "Posting…" : "Post"}
            </button>
          )}
        </div>
      </div>
      <div className="space-y-2">{children}</div>
      {result && (
        <p className={`mt-1.5 text-xs ${result.ok ? "text-emerald-400" : "text-red-300"}`}>
          {result.ok ? "Posted ✓" : result.error}
        </p>
      )}
    </div>
  );
}

function Field({
  label, value, onChange, rows, cap, copyKey, copied, onCopy,
}: {
  label: string; value: string; onChange: (v: string) => void; rows: number; cap: number;
  copyKey: string; copied: string | null; onCopy: () => void;
}) {
  const over = value.length > cap;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-white/45">{label}</span>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] ${over ? "text-red-300" : "text-white/30"}`}>{value.length}/{cap}</span>
          <button onClick={onCopy} className="text-xs font-medium text-[var(--accent)] hover:opacity-80">
            {copied === copyKey ? "Copied ✓" : "Copy"}
          </button>
        </div>
      </div>
      {rows === 1 ? (
        <input value={value} onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-[var(--accent)]/40" />
      ) : (
        <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={rows}
          className="w-full resize-none rounded-lg border border-white/10 bg-black/40 p-2.5 text-sm text-white/85 outline-none focus:border-[var(--accent)]/40" />
      )}
    </div>
  );
}
