"use client";

import { useEffect } from "react";

/**
 * Adds `.in` to every `.reveal` element as it scrolls into view (one-shot per element),
 * driving the fade/translate transition defined in globals.css. Render once near the top
 * of the page; it scans the whole document.
 *
 * Honours prefers-reduced-motion: when set, every `.reveal` is revealed immediately and
 * no observer is created (the CSS block also removes the transition as a belt-and-braces).
 */
export function RevealOnScroll() {
  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>(".reveal"));
    if (nodes.length === 0) return;

    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduce || typeof IntersectionObserver === "undefined") {
      nodes.forEach((n) => n.classList.add("in"));
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.12 },
    );

    nodes.forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, []);

  return null;
}
