"""Pure interval / timeline math shared by cleaning and synthesis.

Frame-snapping + overlap-merging + invert-to-keep are exactly the operations the
research flagged as crash-prone if done sloppily (overlapping trims crash ffmpeg;
unsnapped cuts accumulate A/V drift). Keeping them here, pure and tested, means
both the cleaning and synthesis renderers share one correct implementation.
"""

from __future__ import annotations

from cadence.models import TimeRange


def frame_snap(t: float, fps: float) -> float:
    """Snap a time to the nearest frame boundary so cuts land cleanly."""
    if fps <= 0:
        return t
    return round(t * fps) / fps


def clamp_range(r: TimeRange, lo: float, hi: float) -> TimeRange | None:
    start = max(lo, min(r.start, hi))
    end = max(lo, min(r.end, hi))
    if end - start <= 1e-6:
        return None
    return TimeRange(start, end)


def merge_spans(spans: list[TimeRange], *, gap: float = 0.0) -> list[TimeRange]:
    """Sort and union overlapping/adjacent spans (within ``gap`` seconds)."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda r: r.start)
    merged = [ordered[0]]
    for r in ordered[1:]:
        last = merged[-1]
        if r.start <= last.end + gap:
            if r.end > last.end:
                merged[-1] = TimeRange(last.start, r.end)
        else:
            merged.append(r)
    return merged


def invert_to_keep(removed: list[TimeRange], duration: float) -> list[TimeRange]:
    """Complement of ``removed`` within ``[0, duration]`` -> the KEEP ranges."""
    keep: list[TimeRange] = []
    cursor = 0.0
    for r in merge_spans(removed):
        if r.start > cursor + 1e-6:
            keep.append(TimeRange(cursor, min(r.start, duration)))
        cursor = max(cursor, r.end)
        if cursor >= duration:
            break
    if cursor < duration - 1e-6:
        keep.append(TimeRange(cursor, duration))
    return [r for r in keep if r.duration > 1e-6]


def snap_ranges(ranges: list[TimeRange], fps: float) -> list[TimeRange]:
    out: list[TimeRange] = []
    for r in ranges:
        s, e = frame_snap(r.start, fps), frame_snap(r.end, fps)
        if e - s > 1e-6:
            out.append(TimeRange(s, e))
    return out


def total_duration(ranges: list[TimeRange]) -> float:
    return sum(r.duration for r in ranges)
