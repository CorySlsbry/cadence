"""Unit + integration tests for Module D + §4 (plan + render)."""

from __future__ import annotations

import pytest

from cadence.ffmpeg.builder import build_cut_concat, build_punch_in, build_subtitles
from cadence.ffmpeg.probe import probe_media
from cadence.models import (
    Caption,
    CaptionStyle,
    ColorProfile,
    ColorSwatch,
    EditDecisionList,
    ExposureLabel,
    ExposureStats,
    RGBColor,
    TextZone,
    TimeRange,
    Transcript,
    Word,
)
from cadence.synthesis.captions import _ass_color, _ass_time, build_ass
from cadence.ffmpeg.builder import build_kenburns
from cadence.synthesis.plan import (
    build_generation_plan,
    derive_color_grade,
    group_captions,
    place_broll,
    remap_words_to_output,
)


def mk_transcript(words):
    return Transcript(words=tuple(Word(t, s, e) for t, s, e in words), language="en")


# --------------------------------------------------------------------------- #
# Filtergraph builders (pure)
# --------------------------------------------------------------------------- #
def test_build_cut_concat_two_ranges_with_audio():
    graph, v, a = build_cut_concat([TimeRange(0, 1), TimeRange(2, 3)], has_audio=True)
    assert v == "[cv]" and a == "[ca]"
    assert "trim=0.0000:1.0000" in graph
    assert "atrim=2.0000:3.0000" in graph
    assert "concat=n=2:v=1:a=1[cv][ca]" in graph
    assert graph.count(",setpts=PTS-STARTPTS[kv") == 2   # one PTS reset per video segment
    assert graph.count(",asetpts=PTS-STARTPTS[ka") == 2  # one reset per audio segment


def test_build_cut_concat_requires_ranges():
    with pytest.raises(ValueError):
        build_cut_concat([], has_audio=False)


def test_build_punch_in_forces_even_dims():
    g = build_punch_in("in", "out", zoom=1.12, width=1080, height=1920)
    assert "trunc(" in g and "/2)*2" in g
    # No-op when zoom <= 1.
    assert "null" in build_punch_in("in", "out", zoom=1.0, width=1080, height=1920)


def test_build_subtitles_escapes_windows_drive_colon():
    g = build_subtitles("in", "out", r"C:\caps\file.ass")
    assert "C\\:/caps/file.ass" in g


def test_build_kenburns_has_motion_and_alpha_fade():
    g = build_kenburns("3:v", "bk0", motion="zoom_in", width=1080, height=1920, dur=2.0, fade=0.2)
    assert "crop=1080:1920" in g
    assert "format=yuva420p" in g and "fade=t=in" in g and "fade=t=out" in g
    pan = build_kenburns("3:v", "bk0", motion="pan_right", width=1080, height=1920, dur=2.0, fade=0.0)
    assert "crop=1080:1920:x=" in pan
    # Regression: `crop` has no `eval` option (only `scale` does) — it animates t-based
    # x/y per-frame natively. A stray eval=frame on crop aborts the whole render.
    assert "eval=frame" not in pan


# --------------------------------------------------------------------------- #
# B-roll placement (pure)
# --------------------------------------------------------------------------- #
def test_place_broll_spacing_cycling_and_bounds():
    inserts = place_broll(["a.png", "b.png"], output_duration=20.0, mode="between")
    assert len(inserts) >= 2
    assert all(0 <= i.start < i.end <= 20.0 for i in inserts)          # within bounds
    for x, y in zip(inserts, inserts[1:]):
        assert y.start >= x.end                                        # no overlap, ordered
    assert inserts[0].image_path == "a.png" and inserts[1].image_path == "b.png"  # cycles images


def test_place_broll_empty_when_no_images_or_too_short():
    assert place_broll([], 20.0) == []
    assert place_broll(["a.png"], 2.0) == []


# --------------------------------------------------------------------------- #
# Captions (.ass)
# --------------------------------------------------------------------------- #
def test_ass_color_is_alpha_inverted_bgr():
    # white opaque -> &H00FFFFFF& ; pure red -> &H000000FF&
    assert _ass_color(RGBColor(255, 255, 255)) == "&H00FFFFFF&"
    assert _ass_color(RGBColor(255, 0, 0)) == "&H000000FF&"


def test_ass_time_formatting():
    assert _ass_time(0.0) == "0:00:00.00"
    assert _ass_time(75.5) == "0:01:15.50"


def test_ass_time_carries_at_minute_boundary():
    # Independent rounding used to emit out-of-spec "0:00:60.00"; must carry now.
    assert _ass_time(59.999) == "0:01:00.00"
    assert _ass_time(119.999) == "0:02:00.00"
    assert _ass_time(3599.999) == "1:00:00.00"


def test_build_ass_has_styles_and_dialogue_and_tags():
    caps = [
        Caption("hello world", 0.0, 2.0, zone=TextZone.BOTTOM, style=CaptionStyle.FADE),
        Caption("boom", 2.0, 3.0, zone=TextZone.CENTER, style=CaptionStyle.POP),
    ]
    doc = build_ass(caps, width=1080, height=1920)
    assert "[V4+ Styles]" in doc and "[Events]" in doc
    assert "\\fad(" in doc            # fade tag
    assert "\\fscx0\\fscy0\\t(" in doc  # pop tag
    assert "\\pos(540,1536)" in doc    # bottom zone at 0.80*1920
    assert "\\pos(540,960)" in doc     # center zone at 0.50*1920


def test_build_ass_lifts_bottom_caption_above_letterbox_bar():
    caps = [Caption("under the bar", 0.0, 2.0, zone=TextZone.BOTTOM, style=CaptionStyle.FADE)]
    normal = build_ass(caps, width=1080, height=1920)
    boxed = build_ass(caps, width=1080, height=1920, letterbox=True)
    assert "\\pos(540,1536)" in normal   # 0.80*1920, would sit under the 0.87 bottom bar
    assert "\\pos(540,1421)" in boxed    # lifted to 0.74*1920, clear of the bar
    assert "\\pos(540,1536)" not in boxed


# --------------------------------------------------------------------------- #
# Plan building (pure)
# --------------------------------------------------------------------------- #
def _profile(mean_luma: float, primary: RGBColor) -> ColorProfile:
    return ColorProfile(
        palette=(ColorSwatch(primary, 0.6), ColorSwatch(RGBColor(10, 10, 10), 0.4)),
        exposure=ExposureStats(mean_luma, 40.0, 10.0, 200.0, ExposureLabel.BALANCED),
    )


def test_derive_color_grade_warm_for_red_primary():
    grade = derive_color_grade(_profile(140.0, RGBColor(220, 60, 40)))
    assert grade.temperature > 0.0      # warm
    assert 0.9 <= grade.contrast <= 1.2
    assert grade.brightness == pytest.approx((140 - 128) / 255 * 0.3, abs=1e-3)


def test_remap_words_to_output_compresses_timeline():
    transcript = mk_transcript([("a", 0.0, 0.4), ("b", 2.0, 2.4), ("c", 2.5, 2.9)])
    kept = [TimeRange(0.0, 0.5), TimeRange(2.0, 3.0)]  # the 0.5-2.0 gap is cut
    out = remap_words_to_output(transcript, kept)
    # 'a' stays at 0.0; 'b' shifts from 2.0 -> 0.5 (after 0.5s of kept-1).
    assert out[0] == ("a", pytest.approx(0.0), pytest.approx(0.4))
    assert out[1][0] == "b" and out[1][1] == pytest.approx(0.5, abs=1e-3)


def test_group_captions_chunks_by_word_count():
    words = [(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)]
    caps = group_captions(words, zone=TextZone.BOTTOM, style=CaptionStyle.FADE, max_words=4)
    assert len(caps) == 3
    assert caps[0].text.split() == ["w0", "w1", "w2", "w3"]


def test_build_generation_plan_smart_zoom_and_captions():
    edl = EditDecisionList(
        source="x.mp4",
        source_duration=6.0,
        kept=(TimeRange(0.0, 2.0), TimeRange(3.0, 5.0)),
        removed=(),
        transcript=mk_transcript([("hello", 0.2, 0.6), ("there", 3.2, 3.6)]),
    )
    plan = build_generation_plan(edl)
    assert len(plan.clips) == 2
    assert plan.clips[0].zoom == pytest.approx(1.0)      # first clip no punch
    assert plan.clips[1].zoom > 1.0                       # later clip punches in
    assert plan.captions                                 # captions remapped
    assert plan.to_json()                                 # serializes


# --------------------------------------------------------------------------- #
# THE crown jewel: full pipeline -> a real 1080x1920 60fps render
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.slow
def test_full_pipeline_renders_premium_vertical(reference_video, talking_clip, logo_png, ff, tmp_path):
    from cadence import analyze_reference, build_generation_plan, clean_recording, render_plan
    from cadence.brandboard.store import BrandBoardStore
    from cadence.models import Anchor, AssetKind

    analysis = analyze_reference(reference_video, ff=ff)

    transcript = mk_transcript(
        [
            ("welcome", 0.2, 0.6), ("to", 0.6, 0.8), ("the", 0.8, 1.0), ("show", 1.0, 1.4),
            ("this", 2.0, 2.3), ("is", 2.3, 2.5), ("a", 2.5, 2.6), ("test", 2.6, 3.0),
            ("of", 4.0, 4.2), ("the", 4.2, 4.4), ("pipeline", 4.4, 5.0),
        ]
    )
    edl = clean_recording(talking_clip, transcript=transcript, ff=ff)

    store = BrandBoardStore(":memory:")
    board = store.create_board("Cadence Test")
    store.add_asset(board.id, kind=AssetKind.WATERMARK, name="logo", path=logo_png,
                    opacity=0.7, anchor=Anchor.BOTTOM_RIGHT, scale=0.18)
    store.set_caption_style(board.id, primary=RGBColor(255, 255, 255), outline=RGBColor(0, 0, 0))
    brand = store.get_board(board.id)
    store.close()

    plan = build_generation_plan(edl, analysis=analysis, brand=brand)
    assert plan.width == 1080 and plan.height == 1920 and plan.fps == 60

    out = str(tmp_path / "final.mp4")
    log = str(tmp_path / "graph.txt")
    result = render_plan(plan, out, ff=ff, log_path=log)

    assert result.width == 1080
    assert result.height == 1920
    assert result.fps == pytest.approx(60.0, abs=1.5)
    assert result.duration == pytest.approx(edl.output_duration, abs=0.6)

    info = probe_media(out, ff)
    assert info.has_audio
    assert info.width == 1080 and info.height == 1920


@pytest.mark.integration
@pytest.mark.slow
def test_render_with_broll_overlays_and_keeps_audio(talking_clip, ff, tmp_path):
    from PIL import Image

    from cadence import build_generation_plan as bgp, clean_recording, render_plan

    img = str(tmp_path / "broll.png")
    Image.new("RGB", (700, 900), (20, 40, 120)).save(img)
    edl = clean_recording(talking_clip, ff=ff)
    plan = bgp(edl, broll_images=[img], pacing_mode="match")
    assert plan.broll, "expected at least one b-roll insert"
    out = str(tmp_path / "broll.mp4")
    res = render_plan(plan, out, ff=ff)
    assert res.width == 1080 and res.height == 1920
    assert probe_media(out, ff).has_audio  # voiceover preserved under the b-roll


@pytest.mark.integration
@pytest.mark.slow
def test_render_broll_pan_motions(talking_clip, ff, tmp_path):
    # Regression for the crop-eval bug: pan motions must render (zoom-only masked it).
    from PIL import Image

    from cadence import build_generation_plan as bgp, clean_recording, render_plan
    from cadence.models import BrollInsert, KenBurns

    img = str(tmp_path / "b.png")
    Image.new("RGB", (800, 1000), (40, 80, 120)).save(img)
    edl = clean_recording(talking_clip, ff=ff)
    plan = bgp(edl)
    plan.broll = [
        BrollInsert(img, 1.0, 2.2, motion=KenBurns.PAN_RIGHT),
        BrollInsert(img, 2.6, 3.5, motion=KenBurns.PAN_LEFT),
    ]
    out = str(tmp_path / "pan.mp4")
    res = render_plan(plan, out, ff=ff)
    assert res.width == 1080 and res.height == 1920


@pytest.mark.integration
@pytest.mark.slow
def test_render_multi_source_keeps_audio(talking_clip, ff, tmp_path):
    # Regression: a plan spanning two distinct source files must NOT silently drop audio.
    import shutil

    from cadence import render_plan
    from cadence.models import ClipSpec, GenerationPlan

    second = str(tmp_path / "aroll2.mp4")
    shutil.copy(talking_clip, second)
    plan = GenerationPlan(clips=[
        ClipSpec(source=talking_clip, in_point=0.0, out_point=1.5),
        ClipSpec(source=second, in_point=0.0, out_point=1.5),
    ])
    out = str(tmp_path / "multi.mp4")
    render_plan(plan, out, ff=ff)
    assert probe_media(out, ff).has_audio
