"""Face/subject-aware 16:9 → 9:16 reframe.

When a source is landscape, naive center-crop to 9:16 can slice the speaker off the
edge. This finds the speaker's horizontal center so the crop tracks them instead.

The pure helpers (`crop_filter`, `aggregate_center`) are unit-tested directly; the
MediaPipe + ffmpeg frame sampling in `subject_center_x` is injectable so tests never
need the heavy deps. Detection is entirely best-effort: any failure → None → the
renderer falls back to the original center crop, so reframe can never break a render.
"""

from __future__ import annotations

import os
import subprocess
import urllib.request
from typing import Callable

from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg

# MediaPipe Tasks face detector (this build has no legacy mp.solutions API — same
# Tasks pattern the selfie segmenter uses in matte/replace.py).
_FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)


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


def _ensure_face_model() -> str:
    cache = os.path.join(os.path.expanduser("~"), ".cache", "cadence")
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, "blaze_face_short_range.tflite")
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        urllib.request.urlretrieve(_FACE_MODEL_URL, path)
    return path


def _make_face_detector():
    """Tasks-API face detector + the mediapipe module (for mp.Image). Mirrors
    matte/replace.py's segmenter so it works on this no-`solutions` mediapipe build."""
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    opts = vision.FaceDetectorOptions(
        base_options=python.BaseOptions(model_asset_path=_ensure_face_model()),
        running_mode=vision.RunningMode.IMAGE,
        min_detection_confidence=0.5,
    )
    return vision.FaceDetector.create_from_options(opts), mp


def _box_area(det) -> float:
    b = det.bounding_box  # Tasks API: pixel-space BoundingBox(origin_x, origin_y, width, height)
    return max(0.0, b.width) * max(0.0, b.height)


def _sample_face_centers(src: str, ff: FFmpeg, *, samples: int, sample_w: int) -> list[float | None]:
    """Read ~``samples`` evenly-spaced downscaled RGB frames and return each frame's
    largest-face normalized x-center (``None`` when no face). Best-effort: [] on any error."""
    try:
        import numpy as np

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
        detector, mp = _make_face_detector()
        try:
            while len(centers) < samples:
                buf = proc.stdout.read(fsize)
                if not buf or len(buf) < fsize:
                    break
                frame = np.ascontiguousarray(
                    np.frombuffer(buf, dtype=np.uint8).reshape(sample_h, sample_w, 3)
                )
                res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=frame))
                if not res.detections:
                    centers.append(None)
                    continue
                best = max(res.detections, key=_box_area)
                bb = best.bounding_box  # pixels in the sampled frame
                centers.append(min(1.0, max(0.0, (bb.origin_x + bb.width / 2) / float(sample_w))))
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
