"""Social distribution: per-platform caption generation + publishing adapters."""

from cadence.social.captions import (
    LIMITS,
    GeminiCaptionWriter,
    StubCaptionWriter,
    build_social_captions,
    to_post_text,
)

__all__ = [
    "LIMITS",
    "GeminiCaptionWriter",
    "StubCaptionWriter",
    "build_social_captions",
    "to_post_text",
]
