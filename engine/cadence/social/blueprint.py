"""Creator brand-blueprint → prompt context.

The web app stores an Ikigai-derived blueprint per user (ICP + content pillars +
voice fingerprint). When present, every generated surface (hooks, social captions,
repurpose) is written as THAT creator for THAT audience — "authentic, not original."
This formatter is pure so it's unit-testable; builders accept the result as an
optional ``voice`` block appended to their prompts (empty string = no-op).
"""

from __future__ import annotations

from typing import Any


def _join(items: Any, limit: int = 6) -> str:
    if not isinstance(items, (list, tuple)):
        return ""
    out = [" ".join(str(x).split()) for x in items[:limit] if str(x).strip()]
    return "; ".join(out)


def blueprint_context(bp: dict[str, Any] | None) -> str:
    """Format a brand_blueprints row into a compact prompt block ('' if unusable)."""
    if not isinstance(bp, dict):
        return ""
    icp = bp.get("icp") if isinstance(bp.get("icp"), dict) else {}
    voice = bp.get("voice") if isinstance(bp.get("voice"), dict) else {}
    pillars = bp.get("pillars") if isinstance(bp.get("pillars"), list) else []
    lines: list[str] = []
    if icp.get("who"):
        lines.append(f"Audience: {icp['who']}")
    pains = _join(icp.get("pains"), 4)
    if pains:
        lines.append(f"Their pains: {pains}")
    pillar_names = _join([p.get("name") for p in pillars if isinstance(p, dict)], 5)
    if pillar_names:
        lines.append(f"Content pillars: {pillar_names}")
    if voice.get("tone"):
        lines.append(f"Tone: {voice['tone']}")
    if voice.get("pov"):
        lines.append(f"POV: {voice['pov']}")
    phrases = _join(voice.get("phrases"), 5)
    if phrases:
        lines.append(f"Signature phrasing: {phrases}")
    if not lines:
        return ""
    return (
        "\n\nCREATOR VOICE (write as THIS creator, for THIS audience — never generic):\n- "
        + "\n- ".join(lines)
    )
