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
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cadence,{font_name},{font_size},{_ass_color(primary)},{_ass_color(outline)},"
        f"&H64000000&,1,0,0,0,100,100,0,0,1,{outline_w},2,5,40,40,40,1\n\n"
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
