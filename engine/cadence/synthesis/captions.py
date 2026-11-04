"""Animated caption (.ass) generation.

`force_style` on an SRT cannot animate, so premium captions are authored as a real
Advanced SubStation Alpha file: `\\fad(in,out)` for FADE, `\\fscx0\\fscy0\\t(...)`
scale-pop for POP, `\\an5\\pos(cx,cy)` for exact zone placement. Colours are ASS
`&HAABBGGRR&` (alpha-inverted), which is the #1 caption-colour footgun.
"""

from __future__ import annotations

from cadence.models import Caption, CaptionStyle, RGBColor, TextZone


def _ass_color(color: RGBColor, alpha: int = 0) -> str:
    """RGB -> ASS &HAABBGGRR& (alpha 0 = opaque, 255 = transparent)."""
    return f"&H{alpha:02X}{color.b:02X}{color.g:02X}{color.r:02X}&"


def _ass_time(t: float) -> str:
    # Round to centiseconds FIRST, then derive fields so a carry propagates — else
    # independent rounding can emit an out-of-spec seconds=60 (e.g. "0:00:60.00").
    cs = round(max(0.0, t) * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{c:02d}"


def _escape_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(
    captions: list[Caption],
    *,
    width: int,
    height: int,
    font_name: str = "Arial",
    font_size: int | None = None,
    primary: RGBColor = RGBColor(255, 255, 255),
    outline: RGBColor = RGBColor(0, 0, 0),
    fade_ms: int = 200,
    pop_ms: int = 180,
    letterbox: bool = False,
) -> str:
    """Render a complete .ass document for the given captions.

    When ``letterbox`` is set, BOTTOM-zone captions are lifted above the 2.39:1 bottom
    bar (which sits at 0.87*height and is drawn last) so they stay fully legible."""
    bottom_safe_y = 0.74  # above the bottom letterbox bar with margin
    font_size = font_size or max(24, round(height * 0.05))
    outline_w = max(2, round(font_size * 0.06))
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 1\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cadence,{font_name},{font_size},{_ass_color(primary)},{_ass_color(outline)},"
        f"&H64000000&,1,0,0,0,100,100,0,0,1,{outline_w},2,5,56,56,40,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    for cap in captions:
        cx = width // 2
        anchor_y = cap.zone.anchor_y
        if letterbox and cap.zone == TextZone.BOTTOM:
            anchor_y = min(anchor_y, bottom_safe_y)
        cy = round(anchor_y * height)
        if cap.style == CaptionStyle.POP:
            tag = f"{{\\an5\\pos({cx},{cy})\\fscx0\\fscy0\\t(0,{pop_ms},\\fscx100\\fscy100)}}"
        else:  # FADE
            tag = f"{{\\an5\\pos({cx},{cy})\\fad({fade_ms},{fade_ms})}}"
        text = tag + _escape_text(cap.text)
        lines.append(
            f"Dialogue: 0,{_ass_time(cap.start)},{_ass_time(cap.end)},Cadence,,0,0,0,,{text}\n"
        )
    return "".join(lines)


_KEYWORD_STOPWORDS = frozenset(
    "the a an and or but so if then this that these those is are was were be been being am "
    "to of in on at for with from by as into about over under just very really more most "
    "you your we our they them he she it its his her my me i do does did have has had will "
    "would can could should may might not no yes here there what when how why who".split()
)


def pick_keywords(word_texts: list[str]) -> set[int]:
    """Indices of the words worth emphasizing in a caption line: content words (>= 4 letters,
    not a function word). Falls back to the single longest token so every line has an accent.
    Pure + deterministic."""
    cleaned = ["".join(ch for ch in w.lower() if ch.isalnum()) for w in word_texts]
    keys = {i for i, c in enumerate(cleaned) if len(c) >= 4 and c not in _KEYWORD_STOPWORDS}
    if not keys:
        nonempty = [i for i, c in enumerate(cleaned) if c]
        if nonempty:
            keys.add(max(nonempty, key=lambda j: len(cleaned[j])))
    return keys


def fit_font_size(
    text: str,
    base_size: int,
    width: int,
    *,
    margin: int = 56,
    min_scale: float = 0.55,
) -> int:
    """Font size that keeps ``text`` on ONE line inside the frame.

    ASS karaoke lines can't wrap (WrapStyle 2), so a long group at full size runs off
    screen. Bold Arial averages ~0.58em per character; when the estimated line width
    exceeds the usable width the size shrinks proportionally, floored at ``min_scale``
    so captions never become unreadably small."""
    usable = max(width - 2 * margin, 50)
    est = len(text) * 0.58 * base_size
    if est <= usable:
        return base_size
    return max(int(base_size * usable / est), int(base_size * min_scale))


def build_ass_karaoke(
    captions: list[Caption],
    *,
    width: int,
    height: int,
    font_name: str = "Arial",
    font_size: int | None = None,
    primary: RGBColor = RGBColor(255, 255, 255),
    outline: RGBColor = RGBColor(0, 0, 0),
    keyword: RGBColor = RGBColor(110, 123, 255),
    active_scale: int = 126,
    pop_ms: int = 120,
    letterbox: bool = False,
) -> str:
    """Per-word "karaoke" captions: the whole line is shown and the currently-spoken word
    scale-pops + recolors as it's said (keyword words stay accented). Each word interval is
    its own ASS event at the same position, so the line reads static while the active word
    pops through it. A caption with no ``words`` falls back to one static line (so a plan that
    mixes karaoke + legacy captions still renders — the back-compat contract)."""
    bottom_safe_y = 0.74
    font_size = font_size or max(28, round(height * 0.058))
    outline_w = max(2, round(font_size * 0.06))
    pri, out, kw = _ass_color(primary), _ass_color(outline), _ass_color(keyword)
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cadence,{font_name},{font_size},{pri},{out},&H64000000&,1,0,0,0,100,100,0,0,1,"
        f"{outline_w},2,5,56,56,40,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    for cap in captions:
        cx = width // 2
        anchor_y = cap.zone.anchor_y
        if letterbox and cap.zone == TextZone.BOTTOM:
            anchor_y = min(anchor_y, bottom_safe_y)
        cy = round(anchor_y * height)
        # Karaoke lines can't wrap — shrink the font when a group would overflow the
        # frame; if even the floored size can't fit (pathological text), allow that one
        # line to smart-wrap (\q1) so it can NEVER leave the frame.
        group_text = " ".join(w.text for w in cap.words) if cap.words else cap.text
        fs = fit_font_size(group_text, font_size, width)
        fs_tag = f"\\fs{fs}" if fs != font_size else ""
        if len(group_text) * 0.58 * fs > (width - 2 * 56):
            fs_tag += "\\q1"
        pos = f"{{\\an5\\pos({cx},{cy}){fs_tag}}}"
        words = cap.words
        if not words:  # back-compat: a wordless caption renders as a single static line
            lines.append(
                f"Dialogue: 0,{_ass_time(cap.start)},{_ass_time(cap.end)},Cadence,,0,0,0,,"
                f"{pos}{_escape_text(cap.text)}\n"
            )
            continue
        kw_idx = pick_keywords([w.text for w in words])
        n = len(words)
        for i, w in enumerate(words):
            seg_start = w.start
            seg_end = words[i + 1].start if i + 1 < n else cap.end
            if seg_end - seg_start <= 0.02:
                seg_end = seg_start + 0.06
            parts = []
            for j, wj in enumerate(words):
                t = _escape_text(wj.text)
                if j == i:  # the word being spoken: pop up in scale + accent colour
                    parts.append(
                        f"{{\\c{kw}\\fscx100\\fscy100\\t(0,{pop_ms},\\fscx{active_scale}\\fscy{active_scale})}}"
                        f"{t}{{\\c{pri}\\fscx100\\fscy100}}"
                    )
                elif j in kw_idx:  # a keyword that isn't active right now: stay accented
                    parts.append(f"{{\\c{kw}}}{t}{{\\c{pri}}}")
                else:
                    parts.append(t)
            body = " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ass_time(seg_start)},{_ass_time(seg_end)},Cadence,,0,0,0,,{pos}{body}\n"
            )
    return "".join(lines)


def build_hook_studio(
    hook: str,
    *,
    width: int,
    height: int,
    duration: float = 2.4,
    font_name: str = "Arial",
    primary: RGBColor = RGBColor(255, 255, 255),
    outline: RGBColor = RGBColor(0, 0, 0),
) -> str:
    """A bold, centered, animated opening HOOK card for the scroll-stopping first ~2.4s: the
    hook line scales in with a pop and fades. Returns a complete .ass document (rendered as
    its own overlay pass over the opening of the video)."""
    font_size = fit_font_size(hook.upper(), max(48, round(height * 0.072)), width, margin=60, min_scale=0.5)
    outline_w = max(3, round(font_size * 0.07))
    cx, cy = width // 2, round(height * 0.42)
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Hook,{font_name},{font_size},{_ass_color(primary)},{_ass_color(outline)},"
        f"&H64000000&,1,0,0,0,100,100,0,0,1,{outline_w},3,5,60,60,60,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    dur_ms = max(200, round(duration * 1000))
    out_fade = min(220, dur_ms // 3)
    tag = (
        f"{{\\an5\\pos({cx},{cy})\\fscx46\\fscy46\\t(0,240,\\fscx112\\fscy112)"
        f"\\t(240,400,\\fscx100\\fscy100)\\fad(120,{out_fade})}}"
    )
    return header + f"Dialogue: 0,{_ass_time(0.0)},{_ass_time(duration)},Hook,,0,0,0,,{tag}{_escape_text(hook.upper())}\n"
