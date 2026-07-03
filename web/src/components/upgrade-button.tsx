"use client";

import { useState } from "react";

/**
 * Opens the on-site checkout for a paid plan. /checkout handles auth (→ signup when logged out),
 * referral attribution, and rendering the branded embedded Stripe form (hosted fallback if the
 * publishable key isn't set yet).
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
  return (
    <button
      onClick={() => {
        setBusy(true);
        window.location.href = `/checkout?plan=${plan}`;
      }}
      disabled={busy}
      className={className}
      aria-busy={busy}
    >
      {busy ? "Loading…" : children}
    </button>
  );
}
