"""Unit tests for the creator value-add features: hooks + repurpose (+ multiclip).
LLM is stubbed — no network. Hard-normalization + graceful fallback are the contract."""

from __future__ import annotations

from cadence.models import Transcript, Word
from cadence.multiclip import find_clip_moments, normalize_moments
from cadence.social.hooks import MAX_HOOK_CHARS, build_hooks, normalize_hooks
from cadence.social.repurpose import LIMITS, build_repurpose, normalize_repurpose


class FakeLLM:
    def __init__(self, canned):
        self.canned = canned
        self.prompts: list[str] = []

    def complete(self, prompt, *, temperature=0.7):
        self.prompts.append(prompt)
        return self.canned


class RaisingLLM:
    def complete(self, prompt, *, temperature=0.7):
        raise RuntimeError("llm down")


# ---- hooks ----
def test_normalize_hooks_dedupes_caps_and_trims():
    raw = {"hooks": ["A", "A", "B", "x" * 200, "C", "D", "E"], "cold_open": {"line": "Lead line", "why": "punchy"}}
    out = normalize_hooks(raw, n=5)
    assert len(out["hooks"]) == 5  # capped
    assert out["hooks"][0] == "A" and "A" == out["hooks"][0]  # de-duped (only one A)
    assert out["hooks"].count("A") == 1
    assert all(len(h) <= MAX_HOOK_CHARS for h in out["hooks"])  # trimmed
    assert out["cold_open"]["line"] == "Lead line"


def test_build_hooks_uses_llm_then_normalizes():
    llm = FakeLLM({"hooks": ["Hook one", "Hook two", "Hook three"], "cold_open": {"line": "Open here", "why": "w"}})
    out = build_hooks("I tested three tools today and one clearly won.", llm, n=5)
    assert out["hooks"] == ["Hook one", "Hook two", "Hook three"]
    assert out["cold_open"]["line"] == "Open here"
    assert llm.prompts and "Transcript:" in llm.prompts[0]


def test_build_hooks_falls_back_to_stub_when_llm_raises_or_absent():
    text = "Here is how I edit fast. It saves hours."
    assert build_hooks(text, RaisingLLM())["hooks"]  # raised -> stub, still non-empty
    assert build_hooks(text, None)["hooks"]  # no llm -> stub
    assert build_hooks("   ") is None  # empty transcript -> None


# ---- repurpose ----
def test_normalize_repurpose_caps_and_trims():
    raw = {
        "carousel": [f"slide {i}" for i in range(20)],
        "thread": ["t" * 400, "short tweet"],
        "newsletter": "n " * 600,
        "quote_cards": ["q1", "q2", "q3", "q4", "q5"],
    }
    out = normalize_repurpose(raw)
    assert len(out["carousel"]) == LIMITS["carousel"][0]
    assert len(out["thread"][0]) <= LIMITS["thread"][1]  # 280
    assert len(out["quote_cards"]) == LIMITS["quote_cards"][0]
    assert len(out["newsletter"]) <= 800


def test_build_repurpose_uses_llm_and_falls_back():
    llm = FakeLLM({"carousel": ["s1", "s2"], "thread": ["tw1"], "newsletter": "blurb", "quote_cards": ["q"]})
    out = build_repurpose("A short talk about AI video editing.", llm)
    assert out["carousel"] == ["s1", "s2"] and out["newsletter"] == "blurb"
    assert build_repurpose("hello world", RaisingLLM())["carousel"]  # raised -> stub
    assert build_repurpose("hello world", None)["thread"]  # no llm -> stub
    assert build_repurpose("  ") is None


# ---- multiclip ----
def _transcript(n_words=60, step=0.7):
    return Transcript(words=tuple(Word(f"w{i}", i * step, i * step + step) for i in range(n_words)), language="en")


def test_normalize_moments_clamps_drops_overlaps_and_caps():
    raw = {"clips": [
        {"start": -5, "end": 20, "title": "A", "hook": "h"},      # start clamps to 0
        {"start": 10, "end": 25, "title": "overlap", "hook": "h"},  # overlaps [0,20] -> dropped
        {"start": 30, "end": 33, "title": "tooshort", "hook": "h"},  # 3s < 8 -> dropped
        {"start": 40, "end": 200, "title": "B", "hook": "h"},      # end clamps to 120
    ]}
    out = normalize_moments(raw, duration=120, max_clips=5, min_sec=8, max_sec=90)
    assert [(m.start, m.end) for m in out] == [(0.0, 20.0), (40.0, 120.0)]


def test_find_clip_moments_stub_and_fallbacks():
    tr = _transcript(60, 0.7)  # ~42s
    llm = FakeLLM({"clips": [
        {"start": 2, "end": 15, "title": "One", "hook": "Hook one"},
        {"start": 20, "end": 35, "title": "Two", "hook": "Hook two"},
    ]})
    out = find_clip_moments(tr, 42.0, llm=llm, max_clips=5)
    assert len(out) == 2 and out[0].title == "One" and out[0].duration == 13.0
    assert find_clip_moments(tr, 42.0, llm=None) == []                    # no llm -> single render
    assert find_clip_moments(_transcript(5, 0.5), 2.5, llm=llm) == []      # too short to split
    assert find_clip_moments(Transcript(words=(), language="en"), 50, llm=llm) == []  # no words
