"""Parse the Studio `customization` JSON into engine configs + cinematography +
feature toggles. One source of truth so the web client and the worker agree.

Order of precedence: a `preset` bundle is applied first, then any explicit field
overrides on top (editing a control past a preset just overrides that field).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cadence.config import PRESETS, CinematographyConfig, CleaningConfig, SynthesisConfig


@dataclass(slots=True)
class RenderToggles:
    auto_clean: bool = True
    smart_zoom: bool = True
    color_grade: bool = True
    captions: bool = True
    watermark: bool = True
    ai_broll: bool = True
    letterbox: bool = False
    background_replace: bool = False  # composite speaker over b-roll instead of cutaways
    auto_reframe: bool = False        # landscape source → face-tracked 9:16 crop (vs naive center)


@dataclass(slots=True)
class ParsedControls:
    cleaning: CleaningConfig
    synthesis: SynthesisConfig
    cinematography: CinematographyConfig
    toggles: RenderToggles
    pacing: str = "between"
    broll_mode: str = "ai"            # none | images | ai | background
    broll_quality: str = "standard"   # fast | standard | ultra → Imagen tier (cost/quality)
    broll_caption_overlay: bool = False
    grade_intensity: float = 1.0
    grade_override: dict[str, float] = field(default_factory=dict)
    broll_paths: list[str] = field(default_factory=list)
    music_key: str | None = None        # uploaded music track storage key (worker downloads it)
    music_volume: float = 0.18          # base music level under speech (0..1)
    hook: str | None = None             # opening hook-card text (animated overlay); None = no card


def _b(d: dict, k: str, default: bool) -> bool:
    v = d.get(k, default)
    return bool(v) if v is not None else default


def parse_customization(cust: dict[str, Any] | None) -> ParsedControls:
    cust = cust or {}
    merged: dict[str, Any] = {}
    preset = cust.get("preset")
    if preset and preset in PRESETS:
        merged.update(PRESETS[preset])
    merged.update({k: v for k, v in cust.items() if v is not None and k != "preset"})

    # --- cleaning (smooth-cut fixes are always on; sensitivity tunes thresholds) --- #
    clean = CleaningConfig()
    auto_clean = _b(merged, "auto_clean", True)
    clean.remove_silence = auto_clean and _b(merged, "remove_silences", True)
    sens = merged.get("cut_sensitivity")
    if sens == "gentle":
        clean.silence_db, clean.min_silence_sec = -45.0, 0.45
    elif sens == "aggressive":
        clean.silence_db, clean.min_silence_sec = -36.0, 0.22
    clean.detect_retakes = auto_clean and _b(merged, "detect_retakes", True)
    clean.retake_similarity = float(merged.get("retake_strictness", clean.retake_similarity))
    fillers = int(merged.get("filler_aggressiveness", 1))
    clean.remove_fillers = auto_clean and _b(merged, "remove_fillers", fillers > 0)
    clean.aggressive_fillers = fillers >= 2
    clean.trim_lead_silence = _b(merged, "trim_dead_air", True)
    if "tail_pad_sec" in merged:
        clean.after_pad_sec = float(merged["tail_pad_sec"])
    if "lead_pad_sec" in merged:
        clean.before_pad_sec = float(merged["lead_pad_sec"])
    if "min_kept_segment_sec" in merged:
        clean.min_kept_segment_sec = float(merged["min_kept_segment_sec"])
    clean.snap_cuts_to_words = _b(merged, "snap_cuts_to_words", True)

    # --- synthesis --- #
    syn = SynthesisConfig()
    syn.smart_zoom = _b(merged, "smart_zoom", True)
    syn.zoom_factor = float(merged.get("zoom_intensity", syn.zoom_factor))
    zone = merged.get("caption_zone", "auto")
    if zone in ("top", "center", "bottom"):
        syn.caption_default_zone = zone
    syn.caption_default_style = merged.get("caption_style", syn.caption_default_style)
    if merged.get("caption_mode") in ("legacy", "karaoke"):
        syn.caption_mode = merged["caption_mode"]
    syn.color_grade_to_reference = _b(merged, "color_grade", True)
    if not _b(merged, "audio_crossfade", True):
        syn.audio_crossfade_ms = 0
    elif "crossfade_ms" in merged:
        syn.audio_crossfade_ms = int(merged["crossfade_ms"])

    # --- cinematography --- #
    cine = CinematographyConfig(
        lens=merged.get("lens", "50mm"),
        aperture=float(merged.get("aperture", 2.8)),
        film_stock=merged.get("film_stock", "digital_clean"),
        lighting=merged.get("lighting", "soft_natural"),
        time_of_day=merged.get("time_of_day", "unset"),
        camera_angle=merged.get("camera_angle", "eye_level"),
        shot_type=merged.get("shot_type", "medium"),
        film_grain_amount=float(merged.get("film_grain_amount", 0)) if _b(merged, "film_grain", float(merged.get("film_grain_amount", 0)) > 0) else 0.0,
    )
    # Lens biases the A-roll punch-in (a longer lens "compresses" → slightly more zoom).
    if syn.smart_zoom:
        syn.zoom_factor = round(max(syn.zoom_factor, cine.zoom_bias()), 4)

    broll_mode = merged.get("broll_mode", "ai")
    broll_quality = merged.get("broll_quality", "standard")
    if broll_quality not in ("fast", "standard", "ultra"):
        broll_quality = "standard"
    toggles = RenderToggles(
        auto_clean=_b(merged, "auto_clean", True),
        smart_zoom=syn.smart_zoom,
        color_grade=syn.color_grade_to_reference,
        captions=_b(merged, "captions", True),
        watermark=_b(merged, "watermark", True),
        ai_broll=_b(merged, "ai_broll", True),
        letterbox=(merged.get("framing") == "letterbox_239") or _b(merged, "letterbox", False),
        background_replace=(broll_mode == "background"),
        auto_reframe=_b(merged, "auto_reframe", False),
    )

    return ParsedControls(
        cleaning=clean, synthesis=syn, cinematography=cine, toggles=toggles,
        pacing=merged.get("pacing", "between"),
        broll_mode=broll_mode,
        broll_quality=broll_quality,
        broll_caption_overlay=_b(merged, "broll_caption", False),
        grade_intensity=float(merged.get("grade_intensity", 70)) / 100.0,
        grade_override=cine.grade_override(),
        broll_paths=list(merged.get("broll_paths") or []),
        music_key=merged.get("music_path"),
        music_volume=float(merged.get("music_volume", 0.18)),
        hook=((merged.get("hook") or "").strip() or None),
    )
