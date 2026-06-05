"""Cadence — AI short-form video automation engine.

The engine is organized as clean ports-and-adapters so that the heavy/optional
ML dependencies (Whisper, sentence-transformers, OCR) live behind interfaces and
the core algorithmic logic stays pure and fully unit-testable.

Public surface (lazily loaded so importing one submodule never force-loads the
whole engine):
    from cadence import (
        analyze_reference,        # Module A — reference aesthetic + pacing analysis
        BrandBoardStore,          # Module B — persistent brand equity
        clean_recording,          # Module C — silence / filler / bad-take removal
        build_generation_plan,    # Module D + §4 — the structured render blueprint
        render_plan,              # §4 — FFmpeg synthesis + render
    )
"""

from __future__ import annotations

import importlib
from typing import Any

__version__ = "1.0.0"

_LAZY: dict[str, tuple[str, str]] = {
    "analyze_reference": ("cadence.analysis.analyzer", "analyze_reference"),
    "BrandBoardStore": ("cadence.brandboard.store", "BrandBoardStore"),
    "clean_recording": ("cadence.cleaning.editor", "clean_recording"),
    "build_generation_plan": ("cadence.synthesis.plan", "build_generation_plan"),
    "render_plan": ("cadence.synthesis.renderer", "render_plan"),
}

__all__ = ["__version__", *_LAZY.keys()]


def __getattr__(name: str) -> Any:  # PEP 562 lazy attribute loading
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'cadence' has no attribute {name!r}")
    module = importlib.import_module(target[0])
    return getattr(module, target[1])


def __dir__() -> list[str]:
    return sorted(__all__)
