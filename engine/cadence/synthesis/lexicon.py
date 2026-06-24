"""Caption text correction: fix ASR errors before they reach the screen.

Two problems this solves, in order of importance:
1. BRAND / KEY-TERM mangling — ASR hears "CloutHook" as "cloud hook" / "cloud hoock"
   / "clouthoook". A fuzzy, timing-preserving pass force-corrects those back to the
   canonical spelling. Multi-word mishears ("cloud hoock") are merged into ONE timed
   word so karaoke captions still animate correctly.
2. Ordinary misspellings — a CONSERVATIVE dictionary pass fixes obvious single-word
   typos (edit-distance 1, lowercase, non-dictionary) without touching proper nouns,
   acronyms, brand terms, or the speaker's real word choices. Optional: degrades to a
   no-op if `pyspellchecker` isn't installed (the brand pass always runs).

Operates on the `(text, start, end)` word tuples the caption grouper consumes, so the
fix lands on EVERY caption path (karaoke + legacy) from one chokepoint, and timings are
preserved (a merged brand term spans its source words' interval).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

WordTup = tuple[str, float, float]

# The app's own brand is always protected. Callers may add the creator's brand/product
# names via `custom_terms` so each creator's terms are spelled right too.
DEFAULT_BRAND_TERMS: tuple[str, ...] = ("CloutHook",)

_MAX_WINDOW = 3  # most multi-word brand mishears span ≤ 3 ASR tokens


def _despace(s: str) -> str:
    """Lowercase, alphanumerics only — the comparison form for fuzzy brand matching."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _brand_threshold(canon_len: int) -> int:
    """Allowed edit distance scales with term length (short terms must match tighter)."""
    if canon_len <= 6:
        return 1
    if canon_len <= 12:
        return 2
    return 3


_speller_cache: list = []  # [SpellChecker|None] memo so we import/build at most once


def _get_speller():
    if _speller_cache:
        return _speller_cache[0]
    sp = None
    try:  # pyspellchecker is optional — brand correction never depends on it
        from spellchecker import SpellChecker

        sp = SpellChecker()  # default edit distance 2 — catches transpositions (recieve→receive)
    except Exception:  # noqa: BLE001 - any failure → general spell pass is simply skipped
        sp = None
    _speller_cache.append(sp)
    return sp


_LOWER_WORD = re.compile(r"^([a-z]+)([.,!?;:'\"-]*)$")


def _spell_one(text: str, protected: set[str]) -> str:
    """Conservatively correct ONE token. Only touches a simple all-lowercase word of
    >3 letters that the dictionary doesn't know and has a single edit-1 correction —
    so proper nouns (capitalized), ALL-CAPS acronyms, numbers, and real words are left
    exactly as spoken."""
    sp = _get_speller()
    if sp is None:
        return text
    m = _LOWER_WORD.match(text)
    if not m:
        return text
    word, trailing = m.group(1), m.group(2)
    if len(word) <= 3 or word in protected:
        return text
    if not sp.unknown([word]):  # dictionary already knows it → leave it
        return text
    corr = sp.correction(word)
    if corr and corr != word and _levenshtein(word, corr) <= 2:
        return corr + trailing
    return text


def correct_words_out(
    words_out: list[WordTup],
    *,
    brand_terms: Sequence[str] = DEFAULT_BRAND_TERMS,
    custom_terms: Sequence[str] | None = None,
    spellcheck: bool = True,
) -> list[WordTup]:
    """Return a corrected copy of the ``(text, start, end)`` word list.

    Brand pass runs always (timing-preserving, merges multi-word mishears); the general
    spell pass is conservative and optional. Clean input (e.g. a written faceless script)
    passes through unchanged."""
    terms = [t for t in (list(brand_terms) + list(custom_terms or [])) if t and t.strip()]
    canon = [(t, _despace(t)) for t in terms]
    canon = [(disp, cf) for disp, cf in canon if cf]
    protected = {_despace(t) for _, t in canon} | {t.lower() for t, _ in canon}

    out: list[WordTup] = []
    n = len(words_out)
    i = 0
    while i < n:
        matched = False
        # Prefer the longest window so "cloud hoock" beats a 1-word partial.
        for win in range(min(_MAX_WINDOW, n - i), 0, -1):
            group = words_out[i : i + win]
            joined = _despace("".join(w[0] for w in group))
            if len(joined) < 3:
                continue
            for display, cform in canon:
                thr = _brand_threshold(len(cform))
                # length guard stops short tokens from fuzzily matching long brands
                if abs(len(joined) - len(cform)) <= thr and _levenshtein(joined, cform) <= thr:
                    out.append((display, group[0][1], group[-1][2]))
                    i += win
                    matched = True
                    break
            if matched:
                break
        if matched:
            continue
        w = words_out[i]
        text = _spell_one(w[0], protected) if spellcheck else w[0]
        out.append((text, w[1], w[2]))
        i += 1
    return out
