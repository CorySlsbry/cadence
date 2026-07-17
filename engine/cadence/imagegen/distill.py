"""Gemini-text topic distillation: turn a noisy transcript snippet into a clean,
SPECIFIC b-roll scene + a short on-screen caption (fixing ASR errors).

This is what makes the AI b-roll *relevant* instead of loosely-themed stock imagery.
The distiller is context-aware: it knows the video's overall subject, the full
narration, the creator's direction, and what scenes were already used — and it is
bound by a specificity contract: when the snippet names a concrete product, tool,
brand, or person, the scene depicts THAT THING itself (its real form factor, the
person using it), never a generic metaphor like server racks or glowing circuitry.

It is also bound by an absolute NO-TEXT contract, which outranks specificity. This
prompt is where garbled on-screen text actually originates: it used to order the model
to render a product's "ACTUAL user interface" — a chat thread, a CLI pane, a "model
picker reading the model name" — so the image model was *asked* for a text-bearing
scene and dutifully drew gibberish into it. Downstream anti-text rules can only mop
that up; a scene that never asks for a screen is the fix. Concepts are depicted through
people, places, action, and objects; the burned-in captions carry all the words.
"""

from __future__ import annotations

import os

from cadence.errors import DependencyError

_SYSTEM = (
    "You are a senior short-form video editor writing B-ROLL directions. "
    "Given a transcript snippet from a video, output STRICT JSON: "
    '{"scene": "...", "caption": "..."}. '
    "`scene` = a vivid, concrete scene that visually shows EXACTLY what the speaker is "
    "talking about in THIS snippet (subject, setting, lighting, mood — not instructions, not text). "
    "`caption` = a punchy 2-4 word summary of the snippet's core idea. The caption is used by the "
    "editor OUTSIDE the image and is NEVER rendered into the scene — do not mention it in `scene`.\n"
    "\n"
    "NO-TEXT CONTRACT (absolute — this overrides every other rule):\n"
    "1. NEVER describe a scene containing text or a surface that would carry text. No letters, "
    "words, numbers, headlines, titles, captions, labels, watermarks, logos, or signage — and no "
    "chat windows, terminals, code editors, dashboards, phone/laptop screens with anything on "
    "them, documents, books, or posters. Image models render text as garbled gibberish, so ANY "
    "words in the frame come out wrong and ruin the shot; the finished video burns in its own "
    "captions, so the scene never needs words. If a screen or sign is unavoidable in the setting, "
    "say explicitly that it is blank, dark, abstract, or turned away out of frame — better still, "
    "leave it out of the description entirely.\n"
    "2. Depict EVERY concept through PEOPLE, PLACES, ACTION, and OBJECTS — a person doing the "
    "thing, in a real place, with real props, real light, real emotion. 'Reviewing code' → a "
    "developer leaning back in a dim studio, face lit by an unseen monitor. 'Payments growing' → "
    "hands stacking coins on a worn cafe table. 'Shipping fast' → a courier sprinting a package "
    "down a sunlit street. Never a screenshot, never an interface.\n"
    "\n"
    "SPECIFICITY CONTRACT (apply WITHIN the no-text rule above):\n"
    "3. If the snippet (or the video's subject) names a SPECIFIC product, software, app, model, "
    "brand, device, or person, keep the scene ABOUT that thing — but show its PHYSICAL, HUMAN "
    "side: the real device on a real desk, hands using it, the person themselves in their real "
    "context, the place the work happens. Show what the tool DOES FOR someone, never what it "
    "LOOKS LIKE on a screen. (Real, legible product UIs are supplied separately as curated real "
    "screenshots, so a GENERATED scene must never attempt one.)\n"
    "4. NEVER substitute a generic metaphor (server racks, data centers, abstract circuit boards, "
    "glowing brains, robot hands) when something specific is named. Generic tech imagery is only "
    "allowed when the snippet is genuinely abstract with nothing concrete to show.\n"
    "5. VARIETY: if previous scenes are listed, choose a different composition, angle, and setting "
    "than those — never repeat the same desk-and-laptop framing twice in a row.\n"
    "6. Silently FIX speech-to-text errors using the video subject as context "
    "(e.g. 'cloud code'/'cloud covert' → 'Claude Code', 'clod' → 'Claude', 'fable five' → 'Fable 5').\n"
    "7. Honor the creator's scene direction when given — it overrides style, not specificity, and "
    "never the no-text contract."
)


class GeminiDistiller:
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash") -> None:
        try:
            from google import genai  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise DependencyError("google-genai not installed.") from exc
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise DependencyError("GEMINI_API_KEY not set for distillation.")
        from google import genai

        self._client = genai.Client(api_key=key)
        self._genai = genai
        self.model = model
        self._topic = ""
        self._full_text = ""
        self._direction = ""

    def set_context(self, topic: str = "", full_text: str = "", direction: str = "") -> None:
        """Video-level grounding included in every distill call: the overall subject,
        the (truncated) full narration, and the creator's scene direction."""
        self._topic = (topic or "").strip()[:200]
        self._full_text = (full_text or "").strip()[:1500]
        self._direction = (direction or "").strip()[:400]

    def distill(self, snippet: str, prev_scenes: list[str] | None = None) -> tuple[str, str]:
        """Return ``(scene, caption)``. Falls back to the raw snippet on any failure."""
        from cadence._gemini import gemini_json

        ctx_parts = []
        if self._topic:
            ctx_parts.append(f'VIDEO SUBJECT: "{self._topic}"')
        if self._full_text:
            ctx_parts.append(f"FULL NARRATION (for context):\n{self._full_text}")
        if self._direction:
            ctx_parts.append(f"CREATOR'S SCENE DIRECTION: {self._direction}")
        if prev_scenes:
            recent = "\n".join(f"- {s[:140]}" for s in prev_scenes[-4:])
            ctx_parts.append(f"SCENES ALREADY USED (use a different composition):\n{recent}")
        ctx = ("\n\n".join(ctx_parts) + "\n\n") if ctx_parts else ""

        try:
            data = gemini_json(
                self._client, self.model,
                f"{_SYSTEM}\n\n{ctx}Snippet: \"{snippet.strip()}\"", temperature=0.4,
            )
            scene = str(data.get("scene", "")).strip()
            caption = str(data.get("caption", "")).strip()
            if scene:
                return scene, (caption or scene[:32])
        except Exception:  # noqa: BLE001 - degrade gracefully to the raw snippet
            pass
        return snippet[:120], snippet[:32]
