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
import shutil
import sys
import tempfile
import time
import traceback

# Weights come from GCS via STAGED PARALLEL DOWNLOAD, not a FUSE mount: safetensors
# mmap random reads defeat gcsfuse readahead (measured 2026-07-17: ~20 min per 4.7 GB
# shard ≈ a 7-hour load for 126 GB — the first execution timed out at 17% of one
# transformer). Same-region transfer_manager pulls at GB/s instead, and staging one
# component at a time keeps peak tmpfs (= RAM) at ~57 GB + transient, inside 80 Gi.
WEIGHTS_URI = os.environ.get(
    "A14B_WEIGHTS_URI",
    "gs://cadence-gen-models-uscentral1/wan22-a14b/Wan2.2-I2V-A14B-Diffusers")
LORA_URI = os.environ.get(
    "A14B_LORA_URI",
    "gs://cadence-gen-models-uscentral1/wan22-a14b/loras/wan22-lightning-i2v-seko-v1")
STAGE_DIR = os.environ.get("A14B_STAGE_DIR", "/tmp/a14b")
# THREAD workers: throughput is capped ~0.06 GB/s by the instance network either way
# (PROCESS measured identical), and forking after CUDA init crashes the pool
# (BrokenProcessPool). The real startup win is bf16-at-rest (half the bytes).
DL_WORKERS = int(os.environ.get("A14B_DL_WORKERS", "4"))  # few fat streams: 12 starved each other below the 120s stall timeout
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


def _download_prefix(gs_uri: str, dest: str) -> None:
    """Parallel-download every blob under gs_uri into dest (flattened to the prefix)."""
    from google.cloud import storage
    from google.cloud.storage import transfer_manager

    bucket_name, prefix = _split_gs(gs_uri)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = [b for b in client.list_blobs(bucket_name, prefix=prefix + "/")
             if not b.name.endswith("/") and "/.cache/" not in b.name]
    if not blobs:
        raise RuntimeError(f"no blobs under {gs_uri}")
    # blob_name_prefix PREPENDS to each name to form the full GCS path (it is not a
    # strip!) — so pass RELATIVE names; local files then land at dest/<relative-name>.
    rel_names = [b.name[len(prefix) + 1:] for b in blobs]
    t0 = time.time()
    results = transfer_manager.download_many_to_path(
        bucket, rel_names, destination_directory=dest, blob_name_prefix=prefix + "/",
        max_workers=DL_WORKERS, worker_type=transfer_manager.THREAD,
        download_kwargs={"timeout": 900})
    for name, res in zip(rel_names, results):
        if isinstance(res, Exception):
            raise RuntimeError(f"download failed for {name}: {res!r}")
    gb = sum(b.size or 0 for b in blobs) / 1e9
    dt = time.time() - t0
    print(f"[a14b] downloaded {gb:.1f} GB ({len(rel_names)} files) in {dt:.0f}s "
          f"({gb/max(dt,1e-9):.2f} GB/s)", flush=True)


def _stage(subdir: str) -> str:
    """Download one model component under STAGE_DIR and return its local path."""
    local = os.path.join(STAGE_DIR, subdir)
    _download_prefix(f"{WEIGHTS_URI}/{subdir}", local)
    return local


def _load_pipeline():
    """A14B two-expert MoE + Lightning 4-step LoRAs, fused, bf16-resident.

    The repo ships the transformers as FP32 shards (57 GB each): torch_dtype=bfloat16
    at load is MANDATORY (fp32-resident ~126 GB would OOM the 96 GB card). Components
    are staged→loaded→DELETED one at a time so tmpfs (RAM-backed) peaks at one
    transformer (~57 GB), not the whole repo (126 GB > 80 Gi). Fuse-then-unload
    removes per-step LoRA overhead; flow_shift=5.0 is the Lightning setting (repo
    default 3.0) — with boundary_ratio 0.9 the 4 steps split exactly 2 high / 2 low.
    """
    import torch
    from diffusers import (AutoencoderKLWan, UniPCMultistepScheduler,
                           WanImageToVideoPipeline, WanTransformer3DModel)
    from transformers import T5TokenizerFast, UMT5EncoderModel

    t_all = time.time()
    os.makedirs(STAGE_DIR, exist_ok=True)

    def load_component(subdir: str, loader):
        t0 = time.time()
        local = _stage(subdir)
        model = loader(local)
        shutil.rmtree(local, ignore_errors=True)  # free tmpfs (RAM) before the next one
        print(f"[a14b] {subdir} staged+loaded in {time.time()-t0:.0f}s", flush=True)
        return model

    # device_map="cuda" streams tensors straight to VRAM as shards are read — WITHOUT it
    # the model would materialize on CPU (28.6 GB bf16) while its 57 GB of fp32 shards
    # still sit in RAM-backed tmpfs, busting the 80 Gi limit.
    text_encoder = load_component(
        "text_encoder",
        lambda p: UMT5EncoderModel.from_pretrained(
            p, torch_dtype=torch.bfloat16, device_map="cuda"))
    transformer = load_component(
        "transformer",
        lambda p: WanTransformer3DModel.from_pretrained(
            p, torch_dtype=torch.bfloat16, device_map="cuda"))
    transformer_2 = load_component(
        "transformer_2",
        lambda p: WanTransformer3DModel.from_pretrained(
            p, torch_dtype=torch.bfloat16, device_map="cuda"))
    vae = load_component(
        "vae",
        lambda p: AutoencoderKLWan.from_pretrained(p, torch_dtype=torch.float32).to("cuda"))
    tokenizer = T5TokenizerFast.from_pretrained(_stage("tokenizer"))
    scheduler = UniPCMultistepScheduler.from_pretrained(_stage("scheduler"))
    scheduler = UniPCMultistepScheduler.from_config(scheduler.config, flow_shift=5.0)

    pipe = WanImageToVideoPipeline(
        transformer=transformer, transformer_2=transformer_2, text_encoder=text_encoder,
        tokenizer=tokenizer, vae=vae, scheduler=scheduler,
        image_encoder=None, image_processor=None,
        boundary_ratio=0.9,  # repo model_index.json: high-noise expert for t >= 900
    )

    lora_local = os.path.join(STAGE_DIR, "loras")
    _download_prefix(LORA_URI, lora_local)
    pipe.load_lora_weights(lora_local, weight_name="high_noise_model.safetensors",
                           adapter_name="lx_high")
    pipe.load_lora_weights(lora_local, weight_name="low_noise_model.safetensors",
                           adapter_name="lx_low", load_into_transformer_2=True)
    pipe.set_adapters(["lx_high", "lx_low"], adapter_weights=[1.0, 1.0])
    pipe.fuse_lora(components=["transformer"], adapter_names=["lx_high"], lora_scale=1.0)
    pipe.fuse_lora(components=["transformer_2"], adapter_names=["lx_low"], lora_scale=1.0)
    pipe.unload_lora_weights()
    shutil.rmtree(lora_local, ignore_errors=True)
    print("[a14b] lightning loras fused", flush=True)

    pipe.vae.enable_tiling()  # decode-peak seatbelt at 81f
    print(f"[a14b] ready on cuda in {time.time()-t_all:.0f}s total", flush=True)
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
    # GPU jobs are capped at a 1-hour task timeout, so long manifests shard across
    # parallel tasks (--tasks N): task i renders scenes[i::N], each loading its own
    # model copy on its own GPU. results.json is written per-task (suffix _tK when
    # sharded) so parallel tasks never clobber each other; the caller merges.
    task_idx = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    task_cnt = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))
    total = len(scenes)
    if task_cnt > 1:
        scenes = scenes[task_idx::task_cnt]
    if not scenes:
        print(f"manifest has no scenes for task {task_idx}/{task_cnt}", flush=True)
        return 1 if total == 0 else 0
    print(f"[a14b] task {task_idx}/{task_cnt}: {len(scenes)}/{total} scene(s) "
          f"@ {WIDTH}x{HEIGHT} {FRAMES}f {STEPS}steps", flush=True)

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

    results_name = "results.json" if task_cnt == 1 else f"results_t{task_idx}.json"
    client.bucket(out_bucket).blob(f"{out_prefix}/{results_name}").upload_from_string(
        json.dumps({"task": task_idx, "task_count": task_cnt,
                    "scenes": results, "ok": ok, "total": len(scenes)}, indent=2),
        content_type="application/json")
    print(f"[a14b] done: {ok}/{len(scenes)} rendered", flush=True)
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
