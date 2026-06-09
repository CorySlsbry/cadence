"""Multi-clip moment selection: score/reason parsing + ranking, and whole-video transcript
sampling so long videos get clips from anywhere (not just the first minutes)."""

from __future__ import annotations

import re

from cadence.models import Transcript, Word
from cadence.multiclip import ClipMoment, _timestamped, find_clip_moments, normalize_moments


class FakeLLM:
    def __init__(self, raw):
        self.raw = raw

    def complete(self, prompt):  # find_clip_moments calls llm.complete(prompt) -> raw dict
        return self.raw


def _tr(words):
    return Transcript(words=tuple(Word(t, s, e) for t, s, e in words))


def test_normalize_parses_and_clamps_score_reason():
    raw = {"clips": [
        {"start": 0, "end": 20, "title": "A", "hook": "h", "score": 150, "reason": "great hook"},
        {"start": 25, "end": 40, "title": "B", "hook": "h2", "score": -5, "reason": "x"},
        {"start": 45, "end": 60, "title": "C", "hook": "h3"},                 # missing -> 50
        {"start": 65, "end": 80, "title": "D", "hook": "h4", "score": "bad"},  # invalid -> 50
    ]}
    ms = normalize_moments(raw, duration=120)
    assert [m.score for m in ms] == [100, 0, 50, 50]   # clamped
    assert ms[0].reason == "great hook"


def test_clipmoment_to_dict_carries_score_reason():
    d = ClipMoment(0.0, 10.0, "t", "h", 77, "why").to_dict()
    assert d["score"] == 77 and d["reason"] == "why"


def test_timestamped_long_video_samples_whole_runtime():
    words = []
    t = 0.0
    for i in range(2000):                       # ~4000s of content -> far exceeds max_chars
        words.append((f"sentence{i}.", t, t + 1.5))
        t += 2.0
    text = _timestamped(_tr(words), max_chars=4000)
    assert len(text) <= 4000
    stamps = [float(x) for x in re.findall(r"\[(\d+\.\d)\]", text)]
    assert stamps and max(stamps) >= 0.7 * t      # coverage reaches the back of the video, not just the head


def test_find_clip_moments_returns_scored_moments():
    words = [(f"w{i}.", float(i * 2), float(i * 2 + 1.5)) for i in range(60)]  # ~120s
    raw = {"clips": [
        {"start": 0, "end": 20, "title": "lo", "hook": "h", "score": 30, "reason": "ok"},
        {"start": 25, "end": 50, "title": "hi", "hook": "h", "score": 90, "reason": "fire"},
    ]}
    ms = find_clip_moments(_tr(words), duration=120, llm=FakeLLM(raw))
    assert len(ms) == 2 and {m.score for m in ms} == {30, 90}


def test_find_clip_moments_no_llm_returns_empty():
    words = [(f"w{i}.", float(i), float(i) + 0.5) for i in range(40)]
    assert find_clip_moments(_tr(words), duration=40, llm=None) == []
