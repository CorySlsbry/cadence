"use client";

import * as React from "react";
import { useState } from "react";

/**
 * Collapsible section for phone screens. On sm+ it force-opens and the header
 * becomes a static label (chevron hidden), so desktop keeps the full layout.
 * Renders the numbered/check pill + title itself, so the wrapped Card body should
 * drop its own SectionHead.
 */
export function MobileSection({
  n,
  title,
  done = false,
  defaultOpen = false,
  children,
}: {
  n: number;
  title: string;
  done?: boolean;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-14 w-full items-center gap-3 py-3 text-left sm:cursor-default"
      >
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
            done ? "bg-emerald-500/20 text-emerald-300" : "bg-[var(--accent)]/15 text-[var(--accent)]"
          }`}
        >
          {done ? "✓" : n}
        </span>
        <span className="flex-1 text-sm font-semibold">{title}</span>
        <svg
          className={`h-4 w-4 text-white/40 transition-transform sm:hidden ${open ? "rotate-180" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      <div className={`${open ? "block" : "hidden"} sm:block`}>{children}</div>
    </div>
  );
}
