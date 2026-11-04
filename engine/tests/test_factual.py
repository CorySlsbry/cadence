"""Tests for the factual-image guardrail matcher + manifest loader.

The matcher is a pure function: given the words spoken into a b-roll window and a
list of curated real-asset entries, return the asset whose trigger phrase appears
in the text — preferring the most specific (longest) phrase, on word boundaries,
case-insensitively, tolerant of punctuation. The loader reads a manifest and skips
entries whose image file is not present yet (so the pipeline degrades gracefully
before the screenshot library is captured).
"""

from __future__ import annotations

import json
import os

from cadence.synthesis.factual import (
    FactualAsset,
    load_factual_assets,
    match_factual_asset,
)


def _assets() -> list[FactualAsset]:
    return [
        FactualAsset(key="claude-code", asset_path="code.png", aliases=("claude code", "code tab")),
        FactualAsset(key="claude-skills", asset_path="skills.png", aliases=("claude skills", "skills tab", "skills")),
        FactualAsset(key="claude-cowork", asset_path="cowork.png", aliases=("claude cowork", "cowork", "co-work")),
    ]


def test_match_factual_asset_longest_phrase_wins():
    # "claude code" (specific) must beat the bare "code tab"/"skills" entries when both could match.
    hit = match_factual_asset("so I opened up Claude Code this morning", _assets())
    assert hit is not None and hit.key == "claude-code"


def test_match_factual_asset_more_specific_beats_substring():
    # Text contains both a generic and a specific trigger; the longer phrase must win.
    assets = [
        FactualAsset(key="generic-code", asset_path="g.png", aliases=("code",)),
        FactualAsset(key="claude-code", asset_path="c.png", aliases=("claude code",)),
    ]
    hit = match_factual_asset("the claude code experience", assets)
    assert hit is not None and hit.key == "claude-code"


def test_match_factual_asset_word_boundary_not_substring():
    # "skills" must NOT match inside "skillset".
    assert match_factual_asset("my skillset keeps growing", _assets()) is None
    # but a standalone token must match.
    hit = match_factual_asset("check the skills tab", _assets())
    assert hit is not None and hit.key == "claude-skills"


def test_match_factual_asset_case_insensitive():
    hit = match_factual_asset("CLAUDE SKILLS are wild", _assets())
    assert hit is not None and hit.key == "claude-skills"


def test_match_factual_asset_tolerates_punctuation():
    # "claude-code" (hyphen) and "co-work" should normalize to match "claude code" / "cowork".
    assert match_factual_asset("the claude-code workflow", _assets()).key == "claude-code"
    assert match_factual_asset("I tried co-work yesterday", _assets()).key == "claude-cowork"


def test_match_factual_asset_no_match_returns_none():
    assert match_factual_asset("the weather is nice today", _assets()) is None


def test_match_factual_asset_empty_inputs_return_none():
    assert match_factual_asset("", _assets()) is None
    assert match_factual_asset("claude code", []) is None
    assert match_factual_asset("claude code", None) is None


def test_load_factual_assets_skips_missing_files(tmp_path):
    # One asset has a real file, one is absent — only the present one loads (graceful pre-capture).
    present = tmp_path / "skills.png"
    present.write_bytes(b"\x89PNG\r\n")  # any bytes; loader only checks existence
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {"key": "claude-skills", "asset_path": "skills.png", "aliases": ["skills"]},
                    {"key": "claude-code", "asset_path": "code.png", "aliases": ["claude code"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    loaded = load_factual_assets(str(manifest))
    assert [a.key for a in loaded] == ["claude-skills"]
    assert os.path.isabs(loaded[0].asset_path) and os.path.exists(loaded[0].asset_path)


def test_load_factual_assets_missing_manifest_returns_empty():
    assert load_factual_assets("C:/no/such/manifest.json") == []


def test_load_factual_assets_drops_entries_without_aliases(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"x")
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps({"assets": [{"key": "x", "asset_path": "x.png", "aliases": []}]}),
        encoding="utf-8",
    )
    assert load_factual_assets(str(manifest)) == []


# --------------------------------------------------------------------------- #
# Integration: build_ai_broll honours the guardrail (uses the real asset, skips the model)
# --------------------------------------------------------------------------- #
def _png_bytes(w: int, h: int, color=(20, 30, 40)) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


class _CountingGenerator:
    """A stub ImageGenerator that counts generate() calls — lets us prove the guardrail
    window did NOT hit the model (so it burns 0 tokens)."""

    name = "counting"
    cost_per_image = 0.0

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt, *, aspect="9x16", style_refs=None, seed=None):
        from cadence.imagegen.base import GenResult

        self.calls += 1
        return GenResult(image_bytes=_png_bytes(1080, 1920, (10, 10, 10)), prompt=prompt,
                         cost_usd=0.0, provider="counting")


def test_build_ai_broll_uses_factual_asset_and_skips_generator(tmp_path):
    from cadence.models import KenBurns
    from cadence.synthesis.contextual import build_ai_broll

    # A landscape "UI screenshot" — the guardrail must contain-fit the whole thing to 9:16.
    asset = tmp_path / "claude-code.png"
    asset.write_bytes(_png_bytes(1280, 720, (0, 90, 170)))
    assets = [FactualAsset(key="claude-code", asset_path=str(asset), aliases=("claude code",))]

    # Window 0 (~1.5-3.7s, lookback to -1.5) hears "Claude Code"; window 1 (~6.7-8.9s) does not.
    words = [
        ("I", 0.0, 0.3), ("opened", 0.4, 0.9), ("Claude", 1.0, 1.5), ("Code", 1.6, 2.1),
        ("this", 2.2, 2.5), ("morning", 2.6, 3.1),
        ("then", 6.0, 6.4), ("we", 6.5, 6.8), ("talked", 6.9, 7.4), ("about", 7.5, 7.9),
        ("growth", 8.0, 8.6),
    ]
    out = tmp_path / "out"
    out.mkdir()
    gen = _CountingGenerator()

    inserts = build_ai_broll(words, 12.0, gen, out_dir=str(out), mode="between", factual_assets=assets)

    assert [i.source for i in inserts] == ["factual", "ai"]
    assert gen.calls == 1  # only the non-guarded window generated → guardrail burned 0 model calls
    assert inserts[0].motion == KenBurns.ZOOM_IN
    from PIL import Image

    assert Image.open(inserts[0].image_path).size == (1080, 1920)  # full UI contained into the frame


def test_build_ai_broll_no_factual_assets_is_unchanged(tmp_path):
    # Back-compat: without factual_assets the loop generates every window as before.
    from cadence.synthesis.contextual import build_ai_broll

    words = [("hello", float(i), float(i) + 0.4) for i in range(12)]
    out = tmp_path / "out2"
    out.mkdir()
    gen = _CountingGenerator()
    inserts = build_ai_broll(words, 12.0, gen, out_dir=str(out), mode="between")
    assert all(i.source == "ai" for i in inserts)
    assert gen.calls == len(inserts) >= 1
