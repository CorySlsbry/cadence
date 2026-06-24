"""Composite a photoreal talking-avatar clip into faceless b-roll scenes (the
"presenter" layer), or pass it through full-frame / standalone.

Generalizes the background-replacement spine in ``cadence.matte.replace``: matte the
person (MediaPipe selfie-seg — same clean-license segmenter the bg-replace uses), then
overlay them, scaled + anchored by a framing preset, over the scene video. Audio rides
from the avatar clip. ``full`` framing delegates to ``render_background_replaced`` (the
avatar IS the full-frame speaker over the scenes); ``lower_third`` / ``corner`` overlay a
scaled bust. The composite then feeds the normal ``render_plan`` for captions / grade /
hook card, so the avatar inherits the whole premium finish for free.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg
from cadence.matte.replace import generate_person_mask, render_background_replaced


@dataclass(frozen=True)
class Framing:
    key: str
    scale: float   # avatar width as a fraction of the output width
    anchor: str    # 'center' | 'br' | 'bc' | 'tr'
    pad: int = 48  # px margin from edges for anchored busts


FRAMINGS: dict[str, Framing] = {
    "full": Framing("full", 1.0, "center"),
    "lower_third": Framing("lower_third", 0.42, "br"),
    "corner": Framing("corner", 0.30, "tr"),
}


def _overlay_xy(anchor: str, pad: int) -> str:
    """ffmpeg overlay position expression using main_w/overlay_w so the auto-height
    scaled avatar anchors correctly regardless of its aspect ratio."""
    return {
        "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
        "br": f"main_w-overlay_w-{pad}:main_h-overlay_h-{pad}",
        "bc": f"(main_w-overlay_w)/2:main_h-overlay_h-{pad}",
        "tr": f"main_w-overlay_w-{pad}:{pad}",
    }.get(anchor, "(main_w-overlay_w)/2:(main_h-overlay_h)/2")


def compose_avatar_presenter(
    avatar_clip: str,
    scenes_video: str,
    out: str = "out.mp4",
    *,
    ff: FFmpeg | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    framing: str = "lower_third",
    crf: int = 19,
    mask_path: str | None = None,
) -> str:
    """Matte the avatar from ``avatar_clip`` and overlay it over ``scenes_video`` (the
    faceless AI b-roll), scaled + anchored per ``framing``. Returns ``out``."""
    fr = FRAMINGS.get(framing, FRAMINGS["lower_third"])
    ff = ff or FFmpeg()
    if fr.key == "full":
        # full-frame presenter == background replacement with the avatar as the speaker
        return render_background_replaced(
            avatar_clip, None, out, ff=ff, width=width, height=height, fps=fps,
            crf=crf, mask_path=mask_path, background_video=scenes_video,
        )
    mask = mask_path or tempfile.mktemp(suffix="_amask.mp4")
    mw, mh = min(width, 1080), min(height, 1920)
    generate_person_mask(avatar_clip, mask, ff=ff, width=mw, height=mh, fps=fps)
    aw = (int(width * fr.scale) // 2) * 2  # even width; height auto (scale=w:-2)
    xy = _overlay_xy(fr.anchor, fr.pad)
    info = probe_media(avatar_clip, ff)
    graph = (
        f"[2:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps}[bg];"
        f"[0:v]scale={aw}:-2,fps={fps},setsar=1[fgs];"
        f"[1:v]scale={aw}:-2,format=gray,fps={fps}[mks];"
        f"[fgs][mks]alphamerge[fga];"
        f"[bg][fga]overlay={xy}:format=auto[outv]"
    )
    args = ["-y", "-i", avatar_clip, "-i", mask, "-i", scenes_video,
            "-filter_complex", graph, "-map", "[outv]"]
    if info.has_audio:
        args += ["-map", "0:a"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if info.has_audio:
        args += ["-c:a", "aac", "-b:a", "160k"]
    args += ["-r", str(fps), out]
    ff.run(args, timeout=1800)
    return out
