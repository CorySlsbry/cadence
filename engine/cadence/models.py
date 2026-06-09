"""Core domain model for the Cadence engine.

These are plain, mostly-frozen dataclasses (no pydantic / no heavy imports) so the
algorithmic core stays trivially testable and serialization is explicit. The HTTP
layer wraps these; it does not replace them.

Serialization contract: every public model exposes ``to_dict()`` returning a
JSON-safe ``dict`` (primitives, lists, dicts only). Enums serialize to their
string ``value``. This is what powers the §4 "Generation Plan Blueprint" JSON.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------- #
# Primitives & geometry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RGBColor:
    """An 8-bit-per-channel RGB color."""

    r: int
    g: int
    b: int

    def __post_init__(self) -> None:
        for name, v in (("r", self.r), ("g", self.g), ("b", self.b)):
            if not 0 <= int(v) <= 255:
                raise ValueError(f"RGBColor.{name} out of range 0..255: {v}")

    @property
    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    @property
    def luma(self) -> float:
        """Rec.709 relative luminance (0..255)."""
        return 0.2126 * self.r + 0.7152 * self.g + 0.0722 * self.b

    @classmethod
    def from_hex(cls, value: str) -> "RGBColor":
        s = value.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) != 6:
            raise ValueError(f"invalid hex color: {value!r}")
        return cls(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))

    def to_dict(self) -> dict[str, Any]:
        return {"r": self.r, "g": self.g, "b": self.b, "hex": self.hex}


@dataclass(frozen=True, slots=True)
class BBox:
    """Normalized bounding box; all coords in 0..1 relative to frame size."""

    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A half-open time interval [start, end) in seconds."""

    start: float
    end: float

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"TimeRange end {self.end} < start {self.start}")

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, other: "TimeRange") -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "duration": self.duration}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TimeRange":
        return cls(float(d["start"]), float(d["end"]))


# --------------------------------------------------------------------------- #
# Transcription
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Word:
    """A single recognized word with timing, from any transcription backend."""

    text: str
    start: float
    end: float
    prob: float = 1.0

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "start": self.start, "end": self.end, "prob": self.prob}


@dataclass(frozen=True, slots=True)
class Transcript:
    """An ordered sequence of words. Backend-agnostic."""

    words: tuple[Word, ...] = ()
    language: str = "en"

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def duration(self) -> float:
        return self.words[-1].end if self.words else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"language": self.language, "words": [w.to_dict() for w in self.words]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transcript":
        try:
            words = tuple(
                Word(text=w["text"], start=float(w["start"]), end=float(w["end"]), prob=float(w.get("prob", 1.0)))
                for w in data.get("words", [])
            )
            return cls(words=words, language=data.get("language", "en"))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"invalid transcript payload: {exc}") from exc


# --------------------------------------------------------------------------- #
# Module A — reference analysis
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ColorSwatch:
    color: RGBColor
    weight: float  # fraction of sampled pixels assigned to this cluster (0..1)

    def to_dict(self) -> dict[str, Any]:
        return {"color": self.color.to_dict(), "weight": self.weight}


class ExposureLabel(str, Enum):
    DARK = "dark"
    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"
    BRIGHT = "bright"


@dataclass(frozen=True, slots=True)
class ExposureStats:
    mean_luma: float       # 0..255
    std_luma: float        # contrast proxy
    p05_luma: float
    p95_luma: float
    label: ExposureLabel

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean_luma": self.mean_luma,
            "std_luma": self.std_luma,
            "p05_luma": self.p05_luma,
            "p95_luma": self.p95_luma,
            "label": self.label.value,
        }


@dataclass(frozen=True, slots=True)
class ColorProfile:
    palette: tuple[ColorSwatch, ...]  # sorted by weight desc
    exposure: ExposureStats

    @property
    def primary(self) -> RGBColor | None:
        return self.palette[0].color if self.palette else None

    @property
    def secondary(self) -> RGBColor | None:
        return self.palette[1].color if len(self.palette) > 1 else None

    @property
    def accent(self) -> RGBColor | None:
        return self.palette[2].color if len(self.palette) > 2 else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "palette": [s.to_dict() for s in self.palette],
            "primary": self.primary.hex if self.primary else None,
            "secondary": self.secondary.hex if self.secondary else None,
            "accent": self.accent.hex if self.accent else None,
            "exposure": self.exposure.to_dict(),
        }


class TransitionType(str, Enum):
    HARD_CUT = "hard_cut"
    CROSSFADE = "crossfade"
    FADE_TO_BLACK = "fade_to_black"
    FADE_FROM_BLACK = "fade_from_black"
    ZOOM = "zoom"
    DISSOLVE = "dissolve"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Transition:
    timestamp: float          # seconds, millisecond-precise
    type: TransitionType
    confidence: float         # 0..1
    score: float              # raw detector score (content delta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "type": self.type.value,
            "confidence": self.confidence,
            "score": self.score,
        }


class TextZone(str, Enum):
    """Vertical placement zones per §3 Module D (15% / 50% / 80%)."""

    TOP = "top"        # baseline ~15% from ceiling
    CENTER = "center"  # ~50% dead center
    BOTTOM = "bottom"  # ~80% from floor

    @property
    def anchor_y(self) -> float:
        return {"top": 0.15, "center": 0.50, "bottom": 0.80}[self.value]

    @classmethod
    def from_y(cls, cy: float) -> "TextZone":
        # nearest anchor
        return min(cls, key=lambda z: abs(z.anchor_y - cy))


@dataclass(frozen=True, slots=True)
class TextOverlayEvent:
    start: float
    end: float
    bbox: BBox
    zone: TextZone
    text: str | None = None          # populated only if an OCR backend is available
    color: RGBColor | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "bbox": self.bbox.to_dict(),
            "zone": self.zone.value,
            "text": self.text,
            "color": self.color.hex if self.color else None,
        }


@dataclass(frozen=True, slots=True)
class PacingProfile:
    words_per_minute: float
    avg_segment_sec: float       # mean time between cuts
    cut_density_per_min: float
    beat_interval_sec: float     # dominant rhythm interval
    segment_boundaries: tuple[float, ...]  # cut timestamps incl. 0 and duration

    def to_dict(self) -> dict[str, Any]:
        return {
            "words_per_minute": self.words_per_minute,
            "avg_segment_sec": self.avg_segment_sec,
            "cut_density_per_min": self.cut_density_per_min,
            "beat_interval_sec": self.beat_interval_sec,
            "segment_boundaries": list(self.segment_boundaries),
        }


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: str
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    codec: str = ""

    @property
    def is_vertical(self) -> bool:
        return self.height >= self.width

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReferenceAnalysis:
    """The full output of Module A."""

    media: MediaInfo
    color_profile: ColorProfile
    transitions: tuple[Transition, ...]
    text_overlays: tuple[TextOverlayEvent, ...]
    pacing: PacingProfile
    transcript: Transcript | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media": self.media.to_dict(),
            "color_profile": self.color_profile.to_dict(),
            "transitions": [t.to_dict() for t in self.transitions],
            "text_overlays": [o.to_dict() for o in self.text_overlays],
            "pacing": self.pacing.to_dict(),
            "transcript": self.transcript.to_dict() if self.transcript else None,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# --------------------------------------------------------------------------- #
# Module B — brand board
# --------------------------------------------------------------------------- #
class AssetKind(str, Enum):
    LOGO = "logo"
    WATERMARK = "watermark"
    FONT = "font"
    STINGER = "stinger"      # intro/outro animation clip
    OVERLAY = "overlay"      # pre-rendered frame overlay
    TRANSITION = "transition"  # reusable brand b-roll / cutaway image


class Anchor(str, Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"

    def overlay_xy(self, pad: int = 48) -> tuple[str, str]:
        """ffmpeg overlay x:y expression for this anchor (main=W/H, overlay=w/h)."""
        return {
            "top_left": (f"{pad}", f"{pad}"),
            "top_right": (f"W-w-{pad}", f"{pad}"),
            "bottom_left": (f"{pad}", f"H-h-{pad}"),
            "bottom_right": (f"W-w-{pad}", f"H-h-{pad}"),
            "center": ("(W-w)/2", "(H-h)/2"),
        }[self.value]


@dataclass(slots=True)
class BrandAsset:
    id: str
    kind: AssetKind
    name: str
    path: str
    opacity: float = 1.0
    anchor: Anchor = Anchor.BOTTOM_RIGHT
    scale: float = 1.0              # fraction of frame width for watermark/logo
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["anchor"] = self.anchor.value
        return d


@dataclass(slots=True)
class BrandPalette:
    name: str
    colors: list[RGBColor]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "colors": [c.hex for c in self.colors]}


@dataclass(slots=True)
class BrandBoard:
    id: str
    name: str
    palettes: list[BrandPalette] = field(default_factory=list)
    assets: list[BrandAsset] = field(default_factory=list)
    caption_font_path: str | None = None
    caption_primary: RGBColor | None = None
    caption_outline: RGBColor | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "palettes": [p.to_dict() for p in self.palettes],
            "assets": [a.to_dict() for a in self.assets],
            "caption_font_path": self.caption_font_path,
            "caption_primary": self.caption_primary.hex if self.caption_primary else None,
            "caption_outline": self.caption_outline.hex if self.caption_outline else None,
        }

    def asset_of(self, kind: AssetKind) -> BrandAsset | None:
        for a in self.assets:
            if a.kind == kind:
                return a
        return None


# --------------------------------------------------------------------------- #
# Module C — cleaning / edit decisions
# --------------------------------------------------------------------------- #
class CutReason(str, Enum):
    SILENCE = "silence"
    FILLER = "filler"
    BAD_TAKE = "bad_take"
    LEAD_TRIM = "lead_trim"


@dataclass(frozen=True, slots=True)
class RemovedSpan:
    range: TimeRange
    reason: CutReason
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"range": self.range.to_dict(), "reason": self.reason.value, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RemovedSpan":
        return cls(
            range=TimeRange.from_dict(d["range"]),
            reason=CutReason(d.get("reason", "silence")),
            detail=d.get("detail", ""),
        )


@dataclass(frozen=True, slots=True)
class EditDecisionList:
    """The result of Module C: which spans of the raw recording to KEEP."""

    source: str
    source_duration: float
    kept: tuple[TimeRange, ...]
    removed: tuple[RemovedSpan, ...]
    transcript: Transcript | None = None

    @property
    def output_duration(self) -> float:
        return sum(r.duration for r in self.kept)

    @property
    def removed_duration(self) -> float:
        return sum(r.range.duration for r in self.removed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_duration": self.source_duration,
            "output_duration": self.output_duration,
            "removed_duration": self.removed_duration,
            "kept": [r.to_dict() for r in self.kept],
            "removed": [r.to_dict() for r in self.removed],
            "transcript": self.transcript.to_dict() if self.transcript else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EditDecisionList":
        return cls(
            source=d["source"],
            source_duration=float(d["source_duration"]),
            kept=tuple(TimeRange.from_dict(r) for r in d.get("kept", [])),
            removed=tuple(RemovedSpan.from_dict(r) for r in d.get("removed", [])),
            transcript=Transcript.from_dict(d["transcript"]) if d.get("transcript") else None,
        )


# --------------------------------------------------------------------------- #
# Module D + §4 — generation plan & render
# --------------------------------------------------------------------------- #
class CaptionStyle(str, Enum):
    FADE = "fade"     # alpha blend in/out over a window
    POP = "pop"       # instantaneous hard 0->1 presentation


@dataclass(frozen=True, slots=True)
class CaptionWord:
    """One timed word inside a karaoke caption line (output-timeline seconds)."""

    text: str
    start: float
    end: float

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaptionWord":
        return cls(text=d["text"], start=float(d["start"]), end=float(d["end"]))


@dataclass(slots=True)
class Caption:
    text: str
    start: float
    end: float
    zone: TextZone = TextZone.BOTTOM
    style: CaptionStyle = CaptionStyle.FADE
    words: list[CaptionWord] = field(default_factory=list)  # per-word timing → karaoke; empty = legacy line

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "zone": self.zone.value,
            "style": self.style.value,
            "words": [w.to_dict() for w in self.words],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Caption":
        return cls(
            text=d["text"],
            start=float(d["start"]),
            end=float(d["end"]),
            zone=TextZone(d.get("zone", "bottom")),
            style=CaptionStyle(d.get("style", "fade")),
            words=[CaptionWord.from_dict(w) for w in d.get("words", [])],
        )


@dataclass(slots=True)
class ClipSpec:
    """One A-roll segment placed on the timeline."""

    source: str
    in_point: float
    out_point: float
    zoom: float = 1.0                 # 1.0 = none; 1.1-1.15 = smart punch-in
    transition_in: TransitionType = TransitionType.HARD_CUT
    transition_dur: float = 0.0

    @property
    def duration(self) -> float:
        return self.out_point - self.in_point

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "in_point": self.in_point,
            "out_point": self.out_point,
            "duration": self.duration,
            "zoom": self.zoom,
            "transition_in": self.transition_in.value,
            "transition_dur": self.transition_dur,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClipSpec":
        return cls(
            source=d["source"],
            in_point=float(d["in_point"]),
            out_point=float(d["out_point"]),
            zoom=float(d.get("zoom", 1.0)),
            transition_in=TransitionType(d.get("transition_in", "hard_cut")),
            transition_dur=float(d.get("transition_dur", 0.0)),
        )


@dataclass(slots=True)
class ColorGrade:
    """Programmatic grade to push raw A-roll toward the reference palette."""

    brightness: float = 0.0     # eq brightness, -1..1
    contrast: float = 1.0       # eq contrast, 0..2
    saturation: float = 1.0     # eq saturation, 0..3
    gamma: float = 1.0          # eq gamma, 0.1..10
    temperature: float = 0.0    # colorbalance shift, -1..1 (warm +, cool -)
    shadow_balance: float = 0.0 # split-tone shadows (teal/orange), -1..1 (cool -, warm +)
    grain: float = 0.0          # 35mm film grain amount (0..40), applied as an ffmpeg noise node

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ColorGrade":
        return cls(
            brightness=float(d.get("brightness", 0.0)),
            contrast=float(d.get("contrast", 1.0)),
            saturation=float(d.get("saturation", 1.0)),
            gamma=float(d.get("gamma", 1.0)),
            temperature=float(d.get("temperature", 0.0)),
            shadow_balance=float(d.get("shadow_balance", 0.0)),
            grain=float(d.get("grain", 0.0)),
        )


@dataclass(slots=True)
class WatermarkSpec:
    path: str
    opacity: float = 1.0
    anchor: Anchor = Anchor.BOTTOM_RIGHT
    scale: float = 0.18

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["anchor"] = self.anchor.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WatermarkSpec":
        return cls(
            path=d["path"],
            opacity=float(d.get("opacity", 1.0)),
            anchor=Anchor(d.get("anchor", "bottom_right")),
            scale=float(d.get("scale", 0.18)),
        )


class KenBurns(str, Enum):
    """Motion applied to a still image to make it feel like b-roll."""

    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"


@dataclass(slots=True)
class BrollInsert:
    """A b-roll cutaway: a still image animated (Ken Burns) and overlaid on the
    A-roll during ``[start, end)`` while the speaker's audio continues underneath."""

    image_path: str
    start: float
    end: float
    motion: KenBurns = KenBurns.ZOOM_IN
    fade: float = 0.18      # crossfade in/out at the edges (seconds)
    source: str = "ai"      # provenance: "ai" (generated) | "factual" (curated real asset) | "brand"

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "motion": self.motion.value,
            "fade": self.fade,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BrollInsert":
        return cls(
            image_path=d["image_path"],
            start=float(d["start"]),
            end=float(d["end"]),
            motion=KenBurns(d.get("motion", "zoom_in")),
            fade=float(d.get("fade", 0.18)),
            source=d.get("source", "ai"),
        )


@dataclass(slots=True)
class GenerationPlan:
    """§4 Generation Plan Blueprint — the structured render contract."""

    width: int = 1080
    height: int = 1920
    fps: int = 60
    clips: list[ClipSpec] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    broll: list[BrollInsert] = field(default_factory=list)
    color_grade: ColorGrade = field(default_factory=ColorGrade)
    watermark: WatermarkSpec | None = None
    caption_font_path: str | None = None
    caption_primary_hex: str = "#FFFFFF"
    caption_outline_hex: str = "#000000"
    audio_normalize: bool = True
    letterbox: bool = False     # 2.39:1 cinematic bars
    music_path: str | None = None   # background music bed (ducked under speech)
    music_volume: float = 0.18      # base music level under speech (0..1)
    hook: str | None = None         # opening HOOK card text (animated, first ~2.4s); None = no card

    @property
    def total_duration(self) -> float:
        return sum(c.duration for c in self.clips)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "output": {"width": self.width, "height": self.height, "fps": self.fps},
            "clips": [c.to_dict() for c in self.clips],
            "captions": [c.to_dict() for c in self.captions],
            "broll": [b.to_dict() for b in self.broll],
            "color_grade": self.color_grade.to_dict(),
            "watermark": self.watermark.to_dict() if self.watermark else None,
            "caption_font_path": self.caption_font_path,
            "caption_primary_hex": self.caption_primary_hex,
            "caption_outline_hex": self.caption_outline_hex,
            "audio_normalize": self.audio_normalize,
            "letterbox": self.letterbox,
            "music_path": self.music_path,
            "music_volume": self.music_volume,
            "hook": self.hook,
            "total_duration": self.total_duration,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GenerationPlan":
        try:
            out = d.get("output", {})
            wm = d.get("watermark")
            return cls(
                width=int(out.get("width", 1080)),
                height=int(out.get("height", 1920)),
                fps=int(out.get("fps", 60)),
                clips=[ClipSpec.from_dict(c) for c in d.get("clips", [])],
                captions=[Caption.from_dict(c) for c in d.get("captions", [])],
                broll=[BrollInsert.from_dict(b) for b in d.get("broll", [])],
                color_grade=ColorGrade.from_dict(d.get("color_grade", {})),
                watermark=WatermarkSpec.from_dict(wm) if wm else None,
                caption_font_path=d.get("caption_font_path"),
                caption_primary_hex=d.get("caption_primary_hex", "#FFFFFF"),
                caption_outline_hex=d.get("caption_outline_hex", "#000000"),
                audio_normalize=bool(d.get("audio_normalize", True)),
                letterbox=bool(d.get("letterbox", False)),
                music_path=d.get("music_path"),
                music_volume=float(d.get("music_volume", 0.18)),
                hook=d.get("hook"),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"invalid generation plan: {exc}") from exc

    @classmethod
    def from_json(cls, text: str) -> "GenerationPlan":
        return cls.from_dict(json.loads(text))


@dataclass(frozen=True, slots=True)
class RenderResult:
    output_path: str
    width: int
    height: int
    fps: float
    duration: float
    codec: str
    used_hardware: bool
    encoder: str
    command: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
