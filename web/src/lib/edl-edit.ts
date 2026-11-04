// Pure helpers for the "fix cuts & re-render" flow: turn a persisted EDL into editable
// segments, and rebuild an EDL keeping only the chosen ones. No I/O — easy to reason about.

import type { ProjectEdl } from "@/lib/types";

export type EdlSegment = { index: number; start: number; end: number; text: string };

/** One editable segment per kept span, with the transcript words that fall inside it. */
export function segmentsFromEdl(edl: ProjectEdl | null): EdlSegment[] {
  if (!edl?.kept) return [];
  const words = edl.transcript?.words ?? [];
  return edl.kept.map((r, i) => ({
    index: i,
    start: r.start,
    end: r.end,
    text: words
      .filter((w) => w.start >= r.start - 0.05 && w.end <= r.end + 0.05)
      .map((w) => w.text)
      .join(" ")
      .trim(),
  }));
}

/** A new EDL keeping only the spans whose index is in `keepIndices` (preserving order). */
export function edlWithKept(edl: ProjectEdl, keepIndices: number[]): ProjectEdl {
  const keep = new Set(keepIndices);
  return { ...edl, kept: edl.kept.filter((_, i) => keep.has(i)) };
}

export function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}
