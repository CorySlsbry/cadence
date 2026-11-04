"""§3 Module C.2 — vocal filler scrubbing from a word-timed transcript.

Pure: operates on a :class:`Transcript`, returns removal spans. Supports
multi-word discourse markers ("you know", "i mean") via a longest-match scan.
"""

from __future__ import annotations

from cadence.models import RemovedSpan, TimeRange, CutReason, Transcript, Word


def normalize_token(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == "'").strip("'")


def find_filler_spans(
    transcript: Transcript,
    filler_set: frozenset[str] | set[str] | tuple[str, ...],
    *,
    pad: float = 0.04,
) -> list[RemovedSpan]:
    """Return removal spans for every word/phrase in ``filler_set``.

    Multi-word fillers are matched greedily (longest first) over consecutive words.
    """
    words: list[Word] = list(transcript.words)
    fillers = {f.lower() for f in filler_set}
    max_len = max((len(f.split()) for f in fillers), default=1)
    norm = [normalize_token(w.text) for w in words]

    spans: list[RemovedSpan] = []
    i = 0
    while i < len(words):
        matched = False
        for span_len in range(min(max_len, len(words) - i), 0, -1):
            phrase = " ".join(norm[i : i + span_len]).strip()
            if phrase and phrase in fillers:
                start = max(0.0, words[i].start - pad)
                end = words[i + span_len - 1].end + pad
                spans.append(
                    RemovedSpan(
                        range=TimeRange(round(start, 3), round(end, 3)),
                        reason=CutReason.FILLER,
                        detail=phrase,
                    )
                )
                i += span_len
                matched = True
                break
        if not matched:
            i += 1
    return spans
