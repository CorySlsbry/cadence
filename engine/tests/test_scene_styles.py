"""Faceless scene styles: a style_override must REPLACE the photoreal framing (not fight
it), and the creator's scene direction must reach every generated prompt."""

from __future__ import annotations

import os

from cadence.synthesis.contextual import build_ai_broll, build_ai_prompt_scene


def _png() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 8), (40, 40, 60)).save(buf, "PNG")
    return buf.getvalue()


class _CaptureGen:
    def __init__(self):
        self.prompts: list[str] = []
        self._png = _png()

    def generate(self, prompt, aspect="9x16", style_refs=None, seed=None,
                 init_image=None, ref_image=None):
        self.prompts.append(prompt)
        gen = self

        class R:  # noqa: N801 - tiny stub
            image_bytes = gen._png

        return R()


_WORDS = [("claude", 0.0, 0.4), ("skills", 0.5, 0.9), ("explained", 1.0, 1.5)]


def test_style_override_replaces_photoreal_framing():
    p = build_ai_prompt_scene("a tiny robot", "ROBOT", style_override="handcrafted claymation stop-motion scene")
    assert "claymation" in p
    assert "hyperrealistic" not in p and "Photoreal" not in p


def test_default_prompt_keeps_photoreal_framing():
    p = build_ai_prompt_scene("a tiny robot", "ROBOT")
    assert "hyperrealistic" in p


def test_build_ai_broll_injects_style_and_direction(tmp_path):
    gen = _CaptureGen()
    inserts = build_ai_broll(
        _WORDS, 8.0, gen, out_dir=str(tmp_path), windows=[(0.0, 4.0, None)],
        style_override="bold comic book illustration", direction="the hero is a golden retriever",
    )
    assert len(inserts) == 1 and os.path.exists(inserts[0].image_path)
    assert "comic book" in gen.prompts[0]
    assert "golden retriever" in gen.prompts[0]
    assert "hyperrealistic" not in gen.prompts[0]


def test_build_ai_broll_default_has_no_direction_suffix(tmp_path):
    gen = _CaptureGen()
    build_ai_broll(_WORDS, 8.0, gen, out_dir=str(tmp_path), windows=[(0.0, 4.0, None)])
    assert "scene direction" not in gen.prompts[0]
    assert "hyperrealistic" in gen.prompts[0]
