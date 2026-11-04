"""Captions must never leave the frame: karaoke lines can't wrap (WrapStyle 2), so
oversized groups shrink via fit_font_size, and the hook card self-fits too."""

from __future__ import annotations

from cadence.models import Caption, CaptionWord, TextZone
from cadence.synthesis.captions import build_ass_karaoke, build_hook_studio, fit_font_size


def _cap(words: list[str], start=0.0, end=3.0) -> Caption:
    step = (end - start) / max(len(words), 1)
    return Caption(
        text=" ".join(words), start=start, end=end, zone=TextZone.BOTTOM,
        words=tuple(
            CaptionWord(w, start + i * step, start + (i + 1) * step) for i, w in enumerate(words)
        ),
    )


def test_short_text_keeps_base_size():
    assert fit_font_size("HELLO THERE", 62, 1080) == 62


def test_moderately_long_text_shrinks_to_fit_one_line():
    text = "a thirty char karaoke group!!"  # ~29 chars → proportional shrink above the floor
    fs = fit_font_size(text, 62, 1080)
    assert fs < 62
    assert len(text) * 0.58 * fs <= (1080 - 2 * 56) * 1.01  # fits on one line


def test_shrink_respects_floor():
    fs = fit_font_size("x" * 500, 62, 1080, min_scale=0.55)
    assert fs == int(62 * 0.55)


def test_karaoke_overflow_group_gets_fs_override():
    import re

    long_cap = _cap("supercalifragilistic expialidocious antidisestablishmentarianism extraordinary".split())
    short_cap = _cap(["short", "line"])
    ass = build_ass_karaoke([long_cap, short_cap], width=1080, height=1920)
    long_lines = [l for l in ass.splitlines() if "supercalifragilistic" in l]
    assert long_lines and all(re.search(r"\\fs\d+", l) for l in long_lines)  # shrunk
    assert all("\\q1" in l for l in long_lines)  # and wraps rather than ever overflowing
    # the short group keeps the base size: no \fs<digits> (note: \fscx is a different tag)
    short_lines = [l for l in ass.splitlines() if "short" in l]
    assert short_lines and all(not re.search(r"\\fs\d", l) for l in short_lines)


def test_karaoke_margins_widened():
    ass = build_ass_karaoke([_cap(["hi"])], width=1080, height=1920)
    assert ",56,56,40,1" in ass  # MarginL/R = 56


def test_hook_card_self_fits():
    short = build_hook_studio("STOP SCROLLING", width=1080, height=1920)
    long = build_hook_studio(
        "THE UNBELIEVABLY LONG HOOK LINE THAT WOULD ABSOLUTELY RUN OFF THE FRAME EDGE",
        width=1080, height=1920,
    )
    def style_size(doc: str) -> int:
        line = next(l for l in doc.splitlines() if l.startswith("Style: Hook"))
        return int(line.split(",")[2])
    assert style_size(long) < style_size(short)
