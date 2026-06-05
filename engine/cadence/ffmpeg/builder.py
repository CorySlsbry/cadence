"""Pure filtergraph string builders.

Every function returns deterministic filtergraph text and the output pad label(s)
it produced, with NO side effects — so the exact graph can be asserted in unit
tests (and logged for reproducibility) before any ffmpeg process is spawned.
"""

from __future__ import annotations

from cadence.models import TimeRange


def _even(expr: str) -> str:
    """Force an even pixel dimension (yuv420p crashes on odd dims)."""
    return f"trunc(({expr})/2)*2"


def build_cut_concat(
    kept: list[TimeRange],
    *,
    has_audio: bool,
    vin: str = "0:v",
    ain: str = "0:a",
    prefix: str = "k",
) -> tuple[str, str, str | None]:
    """trim/atrim + setpts reset + concat over the KEEP ranges.

    Returns ``(graph, video_label, audio_label_or_None)``. This is the research's
    "Strategy B" — the reliable A/V-sync path for many cuts.
    """
    if not kept:
        raise ValueError("build_cut_concat requires at least one keep range")
    parts: list[str] = []
    labels: list[str] = []
    for i, r in enumerate(kept):
        vlab = f"{prefix}v{i}"
        parts.append(f"[{vin}]trim={r.start:.4f}:{r.end:.4f},setpts=PTS-STARTPTS[{vlab}]")
        if has_audio:
            alab = f"{prefix}a{i}"
            parts.append(f"[{ain}]atrim={r.start:.4f}:{r.end:.4f},asetpts=PTS-STARTPTS[{alab}]")
            labels.extend([f"[{vlab}]", f"[{alab}]"])
        else:
            labels.append(f"[{vlab}]")
    n = len(kept)
    if has_audio:
        concat = "".join(labels) + f"concat=n={n}:v=1:a=1[cv][ca]"
        graph = ";".join(parts) + ";" + concat
        return graph, "[cv]", "[ca]"
    concat = "".join(labels) + f"concat=n={n}:v=1:a=0[cv]"
    graph = ";".join(parts) + ";" + concat
    return graph, "[cv]", None


def build_normalize(
    in_label: str,
    out_label: str,
    *,
    width: int,
    height: int,
    fps: int,
) -> str:
    """Scale-to-fill + crop + CFR + pixfmt normalization (mandatory pre-step)."""
    return (
        f"[{in_label}]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},format=yuv420p,setsar=1,settb=AVTB[{out_label}]"
    )


def build_punch_in(
    in_label: str,
    out_label: str,
    *,
    zoom: float,
    width: int,
    height: int,
    ramp_sec: float = 1.0,
) -> str:
    """Animated center punch-in via scale+crop (NOT zoompan — avoids integer jitter)."""
    if zoom <= 1.0:
        return f"[{in_label}]null[{out_label}]"
    factor = f"(1+{zoom - 1.0:.4f}*min(t/{ramp_sec:.3f}\\,1))"
    sw = _even(f"iw*{factor}")
    return (
        f"[{in_label}]scale=w={sw}:h=-2:eval=frame,"
        f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2[{out_label}]"
    )


def build_color_grade(
    in_label: str,
    out_label: str,
    *,
    brightness: float,
    contrast: float,
    saturation: float,
    gamma: float,
    temperature: float,
    shadow_balance: float = 0.0,
) -> str:
    """eq + colorbalance grade. `temperature` warms highlights/mids; `shadow_balance`
    independently tints shadows (negative = teal, for a teal-orange split-tone)."""
    t = max(-1.0, min(1.0, temperature))
    sb = max(-1.0, min(1.0, shadow_balance))
    rh, bh = t * 0.3, -t * 0.3          # highlights warmth
    rm, bm = t * 0.2, -t * 0.2          # midtone warmth
    rs, bs = sb * 0.3, -sb * 0.3        # shadow tint (split-tone)
    eq = (
        f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}"
        f":saturation={saturation:.4f}:gamma={gamma:.4f}"
    )
    cb = (
        f"colorbalance=rh={rh:.4f}:bh={bh:.4f}:rm={rm:.4f}:bm={bm:.4f}"
        f":rs={rs:.4f}:bs={bs:.4f}"
    )
    return f"[{in_label}]{eq},{cb}[{out_label}]"


def build_watermark(
    base_label: str,
    wm_input: str,
    out_label: str,
    *,
    opacity: float,
    x_expr: str,
    y_expr: str,
    scale_w: int,
) -> str:
    """Overlay a watermark image with opacity at an anchor expression."""
    opacity = max(0.0, min(1.0, opacity))
    return (
        f"[{wm_input}]format=rgba,colorchannelmixer=aa={opacity:.3f},"
        f"scale={scale_w}:-1[wm];"
        f"[{base_label}][wm]overlay={x_expr}:{y_expr}[{out_label}]"
    )


def build_kenburns(
    in_label: str,
    out_label: str,
    *,
    motion: str,
    width: int,
    height: int,
    dur: float,
    fade: float,
) -> str:
    """Animate a still image into a WxH b-roll clip via scale+crop (no zoompan jitter).

    The chain ends with alpha edge-fades so the overlay blends softly over the A-roll.
    ``in_label`` must be a looped image input of length ``dur``.
    """
    ramp = f"min(t/{max(dur, 0.1):.3f}\\,1)"
    cover = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    if motion in ("zoom_in", "zoom_out"):
        factor = f"(1+0.16*{ramp})" if motion == "zoom_in" else f"(1.16-0.16*{ramp})"
        sw = _even(f"{width}*{factor}")
        anim = f"{cover},scale=w={sw}:h=-2:eval=frame,crop={width}:{height}:(iw-{width})/2:(ih-{height})/2"
    elif motion in ("pan_left", "pan_right"):
        # crop evaluates its x/y expressions per-frame natively (no eval option exists
        # on crop — only scale has one), so a t-based x animates the pan directly.
        wide = _even(f"{width}*1.2")
        base = f"scale={wide}:{height}:force_original_aspect_ratio=increase,crop={wide}:{height},setsar=1"
        xexpr = f"(iw-{width})*{ramp}" if motion == "pan_right" else f"(iw-{width})*(1-{ramp})"
        anim = f"{base},crop={width}:{height}:x='{xexpr}':y=0"
    else:  # pan_up / pan_down
        tall = _even(f"{height}*1.2")
        base = f"scale={width}:{tall}:force_original_aspect_ratio=increase,crop={width}:{tall},setsar=1"
        yexpr = f"(ih-{height})*{ramp}" if motion == "pan_down" else f"(ih-{height})*(1-{ramp})"
        anim = f"{base},crop={width}:{height}:x=0:y='{yexpr}'"

    edge = (
        f",format=yuva420p,fade=t=in:st=0:d={fade:.3f}:alpha=1,"
        f"fade=t=out:st={max(dur - fade, 0):.3f}:d={fade:.3f}:alpha=1"
        if fade > 0
        else ",format=yuva420p"
    )
    return f"[{in_label}]{anim}{edge}[{out_label}]"


def build_subtitles(in_label: str, out_label: str, ass_path: str) -> str:
    """Burn an .ass subtitle file. Windows drive colons must be escaped for the filter."""
    escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    return f"[{in_label}]subtitles='{escaped}'[{out_label}]"
