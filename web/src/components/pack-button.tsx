"use client";

import { useState } from "react";

/** Buys a one-time token pack via Stripe Checkout. Logged-out users go to signup. */
export function PackButton({
  pack,
  className,
  children,
}: {
  pack: string;
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
        body: JSON.stringify({ pack }),
      });
      if (res.status === 401) {
        window.location.href = "/signup";
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
