"""CachingGenerator: library-hit short-circuit, miss passthrough, fail-open behavior."""

from __future__ import annotations

import pytest

from cadence.imagegen.base import GenResult
from cadence.imagegen.cache import CachingGenerator
from cadence.imagegen.ledger import BudgetExceeded

PROMPT = "Claude Code terminal mid-refactor"
PNG = b"\x89PNG-fake-bytes-from-inner"
LIB = b"\x89PNG-fake-bytes-from-library"


class FakeInner:
    name = "fake"
    cost_per_image = 0.05

    def __init__(self, exc: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.exc = exc

    def generate(self, prompt, *, aspect="9x16", style_refs=None, seed=None) -> GenResult:
        self.calls.append(prompt)
        if self.exc is not None:
            raise self.exc
        return GenResult(image_bytes=PNG, prompt=prompt, cost_usd=0.05,
                         provider="fake", seed=seed)


class Recorder:
    def __init__(self, hit: bytes | None = None, exc: Exception | None = None) -> None:
        self.hit = hit
        self.exc = exc
        self.lookups: list[tuple[str, str]] = []
        self.saves: list[tuple[str, str, bytes, str]] = []

    def lookup(self, prompt: str, aspect: str) -> bytes | None:
        self.lookups.append((prompt, aspect))
        if self.exc is not None:
            raise self.exc
        return self.hit

    def save(self, prompt: str, aspect: str, image_bytes: bytes, provider: str) -> None:
        if self.exc is not None:
            raise self.exc
        self.saves.append((prompt, aspect, image_bytes, provider))


def test_library_hit_skips_inner_and_costs_zero():
    inner, rec = FakeInner(), Recorder(hit=LIB)
    gen = CachingGenerator(inner, lookup=rec.lookup, save=rec.save)
    res = gen.generate(PROMPT, aspect="9x16")
    assert res == GenResult(image_bytes=LIB, prompt=PROMPT, cost_usd=0.0,
                            provider="library", seed=None)
    assert inner.calls == []
    assert rec.saves == []


def test_miss_generates_then_saves():
    inner, rec = FakeInner(), Recorder(hit=None)
    gen = CachingGenerator(inner, lookup=rec.lookup, save=rec.save)
    res = gen.generate(PROMPT, aspect="16x9", seed=7)
    assert res.provider == "fake" and res.image_bytes == PNG and res.seed == 7
    assert rec.lookups == [(PROMPT, "16x9")]
    assert rec.saves == [(PROMPT, "16x9", PNG, "fake")]


def test_lookup_failure_falls_through_to_inner():
    inner = FakeInner()
    rec = Recorder(exc=RuntimeError("embedding service down"))
    gen = CachingGenerator(inner, lookup=rec.lookup, save=rec.save)
    res = gen.generate(PROMPT)
    assert res.provider == "fake" and inner.calls == [PROMPT]


def test_save_failure_still_returns_result():
    inner = FakeInner()
    rec = Recorder(hit=None)
    saved_then_broken = Recorder(hit=None, exc=RuntimeError("storage down"))
    gen = CachingGenerator(inner, lookup=rec.lookup, save=saved_then_broken.save)
    res = gen.generate(PROMPT)
    assert res.provider == "fake" and res.image_bytes == PNG


def test_budget_exceeded_propagates_and_skips_save():
    inner = FakeInner(exc=BudgetExceeded("out of tokens"))
    rec = Recorder(hit=None)
    gen = CachingGenerator(inner, lookup=rec.lookup, save=rec.save)
    with pytest.raises(BudgetExceeded):
        gen.generate(PROMPT)
    assert rec.saves == []
