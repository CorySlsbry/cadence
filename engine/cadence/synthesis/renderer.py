"""§4.2 — turn a GenerationPlan into a real rendered MP4.

Builds one deterministic filter_complex (normalize -> punch-in -> grade ->
subtitles -> watermark -> encode), picks a *working* encoder (hardware smoke-test
with graceful software fallback), logs the exact graph, and renders. Every failure
path is typed so the §5 resiliency contract holds.
"""

from __future__ import annotations

import os
import tempfile

from cadence.config import SynthesisConfig
from cadence.errors import FFmpegError, InvalidMediaError, PlanError, RenderError
from cadence.ffmpeg.builder import (
    build_color_grade,
    build_kenburns,
    build_subtitles,
    build_watermark,
)
from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Anchor, GenerationPlan, RGBColor, RenderResult
from cadence.synthesis.captions import build_ass


def _clip_video_chain(clip, idx: int, src_idx: int, w: int, h: int, fps: int) -> str:
    chain = (
        f"[{src_idx}:v]trim={clip.in_point:.4f}:{clip.out_point:.4f},setpts=PTS-STARTPTS,"
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1"
    )
    if clip.zoom > 1.0:
        ramp = max(clip.duration, 0.5)
        factor = f"(1+{clip.zoom - 1.0:.4f}*min(t/{ramp:.3f}\\,1))"
        sw = f"trunc((iw*{factor})/2)*2"
        chain += f",scale=w={sw}:h=-2:eval=frame,crop={w}:{h}:(iw-{w})/2:(ih-{h})/2"
    chain += f",format=yuv420p[v{idx}]"
    return chain


def _encode_args(encoder: str, cfg: SynthesisConfig, fps: int) -> list[str]:
    if encoder == "h264_nvenc":
        return [
            "-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq",
            "-rc", "vbr", "-cq", str(cfg.crf), "-b:v", "0",
            "-rc-lookahead", "20", "-spatial-aq", "1", "-temporal-aq", "1", "-bf", "3",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(fps),
        ]
    if encoder in ("h264_amf", "h264_qsv"):
        return [
            "-c:v", encoder, "-quality", "quality", "-rc", "vbr_latency",
            "-qp_i", str(cfg.crf), "-qp_p", str(cfg.crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(fps),
        ]
    return [
        # "medium" preset: ~as small as "slow" in practice but much faster to encode,
        # which on Cloud Run is real $ saved per render.
        "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(fps),
    ]


def _build_graph(plan: GenerationPlan, source_index: dict[str, int], has_audio: bool,
                 wm_input_idx: int | None, ass_path: str | None,
                 broll_start_idx: int = 0, audio_xf: float = 0.0, music_idx: int | None = None) -> tuple[str, str, str | None]:
    parts: list[str] = []
    n = len(plan.clips)
    for i, clip in enumerate(plan.clips):
        parts.append(_clip_video_chain(clip, i, source_index[clip.source], plan.width, plan.height, plan.fps))
        if has_audio:
            achain = (
                f"[{source_index[clip.source]}:a]atrim={clip.in_point:.4f}:{clip.out_point:.4f},"
                f"asetpts=PTS-STARTPTS"
            )
            # Declick each seam (short equal-power fade at the segment edges) so cuts
            # don't pop/feel abrupt. Doesn't change duration -> no A/V desync.
            dur = clip.out_point - clip.in_point
            # 2x is the overlap-free minimum (fade-in + fade-out); 2.2x keeps a margin
            # but still declicks clips right at the floor instead of leaving them to pop.
            if audio_xf > 0 and dur >= 2.2 * audio_xf:
                achain += (
                    f",afade=t=in:st=0:d={audio_xf:.4f}:curve=tri"
                    f",afade=t=out:st={dur - audio_xf:.4f}:d={audio_xf:.4f}:curve=tri"
                )
            parts.append(achain + f"[a{i}]")

    if has_audio:
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
        parts.append(concat_inputs + f"concat=n={n}:v=1:a=1[cv][ca]")
    else:
        concat_inputs = "".join(f"[v{i}]" for i in range(n))
        parts.append(concat_inputs + f"concat=n={n}:v=1:a=0[cv]")

    cur_v = "cv"
    g = plan.color_grade
    parts.append(build_color_grade(
        cur_v, "vg",
        brightness=g.brightness, contrast=g.contrast, saturation=g.saturation,
        gamma=g.gamma, temperature=g.temperature, shadow_balance=g.shadow_balance,
    ))
    cur_v = "vg"

    # B-roll cutaways: overlay each animated still during its window. The audio track
    # ([ca]) is untouched, so the speaker keeps talking under the b-roll.
    for i, b in enumerate(plan.broll):
        img_idx = broll_start_idx + i
        parts.append(build_kenburns(
            f"{img_idx}:v", f"bk{i}", motion=b.motion.value,
            width=plan.width, height=plan.height, dur=b.duration, fade=b.fade,
        ))
        parts.append(f"[bk{i}]setpts=PTS+{b.start:.4f}/TB[bp{i}]")
        parts.append(
            f"[{cur_v}][bp{i}]overlay=0:0:enable='between(t,{b.start:.4f},{b.end:.4f})':eof_action=pass[vb{i}]"
        )
        cur_v = f"vb{i}"

    if ass_path and plan.captions:
        parts.append(build_subtitles(cur_v, "vs", ass_path))
        cur_v = "vs"

    if wm_input_idx is not None and plan.watermark is not None:
        anchor = plan.watermark.anchor
        pad = 48
        x_expr, y_expr = anchor.overlay_xy(pad)
        scale_w = max(2, round(plan.width * plan.watermark.scale))
        parts.append(build_watermark(
            cur_v, str(wm_input_idx), "vout",
            opacity=plan.watermark.opacity, x_expr=x_expr, y_expr=y_expr, scale_w=scale_w,
        ))
        cur_v = "vout"

    # Film grain (shared across A-roll + b-roll + captions) and cinematic letterbox,
    # applied last so they sit over everything.
    if g.grain and g.grain > 0:
        parts.append(f"[{cur_v}]noise=alls={int(round(min(g.grain, 60)))}:allf=t+u[vgrain]")
        cur_v = "vgrain"
    if plan.letterbox:
        # Bottom bar height = ih (drawbox clamps to the frame) so it reaches the very
        # edge — a literal ih*0.13 truncates and leaves a 1-2px sliver below the bar.
        parts.append(
            f"[{cur_v}]drawbox=x=0:y=0:w=iw:h=ih*0.13:color=black@1.0:t=fill,"
            f"drawbox=x=0:y=ih*0.87:w=iw:h=ih:color=black@1.0:t=fill[vlb]"
        )
        cur_v = "vlb"

    cur_a: str | None = None
    if has_audio:
        speech = "ca"
        if music_idx is not None:
            # Background music bed: base-attenuate it, DUCK it under speech via a sidechain
            # compressor (music dips when the speaker talks), then mix speech (full) + ducked
            # music. asplit because [ca] feeds BOTH the mix and the compressor's sidechain.
            vol = max(0.0, min(1.0, plan.music_volume))
            parts.append("[ca]asplit=2[sp_mix][sp_side]")
            parts.append(f"[{music_idx}:a]volume={vol:.3f}[mvol]")
            parts.append("[mvol][sp_side]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[mduck]")
            parts.append("[sp_mix][mduck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[amus]")
            speech = "amus"
        if plan.audio_normalize:
            parts.append(f"[{speech}]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
        else:
            parts.append(f"[{speech}]anull[aout]")
        cur_a = "aout"

    graph = ";".join(parts)
    return graph, f"[{cur_v}]", (f"[{cur_a}]" if cur_a else None)


def render_plan(
    plan: GenerationPlan,
    out_path: str,
    *,
    ff: FFmpeg | None = None,
    cfg: SynthesisConfig | None = None,
    log_path: str | None = None,
) -> RenderResult:
    ff = ff or FFmpeg()
    cfg = cfg or SynthesisConfig()
    if not plan.clips:
        raise PlanError("generation plan has no clips to render")

    sources = list(dict.fromkeys(c.source for c in plan.clips))  # unique, order-preserving
    for s in sources:
        if not os.path.isfile(s):
            raise PlanError(f"clip source not found: {s}")
    source_index = {s: i for i, s in enumerate(sources)}
    for b in plan.broll:
        if not os.path.isfile(b.image_path):
            raise PlanError(f"b-roll image not found: {b.image_path}")
    # Audio is muxed only when EVERY source has it (concat a=1 requires every segment
    # to carry audio). The per-clip atrim already indexes by source, so multi-source
    # plans keep their audio instead of silently dropping it.
    has_audio = all(probe_media(s, ff).has_audio for s in sources)

    # Generate caption .ass (if any).
    ass_path: str | None = None
    if plan.captions:
        primary = RGBColor.from_hex(plan.caption_primary_hex)
        outline = RGBColor.from_hex(plan.caption_outline_hex)
        font_name = "Arial"
        if plan.caption_font_path:
            font_name = os.path.splitext(os.path.basename(plan.caption_font_path))[0]
        ass = build_ass(
            plan.captions, width=plan.width, height=plan.height,
            font_name=font_name, primary=primary, outline=outline,
            fade_ms=int(cfg.caption_fade_sec * 1000), letterbox=plan.letterbox,
        )
        fd, ass_path = tempfile.mkstemp(suffix=".ass")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(ass)

    wm_input_idx = len(sources) if plan.watermark else None
    broll_start_idx = len(sources) + (1 if plan.watermark else 0)
    music_idx = (broll_start_idx + len(plan.broll)) if (plan.music_path and has_audio) else None

    try:
        graph, vlabel, alabel = _build_graph(
            plan, source_index, has_audio, wm_input_idx, ass_path, broll_start_idx,
            audio_xf=cfg.audio_crossfade_ms / 1000.0, music_idx=music_idx,
        )
        if log_path:
            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write(graph)

        encoder, used_hw = ff.working_video_encoder(
            cfg.hardware_priority, cfg.software_encoder, prefer_hardware=cfg.prefer_hardware
        )
        result = _run_render(ff, plan, out_path, sources, graph, vlabel, alabel, encoder, used_hw, cfg)
        if result is not None:
            return result

        # Hardware path failed at full render: fall back to software and retry once.
        encoder, used_hw = cfg.software_encoder, False
        result = _run_render(ff, plan, out_path, sources, graph, vlabel, alabel, encoder, used_hw, cfg)
        if result is None:
            raise RenderError("render failed on both hardware and software encoders")
        return result
    finally:
        if ass_path and os.path.exists(ass_path):
            try:
                os.unlink(ass_path)
            except OSError:
                pass


def _run_render(ff, plan, out_path, sources, graph, vlabel, alabel, encoder, used_hw, cfg) -> RenderResult | None:
    args = ["-y"]
    for s in sources:
        args += ["-i", s]
    if plan.watermark:
        args += ["-i", plan.watermark.path]
    for b in plan.broll:
        args += ["-loop", "1", "-t", f"{b.duration:.4f}", "-i", b.image_path]
    if plan.music_path and alabel:
        args += ["-stream_loop", "-1", "-i", plan.music_path]  # loop music to cover the speech
    args += ["-filter_complex", graph, "-map", vlabel]
    if alabel:
        args += ["-map", alabel]
    args += _encode_args(encoder, cfg, plan.fps)
    if alabel:
        args += ["-c:a", "aac", "-b:a", cfg.audio_bitrate]
    args.append(out_path)
    try:
        ff.run(args, timeout=900)
        # Validate the output is real — a hardware encoder can exit 0 yet emit a
        # corrupt/zero-duration file; that must also trigger the software fallback.
        out = probe_media(out_path, ff)
        if out.duration <= 0:
            raise InvalidMediaError(f"render produced an empty output: {out_path}")
    except (FFmpegError, InvalidMediaError) as exc:
        if used_hw:
            return None  # signal caller to fall back to software
        raise RenderError(f"software render failed for {out_path}: {exc}") from exc
    return RenderResult(
        output_path=out_path,
        width=out.width,
        height=out.height,
        fps=out.fps,
        duration=out.duration,
        codec=out.codec,
        used_hardware=used_hw,
        encoder=encoder,
        command=args,
    )
