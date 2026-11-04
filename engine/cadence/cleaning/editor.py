"""Module C orchestrator — fuse silence + filler + retake removal into one EDL."""

from __future__ import annotations

from cadence.cleaning.fillers import find_filler_spans
from cadence.cleaning.retakes import detect_retakes
from cadence.cleaning.silence import (
    detect_silence_ranges,
    word_gap_silence_ranges,
)
from cadence.cleaning.similarity import SimilarityScorer
from cadence.config import AGGRESSIVE_FILLERS, DEFAULT_FILLERS, CleaningConfig
from cadence.analysis.frames import extract_audio
from cadence.errors import CleaningError
from cadence.ffmpeg.builder import build_cut_concat
from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import (
    CutReason,
    EditDecisionList,
    RemovedSpan,
    RenderResult,
    TimeRange,
    Transcript,
)
from cadence.timeline import clamp_range, invert_to_keep, merge_spans, snap_ranges
from cadence.transcription.base import Transcriber


def _shrink_asym(r: TimeRange, after: float, before: float) -> TimeRange | None:
    """Pad a silence span asymmetrically: keep ``after`` of the preceding word's
    decay and ``before`` of the breath before the next word (so cuts don't clip)."""
    start, end = r.start + after, r.end - before
    if end - start <= 1e-3:
        return None
    return TimeRange(round(start, 3), round(end, 3))


def _snap_off_words(span: TimeRange, words: list[tuple[float, float]]) -> TimeRange | None:
    """Trim a removed span so its edges land in inter-word gaps — never mid-word —
    and so it never swallows a whole word. The #1 fix for "cuts off words"."""
    s, e = span.start, span.end
    for ws, we in words:
        if ws < s < we:   # leading edge sits inside a word -> push past its end
            s = we
        if ws < e < we:   # trailing edge sits inside a word -> pull back to its start
            e = ws
    for ws, we in words:  # a whole word inside the span -> stop the cut before it
        if s < ws and we < e:
            e = ws
            break
    if e - s <= 1e-3:
        return None
    return TimeRange(round(s, 3), round(e, 3))


def _enforce_min_segment(kept: list[TimeRange], floor: float) -> list[TimeRange]:
    """Absorb micro kept-clips shorter than ``floor`` by bridging the smaller adjacent
    removed gap into a neighbour, so a 0.2s sliver between two cuts stops strobing.

    Re-including a *tiny* silence is the right trade: a sub-floor flash reads as a
    stutter, whereas the bridged gap is imperceptible. Cascades are handled by the loop
    (two adjacent slivers merge into one segment, re-checked against the floor)."""
    if floor <= 0 or len(kept) <= 1:
        return kept
    ranges = [TimeRange(r.start, r.end) for r in kept]
    changed = True
    while changed and len(ranges) > 1:
        changed = False
        for i, r in enumerate(ranges):
            if r.end - r.start >= floor:
                continue
            left_gap = (r.start - ranges[i - 1].end) if i > 0 else float("inf")
            right_gap = (ranges[i + 1].start - r.end) if i < len(ranges) - 1 else float("inf")
            if left_gap <= right_gap and i > 0:
                ranges[i - 1] = TimeRange(ranges[i - 1].start, r.end)
                ranges.pop(i)
            elif i < len(ranges) - 1:
                ranges[i + 1] = TimeRange(r.start, ranges[i + 1].end)
                ranges.pop(i)
            else:  # the only neighbour is itself too short and on the closed side — keep as-is
                continue
            changed = True
            break
    return ranges


def clean_recording(
    path: str,
    *,
    transcript: Transcript | None = None,
    transcriber: Transcriber | None = None,
    cfg: CleaningConfig | None = None,
    ff: FFmpeg | None = None,
    scorer: SimilarityScorer | None = None,
    audio_sample_rate: int = 16000,
) -> EditDecisionList:
    """Produce an :class:`EditDecisionList` of KEEP ranges for a raw recording.

    Works with or without a transcript: silence removal needs only the waveform;
    filler + retake removal additionally need word timings (supply ``transcript``
    directly or a ``transcriber`` to generate one).
    """
    cfg = cfg or CleaningConfig()
    ff = ff or FFmpeg()
    media = probe_media(path, ff)
    duration = media.duration
    if duration <= 0:
        raise CleaningError(f"recording has non-positive duration: {path}")
    fps = media.fps if media.fps > 0 else 30.0

    if transcript is None and transcriber is not None and media.has_audio:
        transcript = transcriber.transcribe(path, ff=ff)

    removed: list[RemovedSpan] = []
    word_bounds = [(w.start, w.end) for w in transcript.words] if (transcript and transcript.words) else []

    def _silence_span(r: TimeRange) -> TimeRange | None:
        shrunk = _shrink_asym(r, cfg.after_pad_sec, cfg.before_pad_sec)
        if shrunk and cfg.snap_cuts_to_words and word_bounds:
            shrunk = _snap_off_words(shrunk, word_bounds)
        return shrunk

    # 1) Silence from the waveform (RMS/dBFS).
    if media.has_audio and cfg.remove_silence:
        audio, sr = extract_audio(path, sample_rate=audio_sample_rate, ff=ff)
        for r in detect_silence_ranges(
            audio, sr, silence_db=cfg.silence_db, min_silence_sec=cfg.min_silence_sec
        ):
            shrunk = _silence_span(r)
            if shrunk:
                removed.append(RemovedSpan(shrunk, CutReason.SILENCE))

    # 2) Silence from transcript word gaps (catches pauses the RMS floor misses).
    if word_bounds and cfg.remove_silence:
        for r in word_gap_silence_ranges(word_bounds, min_gap_sec=cfg.min_silence_sec + 0.2):
            shrunk = _silence_span(r)
            if shrunk:
                removed.append(RemovedSpan(shrunk, CutReason.SILENCE, "word-gap"))

    # 3) Filler words.
    if transcript and cfg.remove_fillers:
        fillers = set(DEFAULT_FILLERS)
        if cfg.aggressive_fillers:
            fillers |= set(AGGRESSIVE_FILLERS)
        removed.extend(find_filler_spans(transcript, fillers, pad=cfg.filler_pad_sec))

    # 4) Bad-take / retake removal.
    if transcript and cfg.detect_retakes:
        removed.extend(
            detect_retakes(
                transcript,
                scorer=scorer,
                similarity_threshold=cfg.retake_similarity,
                min_words=cfg.retake_min_words,
                max_gap_sec=cfg.retake_max_gap_sec,
                window=6,
            )
        )

    # Clamp + frame-snap removed spans, then invert to KEEP.
    clamped: list[TimeRange] = []
    for span in removed:
        c = clamp_range(span.range, 0.0, duration)
        if c:
            clamped.append(c)
    # Merge with a small gap so a sub-word fragment between two cuts is absorbed
    # rather than flashed as a choppy micro-clip.
    merged_removed = merge_spans(clamped, gap=0.08)
    kept = snap_ranges(invert_to_keep(merged_removed, duration), fps)
    # Absorb sub-floor micro-clips so the result doesn't strobe (spec C.5).
    kept = _enforce_min_segment(kept, cfg.min_kept_segment_sec)
    if not kept:  # never produce an empty edit
        kept = [TimeRange(0.0, duration)]

    # Rebuild the canonical removed list (the actual gaps between kept ranges) for the report.
    canonical_removed = _diff_removed(removed, kept, duration)

    return EditDecisionList(
        source=path,
        source_duration=duration,
        kept=tuple(kept),
        removed=tuple(canonical_removed),
        transcript=transcript,
    )


# A meaningful edit (a removed take / scrubbed filler) should be surfaced even when
# it overlaps ambient silence, so attribute by priority, not just by overlap area.
_REASON_PRIORITY = {CutReason.BAD_TAKE: 3, CutReason.FILLER: 2, CutReason.LEAD_TRIM: 1, CutReason.SILENCE: 0}


def _diff_removed(
    original: list[RemovedSpan], kept: list[TimeRange], duration: float
) -> list[RemovedSpan]:
    """Attribute each actually-removed gap to its most meaningful overlapping reason."""
    kept_ranges = merge_spans(list(kept))
    gaps = invert_to_keep(kept_ranges, duration)  # the complement of kept = removed
    result: list[RemovedSpan] = []
    for gap in gaps:
        best_key = (-1, 0.0)  # (reason priority, overlap)
        reason, detail = CutReason.SILENCE, ""
        for span in original:
            overlap = min(gap.end, span.range.end) - max(gap.start, span.range.start)
            if overlap <= 0:
                continue
            key = (_REASON_PRIORITY[span.reason], overlap)
            if key > best_key:
                best_key, reason, detail = key, span.reason, span.detail
        result.append(RemovedSpan(gap, reason, detail))
    return result


def render_edl(
    edl: EditDecisionList,
    out_path: str,
    *,
    ff: FFmpeg | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
    crf: int = 18,
) -> RenderResult:
    """Materialise the cleaned clip from an EDL (trim/concat, software encode)."""
    ff = ff or FFmpeg()
    media = probe_media(edl.source, ff)
    graph, vlabel, alabel = build_cut_concat(list(edl.kept), has_audio=media.has_audio)
    args = ["-y", "-i", edl.source, "-filter_complex", graph, "-map", vlabel]
    if alabel:
        args += ["-map", alabel]
    args += [
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if alabel:
        args += ["-c:a", "aac", "-b:a", "160k"]
    args.append(out_path)
    ff.run(args, timeout=600)

    out = probe_media(out_path, ff)
    return RenderResult(
        output_path=out_path,
        width=out.width,
        height=out.height,
        fps=out.fps,
        duration=out.duration,
        codec=out.codec,
        used_hardware=False,
        encoder="libx264",
        command=args,
    )
