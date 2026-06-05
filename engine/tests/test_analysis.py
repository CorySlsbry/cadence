"""Unit + integration tests for Module A (analysis)."""

from __future__ import annotations

import numpy as np
import pytest

from cadence.analysis.color import compute_color_profile, kmeans
from cadence.analysis.pacing import compute_pacing
from cadence.analysis.text_overlay import active_row_spans
from cadence.analysis.transitions import (
    content_delta,
    detect_from_curves,
    rgb_to_hsv255,
    ssim,
)
from cadence.config import AnalyzerConfig
from cadence.models import RGBColor, TextZone, Transition, TransitionType
from tests import fixtures


# --------------------------------------------------------------------------- #
# Pure colour-space / similarity primitives
# --------------------------------------------------------------------------- #
def _solid(rgb: tuple[int, int, int], h: int = 4, w: int = 4) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = rgb
    return frame


def test_rgb_to_hsv255_pure_hues():
    red = rgb_to_hsv255(_solid((255, 0, 0)))
    green = rgb_to_hsv255(_solid((0, 255, 0)))
    blue = rgb_to_hsv255(_solid((0, 0, 255)))
    # Hue scaled to 0..255: red=0, green=85, blue=170.
    assert red[0, 0, 0] == pytest.approx(0.0, abs=1.0)
    assert green[0, 0, 0] == pytest.approx(85.0, abs=1.0)
    assert blue[0, 0, 0] == pytest.approx(170.0, abs=1.0)
    # Fully saturated, full value.
    for hsv in (red, green, blue):
        assert hsv[0, 0, 1] == pytest.approx(255.0, abs=1.0)
        assert hsv[0, 0, 2] == pytest.approx(255.0, abs=1.0)


def test_content_delta_identical_is_zero_and_opposite_is_large():
    red = rgb_to_hsv255(_solid((224, 48, 32)))
    blue = rgb_to_hsv255(_solid((32, 64, 224)))
    assert content_delta(red, red) == pytest.approx(0.0, abs=1e-9)
    # Distinct scene colours yield a clear non-zero content score.
    assert content_delta(red, blue) > 25.0
    # A full luminance flip (white<->black) maxes the value channel: 255/3 ~= 85.
    white = rgb_to_hsv255(_solid((255, 255, 255)))
    black = rgb_to_hsv255(_solid((0, 0, 0)))
    assert content_delta(white, black) == pytest.approx(85.0, abs=1.0)


def test_ssim_identical_is_one_and_differs_for_distinct():
    # Structured pattern vs its photographic negative -> SSIM collapses.
    checker = ((np.add.outer(np.arange(16), np.arange(16)) % 2) * 255.0)
    assert ssim(checker, checker) == pytest.approx(1.0, abs=1e-6)
    assert ssim(checker, 255.0 - checker) < 0.0


def test_kmeans_recovers_two_separated_clusters():
    rng = np.random.default_rng(0)
    cluster_a = rng.normal((20, 20, 20), 2.0, size=(200, 3))
    cluster_b = rng.normal((230, 230, 230), 2.0, size=(200, 3))
    pixels = np.vstack([cluster_a, cluster_b])
    centers, labels = kmeans(pixels, 2, iters=30, seed=7)
    centers = centers[np.argsort(centers[:, 0])]  # sort by R
    assert centers[0] == pytest.approx([20, 20, 20], abs=4.0)
    assert centers[1] == pytest.approx([230, 230, 230], abs=4.0)


def test_active_row_spans_finds_contiguous_runs():
    density = np.array([0.0, 0.2, 0.3, 0.0, 0.0, 0.5, 0.0])
    assert active_row_spans(density, threshold=0.1) == [(1, 3), (5, 6)]


# --------------------------------------------------------------------------- #
# Pure detector over synthetic curves
# --------------------------------------------------------------------------- #
def test_detect_from_curves_single_hard_cut():
    cfg = AnalyzerConfig()
    content = np.full(60, 2.0)
    content[30] = 90.0  # one sharp spike
    luma = np.full(61, 128.0)
    cuts = detect_from_curves(content, luma, sample_fps=12.0, cfg=cfg)
    assert len(cuts) == 1
    assert cuts[0].type == TransitionType.HARD_CUT
    # Timestamps are intentionally rounded to ms precision.
    assert cuts[0].timestamp == pytest.approx(31 / 12.0, abs=1e-3)


def test_detect_from_curves_classifies_dissolve_plateau():
    cfg = AnalyzerConfig()
    content = np.full(60, 1.0)
    content[28:38] = 40.0  # a sustained plateau -> dissolve
    luma = np.full(61, 128.0)
    cuts = detect_from_curves(content, luma, sample_fps=12.0, cfg=cfg)
    assert any(c.type == TransitionType.DISSOLVE for c in cuts)


def test_detect_from_curves_fade_to_black():
    cfg = AnalyzerConfig()
    content = np.full(40, 1.0)
    content[20] = 80.0
    luma = np.full(41, 128.0)
    luma[21] = 4.0  # frame after the boundary is near-black
    cuts = detect_from_curves(content, luma, sample_fps=12.0, cfg=cfg)
    assert cuts[0].type == TransitionType.FADE_TO_BLACK


def test_compute_pacing_segment_boundaries():
    transitions = (
        Transition(2.0, TransitionType.HARD_CUT, 1.0, 90.0),
        Transition(4.0, TransitionType.HARD_CUT, 1.0, 88.0),
    )
    pacing = compute_pacing(transitions, duration=6.0)
    assert pacing.segment_boundaries == (0.0, 2.0, 4.0, 6.0)
    assert pacing.avg_segment_sec == pytest.approx(2.0)
    assert pacing.cut_density_per_min == pytest.approx(20.0)


# --------------------------------------------------------------------------- #
# Integration against a real generated reference video
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_color_profile_recovers_scene_colors(reference_video, ff):
    from cadence.analysis.frames import extract_frames

    frames = extract_frames(reference_video, fps=1.0, width=128, height=228, ff=ff)
    profile = compute_color_profile(frames, k=5, iters=25, seed=1234)
    palette = [s.color for s in profile.palette]

    def closest_dist(target: RGBColor) -> float:
        return min(
            ((c.r - target.r) ** 2 + (c.g - target.g) ** 2 + (c.b - target.b) ** 2) ** 0.5
            for c in palette
        )

    for hex_color in fixtures.REF_COLORS_HEX:
        target = RGBColor.from_hex(hex_color)
        assert closest_dist(target) < 70.0, f"no palette swatch near {target.hex}"


@pytest.mark.integration
def test_detect_transitions_finds_scene_cuts(reference_video, ff):
    from cadence.analysis.transitions import detect_transitions

    cuts = detect_transitions(reference_video, ff=ff)
    times = [c.timestamp for c in cuts]
    for expected in fixtures.REF_CUTS:
        assert any(abs(t - expected) < 0.3 for t in times), f"missing cut near {expected}s in {times}"
    # The scene cuts should be classified as hard cuts.
    for c in cuts:
        if any(abs(c.timestamp - e) < 0.3 for e in fixtures.REF_CUTS):
            assert c.type == TransitionType.HARD_CUT


@pytest.mark.integration
def test_detect_text_overlays_zones_and_timing(reference_video, ff):
    from cadence.analysis.text_overlay import detect_text_overlays

    events = detect_text_overlays(reference_video, ff=ff)
    assert events, "expected at least the two caption overlays"
    bottoms = [e for e in events if e.zone == TextZone.BOTTOM]
    tops = [e for e in events if e.zone == TextZone.TOP]
    assert bottoms, f"no bottom-zone caption detected: {[e.to_dict() for e in events]}"
    assert tops, f"no top-zone caption detected: {[e.to_dict() for e in events]}"
    # Bottom caption is the one that shows early; top shows late.
    assert min(e.start for e in bottoms) < 1.5
    assert max(e.start for e in tops) > 3.5


@pytest.mark.integration
def test_analyze_reference_end_to_end(reference_video, ff):
    from cadence import analyze_reference

    analysis = analyze_reference(reference_video, ff=ff)
    assert analysis.media.width == fixtures.REF_W
    assert analysis.media.height == fixtures.REF_H
    assert analysis.media.has_audio
    assert analysis.media.duration == pytest.approx(fixtures.REF_DURATION, abs=0.3)
    assert analysis.color_profile.primary is not None
    assert len(analysis.transitions) >= 2
    # Round-trips to JSON-safe dict.
    d = analysis.to_dict()
    assert d["media"]["width"] == fixtures.REF_W
    assert isinstance(analysis.to_json(), str)
