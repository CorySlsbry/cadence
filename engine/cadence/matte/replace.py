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
    feather: int = 3,
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


def _box_blur(a: np.ndarray, k: int) -> np.ndarray:
    """Tiny separable box blur (edge feathering) without scipy."""
    k = max(1, int(k))
    kern = np.ones(k) / k
    out = np.apply_along_axis(lambda m: np.convolve(m, kern, mode="same"), 1, a)
    out = np.apply_along_axis(lambda m: np.convolve(m, kern, mode="same"), 0, out)
    return out


def render_background_replaced(
    src: str,
    background_image: str,
    out: str,
    *,
    ff: FFmpeg | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    zoom: float = 1.08,
    crf: int = 19,
    mask_path: str | None = None,
) -> str:
    """Composite the segmented speaker over a Ken-Burns b-roll background, keep audio."""
    ff = ff or FFmpeg()
    info = probe_media(src, ff)
    import tempfile

    mask = mask_path or tempfile.mktemp(suffix="_mask.mp4")
    generate_person_mask(src, mask, ff=ff, width=width, height=height, fps=fps)

    ramp = f"min(t/{max(info.duration, 1.0):.2f}\\,1)"
    factor = f"(1+{zoom - 1.0:.4f}*{ramp})"
    sw = f"trunc(({width}*{factor})/2)*2"
    graph = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setsar=1[fg];"
        f"[1:v]scale={width}:{height},format=gray,fps={fps}[mk];"
        f"[fg][mk]alphamerge[fga];"
        # background = slow Ken-Burns push on the b-roll image
        f"[2:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps},"
        f"scale=w={sw}:h=-2:eval=frame,crop={width}:{height}:(iw-{width})/2:(ih-{height})/2[bg];"
        f"[bg][fga]overlay=0:0:format=auto[outv]"
    )
    has_audio = info.has_audio
    args = [
        "-y", "-i", src, "-i", mask, "-loop", "1", "-t", f"{info.duration:.3f}", "-i", background_image,
        "-filter_complex", graph, "-map", "[outv]",
    ]
    if has_audio:
        args += ["-map", "0:a"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if has_audio:
        args += ["-c:a", "aac", "-b:a", "160k"]
    args += ["-r", str(fps), out]
    ff.run(args, timeout=1800)
    return out
