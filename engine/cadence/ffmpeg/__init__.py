"""Thin, well-tested wrappers around the ffmpeg / ffprobe binaries."""

from __future__ import annotations

from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg

__all__ = ["FFmpeg", "probe_media"]
