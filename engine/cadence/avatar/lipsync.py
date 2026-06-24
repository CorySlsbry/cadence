"""Client for cadence-gen's ``/lipsync`` endpoint — the self-hosted photoreal talking
avatar (LatentSync for real recordings, EchoMimicV3 for a single frame).

Mirrors :class:`cadence.imagegen.selfhost.SelfHostGenerator`: same env wiring, CRLF-safe
header values, ledger-metered, and falls back to a wrapped provider (e.g. a hosted
lip-sync API) if the GPU lane errors — so an avatar render never hard-fails on a GPU
hiccup. The driving ``audio`` is the FINAL cloned-voice narration, so lip-sync is
frame-accurate by construction.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from dataclasses import dataclass

from cadence.imagegen.ledger import BudgetExceeded, CostLedger

# Avatar renders are far costlier than a $0.002 FLUX image (GPU-seconds on self-host;
# real $ on hosted). The per-second / per-plan ceilings are enforced server-side at the
# API layer; this ledger charge is the in-render meter, same as the image path.
_DEFAULT_COST = float(os.environ.get("CADENCE_AVATAR_COST", "0.05"))


@dataclass(frozen=True)
class LipsyncResult:
    video_bytes: bytes
    cost_usd: float
    provider: str


class LipsyncClient:
    name = "selfhost-lipsync"

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        ledger: CostLedger | None = None,
        fallback: "LipsyncClient | None" = None,
        timeout: float = 1200.0,   # lip-sync over a long clip is heavy; well above animate's 900s
    ) -> None:
        # Secret-mounted env values can carry CRLF; urllib rejects \r\n in header values.
        self.base_url = base_url.strip().rstrip("/")
        self.token = token.strip()
        self.ledger = ledger
        self.fallback = fallback
        self.timeout = timeout
        self.cost_per_render = _DEFAULT_COST

    def synth(
        self,
        *,
        audio: bytes,
        reference: bytes,
        is_video: bool,
        fps: int = 25,
        res: int = 720,
        upscale: bool = True,
    ) -> LipsyncResult:
        """Render a talking-avatar mp4 from ``reference`` (a recording or a frame) driven
        by ``audio``. ``is_video`` picks the re-sync (LatentSync) vs generate (EchoMimicV3)
        lane on the service."""
        if self.ledger is not None and not self.ledger.can_spend(self.cost_per_render):
            raise BudgetExceeded(f"avatar budget cap reached (need ${self.cost_per_render}).")
        ref_key = "video_b64" if is_video else "image_b64"
        payload = {
            "audio_b64": base64.b64encode(audio).decode("ascii"),
            ref_key: base64.b64encode(reference).decode("ascii"),
            "fps": fps,
            "res": res,
            "upscale": upscale,
        }
        req = urllib.request.Request(
            f"{self.base_url}/lipsync",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"content-type": "application/json", "x-gen-token": self.token},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                video = resp.read()
            if not video or len(video) < 1000:
                raise RuntimeError("lipsync returned an empty video")
            if self.ledger is not None:
                self.ledger.charge(self.cost_per_render)
            return LipsyncResult(video_bytes=video, cost_usd=self.cost_per_render, provider=self.name)
        except BudgetExceeded:
            raise
        except Exception as exc:  # noqa: BLE001 - degrade to the wrapped provider, never hard-fail
            if self.fallback is not None:
                print(
                    f"[lipsync] self-host failed ({exc!r}) -> falling back to "
                    f"{getattr(self.fallback, 'name', 'fallback')}",
                    flush=True,
                )
                return self.fallback.synth(
                    audio=audio, reference=reference, is_video=is_video, fps=fps, res=res, upscale=upscale
                )
            raise
