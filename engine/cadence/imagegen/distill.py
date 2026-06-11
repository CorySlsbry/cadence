"""Gemini-text topic distillation: turn a noisy transcript snippet into a clean,
SPECIFIC b-roll scene + a short on-screen caption (fixing ASR errors).

This is what makes the AI b-roll *relevant* instead of loosely-themed stock imagery.
The distiller is context-aware: it knows the video's overall subject, the full
narration, the creator's direction, and what scenes were already used — and it is
bound by a specificity contract: when the snippet names a concrete product, tool,
brand, or person, the scene depicts THAT THING itself (its real interface, its real
form factor), never a generic metaphor like server racks or glowing circuitry.
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
    "`caption` = a punchy 2-4 word on-screen label of the snippet's core idea.\n"
    "\n"
    "SPECIFICITY CONTRACT (the most important rules):\n"
    "1. If the snippet (or the video's subject) names a SPECIFIC product, software, app, model, "
    "brand, device, or person — the scene MUST depict that exact thing as the hero of the frame. "
    "Software/AI tools → their ACTUAL user interface, faithfully described on a laptop/phone screen "
    "filling most of the frame (e.g. 'Claude Code' → a dark terminal-style AI coding session: a CLI "
    "pane with a user prompt, streaming assistant response, green/red code diff lines; 'Claude' or "
    "'Claude Fable 5' → the Anthropic Claude chat interface: clean cream/dark panel, message thread, "
    "model picker reading the model name; 'ChatGPT' → its chat UI; 'Stripe' → its payments dashboard "
    "with revenue graphs). Devices → that exact device. People/companies → them in their real context.\n"
    "2. NEVER substitute a generic metaphor (server racks, data centers, abstract circuit boards, "
    "glowing brains, robot hands) when something specific is named. Generic tech imagery is only "
    "allowed when the snippet is genuinely abstract with nothing concrete to show.\n"
    "3. The on-screen UI text in the scene should include the product's actual name where natural "
    "(window title, model picker, dashboard header).\n"
    "4. VARIETY: if previous scenes are listed, choose a different composition, angle, and setting "
    "than those — never repeat the same desk-and-laptop framing twice in a row.\n"
    "5. Silently FIX speech-to-text errors using the video subject as context "
    "(e.g. 'cloud code'/'cloud covert' → 'Claude Code', 'clod' → 'Claude', 'fable five' → 'Fable 5').\n"
    "6. Honor the creator's scene direction when given — it overrides style, not specificity."
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
