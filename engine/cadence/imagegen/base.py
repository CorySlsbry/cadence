"""The ImageGenerator port + result type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GenResult:
    image_bytes: bytes      # PNG/JPEG bytes of the generated image
    prompt: str
    cost_usd: float
    provider: str
    seed: int | None = None


@runtime_checkable
class ImageGenerator(Protocol):
    """Anything that turns a text prompt into image bytes."""

    name: str
    cost_per_image: float

    def generate(
        self,
        prompt: str,
        *,
        aspect: str = "9x16",
        style_refs: list[str] | None = None,
        seed: int | None = None,
    ) -> GenResult: ...
