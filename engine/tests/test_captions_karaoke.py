"""Per-word karaoke caption engine: keyword selection, word-retaining grouping, the
per-word scale-pop ASS, the hook card, and the legacy back-compat contract."""

from __future__ import annotations

from cadence.config import SynthesisConfig
from cadence.models import (
    Caption,
    CaptionWord,
    EditDecisionList,
    TextZone,
    TimeRange,
    Transcript,
    Word,
)
from cadence.synthesis.captions import build_ass_karaoke, build_hook_studio, pick_keywords
from cadence.synthesis.plan import build_generation_plan, group_karaoke_captions


def _dialogue_lines(ass: str) -> list[str]:
    return [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]


def test_pick_keywords_selects_content_words():
    assert pick_keywords(["the", "Claude", "skills", "are", "amazing"]) == {1, 2, 4}


def test_pick_keywords_falls_back_to_longest_when_all_function_words():
    # No >=4-letter content word → emphasize the single longest token so the line still has an accent.
    assert pick_keywords(["the", "an", "is"]) == {0}


def test_group_karaoke_captions_retains_per_word_timings_and_chunks():
    words = [("Claude", 0.0, 0.4), ("Code", 0.5, 0.9), ("is", 1.0, 1.2),
             ("great", 1.3, 1.8), ("today", 2.0, 2.4)]
    caps = group_karaoke_captions(words, zone=TextZone.BOTTOM, max_words=4, max_dur=2.2)
    assert len(caps) == 2
    assert [w.text for w in caps[0].words] == ["Claude", "Code", "is", "great"]
    assert caps[0].text == "Claude Code is great"
    assert (caps[0].start, caps[0].end) == (0.0, 1.8)
    assert caps[1].words == [CaptionWord("today", 2.0, 2.4)]


def test_build_ass_karaoke_one_event_per_word_with_pop_showing_whole_line():
    caps = group_karaoke_captions(
        [("Claude", 0.0, 0.4), ("Code", 0.5, 0.9), ("rocks", 1.0, 1.6)], zone=TextZone.BOTTOM
    )
    ass = build_ass_karaoke(caps, width=1080, height=1920)
    dlg = _dialogue_lines(ass)
    assert len(dlg) == 3  # one event per word interval
    assert "\\t(" in ass  # the per-word scale-pop transform
    for line in dlg:  # the full line is visible in every event (only the active word pops)
        assert "Claude" in line and "Code" in line and "rocks" in line
    assert "0:00:00.00" in dlg[0]  # first event starts at the first word's start


def test_build_ass_karaoke_wordless_caption_falls_back_to_single_line():
    cap = Caption(text="hello world", start=0.0, end=2.0, zone=TextZone.BOTTOM)  # no per-word data
    dlg = _dialogue_lines(build_ass_karaoke([cap], width=1080, height=1920))
    assert len(dlg) == 1 and "hello world" in dlg[0]


def test_build_hook_studio_renders_animated_uppercase_card():
    ass = build_hook_studio("Stop scrolling now", width=1080, height=1920, duration=2.4)
    assert "[Script Info]" in ass and "Style: Hook" in ass
    assert "STOP SCROLLING NOW" in ass  # uppercased for impact
    assert "\\t(" in ass and "\\fad(" in ass
    dlg = _dialogue_lines(ass)
    assert len(dlg) == 1 and "0:00:02.40" in dlg[0]  # end == duration


def test_caption_words_serialization_roundtrip():
    cap = Caption(text="a b", start=0.0, end=1.0,
                  words=[CaptionWord("a", 0.0, 0.5), CaptionWord("b", 0.5, 1.0)])
    back = Caption.from_dict(cap.to_dict())
    assert back.words == cap.words and back.text == "a b"


def test_build_generation_plan_caption_mode_controls_karaoke():
    tr = Transcript(words=(Word("Claude", 0.0, 0.4), Word("Code", 0.5, 0.9), Word("rocks", 1.0, 1.6)))
    edl = EditDecisionList(source="x.mp4", source_duration=2.0,
                           kept=(TimeRange(0.0, 2.0),), removed=(), transcript=tr)
    karaoke = build_generation_plan(edl, cfg=SynthesisConfig(caption_mode="karaoke"))
    assert karaoke.captions and all(c.words for c in karaoke.captions)
    legacy = build_generation_plan(edl, cfg=SynthesisConfig())
    assert legacy.captions and not any(c.words for c in legacy.captions)


def test_parse_customization_caption_mode_is_reachable_via_api():
    from cadence.customize import parse_customization

    assert parse_customization({"caption_mode": "karaoke"}).synthesis.caption_mode == "karaoke"
    assert parse_customization({}).synthesis.caption_mode == "legacy"
    assert parse_customization({"caption_mode": "bogus"}).synthesis.caption_mode == "legacy"  # invalid ignored


def test_parse_customization_hook_card():
    from cadence.customize import parse_customization

    assert parse_customization({"hook": "  Stop scrolling  "}).hook == "Stop scrolling"  # trimmed
    assert parse_customization({}).hook is None
    assert parse_customization({"hook": "   "}).hook is None  # blank → no card
