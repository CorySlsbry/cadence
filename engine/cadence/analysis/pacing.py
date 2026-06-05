"""Module A.4 — pacing / rhythm fingerprint.

The pacing fingerprint is what lets synthesis "match the reference's feel": the
sequence of shot durations + speaking rate. Pure functions over the already-
detected transitions and (optional) transcript.
"""

from __future__ import annotations

import numpy as np

from cadence.models import PacingProfile, Transition, Transcript


def compute_pacing(
    transitions: tuple[Transition, ...],
    duration: float,
    transcript: Transcript | None = None,
) -> PacingProfile:
    cut_times = sorted(t.timestamp for t in transitions if 0.0 < t.timestamp < duration)
    boundaries = [0.0, *cut_times, duration] if duration > 0 else [0.0]
    seg_lengths = np.diff(boundaries) if len(boundaries) > 1 else np.array([duration])

    avg_segment = float(seg_lengths.mean()) if seg_lengths.size else duration
    cut_density = (len(cut_times) / duration * 60.0) if duration > 0 else 0.0
    beat = float(np.median(seg_lengths)) if seg_lengths.size else avg_segment

    if transcript and transcript.words and duration > 0:
        wpm = len(transcript.words) / duration * 60.0
    else:
        wpm = 0.0

    return PacingProfile(
        words_per_minute=round(wpm, 2),
        avg_segment_sec=round(avg_segment, 3),
        cut_density_per_min=round(cut_density, 3),
        beat_interval_sec=round(beat, 3),
        segment_boundaries=tuple(round(b, 3) for b in boundaries),
    )
