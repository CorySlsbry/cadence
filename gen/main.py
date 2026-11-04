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
GEN_TOKEN = os.environ.get("GEN_TOKEN", "").strip()  # secrets can carry stray CR/LF

app = FastAPI()

_gpu_lock = threading.Lock()        # serializes ALL GPU work (image + animate + swaps)
_state = {"active": None, "pipe": None, "warm": False}
_kokoro = {"engine": None, "lock": threading.Lock()}


def _auth(x_gen_token: str | None) -> None:
    if not GEN_TOKEN or (x_gen_token or "").strip() != GEN_TOKEN:
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
    """Load + warm FLUX on the MAIN thread (uvicorn binds the port after startup
    completes — the deploy's startup probe is configured to wait this out).
    Loading the pipeline from a daemon thread trips torch's pinned-memory
    primary-context bug (c10 'dummyHasPrimaryContext') and segfaults."""
    try:
        import torch

        avail = torch.cuda.is_available()
        print(f"[gen] cuda available={avail} torch={torch.__version__}", flush=True)
        if avail:
            torch.cuda.set_device(0)
            print(f"[gen] device={torch.cuda.get_device_name(0)}", flush=True)
        with _gpu_lock:
            pipe = _get_pipe("flux")
            pipe(prompt="warmup frame, a simple gradient", num_inference_steps=1,
                 guidance_scale=1.0, height=512, width=512)
        _state["warm"] = True
        print("[gen] flux warm", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[gen] warmup failed: {exc!r}", flush=True)


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
        out = pipe(prompt=req.prompt, num_inference_steps=max(1, min(req.steps, 8)),
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


# ============================================================================
# /lipsync — self-hosted PHOTOREAL talking avatar (the "host it ourselves" path)
#
# Two reference modes, chosen by which input is sent:
#   • video_b64 → re-sync the lips on a REAL recording of the user (LatentSync).
#       Highest realism: the base is genuine footage, only the mouth is regenerated.
#   • image_b64 → generate a talking head from one frame (EchoMimicV3).
# Driven by `audio_b64` (the final cloned-voice narration), so lip-sync is
# frame-accurate by construction.
#
# Design notes (match the rest of this service):
#   • Serializes on `_gpu_lock` and FREES the resident diffusers model first — a
#     talking-avatar render owns the L4 for its duration (concurrency=1). At volume
#     this lip-sync lane moves to a SECOND GPU; fine for low volume / the owner.
#   • Face detection uses MediaPipe (Apache-2.0), NOT InsightFace (non-commercial
#     pretrained weights) — keeps the self-host tier commercially clean.
#   • The model itself is invoked via a deploy-time COMMAND TEMPLATE from env
#     (ECHOMIMIC_CMD / LATENTSYNC_CMD), so vendoring the repo + weights to the GCS
#     mount needs NO code change here. Until those are set we 503 with a clear reason
#     (scaffold-safe: the rest of the stack builds against a stable contract).
#
# Command template placeholders: {ref} {audio} {out} {fps} {res} {models}
# e.g. ECHOMIMIC_CMD="python /models/echomimic_v3/infer.py --ref {ref} --audio {audio}
#       --out {out} --fps {fps} --size {res}"
# ============================================================================

import shlex
import shutil
import subprocess

_FACE_DET = {"engine": None, "lock": threading.Lock()}


def _get_face_detector():
    """OpenCV Haar cascade (BSD, bundled with opencv-python-headless) — numpy-2 safe and
    dependency-light. A quality/abuse gate: refuse references with no detectable face.
    (Replaced MediaPipe, whose `solutions` API fails to load under the image's numpy 2;
    still avoids InsightFace's non-commercial weights, so the self-host tier stays clean.)"""
    if _FACE_DET["engine"] is None:
        with _FACE_DET["lock"]:
            if _FACE_DET["engine"] is None:
                import cv2

                _FACE_DET["engine"] = cv2.CascadeClassifier(
                    os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                )
    return _FACE_DET["engine"]


def _first_frame(video_path: str):
    import cv2  # opencv-python-headless

    cap = cv2.VideoCapture(video_path)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(status_code=422, detail="could not read the reference video")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def _has_face(rgb) -> bool:
    import cv2
    import numpy as _np

    gray = cv2.cvtColor(_np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)
    faces = _get_face_detector().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    return len(faces) > 0


def _sample_frames_rgb(video_path: str, n: int = 8):
    """Up to n evenly-spaced frames (RGB). Multi-frame so the face gate doesn't reject a valid
    clip just because frame 0 is a transition or the subject hasn't entered the frame yet."""
    import cv2

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frames = []
    if total <= 1:
        ok, frame = cap.read()
        if ok:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    else:
        idxs = sorted({int(i * (total - 1) / max(1, n - 1)) for i in range(n)})
        for idx in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok:
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    if not frames:
        raise HTTPException(status_code=422, detail="could not read the reference video")
    return frames


def _video_has_face(video_path: str) -> bool:
    return any(_has_face(f) for f in _sample_frames_rgb(video_path))


class LipsyncReq(BaseModel):
    audio_b64: str                       # driving narration (wav/mp3), already the user's voice
    video_b64: str | None = None         # real recording → LatentSync re-sync (preferred)
    image_b64: str | None = None         # single frame → EchoMimicV3 generate
    fps: int = 25
    res: int = 720                        # max side; 1080 for premium
    upscale: bool = True                  # GFPGAN face restore (Apache) when available
    steps: int = 20                       # LatentSync --inference_steps (quality sweep knob)
    guidance: float = 1.5                 # LatentSync --guidance_scale (lip-sync strength)


def _run_model_cmd(env_key: str, ref: str, audio: str, out: str, fps: int, res: int,
                   steps: int = 20, guidance: float = 1.5) -> None:
    """Invoke the vendored avatar model via its env command template. The template is
    the single deploy-time integration point — no code change to swap/upgrade models."""
    tmpl = os.environ.get(env_key, "").strip()
    if not tmpl:
        raise HTTPException(
            status_code=503,
            detail=f"avatar model not provisioned ({env_key} unset) — weights/repo not deployed yet",
        )
    cmd = tmpl.format(ref=shlex.quote(ref), audio=shlex.quote(audio), out=shlex.quote(out),
                      fps=fps, res=res, steps=steps, guidance=guidance, models=MODELS_DIR)
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3000)
    if proc.returncode != 0 or not os.path.exists(out):
        # Print the real failure — a silent degrade here cost us days elsewhere.
        print(f"[gen] lipsync model failed rc={proc.returncode}: {proc.stderr[-800:]}", flush=True)
        raise HTTPException(status_code=500, detail="avatar render failed")


@app.post("/lipsync")
def lipsync(req: LipsyncReq, x_gen_token: str | None = Header(default=None)):
    _auth(x_gen_token)
    if not req.audio_b64 or not (req.video_b64 or req.image_b64):
        raise HTTPException(status_code=422, detail="audio_b64 + one of video_b64/image_b64 required")

    is_video = bool(req.video_b64)
    ref_suffix = ".mp4" if is_video else ".png"
    tmp = tempfile.mkdtemp(prefix="lipsync_")
    try:
        ref_path = os.path.join(tmp, f"ref{ref_suffix}")
        audio_path = os.path.join(tmp, "audio.wav")
        out_path = os.path.join(tmp, "out.mp4")
        with open(ref_path, "wb") as f:
            f.write(base64.b64decode(req.video_b64 or req.image_b64))
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(req.audio_b64))

        # Abuse/quality gate: the reference MUST contain a real, detectable face. Sample several
        # frames for video so a valid clip isn't rejected on a transition/empty first frame.
        has_face = _video_has_face(ref_path) if is_video else _has_face(_read_image_rgb(ref_path))
        if not has_face:
            raise HTTPException(status_code=422, detail="no face detected in the reference")

        res = max(256, min(int(req.res), 1080))
        fps = max(12, min(int(req.fps), 30))
        steps = max(10, min(int(req.steps), 75))
        guidance = max(1.0, min(float(req.guidance), 3.0))
        with _gpu_lock:
            _free_gpu()  # hand the whole L4 to the avatar model (one resident model at a time)
            _run_model_cmd("LATENTSYNC_CMD" if is_video else "ECHOMIMIC_CMD",
                           ref_path, audio_path, out_path, fps, res, steps=steps, guidance=guidance)
        data = open(out_path, "rb").read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return Response(content=data, media_type="video/mp4")


class SyncScoreReq(BaseModel):
    video_b64: str


@app.post("/syncscore")
def syncscore(req: SyncScoreReq, x_gen_token: str | None = Header(default=None)):
    """Objective lip-sync quality for a rendered clip via LatentSync's own SyncNet — LSE-C
    confidence (higher = tighter sync) + AV offset (near 0 = aligned). The metric for the
    no-feedback quality loop. Needs syncnet_v2.model + sfd_face.pth under
    {models}/latentsync/checkpoints/auxiliary (symlinked into the repo at build)."""
    import re

    _auth(x_gen_token)
    if not req.video_b64:
        raise HTTPException(status_code=422, detail="video_b64 required")
    tmp = tempfile.mkdtemp(prefix="syncscore_")
    try:
        vid = os.path.join(tmp, "in.mp4")
        with open(vid, "wb") as f:
            f.write(base64.b64decode(req.video_b64))
        tmpl = os.environ.get("SYNCSCORE_CMD") or (
            "cd /opt/latentsync-venv/repo && /opt/latentsync-venv/bin/python -m eval.eval_sync_conf "
            "--video_path {video}"
        )
        cmd = tmpl.format(video=shlex.quote(vid), models=MODELS_DIR)
        with _gpu_lock:
            _free_gpu()
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=1200)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            print(f"[gen] syncscore failed rc={proc.returncode}: {proc.stderr[-800:]}", flush=True)
            raise HTTPException(status_code=500, detail="sync scoring failed")
        conf = re.search(r"SyncNet confidence:\s*([0-9.]+)", out)
        off = re.search(r"AV offset:\s*(-?[0-9]+)", out)
        result = {
            "confidence": float(conf.group(1)) if conf else None,
            "av_offset": int(off.group(1)) if off else None,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def _read_image_rgb(path: str):
    import numpy as _np
    from PIL import Image

    return _np.asarray(Image.open(path).convert("RGB"))
