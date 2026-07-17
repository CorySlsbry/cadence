"""cadence-gen-premium — Wan 2.2 I2V-A14B batch renderer (Cloud Run JOB, RTX PRO 6000 96GB).

The premium motion lane. Runs to completion per execution (no HTTP): load the A14B
MoE pipeline ONCE (the expensive part), then render EVERY scene in the manifest —
amortizing the model load across a whole video. Scene I/O goes through GCS via the
storage client (works with any bucket); model weights come from the read-only GCS
FUSE mount at /models (see PREMIUM_DEPLOY.md).

Env contract (set per-execution via --update-env-vars):
  A14B_INPUT_PREFIX   gs://bucket/prefix with manifest.json + the scene stills
  A14B_OUTPUT_PREFIX  gs://bucket/prefix for the rendered mp4s + results.json
Optional knobs: A14B_STEPS=4  A14B_FRAMES=81  A14B_FPS=16  A14B_WIDTH=720
  A14B_HEIGHT=1280  A14B_MODELS_DIR  A14B_LORA_DIR

manifest.json: {"scenes": [{"id": "s01", "image": "s01.png", "prompt": "...",
                            "seed": 42, "num_frames": 81?}, ...]}

Exit 0 if at least one scene rendered (per-scene failures are recorded in
results.json, mirroring the worker's degrade-to-still contract); exit 1 only if
the pipeline can't load or every scene fails.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import traceback

MODELS_DIR = os.environ.get(
    "A14B_MODELS_DIR", "/models/wan22-a14b/Wan2.2-I2V-A14B-Diffusers")
LORA_DIR = os.environ.get(
    "A14B_LORA_DIR", "/models/wan22-a14b/loras/wan22-lightning-i2v-seko-v1")
STEPS = int(os.environ.get("A14B_STEPS", "4"))
FRAMES = int(os.environ.get("A14B_FRAMES", "81"))
FPS = int(os.environ.get("A14B_FPS", "16"))
WIDTH = int(os.environ.get("A14B_WIDTH", "720"))
HEIGHT = int(os.environ.get("A14B_HEIGHT", "1280"))


def _split_gs(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"not a gs:// uri: {uri}")
    bucket, _, prefix = uri[5:].partition("/")
    return bucket, prefix.rstrip("/")


def _load_pipeline():
    """A14B two-expert MoE + Lightning 4-step LoRAs, fused, bf16-resident.

    The repo ships the transformers as FP32 shards (57 GB each): torch_dtype=bfloat16
    is MANDATORY (fp32-resident ~126 GB would OOM the 96 GB card). Fuse-then-unload
    removes per-step LoRA overhead; flow_shift=5.0 is the Lightning setting (repo
    default 3.0) — with boundary_ratio 0.9 the 4 steps split exactly 2 high / 2 low.
    """
    import torch
    from diffusers import UniPCMultistepScheduler, WanImageToVideoPipeline

    t0 = time.time()
    pipe = WanImageToVideoPipeline.from_pretrained(MODELS_DIR, torch_dtype=torch.bfloat16)
    print(f"[a14b] pipeline loaded in {time.time()-t0:.0f}s", flush=True)

    pipe.load_lora_weights(LORA_DIR, weight_name="high_noise_model.safetensors",
                           adapter_name="lx_high")
    pipe.load_lora_weights(LORA_DIR, weight_name="low_noise_model.safetensors",
                           adapter_name="lx_low", load_into_transformer_2=True)
    pipe.set_adapters(["lx_high", "lx_low"], adapter_weights=[1.0, 1.0])
    pipe.fuse_lora(components=["transformer"], adapter_names=["lx_high"], lora_scale=1.0)
    pipe.fuse_lora(components=["transformer_2"], adapter_names=["lx_low"], lora_scale=1.0)
    pipe.unload_lora_weights()
    print("[a14b] lightning loras fused", flush=True)

    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=5.0)
    pipe.to("cuda")
    pipe.vae.enable_tiling()  # decode-peak seatbelt at 81f
    print(f"[a14b] ready on cuda in {time.time()-t0:.0f}s total", flush=True)
    return pipe


def main() -> int:
    from google.cloud import storage
    from PIL import Image

    in_uri = os.environ.get("A14B_INPUT_PREFIX", "")
    out_uri = os.environ.get("A14B_OUTPUT_PREFIX", "")
    if not in_uri or not out_uri:
        print("A14B_INPUT_PREFIX / A14B_OUTPUT_PREFIX are required", flush=True)
        return 1

    client = storage.Client()
    in_bucket, in_prefix = _split_gs(in_uri)
    out_bucket, out_prefix = _split_gs(out_uri)
    manifest = json.loads(
        client.bucket(in_bucket).blob(f"{in_prefix}/manifest.json").download_as_bytes())
    scenes = manifest.get("scenes") or []
    if not scenes:
        print("manifest has no scenes", flush=True)
        return 1
    print(f"[a14b] {len(scenes)} scene(s) @ {WIDTH}x{HEIGHT} {FRAMES}f {STEPS}steps", flush=True)

    import torch
    from diffusers.utils import export_to_video

    pipe = _load_pipeline()
    results: list[dict] = []
    ok = 0
    for sc in scenes:
        sid = sc.get("id") or f"s{len(results):03d}"
        t0 = time.time()
        try:
            img_bytes = client.bucket(in_bucket).blob(
                f"{in_prefix}/{sc['image']}").download_as_bytes()
            image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            gen = (torch.Generator("cuda").manual_seed(int(sc["seed"]))
                   if sc.get("seed") is not None else None)
            frames = pipe(
                image=image, prompt=sc.get("prompt") or "",
                negative_prompt=sc.get("negative_prompt") or "",
                height=HEIGHT, width=WIDTH,
                num_frames=int(sc.get("num_frames") or FRAMES),
                num_inference_steps=STEPS,
                guidance_scale=1.0, guidance_scale_2=1.0,  # CFG off (distilled)
                generator=gen,
            ).frames[0]
            with tempfile.TemporaryDirectory() as td:
                mp4 = os.path.join(td, f"{sid}.mp4")
                export_to_video(frames, mp4, fps=FPS)
                client.bucket(out_bucket).blob(
                    f"{out_prefix}/{sid}.mp4").upload_from_filename(mp4)
            ok += 1
            results.append({"id": sid, "status": "ok", "seconds": round(time.time() - t0, 1)})
            print(f"[a14b] {sid} ok in {time.time()-t0:.0f}s ({ok}/{len(scenes)})", flush=True)
        except Exception as exc:  # noqa: BLE001 - one scene must never kill the batch
            traceback.print_exc()
            results.append({"id": sid, "status": "error", "error": repr(exc)[:500]})
            print(f"[a14b] {sid} FAILED: {exc!r}", flush=True)
        finally:
            torch.cuda.empty_cache()

    client.bucket(out_bucket).blob(f"{out_prefix}/results.json").upload_from_string(
        json.dumps({"scenes": results, "ok": ok, "total": len(scenes)}, indent=2),
        content_type="application/json")
    print(f"[a14b] done: {ok}/{len(scenes)} rendered", flush=True)
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
