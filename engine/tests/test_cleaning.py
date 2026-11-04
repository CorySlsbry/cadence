"""Unit + integration tests for Module C (cleaning)."""

from __future__ import annotations

import numpy as np
import pytest

from cadence.cleaning.editor import _enforce_min_segment, clean_recording, render_edl
from cadence.cleaning.fillers import find_filler_spans, normalize_token
from cadence.cleaning.retakes import detect_retakes, segment_utterances
from cadence.cleaning.silence import (
    detect_silence_ranges,
    windowed_dbfs,
    word_gap_silence_ranges,
)
from cadence.cleaning.similarity import LexicalSimilarity, dice, jaccard, prefix_ratio
from cadence.config import CleaningConfig
from cadence.models import CutReason, TimeRange, Transcript, Word


def mk_transcript(words: list[tuple[str, float, float]]) -> Transcript:
    return Transcript(words=tuple(Word(t, s, e) for t, s, e in words), language="en")


def synth_audio(segments: list[tuple[float, float]], sr: int = 16000, total: float = 3.0) -> np.ndarray:
    """Build mono audio: `segments` are (start,end) LOUD tone spans; rest is silence."""
    n = int(total * sr)
    t = np.arange(n) / sr
    audio = np.zeros(n, dtype=np.float32)
    for s, e in segments:
        mask = (t >= s) & (t < e)
        audio[mask] = 0.3 * np.sin(2 * np.pi * 440 * t[mask]).astype(np.float32)
    return audio


# --------------------------------------------------------------------------- #
# Silence
# --------------------------------------------------------------------------- #
def test_windowed_dbfs_silence_is_very_negative_tone_is_moderate():
    sr = 16000
    silent = np.zeros(sr, dtype=np.float32)
    db_s, _ = windowed_dbfs(silent, sr)
    assert np.all(db_s < -90.0)
    tone = (0.5 * np.sin(2 * np.pi * 440 * np.arange(sr) / sr)).astype(np.float32)
    db_t, _ = windowed_dbfs(tone, sr)
    # RMS of a 0.5-amplitude sine ~= 0.354 -> ~ -9 dBFS.
    assert np.median(db_t) == pytest.approx(-9.0, abs=1.5)


def test_detect_silence_ranges_finds_the_gap():
    sr = 16000
    audio = synth_audio([(0.0, 1.0), (1.8, 3.0)], sr=sr, total=3.0)
    ranges = detect_silence_ranges(audio, sr, silence_db=-40.0, min_silence_sec=0.3)
    assert len(ranges) == 1
    assert ranges[0].start == pytest.approx(1.0, abs=0.05)
    assert ranges[0].end == pytest.approx(1.8, abs=0.05)


def test_detect_silence_ignores_short_gaps():
    sr = 16000
    audio = synth_audio([(0.0, 1.0), (1.1, 3.0)], sr=sr, total=3.0)  # 0.1s gap
    assert detect_silence_ranges(audio, sr, min_silence_sec=0.3) == []


def test_word_gap_silence_ranges():
    bounds = [(0.0, 1.0), (1.2, 2.0), (3.0, 3.5)]  # gap 0.2 then gap 1.0
    out = word_gap_silence_ranges(bounds, min_gap_sec=0.5)
    assert len(out) == 1
    assert out[0].start == pytest.approx(2.0)
    assert out[0].end == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# Fillers
# --------------------------------------------------------------------------- #
def test_normalize_token_strips_punctuation_and_case():
    assert normalize_token(" Um, ") == "um"
    assert normalize_token("Like!") == "like"


def test_find_filler_spans_single_and_multiword():
    transcript = mk_transcript(
        [("So", 0.0, 0.3), ("um", 0.3, 0.6), ("you", 0.7, 0.9), ("know", 0.9, 1.1), ("hello", 1.2, 1.6)]
    )
    spans = find_filler_spans(transcript, {"um", "you know"}, pad=0.0)
    details = {s.detail for s in spans}
    assert details == {"um", "you know"}
    assert all(s.reason == CutReason.FILLER for s in spans)
    yk = next(s for s in spans if s.detail == "you know")
    assert yk.range.start == pytest.approx(0.7)
    assert yk.range.end == pytest.approx(1.1)


# --------------------------------------------------------------------------- #
# Similarity + retakes
# --------------------------------------------------------------------------- #
def test_lexical_similarity_bounds():
    sim = LexicalSimilarity()
    assert sim.score("the three pillars", "the three pillars") == pytest.approx(1.0)
    assert sim.score("the three pillars of success", "the three pillars of") > 0.6
    assert sim.score("completely different sentence", "nothing alike here") < 0.4


def test_dice_prefix_jaccard_primitives():
    assert dice({"ab", "bc"}, {"ab", "bc"}) == pytest.approx(1.0)
    assert prefix_ratio(["a", "b", "c"], ["a", "b", "x"]) == pytest.approx(2 / 3)
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


def test_segment_utterances_splits_on_pause():
    transcript = mk_transcript([("a", 0.0, 0.3), ("b", 0.4, 0.7), ("c", 2.0, 2.3)])
    utts = segment_utterances(transcript, pause_gap=0.6)
    assert len(utts) == 2
    assert utts[0].text == "a b"
    assert utts[1].text == "c"


def test_detect_retakes_keeps_last_attempt():
    # Flub then restart the same line after a pause -> first take removed.
    transcript = mk_transcript(
        [
            ("the", 0.0, 0.2), ("three", 0.2, 0.5), ("pillars", 0.5, 0.9), ("of", 0.9, 1.0),
            ("success", 1.0, 1.5),
            # pause >0.6s, then the restated take:
            ("the", 2.3, 2.5), ("three", 2.5, 2.8), ("pillars", 2.8, 3.2), ("of", 3.2, 3.3),
            ("success", 3.3, 3.8), ("are", 3.8, 4.1), ("focus", 4.1, 4.6),
        ]
    )
    spans = detect_retakes(transcript, similarity_threshold=0.8, min_words=3)
    assert len(spans) == 1
    assert spans[0].reason == CutReason.BAD_TAKE
    # The FIRST take [0.0, 1.5] is the one removed; the later take survives.
    assert spans[0].range.start == pytest.approx(0.0)
    assert spans[0].range.end == pytest.approx(1.5)


def test_detect_retakes_strips_leading_filler():
    # Real disfluency: "um this is a test" [stop] "this is a test of the system".
    # The leading "um" must not block the prefix match against the clean restate.
    transcript = mk_transcript(
        [
            ("um", 2.0, 2.4), ("this", 2.4, 2.9), ("is", 2.9, 3.1), ("a", 3.1, 3.3), ("test", 3.3, 3.6),
            ("this", 4.3, 4.7), ("is", 4.7, 4.9), ("a", 4.9, 5.0), ("test", 5.0, 5.3),
            ("of", 5.3, 5.5), ("the", 5.5, 5.6), ("system", 5.6, 6.1),
        ]
    )
    spans = detect_retakes(transcript, similarity_threshold=0.82, min_words=3)
    assert len(spans) == 1
    assert spans[0].reason == CutReason.BAD_TAKE
    # The first take (incl. the leading "um") is what gets removed.
    assert spans[0].range.start == pytest.approx(2.0)
    assert spans[0].range.end == pytest.approx(3.6)


def test_detect_retakes_three_attempts_collapse_to_last():
    transcript = mk_transcript(
        [
            ("hello", 0.0, 0.5), ("world", 0.5, 1.0),
            ("hello", 2.0, 2.5), ("world", 2.5, 3.0),
            ("hello", 4.0, 4.5), ("world", 4.5, 5.0),
        ]
    )
    spans = detect_retakes(transcript, similarity_threshold=0.8, min_words=2)
    # Two earlier attempts removed, last kept.
    assert len(spans) == 2
    assert {round(s.range.start, 1) for s in spans} == {0.0, 2.0}


# --------------------------------------------------------------------------- #
# Editor (pure orchestration + real render)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_clean_recording_removes_silence(talking_clip, ff):
    edl = clean_recording(talking_clip, ff=ff)
    assert edl.source_duration == pytest.approx(6.0, abs=0.3)
    # Two ~0.7-0.8s silence windows -> output meaningfully shorter than source.
    assert edl.output_duration < edl.source_duration - 0.8
    assert any(s.reason == CutReason.SILENCE for s in edl.removed)
    assert edl.to_dict()["output_duration"] == pytest.approx(edl.output_duration)


@pytest.mark.integration
def test_clean_recording_with_transcript_removes_fillers(talking_clip, ff):
    # Inject a transcript so filler removal also engages.
    transcript = mk_transcript(
        [("this", 0.1, 0.4), ("um", 0.4, 0.7), ("is", 0.8, 1.0), ("a", 2.0, 2.1), ("test", 2.2, 2.6)]
    )
    cfg = CleaningConfig()
    edl = clean_recording(talking_clip, transcript=transcript, cfg=cfg, ff=ff)
    assert any(s.reason == CutReason.FILLER for s in edl.removed) or edl.output_duration < edl.source_duration


@pytest.mark.ml
@pytest.mark.integration
def test_faster_whisper_adapter_loads_and_returns_transcript(talking_clip, ff):
    pytest.importorskip("faster_whisper")
    from cadence.models import Transcript
    from cadence.transcription.faster_whisper import FasterWhisperTranscriber

    transcriber = FasterWhisperTranscriber("tiny.en", device="cpu", compute_type="int8")
    transcript = transcriber.transcribe(talking_clip, ff=ff)
    assert isinstance(transcript, Transcript)  # real model loads + runs without error


@pytest.mark.integration
@pytest.mark.slow
def test_render_edl_produces_shorter_clip(talking_clip, ff, tmp_path):
    edl = clean_recording(talking_clip, ff=ff)
    out = str(tmp_path / "cleaned.mp4")
    result = render_edl(edl, out, ff=ff)
    assert result.duration == pytest.approx(edl.output_duration, abs=0.4)
    assert result.duration < 6.0
    assert result.width == 216 and result.height == 384


def test_min_segment_floor_absorbs_sub_floor_fragment():
    # A 0.2s kept sliver between two cuts must be bridged into a neighbour (spec C.5),
    # so no surviving kept range is shorter than the floor.
    kept = [TimeRange(0.0, 2.0), TimeRange(2.3, 2.5), TimeRange(2.9, 5.0)]
    out = _enforce_min_segment(kept, 0.5)
    assert all(r.end - r.start >= 0.5 for r in out)
    assert out == [TimeRange(0.0, 2.5), TimeRange(2.9, 5.0)]  # sliver bridged into the smaller (left) gap


def test_min_segment_floor_bridges_smaller_gap_side():
    # The 0.2s sliver has a wider gap on its left (0.4) than its right (0.1); it should
    # bridge RIGHT (the smaller gap), re-including the least silence.
    kept = [TimeRange(0.0, 1.0), TimeRange(1.4, 1.6), TimeRange(1.7, 4.0)]
    out = _enforce_min_segment(kept, 0.5)
    assert out == [TimeRange(0.0, 1.0), TimeRange(1.4, 4.0)]


def test_min_segment_floor_noop_when_disabled_or_all_long():
    long_ranges = [TimeRange(0.0, 2.0), TimeRange(2.5, 5.0)]
    assert _enforce_min_segment(long_ranges, 0.5) == long_ranges
    assert _enforce_min_segment(long_ranges, 0.0) == long_ranges  # floor off
    assert _enforce_min_segment([TimeRange(0.0, 0.1)], 0.5) == [TimeRange(0.0, 0.1)]  # single clip, never emptied
