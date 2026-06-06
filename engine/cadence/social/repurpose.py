"""Repurposing engine — one video → many text assets.

From the transcript, generate a carousel (slide texts), an X/Twitter thread, a newsletter
blurb, and pull-quote cards. "One input, ten outputs." One cheap gemini-flash call; LLM is
injected (unit-testable); degrades to a deterministic stub and never raises.
"""

from __future__ import annotations

from typing import Any

LIMITS = {"carousel": (8, 200), "thread": (6, 280), "quote_cards": (3, 120)}  # (max_items, max_chars)

_PROMPT = """You are a content repurposing engine. From the transcript of a short video, produce \
ready-to-post derivatives as STRICT JSON:
{{"carousel": ["slide 1", "..."], "thread": ["tweet 1", "..."], "newsletter": "...", "quote_cards": ["...", "..."]}}

Rules:
- "carousel": 5-8 slides. Slide 1 = the hook; last = a CTA. Each <= 200 chars, punchy, standalone.
- "thread": 4-6 tweets telling the same story; tweet 1 hooks; each <= 280 chars; no "1/" numbering.
- "newsletter": a warm 2-4 sentence blurb summarizing the takeaway with a soft CTA.
- "quote_cards": 2-3 short, quotable, standalone lines (<= 120 chars) good on a graphic.
- Keep the creator's voice; no hashtags except naturally inside a tweet; no preamble, JSON only."""


def _clean_list(items: Any, max_items: int, max_chars: int) -> list[str]:
    out: list[str] = []
    for it in items or []:
        s = " ".join(str(it or "").split())
        if not s:
            continue
        out.append(s[:max_chars].rstrip() if len(s) > max_chars else s)
        if len(out) >= max_items:
            break
    return out


def normalize_repurpose(raw: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    nl = " ".join(str(raw.get("newsletter") or "").split())
    return {
        "carousel": _clean_list(raw.get("carousel"), *LIMITS["carousel"]),
        "thread": _clean_list(raw.get("thread"), *LIMITS["thread"]),
        "newsletter": nl[:800].rstrip() if len(nl) > 800 else nl,
        "quote_cards": _clean_list(raw.get("quote_cards"), *LIMITS["quote_cards"]),
    }


def _stub_repurpose(text: str) -> dict[str, Any]:
    lead = (text.split(".")[0] or text)[:160].strip() or "New video"
    return normalize_repurpose({
        "carousel": [lead, "Here's the key idea.", "And why it matters.", "Follow for more."],
        "thread": [lead, "Here's the breakdown.", "The takeaway: keep it simple."],
        "newsletter": f"{lead}. Here's the short version and why it matters.",
        "quote_cards": [lead[:120]],
    })


def build_repurpose(text: str, llm=None) -> dict[str, Any]:
    text = " ".join((text or "").split())
    if not text:
        return None
    if llm is None:
        return _stub_repurpose(text)
    try:
        raw = llm.complete(_PROMPT + f'\n\nTranscript: "{text[:6000]}"')
        out = normalize_repurpose(raw)
        return out if (out["carousel"] or out["thread"] or out["newsletter"]) else _stub_repurpose(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[cadence] build_repurpose LLM failed -> stub: {exc!r}", flush=True)
        return _stub_repurpose(text)
