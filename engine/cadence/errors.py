"""Typed exception hierarchy for the Cadence engine.

Every failure mode the pipeline can hit is a named subclass of ``CadenceError`` so
callers (CLI, HTTP API, Flutter client) can branch on category and produce a
graceful, actionable message instead of an opaque stack trace. This directly
serves §5 "Error Handling & Resiliency".
"""

from __future__ import annotations


class CadenceError(Exception):
    """Base class for all engine errors."""


class DependencyError(CadenceError):
    """A required external binary or optional package is missing/unusable."""


class FFmpegError(CadenceError):
    """ffmpeg/ffprobe returned a non-zero exit code.

    Carries the failing command and captured stderr so the failure is debuggable
    and can drive an auto-fallback (e.g. hardware -> software encoder).
    """

    def __init__(self, message: str, *, command: list[str] | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.command = command or []
        self.stderr = stderr

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        base = super().__str__()
        tail = self.stderr.strip().splitlines()[-12:]
        if tail:
            return base + "\n--- ffmpeg stderr (tail) ---\n" + "\n".join(tail)
        return base


class InvalidMediaError(CadenceError):
    """The supplied media file is missing, unreadable, or has no usable streams."""


class AnalysisError(CadenceError):
    """Reference analysis could not complete."""


class CleaningError(CadenceError):
    """The audio-cleaning / edit-decision stage failed."""


class TranscriptionError(CadenceError):
    """A transcription backend failed to produce a transcript."""


class BrandBoardError(CadenceError):
    """A brand-board persistence or validation error."""


class PlanError(CadenceError):
    """The generation plan is invalid or could not be built."""


class RenderError(CadenceError):
    """Final synthesis/render failed after all fallbacks were exhausted."""
