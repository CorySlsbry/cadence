"""§3 Module C.2 — silence / dead-space detection from the audio waveform.

Windowed RMS -> dBFS, threshold, then group sustained sub-threshold windows. Pure
numpy over a mono float array in [-1, 1], so it is testable with synthetic signals.
"""

from __future__ import annotations

import numpy as np

from cadence.models import TimeRange

_EPS = 1e-10


def windowed_dbfs(audio: np.ndarray, sample_rate: int, window_sec: float = 0.02) -> tuple[np.ndarray, float]:
    """Return ``(dbfs_per_window, window_sec)`` for non-overlapping RMS windows.

    Full-scale (RMS 1.0) maps to 0 dBFS; digital silence to a large negative floor.
    """
    if audio.size == 0:
        return np.zeros(0), window_sec
    win = max(1, int(round(window_sec * sample_rate)))
    n_full = audio.size // win
    if n_full == 0:
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        return np.array([20.0 * np.log10(rms + _EPS)]), audio.size / sample_rate
    trimmed = audio[: n_full * win].astype(np.float64).reshape(n_full, win)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1))
    dbfs = 20.0 * np.log10(rms + _EPS)
    return dbfs, win / sample_rate


def detect_silence_ranges(
    audio: np.ndarray,
    sample_rate: int,
    *,
    silence_db: float = -40.0,
    min_silence_sec: float = 0.30,
    window_sec: float = 0.02,
) -> list[TimeRange]:
    """Spans where the signal stays below ``silence_db`` for >= ``min_silence_sec``."""
    dbfs, actual_win = windowed_dbfs(audio, sample_rate, window_sec)
    if dbfs.size == 0:
        return []
    silent = dbfs < silence_db
    ranges: list[TimeRange] = []
    start: int | None = None
    for i, s in enumerate(silent):
        if s and start is None:
            start = i
        elif not s and start is not None:
            ranges.append((start, i))
            start = None
    if start is not None:
        ranges.append((start, len(silent)))

    out: list[TimeRange] = []
    for a, b in ranges:
        t0, t1 = a * actual_win, b * actual_win
        if t1 - t0 + 1e-9 >= min_silence_sec:
            out.append(TimeRange(round(t0, 3), round(t1, 3)))
    return out


def word_gap_silence_ranges(
    word_bounds: list[tuple[float, float]],
    *,
    min_gap_sec: float = 0.5,
) -> list[TimeRange]:
    """Silences inferred from gaps between consecutive transcript words."""
    out: list[TimeRange] = []
    for (s0, e0), (s1, e1) in zip(word_bounds, word_bounds[1:]):
        if s1 - e0 > min_gap_sec:
            out.append(TimeRange(round(e0, 3), round(s1, 3)))
    return out
