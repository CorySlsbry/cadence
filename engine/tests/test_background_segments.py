"""Unit tests for dynamic-background segment tiling (`_background_segments`).

Pure logic: given per-moment b-roll inserts + a total duration, each image must tile from
its own start to the next image's start (first clamped to 0, last extended to the duration)
so the matted speaker never sits over an empty background.
"""

from dataclasses import dataclass

from cadence.matte.replace import _background_segments


@dataclass
class _Ins:
    image_path: str
    start: float
    end: float = 0.0


def test_tiles_to_next_start_first_clamped_last_extended():
    inserts = [_Ins("a.png", 1.0), _Ins("b.png", 3.0), _Ins("c.png", 7.0)]
    # a: 0->3 (next start), b: 3->7, c: 7->10 (duration)
    assert _background_segments(inserts, 10.0) == [("a.png", 3.0), ("b.png", 4.0), ("c.png", 3.0)]


def test_single_insert_covers_full_duration():
    assert _background_segments([_Ins("a.png", 2.0)], 8.0) == [("a.png", 8.0)]


def test_unsorted_inserts_are_ordered_by_start():
    inserts = [_Ins("c.png", 7.0), _Ins("a.png", 1.0), _Ins("b.png", 3.0)]
    assert _background_segments(inserts, 10.0) == [("a.png", 3.0), ("b.png", 4.0), ("c.png", 3.0)]


def test_empty_inserts_yield_no_segments():
    assert _background_segments([], 10.0) == []


def test_zero_length_windows_are_dropped():
    # a and b share a start -> a's window is 0-length and dropped; b and c tile the rest
    inserts = [_Ins("a.png", 0.0), _Ins("b.png", 0.0), _Ins("c.png", 5.0)]
    assert _background_segments(inserts, 10.0) == [("b.png", 5.0), ("c.png", 5.0)]


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
