"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export function AffiliateActions({ mode, link }: { mode: "join" | "link"; link?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function join() {
    setBusy(true);
    setErr(null);
    const { error } = await createClient().rpc("become_affiliate");
    setBusy(false);
    if (error) setErr(error.message);
    else router.refresh();
  }

  async function copy() {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (mode === "join") {
    return (
      <div>
        <button
          onClick={join}
          disabled={busy}
          className="mt-8 rounded-xl bg-[var(--accent)] px-6 py-3 text-sm font-bold text-black transition hover:brightness-95 disabled:opacity-60"
        >
          {busy ? "…" : "Become an affiliate"}
        </button>
        {err && <p className="mt-3 text-sm text-red-400">{err}</p>}
      </div>
    );
  }

  return (
    <div className="mt-2 flex items-center gap-2">
      <code className="flex-1 truncate rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white/80">{link}</code>
      <button onClick={copy} className="shrink-0 rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-black transition hover:brightness-95">
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
