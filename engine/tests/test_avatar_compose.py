"""Tests for avatar presenter framing/anchor logic (cadence.avatar.compose)."""

from __future__ import annotations

import pytest

from cadence.avatar.compose import FRAMINGS, _overlay_xy


def test_framings_ordered_by_size():
    assert set(FRAMINGS) == {"full", "lower_third", "corner"}
    assert FRAMINGS["full"].scale == 1.0
    assert 0 < FRAMINGS["corner"].scale < FRAMINGS["lower_third"].scale < 1.0


@pytest.mark.parametrize(
    "anchor,expected",
    [
        ("center", "(main_w-overlay_w)/2:(main_h-overlay_h)/2"),
        ("br", "main_w-overlay_w-48:main_h-overlay_h-48"),
        ("tr", "main_w-overlay_w-48:48"),
        ("bc", "(main_w-overlay_w)/2:main_h-overlay_h-48"),
        ("garbage", "(main_w-overlay_w)/2:(main_h-overlay_h)/2"),  # safe default
    ],
)
def test_overlay_xy(anchor, expected):
    assert _overlay_xy(anchor, 48) == expected
