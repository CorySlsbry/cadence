"""Gemini-text topic distillation: turn a noisy transcript snippet into a clean,
photoreal b-roll scene + a short on-screen caption (fixing ASR errors).

This is what makes the AI b-roll *relevant and legible* instead of word-salad — it
runs on the same Gemini key as Imagen, costs ~nothing (flash text), and is optional
(callers fall back to the lexical topic if it's unavailable).
"""

from __future__ import annotations

import json
import os

from cadence.errors import DependencyError

_SYSTEM = (
    "You are a senior short-form video editor writing B-ROLL directions. "
    "Given a transcript snippet from a talking-head video, output STRICT JSON: "
    '{"scene": "...", "caption": "..."}. '
    "`scene` = a vivid, concrete, PHOTOREAL real-world scene that visually illustrates what the "
    "speaker is talking about (describe subject, setting, lighting, mood — NOT instructions, NOT text). "
    "`caption` = a punchy 2-4 word on-screen label of the core idea. "
    "Silently FIX speech-to-text errors (e.g. 'cloud covert'->'Claude code', 'cloud'->'Claude' in an AI context). "
    "If the snippet is vague, infer the most likely premium B-roll for a tech/creator video."
)


class GeminiDistiller:
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash") -> None:
        try:
            from google import genai  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise DependencyError("google-genai not installed.") from exc
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise DependencyError("GEMINI_API_KEY not set for distillation.")
        from google import genai

        self._client = genai.Client(api_key=key)
        self._genai = genai
        self.model = model

    def distill(self, snippet: str) -> tuple[str, str]:
        """Return ``(scene, caption)``. Falls back to the raw snippet on any failure."""
        from google.genai import types

        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=[f"{_SYSTEM}\n\nSnippet: \"{snippet.strip()}\""],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4),
            )
            data = json.loads(resp.text)
            scene = str(data.get("scene", "")).strip()
            caption = str(data.get("caption", "")).strip()
            if scene:
                return scene, (caption or scene[:32])
        except Exception:  # noqa: BLE001 - degrade gracefully to the raw snippet
            pass
        return snippet[:120], snippet[:32]
