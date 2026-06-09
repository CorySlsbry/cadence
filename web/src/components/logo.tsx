"use client";

import { useId } from "react";

/** CloutHook logo — CH gradient badge + wordmark ("Clout" foreground, "Hook" brand gradient). */
export function Logo({
  size = 26,
  wordmark = true,
  className = "",
}: {
  size?: number;
  wordmark?: boolean;
  className?: string;
}) {
  const rid = useId();
  const gid = `chg-${rid}`;
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg width={size} height={size} viewBox="0 0 100 100" aria-label="CloutHook" role="img" className="shrink-0" style={{ filter: "drop-shadow(0 0 7px rgba(122,108,255,0.5))" }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#5C8CFF" />
            <stop offset="52%" stopColor="#7A6CFF" />
            <stop offset="100%" stopColor="#A06BFF" />
          </linearGradient>
        </defs>
        <rect width="100" height="100" rx="24" fill={`url(#${gid})`} />
        <g fill="#fff">
          <path d="M42.7 64.1 A19 19 0 1 1 42.7 35.9" fill="none" stroke="#fff" strokeWidth="10" strokeLinecap="round" />
          <rect x="56" y="31" width="9" height="38" rx="4.5" />
          <rect x="80" y="31" width="9" height="38" rx="4.5" />
          <rect x="56" y="45" width="33" height="9" rx="4.5" />
        </g>
      </svg>
      {wordmark && (
        <span className="font-extrabold tracking-tight leading-none" style={{ fontSize: size * 0.84 }}>
          <span style={{ color: "var(--foreground)" }}>Clout</span>
          <span className="brand-grad-text">Hook</span>
        </span>
      )}
    </span>
  );
}
