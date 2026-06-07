"""Robust Gemini JSON call — tolerant parse + bounded retry.

gemini-2.5-flash in JSON mode still, in production, occasionally (a) wraps the object in
```json fences or emits a trailing comma, or (b) returns ``503 UNAVAILABLE`` / ``429`` under
load. Either one used to make a creator feature silently fall back to its deterministic stub
(observed live: ``find_clip_moments`` died on a trailing comma → 0 clips; ``build_repurpose``
died on a 503). This centralizes a lenient parse + a short backoff retry so a transient blip
never costs the real output. Shared by every JSON-mode caller (hooks, repurpose, multi-clip,
captions, b-roll distill).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_RETRYABLE_MARKERS = (
    "503", "unavailable", "429", "resource_exhausted", "overloaded",
    "high demand", "500", "internal", "deadline", "timeout", "try again",
)
# A model becoming uncallable (404/deprecated/unsupported) should fall over to the next
# model, not abort the whole chain (and not retry — it won't come back).
_UNAVAILABLE_MARKERS = ("404", "not_found", "not found", "not supported", "does not exist")
# When the primary model is overloaded (e.g. gemini-2.5-pro/flash 503 under load), fall over to
# less-loaded models rather than degrade the feature to its stub. Quality-FIRST order so a premium
# (pro) task degrades to a strong model, never straight to lite. Every entry is verified callable
# in JSON mode on the production key; they span backends/generations so a simultaneous outage is
# effectively impossible. (gemini-2.5-pro itself falls over to gemini-2.5-flash here.)
_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-3.5-flash", "gemini-2.5-flash-lite")

# Per-task model selection — premium app: the BEST model for each task, not the biggest everywhere.
# Judgment + highest-leverage creative get the flagship; bulk/formulaic get a strong fast model;
# trivial transforms stay cheap. Env-overridable. All fall over via gemini_json() under load.
MODEL_CLIPS = os.environ.get("CADENCE_MODEL_CLIPS", "gemini-2.5-pro")           # viral-moment judgment
MODEL_HOOKS = os.environ.get("CADENCE_MODEL_HOOKS", "gemini-2.5-pro")           # first-3s creative (highest leverage)
MODEL_REPURPOSE = os.environ.get("CADENCE_MODEL_REPURPOSE", "gemini-3.5-flash")  # bulk multi-format creative
MODEL_CAPTIONS = os.environ.get("CADENCE_MODEL_CAPTIONS", "gemini-3.5-flash")    # per-platform copy
MODEL_DISTILL = os.environ.get("CADENCE_MODEL_DISTILL", "gemini-2.5-flash")      # snippet → b-roll scene prompt (trivial)


def lenient_json_loads(text: str | None) -> dict[str, Any]:
    """Parse a Gemini JSON reply, tolerating code fences + trailing commas. Returns a dict
    (a non-dict top-level becomes ``{}``). Raises ``ValueError`` on empty/unparseable input
    so the caller can retry."""
    if not text or not text.strip():
        raise ValueError("empty Gemini response")
    s = _FENCE.sub("", text.strip())
    for candidate in (s, _TRAILING_COMMA.sub(r"\1", s)):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            continue
    block = re.search(r"\{.*\}", s, re.DOTALL)  # last resort: the outermost object
    if block:
        try:
            data = json.loads(_TRAILING_COMMA.sub(r"\1", block.group(0)))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    raise ValueError("unparseable Gemini JSON")


def is_retryable(exc: Exception) -> bool:
    """Transient API errors (5xx/429/overloaded) and empty/garbled JSON are worth one more
    shot; a deterministic error (bad request, auth) is not."""
    if isinstance(exc, ValueError):  # our own empty/unparseable signal — non-deterministic
        return True
    return any(m in str(exc).lower() for m in _RETRYABLE_MARKERS)


def is_model_unavailable(exc: Exception) -> bool:
    """A model that is 404/deprecated/unsupported — fall over to the next model (no retry)."""
    return any(m in str(exc).lower() for m in _UNAVAILABLE_MARKERS)


def gemini_json(client, model: str, prompt: str, *, temperature: float = 0.7,
                attempts: int = 2, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """``generate_content`` in JSON mode → dict. For each model: lenient parse + bounded
    backoff retry on transient (5xx/429/overloaded) errors and empty/garbled replies; once a
    model's retries are exhausted on a *transient* error, fall over to the next model. A
    deterministic error (bad request/auth) raises immediately (no retry, no fallback)."""
    from google.genai import types

    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=temperature)
    models = [model, *[m for m in _FALLBACK_MODELS if m != model]]
    last: Exception | None = None
    for mdl in models:
        for i in range(attempts):
            try:
                resp = client.models.generate_content(model=mdl, contents=[prompt], config=config)
                return lenient_json_loads(resp.text)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if is_retryable(exc):
                    if i + 1 < attempts:
                        sleep(min(8.0, 2.0 ** i))
                        continue
                    break  # retries exhausted on a transient error → next model
                if is_model_unavailable(exc):
                    break  # this model is 404/deprecated → next model (don't retry)
                raise  # deterministic + model-independent (bad request/auth) → bail
        # fell through this model → try the next one
    raise last  # pragma: no cover - the loop always returns or raises
