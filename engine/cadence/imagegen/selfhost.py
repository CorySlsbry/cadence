"""CloutHook's own generation service (cadence-gen on Cloud Run GPU).

SelfHostGenerator speaks the same generator protocol as ImagenGenerator, so the
whole b-roll pipeline switches providers with two env vars — and every image still
meters through the ledger (tokens are the product's meter; the self-hosted COGS
just makes the margin dramatically better). Any failure falls back to the wrapped
generator (Imagen) so renders never die because the GPU tier hiccuped.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request

from cadence.imagegen.base import GenResult
from cadence.imagegen.ledger import BudgetExceeded, CostLedger

_SIZES = {
    "9x16": (768, 1344),
    "16x9": (1344, 768),
    "1x1": (1024, 1024),
    "3x4": (896, 1152),
    "4x3": (1152, 896),
}

# Diffusion models render arbitrary text as gibberish, and gibberish on screen reads as "trash".
# The rule is ABSOLUTE: a generated scene carries NO text at all — the burned-in karaoke captions
# carry every word. This used to say incidental text may stay "soft, blurred, and illegible",
# which simply INVITED the model to draw blurry gibberish (and it did: a garbled title + a fake
# chat UI shipped). Never re-introduce "illegible"/"blurred" wording here — permission to render
# unreadable text is permission to render text. Legible product UIs come from real screenshots
# (the factual guardrail), never from generation.
_ANTI_TEXT_MARK = "NO TEXT ANYWHERE"
_ANTI_TEXT = (
    f" {_ANTI_TEXT_MARK}: the image contains zero letters, words, numbers, titles, captions, "
    "watermarks, logos, signage, labels, or user-interface text of any kind. Every screen, sign, "
    "book, poster, and label in frame is blank, abstract, or turned away out of frame. Convey the "
    "idea only through people, places, action, and objects."
)


def _augment_prompt(prompt: str) -> str:
    """Append the absolute no-text rule exactly once.

    The double-append guard keys on ``_ANTI_TEXT_MARK`` — a distinct sentinel that is
    interpolated into ``_ANTI_TEXT`` itself, so it cannot drift out of sync when the rule is
    re-worded. (The old guard sniffed for the incidental word "illegible", which silently
    stopped matching the moment the wording changed.)
    """
    p = (prompt or "").strip()
    if _ANTI_TEXT_MARK in p:  # already augmented — don't double-append
        return p
    return (p.rstrip(". ") + "." + _ANTI_TEXT).strip()


class SelfHostGenerator:
    name = "selfhost"
    # FLUX.2-klein on cadence-gen accepts reference/continuity images, so this generator can
    # honor init_image/ref_image. Callers gate visual-cohesion chaining on this flag; generators
    # without it (Imagen/Ideogram/stub) leave the pipeline byte-identical to today.
    supports_image_conditioning = True

    def __init__(self, base_url: str, token: str, *, ledger: CostLedger | None = None,
                 fallback=None, timeout: float | None = None) -> None:
        # Secret-mounted env values can carry CRLF; urllib rejects \r\n in header values.
        self.base_url = base_url.strip().rstrip("/")
        self.token = token.strip()
        self.ledger = ledger
        self.fallback = fallback
        # Wait for the (free, on-brand) self-host image even on a COLD cadence-gen — loading the 4B
        # FLUX from the GCS FUSE mount can take minutes — before falling back to paid Imagen. Tunable
        # via CADENCE_GEN_IMG_TIMEOUT (no rebuild); default 600s, under cadence-gen's own 1800s
        # request timeout. Only the first (cold) image pays this; once warm, images are ~11s.
        self.timeout = (
            timeout if timeout is not None
            else float(os.environ.get("CADENCE_GEN_IMG_TIMEOUT", "600"))
        )
        self.cost_per_image = float(os.environ.get("CADENCE_SELFHOST_COST", "0.002"))

    def generate(self, prompt, *, aspect="9x16", style_refs=None, seed=None,
                 init_image=None, ref_image=None) -> GenResult:
        if self.ledger is not None and not self.ledger.can_spend(self.cost_per_image):
            raise BudgetExceeded(f"AI budget cap reached (need ${self.cost_per_image}).")
        prompt = _augment_prompt(prompt)  # suppress garbled background text (also flows to fallback)
        w, h = _SIZES.get(aspect, _SIZES["9x16"])
        body_obj = {"prompt": prompt, "width": w, "height": h, "steps": 4,
                    **({"seed": seed} if seed is not None else {})}
        # Visual-cohesion conditioning (optional): world/style anchor + previous frame. Only added
        # when present, so a no-chaining request serializes to the exact same body as before.
        if ref_image is not None:
            body_obj["ref_image_b64"] = base64.b64encode(ref_image).decode()
        if init_image is not None:
            body_obj["init_image_b64"] = base64.b64encode(init_image).decode()
        body = json.dumps(body_obj).encode()
        req = urllib.request.Request(
            f"{self.base_url}/image", data=body, method="POST",
            headers={"content-type": "application/json", "x-gen-token": self.token},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                img_bytes = resp.read()
            if not img_bytes or len(img_bytes) < 1000:
                raise RuntimeError("selfhost returned an empty image")
            if self.ledger is not None:
                self.ledger.charge(self.cost_per_image)
            return GenResult(image_bytes=img_bytes, prompt=prompt,
                             cost_usd=self.cost_per_image, provider="selfhost", seed=seed)
        except BudgetExceeded:
            raise
        except Exception as exc:  # noqa: BLE001 - degrade to the wrapped provider
            if self.fallback is not None:
                print(f"[selfhost] image failed ({exc!r}) -> falling back to "
                      f"{getattr(self.fallback, 'name', 'fallback')}", flush=True)
                return self.fallback.generate(prompt, aspect=aspect, style_refs=style_refs, seed=seed)
            raise


def animate_image(base_url: str, token: str, image_bytes: bytes, *, prompt: str,
                  seconds: float = 3.0, fps: int = 24, width: int = 704,
                  height: int = 1280, timeout: float = 900.0) -> bytes:
    # 900s: a COLD first call (Wan hot-swap + load from FUSE + inference) measured
    # 787s on the L4; 600s made the client give up on work the GPU then finished.
    """Image→video on cadence-gen (FastWan distill). Returns MP4 bytes; raises on failure
    (callers decide whether to degrade to the still)."""
    frames = max(17, min(int(round(seconds * fps)) + 1, 121))
    body = json.dumps({
        "image_b64": base64.b64encode(image_bytes).decode(),
        "prompt": prompt, "num_frames": frames, "fps": fps,
        "width": width, "height": height, "steps": 3,
    }).encode()
    req = urllib.request.Request(
        f"{base_url.strip().rstrip('/')}/animate", data=body, method="POST",
        headers={"content-type": "application/json", "x-gen-token": token.strip()},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data or len(data) < 5000:
        raise RuntimeError("selfhost animate returned no video")
    return data
