"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

/**
 * Presentational "command bar" hero card that echoes the studio intake: a glossy dark
 * rounded panel with a faux reference-URL field (cycling placeholder), source chips, and
 * a bright gradient primary CTA. The CTA is a real link to the signup/app route — nothing
 * here actually submits.
 *
 * The cycling placeholder is gated by prefers-reduced-motion (falls back to a static line).
 */

const PROMPTS = [
  "Paste a TikTok or Reels link to match its style…",
  "Drop a viral clip — we map its pacing + captions…",
  "Reference URL → studio-grade vertical cut…",
];

const CHIPS = [
  "Talking head",
  "AI b-roll",
  "Auto-captions",
  "Replace background",
  "Brand kit",
];

export function HeroCommandBar({ href, cta }: { href: string; cta: string }) {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % PROMPTS.length), 3200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="relative mx-auto w-full max-w-2xl">
      {/* gradient halo behind the card */}
      <div
        aria-hidden
        className="absolute -inset-[1px] rounded-[26px] opacity-70 blur-[2px]"
        style={{ background: "var(--brand-grad)" }}
      />
      <div className="relative overflow-hidden rounded-[25px] border border-white/12 bg-[#0e0c1a]/85 p-3 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.9)] backdrop-blur-xl sm:p-4">
        {/* top glossy highlight */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent"
        />

        {/* faux input row */}
        <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/30 p-2 pl-3.5">
          <Sparkles size={18} className="shrink-0 text-[var(--accent)]" aria-hidden />
          <div className="relative h-6 flex-1 overflow-hidden text-left">
            <span
              key={idx}
              className="block truncate text-sm text-white/55 motion-safe:animate-[fadeup_.5s_ease]"
            >
              {PROMPTS[idx]}
            </span>
          </div>
          <Link
            href={href}
            aria-label={cta}
            className="hidden shrink-0 items-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2.5 text-sm font-bold text-black transition hover:brightness-110 sm:inline-flex"
          >
            {cta}
            <ArrowRight size={16} aria-hidden />
          </Link>
        </div>

        {/* source chips */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {CHIPS.map((c) => (
            <span
              key={c}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-white/70"
            >
              {c}
            </span>
          ))}
        </div>

        {/* full-width CTA on phones (≥44px tap target) */}
        <Link
          href={href}
          className="mt-3 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-5 text-sm font-bold text-black transition hover:brightness-110 sm:hidden"
        >
          {cta}
          <ArrowRight size={16} aria-hidden />
        </Link>
      </div>
    </div>
  );
}
