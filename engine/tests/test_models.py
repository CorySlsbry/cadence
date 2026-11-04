"""Serialization round-trip + value-object invariants."""

from __future__ import annotations

import pytest

from cadence.models import (
    Anchor,
    Caption,
    CaptionStyle,
    ClipSpec,
    ColorGrade,
    EditDecisionList,
    GenerationPlan,
    RGBColor,
    TextZone,
    TimeRange,
    Transcript,
    WatermarkSpec,
    Word,
)


def test_rgbcolor_hex_roundtrip_and_validation():
    assert RGBColor.from_hex("#FF8000").hex == "#FF8000"
    assert RGBColor.from_hex("f80").hex == "#FF8800"  # shorthand
    with pytest.raises(ValueError):
        RGBColor(256, 0, 0)


def test_textzone_from_y_picks_nearest_anchor():
    assert TextZone.from_y(0.12) == TextZone.TOP
    assert TextZone.from_y(0.49) == TextZone.CENTER
    assert TextZone.from_y(0.85) == TextZone.BOTTOM


def test_timerange_validation_and_overlap():
    with pytest.raises(ValueError):
        TimeRange(2.0, 1.0)
    assert TimeRange(0, 2).overlaps(TimeRange(1, 3))
    assert not TimeRange(0, 1).overlaps(TimeRange(1, 2))


def test_anchor_overlay_xy():
    assert Anchor.BOTTOM_RIGHT.overlay_xy(48) == ("W-w-48", "H-h-48")
    assert Anchor.CENTER.overlay_xy() == ("(W-w)/2", "(H-h)/2")


def test_transcript_roundtrip():
    t = Transcript(words=(Word("hi", 0.0, 0.5, 0.9), Word("there", 0.5, 1.0)), language="en")
    assert Transcript.from_dict(t.to_dict()).text == "hi there"


def test_generation_plan_roundtrip_is_stable():
    plan = GenerationPlan(
        clips=[ClipSpec("a.mp4", 0.0, 2.0, zoom=1.12)],
        captions=[Caption("hi", 0.0, 1.0, zone=TextZone.CENTER, style=CaptionStyle.POP)],
        color_grade=ColorGrade(brightness=0.1, contrast=1.05, saturation=1.1),
        watermark=WatermarkSpec("logo.png", opacity=0.7, anchor=Anchor.TOP_LEFT, scale=0.2),
    )
    rebuilt = GenerationPlan.from_dict(plan.to_dict())
    assert rebuilt.to_dict() == plan.to_dict()
    assert rebuilt.clips[0].zoom == pytest.approx(1.12)
    assert rebuilt.captions[0].style == CaptionStyle.POP
    assert rebuilt.watermark.anchor == Anchor.TOP_LEFT


def test_generation_plan_from_dict_rejects_malformed():
    with pytest.raises(ValueError):
        GenerationPlan.from_dict({"clips": [{"in_point": 0, "out_point": 1}]})  # missing source
    with pytest.raises(ValueError):
        GenerationPlan.from_dict({"output": [1, 2, 3]})  # output not a dict
    with pytest.raises(ValueError):
        GenerationPlan.from_dict({"clips": [{"source": "a", "in_point": 0, "out_point": 1, "transition_in": "whoosh"}]})


def test_transcript_from_dict_rejects_malformed():
    with pytest.raises(ValueError):
        Transcript.from_dict({"words": [{"start": 0, "end": 1}]})  # missing text
    with pytest.raises(ValueError):
        Transcript.from_dict({"words": "notalist"})


def test_generation_plan_broll_roundtrip():
    from cadence.models import BrollInsert, KenBurns

    plan = GenerationPlan(
        clips=[ClipSpec("a.mp4", 0, 2)],
        broll=[BrollInsert("b.png", 1.0, 2.5, motion=KenBurns.PAN_RIGHT, fade=0.2)],
    )
    rebuilt = GenerationPlan.from_dict(plan.to_dict())
    assert rebuilt.broll[0].image_path == "b.png"
    assert rebuilt.broll[0].motion == KenBurns.PAN_RIGHT
    assert rebuilt.to_dict() == plan.to_dict()


def test_edl_roundtrip():
    edl = EditDecisionList(
        source="x.mp4", source_duration=6.0,
        kept=(TimeRange(0, 2), TimeRange(3, 5)), removed=(),
        transcript=Transcript(words=(Word("a", 0.0, 0.3),)),
    )
    rebuilt = EditDecisionList.from_dict(edl.to_dict())
    assert rebuilt.output_duration == pytest.approx(4.0)
    assert rebuilt.transcript.text == "a"
