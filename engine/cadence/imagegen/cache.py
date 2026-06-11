"""Asset-library caching layer over any ImageGenerator.

A library hit returns the stored image for 0 tokens (the user's delight AND our
margin); a miss generates through the wrapped provider and donates the result back
to the library. The library callables are injected so the engine never learns about
Supabase — the worker owns storage. Every library failure fails OPEN: lookup errors
become misses, save errors are swallowed. Only the wrapped generator's own errors
(e.g. BudgetExceeded → graceful scene degradation upstream) propagate.
"""

from __future__ import annotations

from typing import Callable

from cadence.imagegen.base import GenResult

Lookup = Callable[[str, str], bytes | None]          # (prompt, aspect) -> image bytes
Save = Callable[[str, str, bytes, str], None]        # (prompt, aspect, bytes, provider)


class CachingGenerator:
    name = "library"

    def __init__(self, inner, *, lookup: Lookup, save: Save) -> None:
        self.inner = inner
        self.lookup = lookup
        self.save = save
        self.cost_per_image = getattr(inner, "cost_per_image", 0.0)

    def generate(self, prompt: str, *, aspect: str = "9x16",
                 style_refs: list[str] | None = None, seed: int | None = None) -> GenResult:
        try:
            hit = self.lookup(prompt, aspect)
        except Exception:  # noqa: BLE001 - library down must never block a render
            hit = None
        if hit:
            return GenResult(image_bytes=hit, prompt=prompt, cost_usd=0.0,
                             provider="library", seed=seed)
        res = self.inner.generate(prompt, aspect=aspect, style_refs=style_refs, seed=seed)
        try:
            self.save(prompt, aspect, res.image_bytes, res.provider)
        except Exception:  # noqa: BLE001 - donation is best-effort
            pass
        return res
