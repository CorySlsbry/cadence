"""Google Imagen adapter (via the google-genai SDK / Gemini API).

Imagen 4 supports native 9:16 output and top-tier photorealism. Text rendering is
good-but-not-perfect, so pair with the compositor's `overlay_text` for guaranteed
legible captions. Budget-capped via the ledger.
"""

from __future__ import annotations

import os
import time

from cadence.errors import DependencyError
from cadence.imagegen.base import GenResult
from cadence.imagegen.ledger import BudgetExceeded, CostLedger

_ASPECT = {"9x16": "9:16", "16x9": "16:9", "1x1": "1:1", "3x4": "3:4", "4x3": "4:3"}
_COST = {
    "imagen-4.0-fast-generate-001": 0.02,
    "imagen-4.0-generate-001": 0.04,
    "imagen-4.0-ultra-generate-001": 0.06,
}
# The Studio b-roll quality slider maps to these Imagen 4 tiers (cost/quality).
QUALITY_MODELS = {
    "fast": "imagen-4.0-fast-generate-001",
    "standard": "imagen-4.0-generate-001",
    "ultra": "imagen-4.0-ultra-generate-001",
}


class ImagenGenerator:
    name = "imagen"

    def __init__(self, api_key: str | None = None, *, model: str | None = None, ledger: CostLedger | None = None,
                 min_interval: float | None = None, max_retries: int = 4) -> None:
        try:
            from google import genai  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional dep
            raise DependencyError("google-genai not installed. Run: pip install google-genai") from exc
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise DependencyError("GEMINI_API_KEY / GOOGLE_API_KEY not set for Imagen.")
        self.model = model or os.environ.get("CADENCE_IMAGEN_MODEL", "imagen-4.0-generate-001")
        self.cost_per_image = _COST.get(self.model, 0.04)
        self.ledger = ledger
        # Throttle to respect the API rate limit (Imagen is rate-limited per minute).
        self.min_interval = float(os.environ.get("CADENCE_IMAGEN_INTERVAL", "7")) if min_interval is None else min_interval
        self.max_retries = max_retries
        self._genai = genai
        self._last_call = 0.0

    def generate(self, prompt, *, aspect="9x16", style_refs=None, seed=None) -> GenResult:
        if self.ledger is not None and not self.ledger.can_spend(self.cost_per_image):
            raise BudgetExceeded(f"AI budget cap reached (need ${self.cost_per_image}).")
        client = self._genai.Client(api_key=self.api_key)
        cfg = self._genai.types.GenerateImagesConfig(number_of_images=1, aspect_ratio=_ASPECT.get(aspect, "9:16"))

        # Proactive throttle so back-to-back calls don't trip the per-minute limit.
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = client.models.generate_images(model=self.model, prompt=prompt, config=cfg)
                self._last_call = time.monotonic()
                images = getattr(resp, "generated_images", None) or []
                if not images:
                    raise RuntimeError("Imagen returned no images (possibly a safety block).")
                img_bytes = images[0].image.image_bytes
                if self.ledger is not None:
                    self.ledger.charge(self.cost_per_image)
                return GenResult(image_bytes=img_bytes, prompt=prompt, cost_usd=self.cost_per_image, provider="imagen", seed=seed)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "exhausted" in msg.lower():
                    last_err = exc
                    time.sleep(12 * (attempt + 1))  # backoff: 12s, 24s, 36s …
                    continue
                raise
        # Persistent rate-limit → signal a graceful stop (keep b-roll generated so far).
        raise BudgetExceeded(f"Imagen rate-limited (429) after {self.max_retries} retries: {last_err}")
