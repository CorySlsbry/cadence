"""Contextual AI b-roll: turn what the speaker is saying into a relevant, photoreal
cutaway image.

For each cutaway window we read the words spoken leading into it, distil a topic,
build a hyperrealistic prompt that asks the model to show that topic (with the key
phrase rendered in-scene — Ideogram's strength), generate it, optionally overlay a
guaranteed-legible caption, and emit a :class:`BrollInsert`. Pure except for the
injected :class:`ImageGenerator`, so it's fully testable with the stub.
"""

from __future__ import annotations

import io
import os

from cadence.imagegen.base import ImageGenerator
from cadence.imagegen.ledger import BudgetExceeded
from cadence.models import BrollInsert, KenBurns

_BROLL_CADENCE = {"match": (1.8, 1.6), "between": (2.2, 3.0), "natural": (2.6, 5.0)}
_BROLL_MOTIONS = (KenBurns.ZOOM_IN, KenBurns.PAN_RIGHT, KenBurns.ZOOM_OUT, KenBurns.PAN_LEFT, KenBurns.PAN_UP)

# Words that never make a good b-roll topic.
_STOPWORDS = frozenset(
    "a an the and or but so if then this that these those i you we they he she it my your our their "
    "is are was were be been being am do does did have has had will would can could should may might "
    "of to in on at for with from by as into about over under just like really very much more most "
    "going gonna want need know think thing things stuff okay yeah right here there what when how why "
    "um uh er ah hmm mm".split()
)


def plan_broll_windows(output_duration: float, *, mode: str = "between", lead_in: float = 1.5, tail: float = 1.0):
    """Time slots for cutaways (start, end, motion) — image-agnostic."""
    if output_duration < lead_in + tail + 2.0:
        return []
    clip_len, gap = _BROLL_CADENCE.get(mode, _BROLL_CADENCE["between"])
    windows = []
    t, i = lead_in, 0
    while t + clip_len <= output_duration - tail:
        windows.append((round(t, 3), round(t + clip_len, 3), _BROLL_MOTIONS[i % len(_BROLL_MOTIONS)]))
        t += clip_len + gap
        i += 1
    return windows


def topic_for_window(words_out: list[tuple[str, float, float]], start: float, end: float, *, lookback: float = 2.5) -> str:
    """Salient phrase spoken in the run-up to (and during) the cutaway window."""
    lo = start - lookback
    spoken = [w for (w, s, e) in words_out if s >= lo and s < end]
    content = []
    for w in spoken:
        tok = "".join(ch for ch in w.lower() if ch.isalnum() or ch == "'").strip("'")
        if tok and tok not in _STOPWORDS and len(tok) > 1:
            content.append(tok)
    if not content:
        return ""
    # Keep the densest 5-word phrase; de-dupe consecutive repeats.
    deduped = [content[0]]
    for t in content[1:]:
        if t != deduped[-1]:
            deduped.append(t)
    return " ".join(deduped[-5:])


def raw_text_for_window(words_out: list[tuple[str, float, float]], start: float, end: float, *, lookback: float = 3.0) -> str:
    """The natural sentence spoken into/around the window (for LLM topic distillation)."""
    lo = start - lookback
    return " ".join(w for (w, s, e) in words_out if s >= lo and s < end).strip()


def caption_for_topic(topic: str) -> str:
    return " ".join(w.capitalize() for w in topic.split())[:48]


def build_ai_prompt(topic: str, caption: str) -> str:
    return (
        f"A hyperrealistic, cinematic vertical 9:16 photograph illustrating \"{topic}\". "
        "Premium editorial product photography, soft natural studio lighting, shallow depth of field, "
        "ultra-detailed, modern, clean, high-end. A sleek laptop or device screen visible in the scene "
        f"clearly displays the text \"{caption}\" in crisp modern UI typography. No watermark."
    )


def build_ai_prompt_scene(scene: str, caption: str, cine=None) -> str:
    """The loop-tuned template: a distilled SCENE + cinematography look + a clean CAPTION."""
    look = (
        ", ".join(cine.to_prompt_clauses())
        if cine is not None
        else "50mm lens, at f/2.8 shallow depth of field, soft natural lighting"
    )
    return (
        f"A hyperrealistic cinematic vertical 9:16 photograph: {scene}. {look}. "
        "Ultra detailed, modern, clean, premium editorial. "
        f"The phrase \"{caption}\" appears cleanly on a screen, sign, or surface in the scene in crisp "
        "modern typography. Photoreal, no watermark, no garbled text."
    )


def compose_broll_image(
    image_bytes: bytes,
    caption: str,
    out_path: str,
    *,
    overlay_text: bool = False,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Persist the generated image, optionally overlaying a guaranteed-legible caption
    banner at the top (so the key phrase is readable even if the model flubbed it)."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Cover-fit to the target frame so it fills nicely under Ken Burns.
    scale = max(width / img.width, height / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
    left = (img.width - width) // 2
    top = (img.height - height) // 2
    img = img.crop((left, top, left + width, top + height))

    if overlay_text and caption:
        draw = ImageDraw.Draw(img, "RGBA")
        bar_h = round(height * 0.10)
        draw.rectangle([0, round(height * 0.06), width, round(height * 0.06) + bar_h], fill=(8, 8, 12, 200))
        draw.text((48, round(height * 0.06) + bar_h // 2 - 10), caption, fill=(255, 214, 10))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


def build_ai_broll(
    words_out: list[tuple[str, float, float]],
    output_duration: float,
    generator: ImageGenerator,
    *,
    out_dir: str,
    mode: str = "between",
    style_refs: list[str] | None = None,
    overlay_text: bool = False,
    max_images: int | None = None,
    width: int = 1080,
    height: int = 1920,
    distiller=None,
    cine=None,
) -> list[BrollInsert]:
    """Generate a contextual, photoreal b-roll image for each cutaway window.

    With a ``distiller`` (Gemini), each window's raw sentence is distilled into a clean
    scene + caption (fixing ASR noise) — the loop-proven path. Without one, it falls
    back to the lexical topic. ``compose_broll_image`` guarantees caption legibility
    when ``overlay_text`` is set (useful for weaker text models).
    """
    windows = plan_broll_windows(output_duration, mode=mode)
    if max_images is not None:
        windows = windows[:max_images]
    inserts: list[BrollInsert] = []
    for idx, (start, end, motion) in enumerate(windows):
        if distiller is not None:
            scene, caption = distiller.distill(raw_text_for_window(words_out, start, end))
            prompt = build_ai_prompt_scene(scene, caption, cine=cine)
        else:
            topic = topic_for_window(words_out, start, end) or "a clean modern workspace"
            caption = caption_for_topic(topic)
            prompt = build_ai_prompt_scene(topic, caption, cine=cine)
        try:
            res = generator.generate(prompt, aspect="9x16", style_refs=style_refs)
        except BudgetExceeded:
            break  # budget or persistent rate-limit — keep the cutaways generated so far
        except Exception:  # noqa: BLE001 - a one-off failure (e.g. safety filter) skips just this window
            continue
        path = compose_broll_image(
            res.image_bytes, caption, os.path.join(out_dir, f"ai_broll_{idx}.png"),
            overlay_text=overlay_text, width=width, height=height,
        )
        inserts.append(BrollInsert(image_path=path, start=start, end=end, motion=motion))
    return inserts
