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
        # Proxy the wrapped generator's cohesion capability so callers can still detect it
        # through the cache wrapper.
        self.supports_image_conditioning = getattr(inner, "supports_image_conditioning", False)

    def generate(self, prompt: str, *, aspect: str = "9x16",
                 style_refs: list[str] | None = None, seed: int | None = None,
                 init_image: bytes | None = None, ref_image: bytes | None = None) -> GenResult:
        # CRITICAL: the library is keyed on (prompt, aspect) ONLY. A reference/continuity-conditioned
        # image depends on init_image/ref_image bytes that the key can't represent, so a cache hit
        # would silently return a STALE, UNCHAINED image (and donating one would poison the key for
        # every future render). Bypass the library entirely when conditioning is present — generate
        # fresh, don't donate. Un-conditioned scenes keep the exact caching behavior as before.
        if init_image is not None or ref_image is not None:
            return self.inner.generate(prompt, aspect=aspect, style_refs=style_refs, seed=seed,
                                       init_image=init_image, ref_image=ref_image)
        try:
            hit = self.lookup(prompt, aspect)
        except Exception as exc:  # noqa: BLE001 - library down must never block a render
            print(f"[engine] library lookup failed ({exc!r}); generating", flush=True)
            hit = None
        if hit:
            return GenResult(image_bytes=hit, prompt=prompt, cost_usd=0.0,
                             provider="library", seed=seed)
        res = self.inner.generate(prompt, aspect=aspect, style_refs=style_refs, seed=seed)
        try:
            self.save(prompt, aspect, res.image_bytes, res.provider)
        except Exception as exc:  # noqa: BLE001 - donation is best-effort
            print(f"[engine] library save failed ({exc!r})", flush=True)
        return res
