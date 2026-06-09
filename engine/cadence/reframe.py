"""Face/subject-aware 16:9 → 9:16 reframe.

When a source is landscape, naive center-crop to 9:16 can slice the speaker off the
edge. This finds the speaker's horizontal center so the crop tracks them instead.

The pure helpers (`crop_filter`, `aggregate_center`) are unit-tested directly; the
MediaPipe + ffmpeg frame sampling in `subject_center_x` is injectable so tests never
need the heavy deps. Detection is entirely best-effort: any failure → None → the
renderer falls back to the original center crop, so reframe can never break a render.
"""

from __future__ import annotations

import subprocess
from typing import Callable

from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg


def crop_filter(width: int, height: int, crop_x: float | None) -> str:
    """The ffmpeg ``crop`` filter for the 9:16 frame.

    ``crop_x`` is the subject's normalized horizontal center (0..1) in the *scaled*
    frame; ``None`` → centered crop (the original behavior). ``clip(...)`` keeps the
    window on-frame; commas are escaped for use inside a filter_complex graph.
    """
    if crop_x is None:
        return f"crop={width}:{height}"
    cx = min(1.0, max(0.0, crop_x))
    return f"crop={width}:{height}:x='clip(iw*{cx:.4f}-{width}/2\\,0\\,iw-{width})':y=0"


def aggregate_center(centers: list[float | None]) -> float | None:
    """Median of the per-frame face centers, clamped to [0,1]. ``None`` if no faces
    were found (median is robust to a few stray/false detections)."""
    xs = sorted(c for c in centers if c is not None)
    if not xs:
        return None
    n = len(xs)
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    return min(1.0, max(0.0, med))


def _box_area(det) -> float:
    b = det.location_data.relative_bounding_box
    return max(0.0, b.width) * max(0.0, b.height)


def _sample_face_centers(src: str, ff: FFmpeg, *, samples: int, sample_w: int) -> list[float | None]:
    """Read ~``samples`` evenly-spaced downscaled RGB frames and return each frame's
    largest-face normalized x-center (``None`` when no face). Best-effort: [] on any error."""
    try:
        import numpy as np
        import mediapipe as mp

        info = probe_media(src, ff)
        dur = max(info.duration, 0.1)
        fps = max(samples / dur, 0.1)  # ~`samples` frames spread across the clip
        sample_h = max(2, int(round(sample_w * info.height / max(info.width, 1))) // 2 * 2)
        proc = subprocess.Popen(
            [ff.ffmpeg_bin, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", src,
             "-vf", f"fps={fps:.4f},scale={sample_w}:{sample_h}", "-frames:v", str(samples),
             "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        assert proc.stdout is not None
        fsize = sample_w * sample_h * 3
        centers: list[float | None] = []
        detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.5
        )
        try:
            while len(centers) < samples:
                buf = proc.stdout.read(fsize)
                if not buf or len(buf) < fsize:
                    break
                frame = np.frombuffer(buf, dtype=np.uint8).reshape(sample_h, sample_w, 3)
                res = detector.process(frame)
                if not res.detections:
                    centers.append(None)
                    continue
                best = max(res.detections, key=_box_area)
                box = best.location_data.relative_bounding_box
                centers.append(min(1.0, max(0.0, box.xmin + box.width / 2)))
        finally:
            proc.stdout.close()
            proc.wait()
            detector.close()
        return centers
    except Exception:  # noqa: BLE001 - detection is best-effort; never break a render
        return []


def subject_center_x(
    src: str,
    ff: FFmpeg,
    *,
    samples: int = 12,
    sample_w: int = 360,
    sampler: Callable[[], list[float | None]] | None = None,
    probe: Callable[[str, FFmpeg], object] | None = None,
) -> float | None:
    """Subject's normalized horizontal center for a LANDSCAPE source, else ``None``.

    Portrait/square needs no horizontal reframe (returns None); ``None`` is also
    returned when no face is found, so the caller keeps the centered crop.
    """
    info = (probe or probe_media)(src, ff)
    if info.width <= info.height:  # portrait / square → vertical crop only, never horizontal
        return None
    sample = sampler or (lambda: _sample_face_centers(src, ff, samples=samples, sample_w=sample_w))
    return aggregate_center(sample())


def apply_auto_reframe(plan, ff: FFmpeg) -> None:
    """Set ``crop_x`` on every A-roll clip so landscape sources track the speaker.

    Cached per source (a single speaker's horizontal position is ~stable within one
    source file), so an N-clip plan from one recording costs one detection pass.
    """
    centers: dict[str, float | None] = {}
    for clip in plan.clips:
        if clip.source not in centers:
            centers[clip.source] = subject_center_x(clip.source, ff)
        clip.crop_x = centers[clip.source]
