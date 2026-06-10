"use client";

import { useEffect } from "react";

/**
 * Captures an affiliate referral code from the landing URL (?ref=CODE) into BOTH
 * localStorage (read by the signup form for instant attribution) and a 90-day
 * cookie (read server-side by the app layout, which claims it after ANY signup
 * path — email, Google OAuth, magic link). Render once on the public landing page.
 */
export function RefCapture() {
  useEffect(() => {
    try {
      const code = new URLSearchParams(window.location.search).get("ref");
      if (!code) return;
      const clean = code.toLowerCase().trim().slice(0, 24);
      localStorage.setItem("ch_ref", clean);
      document.cookie = `ch_ref=${encodeURIComponent(clean)}; max-age=${60 * 60 * 24 * 90}; path=/; samesite=lax; secure`;
    } catch {
      /* ignore (private mode / storage disabled) */
    }
  }, []);
  return null;
}
