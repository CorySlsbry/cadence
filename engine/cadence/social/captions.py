"""Generate platform-tailored post copy (caption + hashtags + @mentions) for a
finished short video, so it's "ready to post" to TikTok, YouTube Shorts, and Instagram
Reels.

The rules baked in here are the 2026 platform conventions (verified via research):

- **TikTok** — caption up to 2,200 chars (Content Posting API limit; in-app is 4,000);
  front-load the hook in the first ~150 chars; **3–5** targeted hashtags (a hard cap of 5
  exists; #fyp no longer helps); @mentions count toward the limit, use sparingly.
- **YouTube Shorts** — no single caption: a **title ≤100** (display ~70) + a
  **description ≤5,000** (only ~157 chars show above "Show more"); **2–3** hashtags in the
  description and **always #Shorts**; >15 hashtags voids them all; tags are near-dead.
- **Instagram Reels** — caption ≤2,200 (first ~125 shown); **3–5** specific hashtags
  (hashtag-heavy posts get ~23% *less* reach; keywords beat hashtags now); @mentions link
  + notify, up to 20 per post.

The LLM writes the draft; pure normalization functions then HARD-enforce every limit so
we never depend on the model obeying them. The writer is injected (Gemini or a stub), so
``build_social_captions`` is fully unit-testable.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from cadence.errors import DependencyError

# Hard platform limits (enforced after generation, never trusted to the LLM).
LIMITS: dict[str, dict[str, int]] = {
    "tiktok": {"caption": 2200, "hashtags": 5, "mentions": 3},
    "instagram": {"caption": 2200, "hashtags": 5, "mentions": 5},
    "youtube": {"title": 100, "description": 5000, "hashtags": 3},
}


class CaptionWriter(Protocol):
    """Produces a raw per-platform caption draft from a transcript."""

    def write(self, transcript_text: str, *, product: str | None, handle: str | None, voice: str = "") -> dict[str, Any]: ...


# --------------------------------------------------------------------------- #
# Pure normalization (unit-testable without any LLM)
# --------------------------------------------------------------------------- #
def _clean_tag(tag: str) -> str:
    """Normalize one hashtag: single leading '#', no spaces/punctuation gaps."""
    body = "".join(ch for ch in str(tag) if ch.isalnum() or ch in "_#")
    body = body.lstrip("#")
    return f"#{body}" if body else ""


def clean_hashtags(tags: Any, limit: int, *, ensure: list[str] | None = None) -> list[str]:
    """De-duplicate (case-insensitive), drop empties, force '#', cap at ``limit``.
    ``ensure`` tags (e.g. '#Shorts') are guaranteed present and counted in the cap."""
    out: list[str] = []
    seen: set[str] = set()
    for t in (ensure or []) + list(tags or []):
        c = _clean_tag(t)
        key = c.lower()
        if c and key not in seen:
            seen.add(key)
            out.append(c)
    return out[:limit]


def clean_mentions(mentions: Any, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in list(mentions or []):
        body = "".join(ch for ch in str(m) if ch.isalnum() or ch in "_.@").lstrip("@")
        if not body:
            continue
        handle = f"@{body}"
        if handle.lower() not in seen:
            seen.add(handle.lower())
            out.append(handle)
    return out[:limit]


def trim_text(text: str, limit: int) -> str:
    """Hard-cap to ``limit`` chars, breaking on a word boundary when possible."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.6 else cut).rstrip()


def normalize(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Coerce an LLM draft into the canonical, limit-enforced structure."""
    tt = raw.get("tiktok") or {}
    ig = raw.get("instagram") or {}
    yt = raw.get("youtube") or {}
    return {
        "tiktok": {
            "caption": trim_text(str(tt.get("caption", "")), LIMITS["tiktok"]["caption"]),
            "hashtags": clean_hashtags(tt.get("hashtags"), LIMITS["tiktok"]["hashtags"]),
            "mentions": clean_mentions(tt.get("mentions"), LIMITS["tiktok"]["mentions"]),
        },
        "instagram": {
            "caption": trim_text(str(ig.get("caption", "")), LIMITS["instagram"]["caption"]),
            "hashtags": clean_hashtags(ig.get("hashtags"), LIMITS["instagram"]["hashtags"]),
            "mentions": clean_mentions(ig.get("mentions"), LIMITS["instagram"]["mentions"]),
        },
        "youtube": {
            "title": trim_text(str(yt.get("title", "")), LIMITS["youtube"]["title"]),
            "description": trim_text(str(yt.get("description", "")), LIMITS["youtube"]["description"]),
            # #Shorts is mandatory for Shorts-feed routing.
            "hashtags": clean_hashtags(yt.get("hashtags"), LIMITS["youtube"]["hashtags"], ensure=["#Shorts"]),
        },
    }


def to_post_text(platform: str, block: dict[str, Any]) -> str:
    """Assemble the final caption string a platform/aggregator expects.

    TikTok/Instagram put hashtags + mentions inline in the caption; YouTube's "text" is
    the description (the title is a separate field) with hashtags appended."""
    if platform == "youtube":
        base = block.get("description", "")
        tags = " ".join(block.get("hashtags", []))
        return f"{base}\n\n{tags}".strip()
    caption = block.get("caption", "")
    extras = " ".join(block.get("mentions", []) + block.get("hashtags", []))
    return f"{caption}\n\n{extras}".strip()


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
_PROMPT = """You are a senior short-form social copywriter. From the transcript of a vertical short \
video, write platform-tailored post copy as STRICT JSON for TikTok, YouTube Shorts, and Instagram Reels.

Rules (2026, follow exactly):
- HOOK FIRST: lead with the single most compelling, searchable keyword phrase in the first line.
- Captions are SEO: use natural-language phrases real people search; reinforce what's said on screen.
- TikTok: one caption ~150-300 chars; end with a light question/CTA to drive comments. EXACTLY 3-5 \
targeted hashtags (one broad niche + one or two mid community + one trending if truly relevant). \
Never use #fyp/#foryou.
- Instagram: one caption with the hook + keyword in the first ~70 chars, ~150-220 chars total; 3-5 \
specific hashtags (fewer is better — keyword in the caption matters more).
- YouTube Shorts: a "title" <=70 chars, keyword-rich; a "description" that front-loads the hook in the \
first ~150 chars, ~300-500 chars total, ending with a soft CTA; 2-3 hashtags and ALWAYS include #Shorts.
- @mentions: ONLY include accounts/brands EXPLICITLY named in the transcript. If none are clearly \
named, return an empty list. NEVER invent or guess handles.
- Tasteful tone: at most 1-3 emojis, no clickbait lies, no hashtag stuffing.{product_line}

Output STRICT JSON with this exact shape (no commentary):
{{"tiktok":{{"caption":"","hashtags":[],"mentions":[]}},
 "instagram":{{"caption":"","hashtags":[],"mentions":[]}},
 "youtube":{{"title":"","description":"","hashtags":[]}}}}
"""


def _product_line(product: str | None, handle: str | None) -> str:
    if not product:
        return ""
    tail = f" ({handle})" if handle else ""
    return (
        f"\n- This video was made with {product}{tail}. You MAY add ONE soft, natural credit/CTA to "
        f"{product} at the END of each caption/description (not in the hook). Keep it subtle."
    )


class GeminiCaptionWriter:
    """Gemini-backed writer (one cheap gemini-2.5-flash call returns all platforms)."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash") -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - optional dep
            raise DependencyError("google-genai not installed.") from exc
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise DependencyError("GEMINI_API_KEY not set for caption generation.")
        self._client = genai.Client(api_key=key)
        self.model = model

    def write(self, transcript_text: str, *, product: str | None, handle: str | None, voice: str = "") -> dict[str, Any]:
        from cadence._gemini import gemini_json

        prompt = _PROMPT.format(product_line=_product_line(product, handle))
        full = f'{prompt}{voice}\n\nTranscript: "{transcript_text.strip()[:6000]}"'
        return gemini_json(self._client, self.model, full, temperature=0.7)


class StubCaptionWriter:
    """Deterministic, dependency-free writer for tests + a no-key fallback. Builds a
    plain caption from the transcript's first sentence — no network, no cost."""

    def write(self, transcript_text: str, *, product: str | None, handle: str | None, voice: str = "") -> dict[str, Any]:
        text = " ".join(transcript_text.split())
        lead = (text.split(".")[0] or text)[:120].strip() or "New video"
        cta = f" Made with {product}." if product else ""
        return {
            "tiktok": {"caption": f"{lead}.{cta}", "hashtags": ["#creator", "#shortform", "#video"], "mentions": []},
            "instagram": {"caption": f"{lead}.{cta}", "hashtags": ["#reels", "#creator", "#video"], "mentions": []},
            "youtube": {"title": lead[:70], "description": f"{lead}.{cta}", "hashtags": ["#Shorts", "#creator"]},
        }


def build_social_captions(
    transcript_text: str,
    writer: CaptionWriter,
    *,
    product: str | None = None,
    handle: str | None = None,
    voice: str = "",
) -> dict[str, dict[str, Any]]:
    """Generate + hard-normalize per-platform captions (``voice`` = the creator's
    blueprint context, personalizing the copy). Falls back to a deterministic
    stub draft if the writer fails, so a render never loses its captions to an LLM blip."""
    try:
        raw = writer.write(transcript_text, product=product, handle=handle, voice=voice)
    except Exception as exc:  # noqa: BLE001 - never fail the render over caption generation
        print(f"[cadence] caption writer failed -> stub: {exc!r}", flush=True)
        raw = StubCaptionWriter().write(transcript_text, product=product, handle=handle, voice=voice)
    return normalize(raw if isinstance(raw, dict) else {})
