"use client";

import { useEffect } from "react";

/**
 * Captures an affiliate referral code from the landing URL (?ref=CODE) into localStorage.
 * It's claimed onto the new user's profile at signup (see auth-form). Render once on the
 * public landing page.
 */
export function RefCapture() {
  useEffect(() => {
    try {
      const code = new URLSearchParams(window.location.search).get("ref");
      if (code) localStorage.setItem("ch_ref", code);
    } catch {
      /* ignore (private mode / storage disabled) */
    }
  }, []);
  return null;
}
