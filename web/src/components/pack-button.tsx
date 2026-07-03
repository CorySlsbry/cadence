"use client";

import { useState } from "react";

/** Opens the on-site checkout for a one-time token pack (branded embedded Stripe form). */
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
  return (
    <button
      onClick={() => {
        setBusy(true);
        window.location.href = `/checkout?pack=${pack}`;
      }}
      disabled={busy}
      className={className}
      aria-busy={busy}
    >
      {busy ? "Loading…" : children}
    </button>
  );
}
