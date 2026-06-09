"""MediaPipe person-mask generation + FFmpeg background composite."""

from __future__ import annotations

import os
import subprocess
import urllib.request

import numpy as np

from cadence.errors import DependencyError, FFmpegError
from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg

_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite"


def _ensure_model() -> str:
    cache = os.path.join(os.path.expanduser("~"), ".cache", "cadence")
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, "selfie_segmenter.tflite")
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        urllib.request.urlretrieve(_MODEL_URL, path)
    return path


def _make_segmenter():
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    opts = vision.ImageSegmenterOptions(
        base_options=python.BaseOptions(model_asset_path=_ensure_model()),
        running_mode=vision.RunningMode.IMAGE,
        output_confidence_masks=True,
        output_category_mask=False,
    )
    return vision.ImageSegmenter.create_from_options(opts)


def generate_person_mask(
    src: str,
    mask_out: str,
    *,
    ff: FFmpeg | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    model_selection: int = 1,
    feather: int = 2,
) -> str:
    """Write a grayscale person-alpha video (white = keep speaker) for ``src``.

    Frames are normalized to WxH, run through MediaPipe Selfie Segmentation, and the
    soft mask is piped straight into an ffmpeg encoder — one streaming pass.
    """
    try:
        import mediapipe as mp
    except ImportError as exc:  # pragma: no cover - optional dep
        raise DependencyError("mediapipe not installed. Run: pip install mediapipe") from exc
    ff = ff or FFmpeg()
    segmenter = _make_segmenter()

    reader = subprocess.Popen(
        [ff.ffmpeg_bin, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", src,
         "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps}",
         "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    writer = subprocess.Popen(
        [ff.ffmpeg_bin, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", mask_out],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    assert reader.stdout is not None and writer.stdin is not None
    fsize = width * height * 3
    try:
        while True:
            buf = reader.stdout.read(fsize)
            if not buf or len(buf) < fsize:
                break
            frame = np.ascontiguousarray(np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3))
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            res = segmenter.segment(mp_img)
            mask = np.asarray(res.confidence_masks[0].numpy_view(), dtype=np.float32)  # HxW 0..1, person
            # Sharpen the soft confidence mask into a crisper alpha edge (kills the soft halo /
            # fringe around the speaker): steepen the 0..1 transition, then a tiny blur for AA.
            mask = np.clip((mask - 0.5) * 3.0 + 0.5, 0.0, 1.0)
            if feather > 1:
                mask = _box_blur(mask, feather)
            writer.stdin.write((np.clip(mask, 0.0, 1.0) * 255).astype(np.uint8).tobytes())
    finally:
        segmenter.close()
        reader.stdout.close()
        writer.stdin.close()
        reader.wait()
        if writer.wait() != 0:
            raise FFmpegError("mask encode failed", command=["ffmpeg", "<mask>"])
    return mask_out


def _box_blur1d(a: np.ndarray, k: int, axis: int) -> np.ndarray:
    """1-D box blur along ``axis`` via cumulative sum — O(n) and numerically equal to
    ``np.convolve(line, np.ones(k)/k, mode="same")`` with zero-padded edges."""
    n = a.shape[axis]
    if k <= 1 or n == 0:
        return a
    am = np.moveaxis(a, axis, -1)
    cs = np.concatenate(
        [np.zeros(am.shape[:-1] + (1,), dtype=np.float64), np.cumsum(am, axis=-1, dtype=np.float64)],
        axis=-1,
    )
    offset = (k - 1) // 2
    idx = np.arange(n)
    lo = np.clip(idx + offset - k + 1, 0, n)
    hi = np.clip(idx + offset + 1, 0, n)
    out = (cs[..., hi] - cs[..., lo]) / k
    return np.moveaxis(out, -1, axis)


def _box_blur(a: np.ndarray, k: int) -> np.ndarray:
    """Separable box blur (matte edge feathering) via O(n) cumsum instead of the old
    O(n*k) ``apply_along_axis(np.convolve)`` — this runs on EVERY matte frame, so the
    cumsum form meaningfully cuts background-replace render time. Equivalent to two
    passes of a 1/k uniform 'same' kernel. No scipy."""
    k = max(1, int(k))
    if k == 1:
        return np.asarray(a, dtype=np.float64)
    out = _box_blur1d(np.asarray(a, dtype=np.float64), k, 1)
    out = _box_blur1d(out, k, 0)
    return out


def _background_segments(inserts, duration: float) -> list[tuple[str, float]]:
    """Tile b-roll images across ``[0, duration)`` so the background is never empty: image
    ``i`` is shown from its own start to the next image's start (the first is clamped back to
    0, the last extended to ``duration``). Pure function — returns ``(image_path, seconds)``."""
    items = sorted(inserts, key=lambda x: x.start)
    segs: list[tuple[str, float]] = []
    for i, ins in enumerate(items):
        seg_start = 0.0 if i == 0 else float(ins.start)
        seg_end = float(items[i + 1].start) if i + 1 < len(items) else float(duration)
        seg_dur = round(seg_end - seg_start, 3)
        if seg_dur > 0.05:
            segs.append((ins.image_path, seg_dur))
    return segs


def build_background_video(
    inserts,
    duration: float,
    out: str,
    *,
    ff: FFmpeg | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    zoom: float = 1.08,
    crf: int = 20,
) -> str:
    """Stitch per-moment AI b-roll images into a full-duration, full-screen background video:
    each image is held for its window with a gentle Ken-Burns push, then concatenated. Used
    by background-replace mode so the matted speaker sits over a *changing* background that
    follows the talking points (vs one static image)."""
    ff = ff or FFmpeg()
    segs = _background_segments(inserts, duration)
    if not segs:
        raise ValueError("build_background_video: no usable segments")
    args: list[str] = ["-y"]
    for path, seg_dur in segs:
        args += ["-loop", "1", "-t", f"{seg_dur:.3f}", "-i", path]
    chains: list[str] = []
    labels: list[str] = []
    for i, (_path, seg_dur) in enumerate(segs):
        ramp = f"min(t/{max(seg_dur, 1.0):.2f}\\,1)"
        factor = f"(1+{zoom - 1.0:.4f}*{ramp})"
        sw = f"trunc(({width}*{factor})/2)*2"
        chains.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps},"
            f"scale=w={sw}:h=-2:eval=frame,crop={width}:{height}:(iw-{width})/2:(ih-{height})/2[v{i}]"
        )
        labels.append(f"[v{i}]")
    graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(segs)}:v=1:a=0[outv]"
    args += [
        "-filter_complex", graph, "-map", "[outv]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-r", str(fps), out,
    ]
    ff.run(args, timeout=1800)
    return out


def render_background_replaced(
    src: str,
    background_image: str | None = None,
    out: str = "out.mp4",
    *,
    ff: FFmpeg | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    zoom: float = 1.08,
    crf: int = 19,
    mask_path: str | None = None,
    background_video: str | None = None,
) -> str:
    """Composite the segmented speaker over a b-roll background, keeping audio. The background
    is either a single still image (a Ken-Burns push) or — when ``background_video`` is given —
    a full-duration video (e.g. a per-moment AI b-roll slideshow) used as-is behind the speaker."""
    if background_video is None and background_image is None:
        raise ValueError("render_background_replaced needs a background_image or background_video")
    ff = ff or FFmpeg()
    info = probe_media(src, ff)
    import tempfile

    mask = mask_path or tempfile.mktemp(suffix="_mask.mp4")
    generate_person_mask(src, mask, ff=ff, width=width, height=height, fps=fps)

    if background_video is not None:
        # The slideshow already covers the full duration + carries its own motion.
        bg_input = ["-i", background_video]
        bg_chain = (
            f"[2:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps}[bg];"
        )
    else:
        ramp = f"min(t/{max(info.duration, 1.0):.2f}\\,1)"
        factor = f"(1+{zoom - 1.0:.4f}*{ramp})"
        sw = f"trunc(({width}*{factor})/2)*2"
        bg_input = ["-loop", "1", "-t", f"{info.duration:.3f}", "-i", background_image]
        bg_chain = (
            f"[2:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps},"
            f"scale=w={sw}:h=-2:eval=frame,crop={width}:{height}:(iw-{width})/2:(ih-{height})/2[bg];"
        )

    graph = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setsar=1[fg];"
        f"[1:v]scale={width}:{height},format=gray,fps={fps}[mk];"
        f"[fg][mk]alphamerge[fga];"
        f"{bg_chain}"
        f"[bg][fga]overlay=0:0:format=auto[outv]"
    )
    has_audio = info.has_audio
    args = ["-y", "-i", src, "-i", mask] + bg_input + ["-filter_complex", graph, "-map", "[outv]"]
    if has_audio:
        args += ["-map", "0:a"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if has_audio:
        args += ["-c:a", "aac", "-b:a", "160k"]
    args += ["-r", str(fps), out]
    ff.run(args, timeout=1800)
    return out
