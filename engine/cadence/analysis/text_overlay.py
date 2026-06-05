"""Module A.3 — text-overlay region + typography mapping.

Short-form captions are high-frequency (sharp edges), spatially blocky, and
temporally stable — they pop in, hold for a beat, pop out. We exploit exactly
that: per-frame edge-density banding locates caption *regions* and their vertical
zone, and temporal persistence yields precise display start/end durations. This
needs no OCR and is sufficient for synthesis (we re-author captions from the
cleaned transcript). Reading the reference's literal *words* is an optional
enrichment behind the :class:`OcrBackend` port.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from cadence.analysis.frames import iter_frames
from cadence.config import AnalyzerConfig
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import BBox, RGBColor, TextOverlayEvent, TextZone


class OcrBackend(Protocol):
    """Optional: extract literal text + dominant colour from a cropped region."""

    def read(self, crop: np.ndarray) -> tuple[str | None, RGBColor | None]: ...


# --------------------------------------------------------------------------- #
# Edge banding (pure)
# --------------------------------------------------------------------------- #
def edge_density_grid(frame: np.ndarray, rows: int, cols: int, *, edge_mag: float = 36.0) -> np.ndarray:
    """Fraction of strong-edge pixels per ``rows``x``cols`` cell (0..1)."""
    gray = frame.astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    gx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    gy = np.abs(np.diff(gray, axis=0, append=gray[-1:, :]))
    mag = gx + gy
    edges = (mag > edge_mag).astype(np.float64)

    h, w = edges.shape
    ch, cw = h // rows, w // cols
    if ch == 0 or cw == 0:
        return np.zeros((rows, cols))
    edges = edges[: ch * rows, : cw * cols]
    grid = edges.reshape(rows, ch, cols, cw).mean(axis=(1, 3))
    return grid


def active_row_spans(row_density: np.ndarray, threshold: float) -> list[tuple[int, int]]:
    """Contiguous spans ``[start, end)`` of rows whose density exceeds threshold."""
    active = row_density > threshold
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(active)))
    return spans


def _frame_bands(grid: np.ndarray, threshold: float, *, min_cells: int = 2) -> list[BBox]:
    """Locate caption bands in one edge grid as normalized bounding boxes.

    Detection is CELL-level, not row-mean: a caption is a localized cluster of
    high-edge cells, so averaging a high-density caption across the full row width
    (where most cells are flat background) would wash the signal out. A row counts
    as active when it contains at least one above-threshold cell; ``min_cells``
    suppresses single-cell speckle.
    """
    rows, cols = grid.shape
    active = grid > threshold                       # (rows, cols) bool
    row_active = active.any(axis=1).astype(np.float64)
    bands: list[BBox] = []
    for r0, r1 in active_row_spans(row_active, 0.5):
        block = active[r0:r1]
        if int(block.sum()) < min_cells:
            continue
        active_cols = np.where(block.any(axis=0))[0]
        c0, c1 = int(active_cols.min()), int(active_cols.max()) + 1
        bands.append(BBox(x=c0 / cols, y=r0 / rows, w=(c1 - c0) / cols, h=(r1 - r0) / rows))
    return bands


def _y_overlap(a: BBox, b: BBox) -> float:
    top = max(a.y, b.y)
    bot = min(a.y + a.h, b.y + b.h)
    inter = max(0.0, bot - top)
    union = max(a.y + a.h, b.y + b.h) - min(a.y, b.y)
    return inter / union if union > 0 else 0.0


def group_bands_to_events(
    per_frame: list[tuple[float, list[BBox]]],
    *,
    min_duration: float,
    sample_dt: float,
    y_overlap_thresh: float = 0.3,
) -> list[TextOverlayEvent]:
    """Track bands across frames into persistent overlay events.

    ``per_frame`` is ``[(timestamp, [bands]), ...]`` in time order.
    """
    open_tracks: list[dict] = []  # {bbox, start, last_t}
    done: list[dict] = []
    gap_tol = sample_dt * 2.5

    for t, bands in per_frame:
        matched = [False] * len(open_tracks)
        used = [False] * len(bands)
        for ti, track in enumerate(open_tracks):
            best, best_ov = -1, y_overlap_thresh
            for bi, band in enumerate(bands):
                if used[bi]:
                    continue
                ov = _y_overlap(track["bbox"], band)
                if ov >= best_ov:
                    best, best_ov = bi, ov
            if best >= 0:
                used[best] = True
                matched[ti] = True
                track["last_t"] = t
                track["bbox"] = bands[best]  # follow drift
        # Close stale tracks.
        still_open = []
        for ti, track in enumerate(open_tracks):
            if matched[ti] or (t - track["last_t"]) <= gap_tol:
                still_open.append(track)
            else:
                done.append(track)
        open_tracks = still_open
        # Open new tracks for unmatched bands.
        for bi, band in enumerate(bands):
            if not used[bi]:
                open_tracks.append({"bbox": band, "start": t, "last_t": t})
    done.extend(open_tracks)

    events: list[TextOverlayEvent] = []
    for track in done:
        duration = track["last_t"] - track["start"] + sample_dt
        if duration + 1e-9 < min_duration:
            continue
        bbox = track["bbox"]
        events.append(
            TextOverlayEvent(
                start=round(track["start"], 3),
                end=round(track["start"] + duration, 3),
                bbox=bbox,
                zone=TextZone.from_y(bbox.cy),
            )
        )
    events.sort(key=lambda e: e.start)
    return events


def detect_text_overlays(
    path: str,
    *,
    cfg: AnalyzerConfig | None = None,
    ff: FFmpeg | None = None,
    sample_fps: float = 5.0,
    rows: int = 18,
    cols: int = 12,
    width: int = 216,
    height: int = 384,
) -> tuple[TextOverlayEvent, ...]:
    cfg = cfg or AnalyzerConfig()
    ff = ff or FFmpeg()
    sample_dt = 1.0 / sample_fps
    per_frame: list[tuple[float, list[BBox]]] = []
    idx = 0
    for frame in iter_frames(path, fps=sample_fps, width=width, height=height, ff=ff):
        grid = edge_density_grid(frame, rows, cols)
        bands = _frame_bands(grid, cfg.text_edge_threshold)
        per_frame.append((idx * sample_dt, bands))
        idx += 1
    events = group_bands_to_events(
        per_frame, min_duration=cfg.text_min_duration_sec, sample_dt=sample_dt
    )
    return tuple(events)
