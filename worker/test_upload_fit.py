"""Upload fit-guard math: the re-encode bitrate must land renders safely under the
storage cap for any duration, never starving audio or collapsing to garbage video."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from cadence_worker import AUDIO_FIT_BPS, fit_video_bitrate

MB = 1024 * 1024


def test_budget_lands_under_cap_with_headroom():
    # 48MB cap, 35s video → bits at the computed rate + audio must stay under the cap.
    limit, dur = 48 * MB, 35.0
    v = fit_video_bitrate(limit, dur)
    total_bits = (v + AUDIO_FIT_BPS) * dur
    assert total_bits < limit * 8                 # fits
    assert total_bits > limit * 8 * 0.85          # but doesn't waste the budget


def test_longer_video_gets_lower_bitrate():
    limit = 48 * MB
    assert fit_video_bitrate(limit, 90) < fit_video_bitrate(limit, 30)


def test_floor_protects_pathological_durations():
    # 10-minute video into 48MB would imply ~0.5Mbps total; floor keeps it watchable.
    assert fit_video_bitrate(48 * MB, 600) == 500_000


def test_zero_duration_does_not_divide_by_zero():
    assert fit_video_bitrate(48 * MB, 0) >= 500_000


def test_higher_cap_scales_bitrate_up():
    # Once the project cap is raised (e.g. 490MB), the same duration gets ~10x the bitrate.
    assert fit_video_bitrate(490 * MB, 35) > 9 * fit_video_bitrate(48 * MB, 35)
