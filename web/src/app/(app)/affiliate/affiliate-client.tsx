"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export function JoinButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function join() {
    setBusy(true);
    setErr(null);
    const { error } = await createClient().rpc("become_affiliate");
    setBusy(false);
    if (error) setErr(error.message);
    else router.refresh();
  }

  return (
    <div>
      <button
        onClick={join}
        disabled={busy}
        className="press mt-8 rounded-xl bg-[var(--accent)] px-6 py-3 text-sm font-bold text-black transition-[filter] hover:brightness-95 disabled:opacity-60"
      >
        {busy ? "…" : "Become an affiliate"}
      </button>
      {err && <p className="mt-3 text-sm text-red-400">{err}</p>}
    </div>
  );
}

/** The share link: customizable handle + one-tap copy for both formats. */
export function LinkCard({ code }: { code: string }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(code);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const pretty = `clouthook.com/r/${code}`;
  const classic = `clouthook.com/?ref=${code}`;

  async function save() {
    const next = draft.toLowerCase().trim();
    if (next === code) {
      setEditing(false);
      return;
    }
    setBusy(true);
    setErr(null);
    const { data, error } = await createClient().rpc("set_affiliate_code", { p_code: next });
    setBusy(false);
    const res = data as { ok?: boolean; error?: string } | null;
    if (error || !res?.ok) {
      setErr(error?.message || res?.error || "Couldn't update the link.");
      return;
    }
    setEditing(false);
    router.refresh();
  }

  async function copy(key: string, value: string) {
    await navigator.clipboard.writeText(`https://${value}`);
    setCopied(key);
    setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500);
  }

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs uppercase tracking-wide text-white/40">Your link</div>
        {!editing ? (
          <button onClick={() => { setDraft(code); setEditing(true); setErr(null); }} className="press text-xs font-medium text-[var(--accent)] hover:opacity-80">
            Customize
          </button>
        ) : (
          <button onClick={() => setEditing(false)} className="press text-xs text-white/40 hover:text-white/70">
            Cancel
          </button>
        )}
      </div>

      {editing ? (
        <div className="mt-3">
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-sm text-white/45">clouthook.com/r/</span>
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && save()}
              maxLength={20}
              placeholder="yourname"
              className="w-44 rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none transition-colors focus:border-[var(--accent)]"
            />
            <button
              onClick={save}
              disabled={busy}
              className="press rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-black transition-[filter] hover:brightness-95 disabled:opacity-60"
            >
              {busy ? "…" : "Save"}
            </button>
          </div>
          <p className="mt-2 text-xs text-white/35">3–20 characters: letters, numbers, dashes. Changing it retires the old link.</p>
          {err && <p className="mt-2 text-sm text-red-400">{err}</p>}
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          {[
            { key: "pretty", label: "Say it on camera", value: pretty },
            { key: "classic", label: "For bios & descriptions", value: classic },
          ].map((l) => (
            <div key={l.key} className="flex items-center gap-2">
              <span className="w-40 shrink-0 text-xs text-white/40">{l.label}</span>
              <code className="flex-1 truncate rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white/85">{l.value}</code>
              <button
                onClick={() => copy(l.key, l.value)}
                className="press shrink-0 rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-black transition-[filter] hover:brightness-95"
              >
                {copied === l.key ? "Copied" : "Copy"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Stripe Connect Express onboarding entry point. */
export function PayoutSetupButton({ label }: { label: string }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/affiliate/connect", { method: "POST" });
      const j = (await r.json()) as { url?: string; error?: string };
      if (!r.ok || !j.url) throw new Error(j.error || "Couldn't start payout setup.");
      window.location.href = j.url;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't start payout setup.");
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        onClick={start}
        disabled={busy}
        className="press rounded-xl bg-[var(--accent)] px-5 py-2.5 text-sm font-bold text-black transition-[filter] hover:brightness-95 disabled:opacity-60"
      >
        {busy ? "Opening Stripe…" : label}
      </button>
      {err && <p className="mt-2 text-sm text-red-400">{err}</p>}
    </div>
  );
}
