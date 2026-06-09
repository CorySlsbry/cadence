"""Tunable configuration for every stage of the pipeline.

All magic numbers the spec calls out live here as typed, documented defaults so
they can be overridden per-call (CLI flag, API body) without touching algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Canonical vocal fillers scrubbed by Module C §3.2. Lower-cased, punctuation
# stripped before matching. "like"/"so" are context-sensitive, hence opt-in via
# `aggressive_fillers`.
DEFAULT_FILLERS: tuple[str, ...] = ("um", "uh", "erm", "uhm", "ah", "eh", "hmm", "mm", "mhm")
AGGRESSIVE_FILLERS: tuple[str, ...] = ("like", "so", "basically", "literally", "actually", "right", "okay", "you know", "i mean", "kind of", "sort of")


@dataclass(slots=True)
class AnalyzerConfig:
    # Frame sampling (§3 Module A.1: "Sample frames at 1-second intervals").
    sample_fps: float = 1.0
    # Downscaled analysis resolution (keeps K-means + SSIM fast and isolate-safe).
    analysis_width: int = 256
    analysis_height: int = 456  # 9:16 of 256
    # K-means dominant-palette extraction.
    palette_k: int = 5
    kmeans_iters: int = 25
    kmeans_seed: int = 1234
    # Transition detection. `content_threshold` is the HSV content-delta score
    # (PySceneDetect ContentDetector parlance) above which a HARD CUT is marked.
    # `adaptive_ratio` + `min_content_val` implement the AdaptiveDetector idea:
    # only fire when a frame's score is `adaptive_ratio`x its neighbourhood mean,
    # which rejects whip-pan / zoom / handheld false positives on short-form video.
    transition_sample_fps: float = 12.0     # dense sampling for ms-precise cuts
    content_threshold: float = 27.0         # strong-cut absolute floor (ContentDetector default)
    adaptive_ratio: float = 3.0             # frame score must exceed this x neighbour mean
    min_content_val: float = 15.0           # below this, never a cut
    neighbor_frames: int = 4                # rolling window radius (each side) for the ratio
    dissolve_peak_frac: float = 0.4         # plateau frames above this fraction of peak => dissolve
    dissolve_min_frames: int = 5            # consecutive elevated frames => crossfade/dissolve
    ssim_cut_threshold: float = 0.55        # SSIM below this between adjacent frames => hard scene change
    fade_luma_threshold: float = 16.0       # mean luma below this => fade-to-black frame
    min_scene_len_sec: float = 0.4          # suppress double-fires within this window
    # Text-overlay region detection.
    text_edge_threshold: float = 0.085      # min edge-density in a band to flag text
    text_min_duration_sec: float = 0.3      # ignore flickers shorter than this


@dataclass(slots=True)
class CleaningConfig:
    # §3 Module C.2 Smart Cuts — silence.
    remove_silence: bool = True             # master toggle for silence/dead-air cutting
    silence_db: float = -40.0               # amplitude floor (dBFS)
    min_silence_sec: float = 0.35           # only cut silence longer than this
    # Asymmetric breathing room around cuts (replaces a single symmetric pad): keep
    # more of a word's trailing decay (after_pad) and a clear breath before the next
    # word (before_pad) so cuts never clip word onsets/tails or feel abrupt.
    after_pad_sec: float = 0.15             # kept after the preceding word ends
    before_pad_sec: float = 0.10            # kept before the next word begins
    snap_cuts_to_words: bool = True         # never cut into a word (snap removed spans off word spans)
    word_snap_radius_sec: float = 0.12      # how far a cut edge may move to reach a word boundary
    min_kept_segment_sec: float = 0.40      # absorb micro kept-clips (avoids choppy stutter)
    # §3 Module C.2 — filler scrubbing.
    remove_fillers: bool = True
    aggressive_fillers: bool = False
    filler_pad_sec: float = 0.04
    # §3 Module C.1 — bad-take / retake detection.
    detect_retakes: bool = True
    retake_similarity: float = 0.82         # cosine/lexical sim >= this => same line restated
    retake_min_words: int = 3               # only compare phrases of this many+ words
    retake_max_gap_sec: float = 6.0         # restart must follow within this window
    # Trim leading/trailing dead air.
    trim_lead_silence: bool = True


@dataclass(slots=True)
class SynthesisConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 60
    # §3 Module D — smart zoom punch-in to mask jump cuts.
    smart_zoom: bool = True
    zoom_factor: float = 1.12               # within the spec's 1.10–1.15 band
    # §3 Module D — caption transition timing.
    caption_fade_sec: float = 0.20          # 200ms alpha blend
    caption_default_zone: str = "bottom"
    caption_default_style: str = "fade"
    caption_mode: str = "legacy"            # "legacy" = per-line | "karaoke" = per-word scale-pop captions
    audio_crossfade_ms: int = 18            # feather each cut seam so jumps aren't abrupt (0 = hard cut)
    # Encoder.
    prefer_hardware: bool = True
    hardware_priority: tuple[str, ...] = ("h264_nvenc", "h264_amf", "h264_qsv")
    software_encoder: str = "libx264"
    video_bitrate: str = "12M"
    audio_bitrate: str = "192k"
    crf: int = 21                           # software-encoder quality (premium-grade; ~halves file size vs 19)
    color_grade_to_reference: bool = True


# --------------------------------------------------------------------------- #
# Professional production controls (cinematography). Each value maps to a prompt
# clause for the AI b-roll (Imagen is prompt-only) and/or a render param.
# --------------------------------------------------------------------------- #
_LENS_CLAUSES: dict[str, str] = {
    "24mm": "shot on a 24mm wide-angle lens, expansive field of view, deep environmental context",
    "35mm": "35mm lens, natural reportage field of view, documentary framing",
    "50mm": "50mm lens, natural human-eye perspective, true-to-life proportions",
    "85mm": "85mm short-telephoto portrait lens, compressed perspective, creamy out-of-focus background, strong subject separation",
    "100mm_macro": "100mm macro lens, extreme close detail, razor-thin focal plane",
    "anamorphic": "vintage anamorphic lenses, 2.0x squeeze, oval bokeh, horizontal blue lens flares, cinematic widescreen",
}
_LENS_ZOOM: dict[str, float] = {"24mm": 1.06, "35mm": 1.10, "50mm": 1.12, "85mm": 1.15, "100mm_macro": 1.15, "anamorphic": 1.14}
_APERTURE_CLAUSES: list[tuple[float, str]] = [
    (1.4, "wide open at f/1.4, extremely shallow depth of field, creamy bokeh, dreamy subject isolation"),
    (2.8, "at f/2.8, shallow depth of field, clear subject separation"),
    (5.6, "at f/5.6, moderate depth of field"),
    (11.0, "at f/11, deep depth of field, most of the scene sharp"),
    (16.0, "at f/16, deep focus, sharp front to back, subtle sunstars"),
]
_LIGHTING_CLAUSES: dict[str, str] = {
    "high_key": "bright high-key lighting, clean and airy",
    "soft_natural": "soft natural lighting, gentle and flattering",
    "golden_hour": "warm golden-hour light, long soft shadows",
    "low_key": "moody low-key lighting, deep shadows, dramatic",
    "chiaroscuro": "chiaroscuro lighting, strong light-dark contrast, single key light",
    "neon": "vibrant neon lighting, saturated colored glow, night-city mood",
}
_TIME_CLAUSES: dict[str, str] = {
    "sunrise": "at sunrise, cool dawn light", "midday": "bright midday sun, crisp shadows",
    "golden_hour": "during golden hour, warm low sun", "blue_hour": "during blue hour, cool twilight",
    "night": "at night, artificial light sources",
}
_ANGLE_CLAUSES: dict[str, str] = {
    "low_angle": "low-angle shot looking up, heroic perspective",
    "high_angle": "high-angle shot looking down", "overhead": "directly overhead top-down flat-lay, 90-degree bird-eye view",
    "dutch": "dutch angle, canted horizon, dynamic unease", "ots": "over-the-shoulder framing, foreground shoulder soft",
}
_SHOT_CLAUSES: dict[str, str] = {
    "ecu": "extreme close-up", "closeup": "tight close-up shot", "medium": "medium shot",
    "wide": "wide establishing shot", "aerial": "aerial drone shot",
}
# film_stock -> (prompt clause, ColorGrade override deltas). Single source of truth so
# the AI b-roll and the graded A-roll never drift ("two cameras" tell).
FILM_STOCKS: dict[str, tuple[str, dict[str, float]]] = {
    "digital_clean": ("clean modern digital cinema look, true color", {}),
    "portra_400": ("Kodak Portra 400, warm skin tones, soft pastel palette, fine grain",
                   {"brightness": 0.02, "contrast": 0.95, "saturation": 1.05, "temperature": 0.18}),
    "vision3": ("Kodak Vision3 500T cinema stock, filmic latitude, rich shadows",
                {"contrast": 1.08, "saturation": 1.04, "temperature": 0.06, "gamma": 0.97}),
    "teal_orange": ("Hollywood teal-and-orange grade, warm skin vs cool teal shadows",
                    {"saturation": 1.18, "temperature": 0.22, "shadow_balance": -0.18}),
    "bleach_bypass": ("bleach bypass, desaturated, crushed blacks, metallic contrast",
                      {"saturation": 0.55, "contrast": 1.25, "brightness": -0.04}),
    "bw_trix": ("black and white, Kodak Tri-X 400, deep blacks, classic grain",
                {"saturation": 0.0, "contrast": 1.15, "gamma": 0.95}),
    "cross_process": ("cross-processed film, shifted greens and yellows, high contrast",
                      {"saturation": 1.2, "contrast": 1.12, "temperature": -0.1}),
}


@dataclass(slots=True)
class CinematographyConfig:
    """Pro look controls — composed into the AI b-roll prompt + a grade override."""

    lens: str = "50mm"
    aperture: float = 2.8
    film_stock: str = "digital_clean"
    lighting: str = "soft_natural"
    time_of_day: str = "unset"
    camera_angle: str = "eye_level"
    shot_type: str = "medium"
    film_grain_amount: float = 0.0

    def _aperture_clause(self) -> str:
        nearest = min(_APERTURE_CLAUSES, key=lambda kv: abs(kv[0] - self.aperture))
        return nearest[1]

    def to_prompt_clauses(self) -> list[str]:
        """De-duped, length-capped list of cinematography modifiers (max ~5)."""
        clauses: list[str] = []
        clauses.append(_LENS_CLAUSES.get(self.lens, _LENS_CLAUSES["50mm"]))
        clauses.append(self._aperture_clause())
        stock = FILM_STOCKS.get(self.film_stock)
        if stock and self.film_stock != "digital_clean":
            clauses.append(stock[0])
        # Suppress lighting if time_of_day already implies it (golden_hour overlap).
        if self.time_of_day not in ("unset", "") and self.time_of_day in _TIME_CLAUSES:
            clauses.append(_TIME_CLAUSES[self.time_of_day])
        elif self.lighting in _LIGHTING_CLAUSES and self.lighting != "soft_natural":
            clauses.append(_LIGHTING_CLAUSES[self.lighting])
        if self.camera_angle in _ANGLE_CLAUSES:
            clauses.append(_ANGLE_CLAUSES[self.camera_angle])
        if self.film_grain_amount >= 8:
            tier = "very fine grain" if self.film_grain_amount < 18 else ("visible grain" if self.film_grain_amount < 32 else "heavy analog texture")
            clauses.append(f"subtle 35mm film {tier}, organic analog texture")
        return clauses[:5]

    def grade_override(self) -> dict[str, float]:
        return dict(FILM_STOCKS.get(self.film_stock, ("", {}))[1])

    def zoom_bias(self) -> float:
        return _LENS_ZOOM.get(self.lens, 1.12)


# Preset bundles — each writes a complete set of control values. Smooth-cut quality
# fixes are ON in every preset (baseline, not style).
PRESETS: dict[str, dict[str, object]] = {
    "cinematic": {"lens": "85mm", "aperture": 2.8, "film_stock": "portra_400", "lighting": "soft_natural",
                  "broll_motion": "zoom_in", "framing": "full_916", "film_grain": True, "film_grain_amount": 12,
                  "zoom_intensity": 1.14, "color_grade": True, "caption_style": "pop", "caption_zone": "bottom",
                  "broll_mode": "ai", "ai_broll": True, "filler_aggressiveness": 1},
    "cinematic_film": {"lens": "anamorphic", "aperture": 2.8, "film_stock": "vision3", "lighting": "low_key",
                       "broll_motion": "zoom_in", "framing": "letterbox_239", "film_grain": True, "film_grain_amount": 16,
                       "zoom_intensity": 1.12, "color_grade": True, "caption_style": "fade", "caption_zone": "bottom",
                       "broll_mode": "ai", "ai_broll": True, "filler_aggressiveness": 1},
    "clean_ugc": {"lens": "35mm", "aperture": 5.6, "film_stock": "digital_clean", "lighting": "high_key",
                  "broll_motion": "zoom_in", "framing": "full_916", "film_grain": False, "film_grain_amount": 0,
                  "zoom_intensity": 1.10, "color_grade": False, "caption_style": "pop", "caption_zone": "bottom",
                  "broll_mode": "none", "ai_broll": False, "filler_aggressiveness": 1},
    "documentary": {"lens": "35mm", "aperture": 5.6, "film_stock": "digital_clean", "lighting": "soft_natural",
                    "broll_motion": "pan_right", "framing": "full_916", "film_grain": False, "film_grain_amount": 0,
                    "zoom_intensity": 1.10, "color_grade": True, "caption_style": "fade", "caption_zone": "bottom",
                    "broll_mode": "ai", "ai_broll": True, "filler_aggressiveness": 1},
    "gritty_doc": {"lens": "35mm", "aperture": 5.6, "film_stock": "bleach_bypass", "lighting": "low_key",
                   "broll_motion": "static", "framing": "full_916", "film_grain": True, "film_grain_amount": 24,
                   "zoom_intensity": 1.12, "color_grade": True, "caption_style": "fade", "caption_zone": "bottom",
                   "broll_mode": "ai", "ai_broll": True, "filler_aggressiveness": 2},
}


@dataclass(slots=True)
class EngineConfig:
    analyzer: AnalyzerConfig = field(default_factory=AnalyzerConfig)
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
