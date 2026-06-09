"""§4.1 — build the structured Generation Plan Blueprint.

Maps the reference analysis (style), the edit-decision list (what footage to keep),
and the brand board (equity) into one :class:`GenerationPlan` — the single,
serializable contract the renderer consumes. Captions are re-timed onto the
*cleaned* output timeline so they track the cut footage, not the raw source.
"""

from __future__ import annotations

from collections import Counter

from cadence.config import SynthesisConfig
from cadence.models import (
    AssetKind,
    BrandBoard,
    BrollInsert,
    Caption,
    CaptionStyle,
    CaptionWord,
    ClipSpec,
    ColorGrade,
    ColorProfile,
    EditDecisionList,
    GenerationPlan,
    ReferenceAnalysis,
    TextZone,
    TimeRange,
    Transcript,
    TransitionType,
    WatermarkSpec,
)
from cadence.synthesis.contextual import plan_broll_windows


def place_broll(images: list[str], output_duration: float, *, mode: str = "between") -> list[BrollInsert]:
    """Distribute animated-still cutaways across the cleaned timeline, cycling through
    the user's images. The audio keeps playing underneath, so this reads as b-roll
    over a continuous voiceover. (Window timing is shared with the AI b-roll path.)"""
    if not images:
        return []
    return [
        BrollInsert(image_path=images[i % len(images)], start=s, end=e, motion=m)
        for i, (s, e, m) in enumerate(plan_broll_windows(output_duration, mode=mode))
    ]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def derive_color_grade(profile: ColorProfile) -> ColorGrade:
    """A premium grade that nudges raw A-roll toward the reference's exposure/palette."""
    exp = profile.exposure
    brightness = _clamp((exp.mean_luma - 128.0) / 255.0 * 0.3, -0.18, 0.18)
    contrast = 1.0 + _clamp((exp.std_luma - 50.0) / 200.0, -0.08, 0.16)
    saturation = 1.08  # gentle, premium colour pop
    primary = profile.primary
    warmth = ((primary.r - primary.b) / 255.0) if primary else 0.0
    temperature = _clamp(warmth * 0.4, -0.3, 0.3)
    return ColorGrade(
        brightness=round(brightness, 4),
        contrast=round(contrast, 4),
        saturation=saturation,
        gamma=1.0,
        temperature=round(temperature, 4),
    )


def remap_words_to_output(
    transcript: Transcript, kept: list[TimeRange]
) -> list[tuple[str, float, float]]:
    """Map words that survive the cuts onto the compressed output timeline."""
    out: list[tuple[str, float, float]] = []
    offset = 0.0
    for r in kept:
        for w in transcript.words:
            if w.start >= r.start - 1e-3 and w.end <= r.end + 1e-3:
                out.append((w.text, offset + (w.start - r.start), offset + (w.end - r.start)))
        offset += r.duration
    out.sort(key=lambda t: t[1])
    return out


def group_captions(
    words_out: list[tuple[str, float, float]],
    *,
    zone: TextZone,
    style: CaptionStyle,
    max_words: int = 4,
    max_dur: float = 2.2,
) -> list[Caption]:
    captions: list[Caption] = []
    chunk: list[tuple[str, float, float]] = []

    def flush() -> None:
        if not chunk:
            return
        text = " ".join(w[0] for w in chunk).strip()
        captions.append(Caption(text=text, start=round(chunk[0][1], 3), end=round(chunk[-1][2], 3), zone=zone, style=style))

    for word in words_out:
        if chunk and (len(chunk) >= max_words or (word[2] - chunk[0][1]) > max_dur):
            flush()
            chunk = []
        chunk.append(word)
    flush()
    return captions


def group_karaoke_captions(
    words_out: list[tuple[str, float, float]],
    *,
    zone: TextZone,
    style: CaptionStyle = CaptionStyle.POP,
    max_words: int = 4,
    max_dur: float = 2.2,
) -> list[Caption]:
    """Like :func:`group_captions`, but each line RETAINS its per-word timings (``Caption.words``)
    so the renderer animates a per-word scale-pop ("karaoke") caption. Same chunking rules."""
    captions: list[Caption] = []
    chunk: list[tuple[str, float, float]] = []

    def flush() -> None:
        if not chunk:
            return
        text = " ".join(w[0] for w in chunk).strip()
        words = [CaptionWord(text=w[0], start=round(w[1], 3), end=round(w[2], 3)) for w in chunk]
        captions.append(
            Caption(text=text, start=round(chunk[0][1], 3), end=round(chunk[-1][2], 3),
                    zone=zone, style=style, words=words)
        )

    for word in words_out:
        if chunk and (len(chunk) >= max_words or (word[2] - chunk[0][1]) > max_dur):
            flush()
            chunk = []
        chunk.append(word)
    flush()
    return captions


def _dominant_zone(analysis: ReferenceAnalysis | None, default: TextZone) -> TextZone:
    if analysis and analysis.text_overlays:
        counts = Counter(o.zone for o in analysis.text_overlays)
        return counts.most_common(1)[0][0]
    return default


def build_generation_plan(
    edl: EditDecisionList,
    *,
    analysis: ReferenceAnalysis | None = None,
    brand: BrandBoard | None = None,
    cfg: SynthesisConfig | None = None,
    broll_images: list[str] | None = None,
    pacing_mode: str = "between",
) -> GenerationPlan:
    cfg = cfg or SynthesisConfig()

    # 1) Clips — one per KEEP range; smart-zoom punches in on every clip after the
    #    first to mask the jump cut as an intentional angle change (§3 Module D).
    clips: list[ClipSpec] = []
    for i, r in enumerate(edl.kept):
        zoom = cfg.zoom_factor if (cfg.smart_zoom and i > 0) else 1.0
        clips.append(
            ClipSpec(
                source=edl.source,
                in_point=r.start,
                out_point=r.end,
                zoom=zoom,
                transition_in=TransitionType.HARD_CUT,
            )
        )

    # 2) Captions — re-timed onto the cleaned output timeline.
    captions: list[Caption] = []
    if edl.transcript and edl.transcript.words:
        zone = _dominant_zone(analysis, TextZone(cfg.caption_default_zone))
        style = CaptionStyle(cfg.caption_default_style)
        words_out = remap_words_to_output(edl.transcript, list(edl.kept))
        if getattr(cfg, "caption_mode", "legacy") == "karaoke":
            captions = group_karaoke_captions(words_out, zone=zone, style=style)
        else:
            captions = group_captions(words_out, zone=zone, style=style)

    # 3) Colour grade — derived from the reference palette/exposure.
    grade = ColorGrade()
    if analysis and cfg.color_grade_to_reference:
        grade = derive_color_grade(analysis.color_profile)

    # 4) Watermark + caption styling from the brand board.
    watermark: WatermarkSpec | None = None
    caption_font = None
    caption_primary = "#FFFFFF"
    caption_outline = "#000000"
    if brand:
        wm_asset = brand.asset_of(AssetKind.WATERMARK) or brand.asset_of(AssetKind.LOGO)
        if wm_asset:
            watermark = WatermarkSpec(
                path=wm_asset.path,
                opacity=wm_asset.opacity,
                anchor=wm_asset.anchor,
                scale=wm_asset.scale,
            )
        caption_font = brand.caption_font_path
        if brand.caption_primary:
            caption_primary = brand.caption_primary.hex
        if brand.caption_outline:
            caption_outline = brand.caption_outline.hex

    broll = place_broll(broll_images or [], edl.output_duration, mode=pacing_mode)

    return GenerationPlan(
        width=cfg.width,
        height=cfg.height,
        fps=cfg.fps,
        clips=clips,
        captions=captions,
        broll=broll,
        color_grade=grade,
        watermark=watermark,
        caption_font_path=caption_font,
        caption_primary_hex=caption_primary,
        caption_outline_hex=caption_outline,
        audio_normalize=True,
    )
