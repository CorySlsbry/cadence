"""Synthetic-media generators for the test suite.

Every fixture has a KNOWN ground truth so tests assert against an independent
oracle (per CLAUDE.md Writing-Tests best practices), not against the engine's own
output. Captions are rendered as high-edge-density PNGs (real glyphs via Pillow's
built-in font) and overlaid at known times/zones, so the text-region detector has
something genuine to find without depending on system fonts.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

from cadence.ffmpeg.runner import FFmpeg

# Ground-truth constants the tests assert against.
REF_W, REF_H = 216, 384
REF_SCENE_SEC = 2.0
REF_CUTS = (2.0, 4.0)          # hard cuts between the three colour scenes
REF_DURATION = 6.0
REF_COLORS_HEX = ("E03020", "20C030", "2040E0")  # red-ish, green-ish, blue-ish
REF_BOTTOM_CAPTION = (0.4, 1.8)  # (start, end) seconds, bottom zone
REF_TOP_CAPTION = (4.2, 5.6)     # top zone


def make_caption_png(path: str, text: str, *, w: int = 150, h: int = 48) -> None:
    """Render a white caption strip with black outline -> high edge density."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w - 1, h - 1], fill=(0, 0, 0, 160))
    # stroke gives extra edges (and PIL's default font has no external dependency)
    draw.text((8, 12), text, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    img.save(path)


def make_reference_video(ff: FFmpeg, out_path: str, *, tmp_dir: str) -> None:
    """3 solid-colour scenes, hard cuts at 2s & 4s, captions bottom then top, tone audio."""
    cap_bottom = os.path.join(tmp_dir, "cap_bottom.png")
    cap_top = os.path.join(tmp_dir, "cap_top.png")
    make_caption_png(cap_bottom, "HOOK LINE")
    make_caption_png(cap_top, "BIG FINISH")

    c0, c1, c2 = REF_COLORS_HEX
    args = [
        "-y",
        "-f", "lavfi", "-i", f"color=c=0x{c0}:s={REF_W}x{REF_H}:r=30:d={REF_SCENE_SEC}",
        "-f", "lavfi", "-i", f"color=c=0x{c1}:s={REF_W}x{REF_H}:r=30:d={REF_SCENE_SEC}",
        "-f", "lavfi", "-i", f"color=c=0x{c2}:s={REF_W}x{REF_H}:r=30:d={REF_SCENE_SEC}",
        "-loop", "1", "-t", str(REF_DURATION), "-i", cap_bottom,
        "-loop", "1", "-t", str(REF_DURATION), "-i", cap_top,
        "-f", "lavfi", "-i", f"sine=frequency=330:duration={REF_DURATION}",
        "-filter_complex",
        (
            "[0:v][1:v][2:v]concat=n=3:v=1:a=0[base];"
            f"[base][3:v]overlay=x=(W-w)/2:y=H*0.78:enable='between(t,{REF_BOTTOM_CAPTION[0]},{REF_BOTTOM_CAPTION[1]})'[o1];"
            f"[o1][4:v]overlay=x=(W-w)/2:y=H*0.10:enable='between(t,{REF_TOP_CAPTION[0]},{REF_TOP_CAPTION[1]})'[v]"
        ),
        "-map", "[v]", "-map", "5:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-shortest",
        out_path,
    ]
    ff.run(args, timeout=120)


def make_talking_clip(
    ff: FFmpeg,
    out_path: str,
    *,
    duration: float = 6.0,
    silence_windows: tuple[tuple[float, float], ...] = ((1.0, 1.8), (3.0, 3.7)),
    w: int = 216,
    h: int = 384,
) -> None:
    """Moving-content video with a tone audio muted during `silence_windows`."""
    vol_chain = ",".join(
        f"volume=enable='between(t,{s},{e})':volume=0" for s, e in silence_windows
    )
    af = f"sine=frequency=440:duration={duration}"
    args = [
        "-y",
        "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=30:d={duration}",
        "-f", "lavfi", "-i", af,
        "-af", vol_chain,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-shortest",
        out_path,
    ]
    ff.run(args, timeout=120)


def make_logo_png(path: str, *, size: int = 64) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(255, 80, 40, 255))
    draw.text((size // 4, size // 3), "C", fill=(255, 255, 255, 255))
    img.save(path)
