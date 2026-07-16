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
from cadence.synthesis.factual import compose_factual_asset, match_factual_asset

_BROLL_CADENCE = {"match": (1.8, 1.6), "between": (2.2, 3.0), "natural": (2.6, 5.0),
                  # "background": dense + gapless — a fresh image ~every 2.5s so the
                  # replace-BG dynamic background changes constantly with the talking points.
                  "background": (2.5, 0.0)}
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


def plan_background_windows(words_out, output_duration: float, *, interval: float = 4.0,
                           pause_gap: float = 0.4, snap: float = 1.5):
    """Change-point windows for the replace-BG dynamic background: a fresh image roughly every
    ``interval`` seconds (the minimum hold), each snapped FORWARD up to ``snap`` s onto the next
    new-audio-section boundary (a word starting after a pause > ``pause_gap``) so changes land on
    speech transitions. Tiles ``[0, output_duration)`` with no gaps. Pure/deterministic."""
    boundaries: list[float] = []
    prev_end: float | None = None
    for (_w, s, e) in (words_out or []):
        if prev_end is not None and (s - prev_end) > pause_gap:
            boundaries.append(float(s))
        prev_end = e
    changes = [0.0]
    while changes[-1] + interval < output_duration - 0.5:
        target = changes[-1] + interval
        nb = next((b for b in boundaries if target <= b <= target + snap), None)
        changes.append(round(nb if nb is not None else target, 3))
    windows = []
    for idx, t in enumerate(changes):
        end = changes[idx + 1] if idx + 1 < len(changes) else float(output_duration)
        if end - t > 0.05:
            windows.append((round(t, 3), round(end, 3), _BROLL_MOTIONS[idx % len(_BROLL_MOTIONS)]))
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


def build_ai_prompt_scene(
    scene: str, caption: str, cine=None, style_override: str | None = None, world: str = ""
) -> str:
    """The loop-tuned template: a distilled SCENE + cinematography look + a clean CAPTION.

    ``style_override`` swaps the photoreal framing for a named art style (claymation,
    3D cartoon, anime, …) — the override REPLACES the photographic language entirely,
    because "hyperrealistic photograph" and "claymation" fight each other in the model.
    ``world`` is a video-level visual anchor (same recurring subject / setting / palette /
    lighting) prepended to EVERY scene so the whole render reads as one continuous film
    instead of a slideshow of unrelated images. Paired with a locked seed in build_ai_broll.
    """
    anchor = f"{world}. " if world else ""
    if style_override:
        return (
            f"{anchor}A {style_override}, vertical 9:16 composition: {scene}. "
            "Ultra detailed, premium quality, masterfully crafted, rich texture and depth. "
            f"The phrase \"{caption}\" appears cleanly integrated into the scene in crisp readable "
            "typography. No watermark, no garbled text."
        )
    look = (
        ", ".join(cine.to_prompt_clauses())
        if cine is not None
        else "50mm lens, at f/2.8 shallow depth of field, soft natural lighting"
    )
    return (
        f"{anchor}A hyperrealistic cinematic vertical 9:16 photograph: {scene}. {look}. "
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
    windows: list | None = None,
    distiller=None,
    cine=None,
    factual_assets: list | None = None,
    style_override: str | None = None,
    direction: str = "",
    context_topic: str = "",
) -> list[BrollInsert]:
    """Generate a contextual, photoreal b-roll image for each cutaway window.

    With a ``distiller`` (Gemini), each window's raw sentence is distilled into a clean
    scene + caption (fixing ASR noise) — the loop-proven path. Without one, it falls
    back to the lexical topic. ``compose_broll_image`` guarantees caption legibility
    when ``overlay_text`` is set (useful for weaker text models).

    Factual-image guardrail: when ``factual_assets`` is supplied and a window's spoken
    text names a guarded term (e.g. "Claude Code"), the EXACT curated real screenshot is
    used for that window instead of a generated image — so it's 100% accurate and burns
    0 AI tokens (we skip the generator entirely). See :mod:`cadence.synthesis.factual`.
    """
    if windows is None:
        windows = plan_broll_windows(output_duration, mode=mode)
    if max_images is not None:
        windows = windows[:max_images]
    # Ground the distiller in the WHOLE video so every scene is specific to the real
    # subject (named tools get depicted as themselves, ASR fixes use global context).
    if distiller is not None and hasattr(distiller, "set_context"):
        full_text = " ".join(w[0] for w in words_out)
        distiller.set_context(topic=context_topic, full_text=full_text, direction=direction)
    # Visual COHESION: one locked seed + a shared "world anchor" prepended to every scene so
    # the render reads as ONE continuous film instead of a slideshow of unrelated images. The
    # seed is stable per-topic (deterministic) so all scenes share the model's aesthetic; the
    # anchor keeps subject/setting/palette/lighting consistent. $0 extra GPU (same gen call).
    import hashlib

    video_seed = int(hashlib.sha256((context_topic or "cadence").encode()).hexdigest()[:8], 16)
    world = (
        "Consistent cinematic world across every shot: the SAME recurring subject/character, "
        "setting, colour palette, film stock, and lighting throughout — as if these are frames "
        "from ONE continuous film, not separate images"
    )
    prev_scenes: list[str] = []
    inserts: list[BrollInsert] = []
    for idx, (start, end, motion) in enumerate(windows):
        window_text = raw_text_for_window(words_out, start, end)
        # Factual-image guardrail (pre-step): a guarded term in this window → use the real
        # curated screenshot, skip the model. 0 tokens (charging lives inside generate()).
        if factual_assets:
            fa = match_factual_asset(window_text, factual_assets)
            if fa is not None:
                try:
                    with open(fa.asset_path, "rb") as fh:
                        asset_bytes = fh.read()
                    path = compose_factual_asset(
                        asset_bytes, os.path.join(out_dir, f"ai_broll_{idx}.png"),
                        width=width, height=height,
                    )
                    inserts.append(BrollInsert(image_path=path, start=start, end=end,
                                               motion=KenBurns.ZOOM_IN, source="factual"))
                    print(f"[broll] factual guardrail: '{fa.key}' -> "
                          f"{os.path.basename(path)} @ {start:.1f}-{end:.1f}s", flush=True)
                    continue
                except Exception as exc:  # noqa: BLE001 - unreadable asset → fall through to AI gen
                    print(f"[broll] factual asset unreadable ({fa.key}): {exc!r} -> AI fallback",
                          flush=True)
        if distiller is not None:
            try:
                scene, caption = distiller.distill(window_text, prev_scenes=prev_scenes)
            except TypeError:  # older distillers without the prev_scenes kwarg
                scene, caption = distiller.distill(window_text)
            prev_scenes.append(scene)
            prompt = build_ai_prompt_scene(scene, caption, cine=cine, style_override=style_override, world=world)
        else:
            topic = topic_for_window(words_out, start, end) or "a clean modern workspace"
            caption = caption_for_topic(topic)
            prompt = build_ai_prompt_scene(topic, caption, cine=cine, style_override=style_override, world=world)
        if direction:
            prompt = f"{prompt} Creator's scene direction (follow it): {direction}"
        try:
            res = generator.generate(prompt, aspect="9x16", style_refs=style_refs, seed=video_seed)
        except BudgetExceeded:
            break  # budget or persistent rate-limit — keep the cutaways generated so far
        except Exception as exc:  # noqa: BLE001 - a one-off failure (e.g. safety filter) skips this window
            print(f"[broll] generate failed @ {start:.1f}s: {exc!r}", flush=True)
            continue
        path = compose_broll_image(
            res.image_bytes, caption, os.path.join(out_dir, f"ai_broll_{idx}.png"),
            overlay_text=overlay_text, width=width, height=height,
        )
        inserts.append(BrollInsert(image_path=path, start=start, end=end, motion=motion))
    return inserts
