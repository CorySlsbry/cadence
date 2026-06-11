"""cadence-gen — CloutHook's self-hosted generation service (Cloud Run GPU, 1×L4).

Endpoints (bearer-style header auth via GEN_TOKEN):
  POST /image    FLUX.2-klein-4B text→image (Apache 2.0, 4-step distilled, bf16)
  POST /animate  FastWan2.2-TI2V-5B image→video (Apache 2.0, 3-step distilled)
  POST /tts      Kokoro-82M speech (Apache 2.0, CPU — never blocks on the GPU)
  GET  /healthz  503 until the image pipeline is warm (Cloud Run startup probe)

Design: ONE GPU model resident at a time (24GB L4). /image and /animate serialize on
a GPU lock and hot-swap pipelines when the modality changes; /tts runs on CPU threads
concurrently. Weights come from a GCS FUSE mount at $MODELS_DIR (never baked into the
image, per Cloud Run GPU best practices).
"""

from __future__ import annotations

import base64
import gc
import io
import os
import tempfile
import threading

import numpy as np
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

MODELS_DIR = os.environ.get("MODELS_DIR", "/models")
GEN_TOKEN = os.environ.get("GEN_TOKEN", "")

app = FastAPI()

_gpu_lock = threading.Lock()        # serializes ALL GPU work (image + animate + swaps)
_state = {"active": None, "pipe": None, "warm": False}
_kokoro = {"engine": None, "lock": threading.Lock()}


def _auth(x_gen_token: str | None) -> None:
    if not GEN_TOKEN or x_gen_token != GEN_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")


def _free_gpu() -> None:
    if _state["pipe"] is not None:
        del _state["pipe"]
        _state["pipe"] = None
        _state["active"] = None
        gc.collect()
        import torch

        torch.cuda.empty_cache()


def _load_flux():
    """FLUX.2-klein-4B in bf16 — fits the L4 with headroom; 4 steps, guidance 1.0."""
    import torch
    from diffusers import Flux2KleinPipeline

    pipe = Flux2KleinPipeline.from_pretrained(
        os.path.join(MODELS_DIR, "flux2-klein-4b"), torch_dtype=torch.bfloat16
    ).to("cuda")
    return pipe


def _load_wan():
    """FastWan2.2-TI2V-5B (3-step distill) with CPU offload + VAE tiling for the L4."""
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline

    root = os.path.join(MODELS_DIR, "fastwan22-ti2v-5b")
    vae = AutoencoderKLWan.from_pretrained(root, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanImageToVideoPipeline.from_pretrained(root, vae=vae, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    try:
        pipe.vae.enable_tiling()
    except Exception:  # noqa: BLE001 - tiling is an optimization, not a requirement
        pass
    return pipe


def _get_pipe(kind: str):
    """Hot-swap so exactly one GPU model is resident (caller must hold _gpu_lock)."""
    if _state["active"] != kind:
        _free_gpu()
        _state["pipe"] = _load_flux() if kind == "flux" else _load_wan()
        _state["active"] = kind
    return _state["pipe"]


def _get_kokoro():
    if _kokoro["engine"] is None:
        with _kokoro["lock"]:
            if _kokoro["engine"] is None:
                from kokoro_onnx import Kokoro

                _kokoro["engine"] = Kokoro(
                    os.path.join(MODELS_DIR, "kokoro", "kokoro-v1.0.onnx"),
                    os.path.join(MODELS_DIR, "kokoro", "voices-v1.0.bin"),
                )
    return _kokoro["engine"]


@app.on_event("startup")
def _warmup() -> None:
    def run():
        try:
            with _gpu_lock:
                pipe = _get_pipe("flux")
                pipe("warmup frame, a simple gradient", num_inference_steps=1,
                     guidance_scale=1.0, height=512, width=512)
            _state["warm"] = True
            print("[gen] flux warm", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[gen] warmup failed: {exc!r}", flush=True)

    threading.Thread(target=run, daemon=True).start()


@app.get("/healthz")
def healthz():
    if not _state["warm"]:
        raise HTTPException(status_code=503, detail="warming")
    return {"ok": True, "active": _state["active"]}


class ImageReq(BaseModel):
    prompt: str
    width: int = 768
    height: int = 1344
    steps: int = 4
    seed: int | None = None


@app.post("/image")
def image(req: ImageReq, x_gen_token: str | None = Header(default=None)):
    _auth(x_gen_token)
    import torch

    w = max(256, min(req.width, 1536)) // 16 * 16
    h = max(256, min(req.height, 1536)) // 16 * 16
    gen = torch.Generator("cuda").manual_seed(req.seed) if req.seed is not None else None
    with _gpu_lock:
        pipe = _get_pipe("flux")
        out = pipe(req.prompt, num_inference_steps=max(1, min(req.steps, 8)),
                   guidance_scale=1.0, height=h, width=w, generator=gen)
    img = out.images[0]
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


class AnimateReq(BaseModel):
    image_b64: str          # PNG/JPEG of the scene to animate
    prompt: str = "subtle cinematic motion, characters move naturally"
    num_frames: int = 73    # ~3s @ 24fps
    fps: int = 24
    width: int = 704
    height: int = 1280
    steps: int = 3          # FastWan distill


@app.post("/animate")
def animate(req: AnimateReq, x_gen_token: str | None = Header(default=None)):
    _auth(x_gen_token)
    from PIL import Image
    from diffusers.utils import export_to_video

    raw = base64.b64decode(req.image_b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w = max(256, min(req.width, 1280)) // 16 * 16
    h = max(256, min(req.height, 1280)) // 16 * 16
    img = img.resize((w, h))
    frames_n = max(17, min(req.num_frames, 121))
    with _gpu_lock:
        pipe = _get_pipe("wan")
        out = pipe(image=img, prompt=req.prompt, height=h, width=w,
                   num_frames=frames_n, num_inference_steps=max(2, min(req.steps, 8)),
                   guidance_scale=1.0)
    frames = out.frames[0]
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        path = tf.name
    export_to_video(frames, path, fps=req.fps)
    data = open(path, "rb").read()
    os.unlink(path)
    return Response(content=data, media_type="video/mp4")


class TtsLine(BaseModel):
    text: str
    voice: str = "af_heart"


class TtsReq(BaseModel):
    lines: list[TtsLine]
    speed: float = 1.0
    gap_ms: int = 240


@app.post("/tts")
def tts(req: TtsReq, x_gen_token: str | None = Header(default=None)):
    """Kokoro speech — single narration or multi-voice dialogue (one entry per line).
    Returns 24kHz mono WAV. CPU-only: runs even while the GPU is mid-animation."""
    _auth(x_gen_token)
    import soundfile as sf

    if not req.lines:
        raise HTTPException(status_code=422, detail="no lines")
    k = _get_kokoro()
    gap = np.zeros(int(24000 * max(req.gap_ms, 0) / 1000), dtype=np.float32)
    parts: list[np.ndarray] = []
    for line in req.lines[:200]:
        text = line.text.strip()
        if not text:
            continue
        samples, _sr = k.create(text, voice=line.voice, speed=max(0.6, min(req.speed, 1.4)),
                                lang="en-us")
        parts.append(samples.astype(np.float32))
        parts.append(gap)
    if not parts:
        raise HTTPException(status_code=422, detail="empty script")
    audio = np.concatenate(parts[:-1] if len(parts) > 1 else parts)
    buf = io.BytesIO()
    sf.write(buf, audio, 24000, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")
