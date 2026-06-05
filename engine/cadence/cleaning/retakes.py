"""§3 Module C.1 — bad-take / retake detection.

Segment the transcript into pause-separated utterances, compare nearby utterances,
and when a line is restated, keep only the LAST attempt (Descript behaviour).
Union-find collapses 3+ attempts (A,B,C) into one cluster so only C survives.
Precision-first: deleting the wrong take is catastrophic.
"""

from __future__ import annotations

from dataclasses import dataclass

from cadence.cleaning.similarity import LexicalSimilarity, SimilarityScorer
from cadence.cleaning.fillers import normalize_token
from cadence.config import DEFAULT_FILLERS
from cadence.models import CutReason, RemovedSpan, TimeRange, Transcript, Word


def _comparison_text(text: str, fillers: frozenset[str] | set[str]) -> str:
    """Normalize an utterance for similarity scoring: drop fillers, lower-case.

    Stripping fillers is what lets a false-start like "um this is a test" match the
    clean restate "this is a test of ..." — without it the leading "um" destroys the
    prefix signal (the research's flagged disfluency case).
    """
    toks = [normalize_token(w) for w in text.split()]
    return " ".join(t for t in toks if t and t not in fillers)


@dataclass(frozen=True, slots=True)
class Utterance:
    words: tuple[Word, ...]
    index: int

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def token_count(self) -> int:
        return sum(1 for w in self.words if normalize_token(w.text))


def segment_utterances(transcript: Transcript, *, pause_gap: float = 0.6) -> list[Utterance]:
    """Split words into utterances wherever the inter-word gap exceeds ``pause_gap``."""
    utterances: list[Utterance] = []
    bucket: list[Word] = []
    for w in transcript.words:
        if bucket and (w.start - bucket[-1].end) > pause_gap:
            utterances.append(Utterance(tuple(bucket), len(utterances)))
            bucket = []
        bucket.append(w)
    if bucket:
        utterances.append(Utterance(tuple(bucket), len(utterances)))
    return utterances


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def detect_retakes(
    transcript: Transcript,
    *,
    scorer: SimilarityScorer | None = None,
    similarity_threshold: float = 0.82,
    min_words: int = 3,
    max_gap_sec: float = 6.0,
    window: int = 6,
    pause_gap: float = 0.6,
    strip_fillers: frozenset[str] | set[str] = frozenset(DEFAULT_FILLERS),
) -> list[RemovedSpan]:
    scorer = scorer or LexicalSimilarity()
    utts = segment_utterances(transcript, pause_gap=pause_gap)
    n = len(utts)
    if n < 2:
        return []

    fillers = set(strip_fillers)
    compare_text = [_comparison_text(u.text, fillers) for u in utts]
    # Effective token count excludes fillers, so a "um this is a test" still gates.
    eff_tokens = [len(t.split()) if t else 0 for t in compare_text]

    uf = _UnionFind(n)
    flagged = False
    for i in range(n):
        if eff_tokens[i] < min_words:
            continue
        for j in range(i + 1, min(i + 1 + window, n)):
            if eff_tokens[j] < min_words:
                continue
            if utts[j].start - utts[i].end > max_gap_sec:
                break
            if scorer.score(compare_text[i], compare_text[j]) >= similarity_threshold:
                uf.union(i, j)
                flagged = True
    if not flagged:
        return []

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    spans: list[RemovedSpan] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        keep = max(members, key=lambda k: utts[k].start)  # keep the LAST attempt
        for k in members:
            if k == keep:
                continue
            u = utts[k]
            spans.append(
                RemovedSpan(
                    range=TimeRange(round(u.start, 3), round(u.end, 3)),
                    reason=CutReason.BAD_TAKE,
                    detail=f"retake; superseded by utterance #{utts[keep].index}",
                )
            )
    spans.sort(key=lambda s: s.range.start)
    return spans
