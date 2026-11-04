"""Decorative frame overlay — composite a transparent PNG over the finished video.

The frame scales to the video's exact dimensions, so one 1080x1920 asset serves
every output size. Audio is passed through untouched. Runs as the LAST visual
pass: presets are designed caption-safe (edges/corners only), so captions burned
earlier stay readable.
"""

from __future__ import annotations

import os

from cadence.ffmpeg.runner import FFmpeg


def apply_frame(ff: FFmpeg, video_path: str, frame_png: str, out_path: str,
                *, timeout: float = 900.0) -> str:
    if not os.path.exists(frame_png):
        raise FileNotFoundError(f"frame image not found: {frame_png}")
    ff.run([
        "-i", video_path,
        "-i", frame_png,
        "-filter_complex",
        "[1:v][0:v]scale2ref=w=iw:h=ih[fr][base];[base][fr]overlay=0:0:format=auto",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-y", out_path,
    ], timeout=timeout)
    return out_path
