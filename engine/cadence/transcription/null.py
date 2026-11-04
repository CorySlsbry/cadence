"""Deterministic transcribers: a pre-supplied transcript, or one loaded from JSON.

These make the entire cleaning pipeline testable and usable WITHOUT any ML model:
a caller who already has a transcript (or word-timed JSON exported elsewhere) can
drive the engine end-to-end.
"""

from __future__ import annotations

import json

from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Transcript


class InjectedTranscriber:
    """Returns a fixed transcript regardless of input. For tests / known scripts."""

    def __init__(self, transcript: Transcript) -> None:
        self._transcript = transcript

    def transcribe(self, path: str, *, ff: FFmpeg | None = None) -> Transcript:
        return self._transcript


class JsonFileTranscriber:
    """Loads a :class:`Transcript` from a JSON file in the engine's own schema."""

    def __init__(self, json_path: str) -> None:
        self._json_path = json_path

    def transcribe(self, path: str, *, ff: FFmpeg | None = None) -> Transcript:
        with open(self._json_path, encoding="utf-8") as fh:
            return Transcript.from_dict(json.load(fh))
