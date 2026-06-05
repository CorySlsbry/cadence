"""Transcription adapters (ports-and-adapters). The cleaning algorithms depend
only on the :class:`Transcript` data type, never on a concrete backend."""

from __future__ import annotations

from cadence.transcription.base import Transcriber
from cadence.transcription.null import InjectedTranscriber, JsonFileTranscriber

__all__ = ["Transcriber", "InjectedTranscriber", "JsonFileTranscriber"]
