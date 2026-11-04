"""Tests for caption brand/spell correction (cadence.synthesis.lexicon)."""

from __future__ import annotations

import pytest

from cadence.synthesis.lexicon import _levenshtein, correct_words_out


@pytest.mark.parametrize(
    "a,b,dist",
    [
        ("clouthook", "clouthook", 0),
        ("cloudhook", "clouthook", 1),       # d->t
        ("cloudhoock", "clouthook", 2),      # d->t + extra c
        ("kitten", "sitting", 3),
        ("", "abc", 3),
    ],
)
def test_levenshtein(a, b, dist):
    assert _levenshtein(a, b) == dist


@pytest.mark.parametrize(
    "raw,expected",
    [
        # multi-word ASR mishears collapse to ONE canonical, timed word
        ([("cloud", 0.0, 0.3), ("hoock", 0.3, 0.6)], [("CloutHook", 0.0, 0.6)]),
        ([("clout", 1.0, 1.4), ("hook", 1.4, 1.9)], [("CloutHook", 1.0, 1.9)]),
        # single-token mishears
        ([("cloudhook", 2.0, 2.5)], [("CloutHook", 2.0, 2.5)]),
        ([("clouthoook", 0.0, 0.5)], [("CloutHook", 0.0, 0.5)]),
        # already correct → unchanged
        ([("CloutHook", 0.0, 0.5)], [("CloutHook", 0.0, 0.5)]),
    ],
)
def test_brand_correction_and_merge(raw, expected):
    assert correct_words_out(raw, spellcheck=False) == expected


@pytest.mark.parametrize(
    "raw",
    [
        [("cloud", 0.0, 0.3)],                       # the sky/cloud — must NOT become CloutHook
        [("cloud", 0.0, 0.3), ("computing", 0.3, 0.9)],
        [("clout", 0.0, 0.3), ("chaser", 0.3, 0.8)],
    ],
)
def test_no_false_positive_on_ordinary_words(raw):
    # length guard + edit threshold keep lone/unrelated words intact
    assert correct_words_out(raw, spellcheck=False) == raw


def test_brand_correction_preserves_surrounding_timing():
    raw = [
        ("welcome", 0.0, 0.4),
        ("to", 0.4, 0.5),
        ("cloud", 0.5, 0.8),
        ("hoock", 0.8, 1.1),
        ("today", 1.1, 1.6),
    ]
    out = correct_words_out(raw, spellcheck=False)
    assert out == [
        ("welcome", 0.0, 0.4),
        ("to", 0.4, 0.5),
        ("CloutHook", 0.5, 1.1),  # merged interval spans both source words
        ("today", 1.1, 1.6),
    ]


def test_custom_brand_term():
    raw = [("neuron", 0.0, 0.3), ("hq", 0.3, 0.6)]
    out = correct_words_out(raw, custom_terms=["Neuron HQ"], spellcheck=False)
    assert out == [("Neuron HQ", 0.0, 0.6)]


def test_clean_script_passes_through_unchanged():
    # a written faceless script is already correct → no-op (idempotence on good input)
    raw = [("post", 0.0, 0.3), ("a", 0.3, 0.4), ("video", 0.4, 0.9), ("with", 0.9, 1.1)]
    assert correct_words_out(raw, spellcheck=False) == raw


def test_spellcheck_leaves_proper_nouns_and_short_words():
    # deterministic regardless of whether pyspellchecker is installed:
    # capitalized tokens and <=3-letter tokens are never spell-corrected.
    raw = [("Anthropic", 0.0, 0.4), ("AI", 0.4, 0.6), ("the", 0.6, 0.8)]
    assert correct_words_out(raw, spellcheck=True) == raw


def test_spellcheck_fixes_obvious_typo_when_available():
    sp = pytest.importorskip("spellchecker")  # optional dep; skip if absent
    _ = sp
    out = correct_words_out([("recieve", 0.0, 0.5)], spellcheck=True)
    assert out == [("receive", 0.0, 0.5)]
