"""The Transcriber port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Transcript


@runtime_checkable
class Transcriber(Protocol):
    """Anything that turns a media file into a word-timed :class:`Transcript`."""

    def transcribe(self, path: str, *, ff: FFmpeg | None = None) -> Transcript: ...
