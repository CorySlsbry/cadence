"use client";

import { useState } from "react";

/**
 * Starts Stripe checkout for a paid plan. Logged-in users go straight to the hosted
 * checkout; logged-out users are sent to signup with the plan preserved.
 */
export function UpgradeButton({
  plan,
  className,
  children,
}: {
  plan: "base" | "creator";
  className?: string;
  children: React.ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan }),
      });
      if (res.status === 401) {
        window.location.href = `/signup?plan=${plan}`;
        return;
      }
      const data = (await res.json()) as { url?: string; error?: string };
      if (data.url) {
        window.location.href = data.url;
        return;
      }
      setError(data.error ?? "Could not start checkout");
      setBusy(false);
    } catch {
      setError("Could not start checkout");
      setBusy(false);
    }
  }

  return (
    <button onClick={go} disabled={busy} className={className} aria-busy={busy}>
      {busy ? "Redirecting…" : children}
      {error && <span className="mt-1 block text-xs font-normal text-red-400">{error}</span>}
    </button>
  );
}
