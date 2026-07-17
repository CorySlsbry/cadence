# cadence-gen-premium — Wan 2.2 I2V-A14B on Cloud Run Jobs (RTX PRO 6000 Blackwell)

The **premium motion lane**: top open-weight image-to-video (Wan 2.2 I2V-A14B, Apache-2.0,
two-expert MoE) + lightx2v Lightning 4-step LoRAs, run as an **on-demand Cloud Run JOB** on the
96 GB RTX PRO 6000 Blackwell in us-central1.

**Why a Job, not a service:** the RTX PRO 6000 on Cloud Run *services* cannot scale to zero
(instance-based billing, min-instance ~$4.72/hr all-in ≈ $3,450/mo idle). **Jobs bill only for the
execution's lifecycle** — ~$0 idle. One execution loads the model once and renders ALL scenes of a
video (see `main.py`), amortizing the load. Fits the async "notify when done" render UX.

## One-time setup

1. **Stage weights** (~129 GB → `gs://cadence-gen-models-uscentral1/wan22-a14b/`):

   ```bash
   gcloud builds submit --no-source --config gen/download_a14b.cloudbuild.yaml --project builder-ai-497610
   ```

2. **Build the image:**

   ```bash
   gcloud builds submit gen/premium --config gen/premium/cloudbuild.yaml \
     --substitutions _IMAGE=us-central1-docker.pkg.dev/builder-ai-497610/cadence/gen-premium:v1 \
     --project builder-ai-497610
   ```

3. **Create the job** (flags per Cloud Run Jobs GPU docs; RTX PRO 6000 requires ≥20 CPU + ≥80Gi;
   `--no-gpu-zonal-redundancy` is what the auto-granted 3-GPU quota covers):

   ```bash
   gcloud run jobs create cadence-gen-premium \
     --project builder-ai-497610 --region us-central1 \
     --image us-central1-docker.pkg.dev/builder-ai-497610/cadence/gen-premium:v1 \
     --cpu 20 --memory 96Gi \
     --gpu 1 --gpu-type nvidia-rtx-pro-6000 --no-gpu-zonal-redundancy \
     --task-timeout 3h --max-retries 0 --parallelism 1 --tasks 1 \
     --service-account cadence-run@builder-ai-497610.iam.gserviceaccount.com \
     --add-volume name=models,type=cloud-storage,bucket=cadence-gen-models-uscentral1,readonly=true \
     --add-volume-mount volume=models,mount-path=/models
   ```

   The `cadence-run@` SA already has storage access for the models bucket; scene I/O uses the
   storage client against whatever bucket the execution's env points at (grant objectAdmin on that
   bucket/prefix if it's a new one).

## Per-render execution

The caller (worker) uploads `manifest.json` + scene stills under an input prefix, then:

```bash
gcloud run jobs execute cadence-gen-premium \
  --project builder-ai-497610 --region us-central1 --wait \
  --update-env-vars A14B_INPUT_PREFIX=gs://BUCKET/jobs/JOB_ID/in,A14B_OUTPUT_PREFIX=gs://BUCKET/jobs/JOB_ID/out
```

Outputs: `out/<scene-id>.mp4` (720×1280 @ 16 fps, 81 frames ≈ 5.1 s) + `out/results.json`
(per-scene ok/error — mirrors the worker's degrade-to-still contract). Exit 0 if ≥1 scene rendered.

Knobs (env): `A14B_STEPS=4` `A14B_FRAMES=81` `A14B_FPS=16` `A14B_WIDTH=720` `A14B_HEIGHT=1280`.

## Model facts (verified 2026-07-16, sources in vault Premium-Video-System.md)

- `Wan-AI/Wan2.2-I2V-A14B-Diffusers`: transformer (high-noise) + transformer_2 (low-noise),
  **FP32 shards 57 GB each** → `torch_dtype=bfloat16` at load is MANDATORY (bf16-resident total
  ~69 GB weights, ~77–82 GB peak @ 720p 81f → fits 96 GB; fp32 would OOM).
- Lightning LoRAs: `lightx2v/Wan2.2-Lightning` → `Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1`
  (`high_noise_model.safetensors` → transformer, `low_noise_model.safetensors` →
  transformer_2 via `load_into_transformer_2=True`), fuse then unload.
- Lightning settings: **4 steps, flow_shift 5.0, guidance 1.0/1.0 (CFG off)** — with the repo's
  `boundary_ratio 0.9` the 4 steps split exactly 2 high-noise / 2 low-noise.
- Base image `pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime` — cu128 wheels carry sm_120
  (Blackwell); the L4 lane's cu126 image does NOT run on this GPU.

## Cost model

$4.722/hr all-in (20 vCPU + 80 Gi + GPU), billed per-second for the execution only.
Model load ~5–15 min (126 GB FUSE read) + ~30–90 s/scene → a 60–90 s short (~15–20 scenes)
≈ 20–40 min ≈ **$1.60–3.20**; a 15-min long-form (~130 scenes) ≈ 2–3.5 h ≈ **$10–17**.
Meter it: premium/Cinematic renders should carry a token multiplier (Agency tier absorbs it).

## Rollout plan (worker wiring — next phase)

`_render_faceless` gets a premium branch: when the job/tier requests Cinematic motion, upload
stills+manifest, execute this job (Cloud Run Jobs API, async poll), pull the mp4s into the same
`by_image` map the compositor already consumes (palindrome/xfade path unchanged). Free tier keeps
FastWan-5B on the scale-to-zero L4. Fallback option if Job quality/cost disappoints:
HunyuanVideo-1.5 on the L4 (license carve-out: no EU/UK/KR output monetization).
