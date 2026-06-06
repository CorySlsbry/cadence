"""Hook generator + A/B variants.

The first ~3 seconds and the first caption line decide a short's reach (≈50% drop-off
at 3s; the caption is also a search surface in 2026). From the transcript this produces
several punchy opening-line options PLUS a "cold open" suggestion — the strongest line
already in the take to lead with. One cheap gemini-flash call; the LLM is injected so
``build_hooks`` is unit-testable, and it degrades to a deterministic stub (never raises).
"""

from __future__ import annotations

from typing import Any

MAX_HOOK_CHARS = 120
MAX_HOOKS = 5

_PROMPT = """You are a short-form video hook strategist. From the transcript of a vertical short, \
write opening "hooks" that maximize the first-3-seconds hold + searchability (2026).

Return STRICT JSON:
{{"hooks": ["...", "..."], "cold_open": {{"line": "...", "why": "..."}}}}

Rules:
- "hooks": EXACTLY {n} distinct spoken/overlay opening lines, each <= 100 chars, punchy, \
curiosity- or stakes-driven, no clickbait lies, no hashtags. Vary the angle (question, bold claim, \
number/stat, contrarian, "here's how"). Lead with the searchable keyword where natural.
- "cold_open": pick the single most arresting sentence ALREADY IN the transcript to open with \
(verbatim or lightly tightened) + a one-line "why" it hooks. If nothing strong exists, synthesize one.
- No preamble, JSON only."""


def _clean_line(s: Any, limit: int) -> str:
    s = " ".join(str(s or "").split())
    return s[:limit].rstrip() if len(s) > limit else s


def normalize_hooks(raw: dict[str, Any], n: int = MAX_HOOKS) -> dict[str, Any]:
    """Coerce + hard-cap an LLM draft into the canonical hook structure."""
    raw = raw if isinstance(raw, dict) else {}
    hooks: list[str] = []
    seen: set[str] = set()
    for h in raw.get("hooks") or []:
        line = _clean_line(h, MAX_HOOK_CHARS)
        if line and line.lower() not in seen:
            seen.add(line.lower())
            hooks.append(line)
    co = raw.get("cold_open") if isinstance(raw.get("cold_open"), dict) else {}
    return {
        "hooks": hooks[:n],
        "cold_open": {
            "line": _clean_line(co.get("line", ""), 200),
            "why": _clean_line(co.get("why", ""), 200),
        },
    }


def _stub_hooks(text: str, n: int) -> dict[str, Any]:
    lead = (text.split(".")[0] or text)[:90].strip() or "Watch this"
    base = [
        f"{lead}?",
        f"Here's what nobody tells you: {lead.lower()}",
        f"The truth about {lead.lower()}",
        "Stop scrolling — this changes things.",
        f"3 things I learned: {lead.lower()}",
    ]
    return normalize_hooks({"hooks": base, "cold_open": {"line": lead, "why": "Strong, concrete opener."}}, n)


def build_hooks(text: str, llm=None, *, n: int = MAX_HOOKS) -> dict[str, Any]:
    """Generate hook options + a cold-open from transcript text. Falls back to a
    deterministic stub if no LLM / on any failure (a hook blip never fails a render)."""
    text = " ".join((text or "").split())
    if not text:
        return None  # nothing to hook
    if llm is None:
        return _stub_hooks(text, n)
    try:
        raw = llm.complete(_PROMPT.format(n=n) + f'\n\nTranscript: "{text[:6000]}"')
        out = normalize_hooks(raw, n)
        return out if out["hooks"] else _stub_hooks(text, n)
    except Exception:  # noqa: BLE001
        return _stub_hooks(text, n)
