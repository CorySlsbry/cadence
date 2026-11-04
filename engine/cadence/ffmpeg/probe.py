"""ffprobe-backed media inspection."""

from __future__ import annotations

import json
import os
from fractions import Fraction

from cadence.errors import InvalidMediaError
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import MediaInfo


def _parse_fps(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_media(path: str, ff: FFmpeg | None = None) -> MediaInfo:
    """Return a :class:`MediaInfo` for ``path`` or raise :class:`InvalidMediaError`."""
    if not os.path.isfile(path):
        raise InvalidMediaError(f"media file not found: {path}")
    ff = ff or FFmpeg()
    raw = ff.probe_raw(
        [
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            path,
        ]
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - ffprobe guarantees json
        raise InvalidMediaError(f"could not parse ffprobe output for {path}") from exc

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise InvalidMediaError(f"no video stream in {path}")

    width = int(video.get("width", 0))
    height = int(video.get("height", 0))
    if width <= 0 or height <= 0:
        raise InvalidMediaError(f"invalid video dimensions in {path}: {width}x{height}")

    fps = _parse_fps(video.get("avg_frame_rate")) or _parse_fps(video.get("r_frame_rate"))

    duration = 0.0
    for source in (video.get("duration"), data.get("format", {}).get("duration")):
        try:
            duration = float(source)
            if duration > 0:
                break
        except (TypeError, ValueError):
            continue

    return MediaInfo(
        path=path,
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        has_audio=audio is not None,
        codec=video.get("codec_name", ""),
    )
