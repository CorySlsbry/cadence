"""Free, deterministic placeholder generator.

Renders a tasteful gradient card with the topic text so the entire AI-b-roll
pipeline is fully testable and demoable at $0 — and swapping in a real provider
is a one-line config change.
"""

from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageDraw

from cadence.imagegen.base import GenResult

_ASPECTS = {"9x16": (1080, 1920), "16x9": (1920, 1080), "1x1": (1080, 1080)}


def _seeded_color(text: str, lo: int = 30, hi: int = 200) -> tuple[int, int, int]:
    h = hashlib.sha256(text.encode()).digest()
    span = hi - lo
    return (lo + h[0] % span, lo + h[1] % span, lo + h[2] % span)


class StubGenerator:
    name = "stub"
    cost_per_image = 0.0

    def generate(self, prompt, *, aspect="9x16", style_refs=None, seed=None) -> GenResult:
        w, h = _ASPECTS.get(aspect, (1080, 1920))
        top = _seeded_color(prompt)
        bot = _seeded_color(prompt[::-1])
        img = Image.new("RGB", (w, h))
        px = img.load()
        for y in range(h):  # vertical gradient
            t = y / h
            row = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
            for x in range(w):
                px[x, y] = row
        draw = ImageDraw.Draw(img)
        label = (prompt[:60] + "…") if len(prompt) > 60 else prompt
        draw.rectangle([60, h // 2 - 80, w - 60, h // 2 + 80], fill=(0, 0, 0, 180))
        draw.text((90, h // 2 - 20), f"[stub] {label}", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return GenResult(image_bytes=buf.getvalue(), prompt=prompt, cost_usd=0.0, provider="stub", seed=seed)
