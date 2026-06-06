"""Social distribution: captions, hooks, repurposing + publishing adapters."""

from cadence.social._llm import GeminiJSON, transcript_text
from cadence.social.captions import (
    LIMITS,
    GeminiCaptionWriter,
    StubCaptionWriter,
    build_social_captions,
    to_post_text,
)
from cadence.social.hooks import build_hooks, normalize_hooks
from cadence.social.repurpose import build_repurpose, normalize_repurpose

__all__ = [
    "LIMITS",
    "GeminiCaptionWriter",
    "GeminiJSON",
    "StubCaptionWriter",
    "build_hooks",
    "build_repurpose",
    "build_social_captions",
    "normalize_hooks",
    "normalize_repurpose",
    "to_post_text",
    "transcript_text",
]
