"""Unit tests for plan_background_windows — the replace-BG dynamic-background change planner:
a new image ~every `interval` seconds (minimum hold), snapped forward onto new audio sections.
"""

from cadence.synthesis.contextual import plan_background_windows


def test_no_speech_changes_every_interval_and_tiles_to_end():
    w = plan_background_windows([], 12.0, interval=4.0)
    starts = [s for (s, _e, _m) in w]
    assert starts == [0.0, 4.0, 8.0]
    assert w[-1][1] == 12.0  # tiles to the full duration, no trailing gap


def test_snaps_change_forward_onto_a_section_boundary():
    # boundary at 4.8 (a 3.8s pause before "c"); "d" is continuous (no boundary)
    words = [("a", 0.0, 0.5), ("b", 0.6, 1.0), ("c", 4.8, 5.2), ("d", 5.3, 5.7)]
    starts = [s for (s, _e, _m) in plan_background_windows(words, 12.0, interval=4.0, pause_gap=0.4, snap=1.5)]
    assert 4.8 in starts  # the ~4s change snapped forward to the section start


def test_minimum_hold_is_respected():
    starts = [s for (s, _e, _m) in plan_background_windows([], 20.0, interval=4.0)]
    gaps = [round(starts[i + 1] - starts[i], 3) for i in range(len(starts) - 1)]
    assert all(g >= 4.0 - 1e-6 for g in gaps)


def test_short_clip_single_window():
    w = plan_background_windows([], 3.0, interval=4.0)
    assert w == [(0.0, 3.0, w[0][2])]


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
