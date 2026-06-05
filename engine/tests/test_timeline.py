"""Unit tests for the pure timeline/interval math."""

from __future__ import annotations

import pytest

from cadence.models import TimeRange
from cadence.timeline import (
    clamp_range,
    frame_snap,
    invert_to_keep,
    merge_spans,
    snap_ranges,
    total_duration,
)


def test_frame_snap_rounds_to_nearest_frame():
    assert frame_snap(0.51, 30.0) == pytest.approx(round(0.51 * 30) / 30)
    assert frame_snap(1.0, 0.0) == 1.0  # guard against zero fps


def test_merge_spans_unions_overlaps_and_adjacency():
    spans = [TimeRange(0, 2), TimeRange(1.5, 3), TimeRange(5, 6)]
    merged = merge_spans(spans)
    assert [(r.start, r.end) for r in merged] == [(0, 3), (5, 6)]


def test_merge_spans_respects_gap_join():
    spans = [TimeRange(0, 1), TimeRange(1.05, 2)]
    assert len(merge_spans(spans, gap=0.1)) == 1
    assert len(merge_spans(spans, gap=0.0)) == 2


def test_invert_to_keep_is_complement():
    removed = [TimeRange(1, 2), TimeRange(4, 5)]
    keep = invert_to_keep(removed, duration=6.0)
    assert [(r.start, r.end) for r in keep] == [(0, 1), (2, 4), (5, 6)]


def test_invert_to_keep_empty_removed_keeps_all():
    keep = invert_to_keep([], duration=6.0)
    assert [(r.start, r.end) for r in keep] == [(0, 6)]


def test_clamp_range_drops_zero_width():
    assert clamp_range(TimeRange(5, 5), 0, 10) is None
    r = clamp_range(TimeRange(-1, 3), 0, 10)
    assert r is not None and (r.start, r.end) == (0, 3)


def test_snap_and_total_duration():
    ranges = [TimeRange(0.0, 1.0), TimeRange(2.0, 2.5)]
    assert total_duration(snap_ranges(ranges, 30.0)) == pytest.approx(1.5, abs=0.05)
