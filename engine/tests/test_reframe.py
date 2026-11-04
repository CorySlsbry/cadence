"""Face-aware 16:9 → 9:16 reframe: the ffmpeg crop string, the robust center
aggregation, and the landscape-only / no-face fallbacks (detection injected)."""

from __future__ import annotations

from dataclasses import dataclass

from cadence.reframe import aggregate_center, apply_auto_reframe, crop_filter, subject_center_x


@dataclass
class _Info:
    width: int
    height: int
    duration: float = 30.0


def test_crop_filter_none_is_centered():
    assert crop_filter(1080, 1920, None) == "crop=1080:1920"


def test_crop_filter_tracks_subject_with_clamped_window():
    # cx=0.75 → window centered on 75% of the scaled width, kept on-frame via clip().
    assert (
        crop_filter(1080, 1920, 0.75)
        == "crop=1080:1920:x='clip(iw*0.7500-1080/2\\,0\\,iw-1080)':y=0"
    )


def test_crop_filter_clamps_out_of_range_center():
    assert "iw*1.0000-" in crop_filter(1080, 1920, 1.5)
    assert "iw*0.0000-" in crop_filter(1080, 1920, -0.3)


def test_aggregate_center_is_median_ignoring_misses():
    # median of [0.2, 0.4, 0.9] = 0.4; the None (no-face frame) is ignored.
    assert aggregate_center([0.2, None, 0.9, 0.4]) == 0.4


def test_aggregate_center_none_when_no_faces():
    assert aggregate_center([None, None]) is None
    assert aggregate_center([]) is None


def test_aggregate_center_clamps():
    assert aggregate_center([1.4]) == 1.0


def test_subject_center_portrait_skips_detection():
    # width <= height → vertical crop only; detector must never run.
    called = {"n": 0}

    def sampler():
        called["n"] += 1
        return [0.9]

    out = subject_center_x("x.mp4", ff=None, sampler=sampler, probe=lambda s, f: _Info(1080, 1920))
    assert out is None and called["n"] == 0


def test_subject_center_landscape_returns_median_center():
    out = subject_center_x(
        "x.mp4", ff=None,
        sampler=lambda: [0.80, 0.82, None, 0.78],
        probe=lambda s, f: _Info(1920, 1080),
    )
    assert out == 0.80


def test_subject_center_landscape_no_face_falls_back_to_none():
    out = subject_center_x(
        "x.mp4", ff=None, sampler=lambda: [None, None], probe=lambda s, f: _Info(1920, 1080)
    )
    assert out is None


def test_apply_auto_reframe_sets_crop_x_per_source_cached():
    @dataclass
    class _Clip:
        source: str
        crop_x: float | None = None

    @dataclass
    class _Plan:
        clips: list

    plan = _Plan(clips=[_Clip("a.mp4"), _Clip("a.mp4"), _Clip("b.mp4")])
    calls: list[str] = []

    import cadence.reframe as rf

    orig = rf.subject_center_x
    rf.subject_center_x = lambda src, ff: (calls.append(src) or (0.7 if src == "a.mp4" else 0.3))
    try:
        apply_auto_reframe(plan, ff=None)
    finally:
        rf.subject_center_x = orig

    assert [c.crop_x for c in plan.clips] == [0.7, 0.7, 0.3]
    assert calls == ["a.mp4", "b.mp4"]  # "a.mp4" detected once, then cached
