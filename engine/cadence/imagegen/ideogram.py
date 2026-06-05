"""Ideogram v3 adapter — the chosen provider (best in-frame text + good realism).

POST multipart/form-data to https://api.ideogram.ai/v1/ideogram-v3/generate with an
`Api-Key` header. Defaults tuned for premium vertical b-roll: 9x16, REALISTIC style,
QUALITY rendering, MagicPrompt on. Brand images can be passed as style references so
generated b-roll matches the user's look. Every successful call is charged to the
ledger so spend can never exceed the cap.
"""

from __future__ import annotations

import os

from cadence.errors import DependencyError
from cadence.imagegen.base import GenResult
from cadence.imagegen.ledger import CostLedger

_ENDPOINT = "https://api.ideogram.ai/v1/ideogram-v3/generate"


class IdeogramGenerator:
    name = "ideogram"
    cost_per_image = 0.03  # USD, Ideogram 3.0 default rendering

    def __init__(
        self,
        api_key: str | None = None,
        *,
        ledger: CostLedger | None = None,
        rendering_speed: str = "QUALITY",
        style_type: str = "REALISTIC",
        magic_prompt: str = "ON",
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("IDEOGRAM_API_KEY")
        if not self.api_key:
            raise DependencyError(
                "IDEOGRAM_API_KEY not set. Get a key at https://developer.ideogram.ai and "
                "export IDEOGRAM_API_KEY=... (or add it to worker/.env)."
            )
        self.ledger = ledger
        self.rendering_speed = rendering_speed
        self.style_type = style_type
        self.magic_prompt = magic_prompt
        self.timeout = timeout

    def generate(self, prompt, *, aspect="9x16", style_refs=None, seed=None) -> GenResult:
        import httpx

        if self.ledger is not None and not self.ledger.can_spend(self.cost_per_image):
            from cadence.imagegen.ledger import BudgetExceeded

            raise BudgetExceeded(f"AI budget cap reached; cannot generate (need ${self.cost_per_image}).")

        # Multipart form. Text fields use (None, value); style refs are binary files.
        files: list[tuple[str, tuple]] = [
            ("prompt", (None, prompt)),
            ("aspect_ratio", (None, aspect)),
            ("rendering_speed", (None, self.rendering_speed)),
            ("style_type", (None, self.style_type)),
            ("magic_prompt", (None, self.magic_prompt)),
        ]
        if seed is not None:
            files.append(("seed", (None, str(int(seed)))))
        for i, ref in enumerate(style_refs or []):
            with open(ref, "rb") as fh:
                files.append(("style_reference_images", (f"ref{i}.png", fh.read(), "image/png")))

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(_ENDPOINT, headers={"Api-Key": self.api_key}, files=files)
            resp.raise_for_status()
            data = resp.json()["data"]
            if not data:
                raise RuntimeError("Ideogram returned no images")
            entry = data[0]
            img = client.get(entry["url"]).content

        if self.ledger is not None:
            self.ledger.charge(self.cost_per_image)  # only charge on success
        return GenResult(
            image_bytes=img, prompt=prompt, cost_usd=self.cost_per_image,
            provider="ideogram", seed=entry.get("seed"),
        )
