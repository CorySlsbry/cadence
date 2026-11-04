"""Shared Gemini JSON helper for the text-generation creator features (hooks, repurpose).

Captions has its own writer; these newer features share this thin client. Inject a stub
with the same ``.complete(prompt) -> dict`` shape to unit-test without a network call.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from cadence.errors import DependencyError


class JSONLLM(Protocol):
    def complete(self, prompt: str, *, temperature: float = ...) -> dict[str, Any]: ...


class GeminiJSON:
    """gemini-2.5-flash in strict-JSON mode (cheap; ~$0 per call)."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash") -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - optional dep
            raise DependencyError("google-genai not installed.") from exc
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise DependencyError("GEMINI_API_KEY not set.")
        self._client = genai.Client(api_key=key)
        self.model = model

    def complete(self, prompt: str, *, temperature: float = 0.7) -> dict[str, Any]:
        from cadence._gemini import gemini_json

        return gemini_json(self._client, self.model, prompt, temperature=temperature)


def transcript_text(edl_or_transcript) -> str:
    """Join a Transcript's words into plain text (works on an EDL or a Transcript)."""
    tr = getattr(edl_or_transcript, "transcript", edl_or_transcript)
    words = getattr(tr, "words", None) if tr else None
    if not words:
        return ""
    return " ".join(w.text for w in words).strip()
