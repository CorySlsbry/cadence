"""Tests for the AI contextual-b-roll pipeline (provider-agnostic, stub-driven)."""

from __future__ import annotations

import os

import pytest

from cadence.imagegen.base import GenResult
from cadence.imagegen.ledger import BudgetExceeded, CostLedger
from cadence.imagegen.stub import StubGenerator
from cadence.synthesis.contextual import (
    build_ai_broll,
    build_ai_prompt,
    caption_for_topic,
    compose_broll_image,
    plan_broll_windows,
    topic_for_window,
)


# --------------------------------------------------------------------------- #
# Stub generator
# --------------------------------------------------------------------------- #
def test_stub_generator_returns_png_of_right_aspect():
    res = StubGenerator().generate("hello world", aspect="9x16")
    assert res.provider == "stub" and res.cost_usd == 0.0
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(res.image_bytes))
    assert (img.width, img.height) == (1080, 1920)


def test_stub_is_deterministic():
    a = StubGenerator().generate("same prompt")
    b = StubGenerator().generate("same prompt")
    assert a.image_bytes == b.image_bytes


# --------------------------------------------------------------------------- #
# Cost ledger
# --------------------------------------------------------------------------- #
def test_cost_ledger_caps_spend_and_persists(tmp_path):
    path = str(tmp_path / "spend.json")
    ledger = CostLedger(path, cap_usd=0.10)
    assert ledger.remaining() == pytest.approx(0.10)
    for _ in range(3):
        ledger.charge(0.03)  # 0.09 total
    assert ledger.spent() == pytest.approx(0.09)
    assert ledger.can_spend(0.03) is False  # 0.12 > 0.10
    with pytest.raises(BudgetExceeded):
        ledger.charge(0.03)
    # Persists across instances.
    assert CostLedger(path, cap_usd=0.10).spent() == pytest.approx(0.09)


# --------------------------------------------------------------------------- #
# Contextual topic / prompt
# --------------------------------------------------------------------------- #
def test_topic_for_window_extracts_content_words():
    words = [("Claude", 0.2, 0.5), ("skills", 0.5, 0.9), ("are", 0.9, 1.0), ("powerful", 1.0, 1.6)]
    topic = topic_for_window(words, start=1.6, end=3.8)
    assert "claude" in topic and "skills" in topic and "powerful" in topic
    assert "are" not in topic  # stopword dropped


def test_prompt_includes_topic_but_never_orders_the_caption_rendered():
    """The prompt must describe the TOPIC but never hand the caption to the image model.

    This used to assert the caption appeared in the prompt — the prompt literally ordered a
    screen in-scene to display it — which is what shipped garbled on-screen text. The caption
    still reaches ``compose_broll_image`` for the PIL-drawn overlay; it must not reach the model.
    """
    cap = caption_for_topic("claude skills")
    assert cap == "Claude Skills"
    prompt = build_ai_prompt("claude skills", cap)
    assert "claude skills" in prompt
    assert "hyperrealistic" in prompt.lower()
    assert cap not in prompt  # the model is never asked to render the caption


def test_plan_broll_windows_spacing():
    w = plan_broll_windows(20.0, mode="between")
    assert len(w) >= 2
    for (s, e, _), (s2, _, _) in zip(w, w[1:]):
        assert e <= s2  # ordered, non-overlapping
    assert all(0 <= s < e <= 20.0 for s, e, _ in w)


def test_compose_broll_image_writes_target_size(tmp_path):
    res = StubGenerator().generate("topic")
    out = str(tmp_path / "b.png")
    compose_broll_image(res.image_bytes, "Claude Skills", out, overlay_text=True, width=1080, height=1920)
    from PIL import Image

    img = Image.open(out)
    assert (img.width, img.height) == (1080, 1920)


# --------------------------------------------------------------------------- #
# Orchestration (build_ai_broll)
# --------------------------------------------------------------------------- #
def test_build_ai_broll_generates_per_window(tmp_path):
    words = [("claude", 0.2, 0.6), ("skills", 0.6, 1.2), ("automation", 5.0, 5.6), ("workflow", 9.0, 9.6)]
    inserts = build_ai_broll(words, 20.0, StubGenerator(), out_dir=str(tmp_path), mode="between")
    assert len(inserts) >= 2
    assert all(os.path.isfile(b.image_path) for b in inserts)
    assert all(b.end > b.start for b in inserts)


def test_build_ai_broll_stops_on_budget(tmp_path):
    class _Budgeted:
        name = "budgeted"
        cost_per_image = 0.03

        def __init__(self):
            self.calls = 0

        def generate(self, prompt, *, aspect="9x16", style_refs=None, seed=None):
            self.calls += 1
            if self.calls > 1:
                raise BudgetExceeded("cap reached")
            return GenResult(StubGenerator().generate(prompt).image_bytes, prompt, 0.03, "budgeted")

    inserts = build_ai_broll([("topic", 0.0, 0.5)], 30.0, _Budgeted(), out_dir=str(tmp_path), mode="match")
    assert len(inserts) == 1  # stopped after the budget ran out


def test_build_ai_broll_respects_max_images(tmp_path):
    inserts = build_ai_broll([("x", 0.0, 0.5)], 60.0, StubGenerator(), out_dir=str(tmp_path), mode="match", max_images=2)
    assert len(inserts) == 2
