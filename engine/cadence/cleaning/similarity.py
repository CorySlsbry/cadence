"""Phrase-similarity scorers for retake detection (ports-and-adapters).

Default :class:`LexicalSimilarity` needs no ML and catches verbatim/near-verbatim
restarts (the common "flub then restate the same line" case) via char 3-gram Dice +
token prefix + token Jaccard. :class:`SemanticSimilarity` (optional, sentence-
transformers) upgrades recall on paraphrased restates. The research is explicit:
embeddings-only is fragile, so the lexical signal is the floor, semantic is additive.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cadence.cleaning.fillers import normalize_token


@runtime_checkable
class SimilarityScorer(Protocol):
    def score(self, a: str, b: str) -> float: ...


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    s = "".join(text.split())
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def dice(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return 2 * inter / (len(a) + len(b))


def _tokens(text: str) -> list[str]:
    return [t for t in (normalize_token(w) for w in text.split()) if t]


def prefix_ratio(a_tokens: list[str], b_tokens: list[str]) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    common = 0
    for x, y in zip(a_tokens, b_tokens):
        if x == y:
            common += 1
        else:
            break
    return common / min(len(a_tokens), len(b_tokens))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class LexicalSimilarity:
    """Composite lexical similarity in [0, 1] — the max of three robust signals."""

    def score(self, a: str, b: str) -> float:
        ta, tb = _tokens(a), _tokens(b)
        d = dice(_char_ngrams(a.lower()), _char_ngrams(b.lower()))
        p = prefix_ratio(ta, tb)
        j = jaccard(set(ta), set(tb))
        return max(d, p, j)


class SemanticSimilarity:
    """Optional sentence-transformers cosine similarity. Requires the `ml` extra."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(model_name)

    def score(self, a: str, b: str) -> float:
        import numpy as np

        emb = self._model.encode([a, b], normalize_embeddings=True)
        return float(np.dot(emb[0], emb[1]))
