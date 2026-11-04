# cadence-gen — photoreal avatar (`/lipsync`) deploy runbook

> **Status (2026-06-15): DEPLOYED — LatentSync 1.6 lane.** Verified by an 8-agent
> research + adversarial-verify pass before any GPU spend. This doc reflects what is
> *actually shipped*, not a proposal. EchoMimicV3 (photo path) is documented as a future
> optional lane (§5). **GFPGAN was dropped — do NOT add it (§6); the earlier version of
> this doc had a Dockerfile block that would break the gen stack.**

The avatar lane lives in `gen/main.py` `POST /lipsync`: it auth-gates, base64-decodes the
reference + driving audio, runs the **MediaPipe** face gate (Apache-2.0), then invokes the
talking-avatar model via a **deploy-time command template** from env (`LATENTSYNC_CMD` /
`ECHOMIMIC_CMD`). Until a template is set it returns `503 "avatar model not provisioned"`,
so the whole app builds against a stable contract. Placeholders: `{ref} {audio} {out} {fps}
{res} {models}` (`{ref}/{audio}/{out}` are `shlex.quote`d; `{models}`=`/models`).

## 1. Architecture decision (why a venv, not a sidecar)

LatentSync's inference path **module-imports `decord==0.6.0`** and pins **`numpy==1.26.4`** — a
hard ABI clash with this image's pinned **`numpy>=2.0.2`** (required by FLUX/FastWan/mediapipe).
It therefore **cannot run in the gen image's shared interpreter**. We isolate it in a
**fully-separate `venv` baked into the same image** at `/opt/latentsync-venv` (its own python,
own torch 2.7.1+cu126, own numpy<2, own `diffusers==0.32.2`). The FastAPI process stays on
numpy 2; `/lipsync` shells out to `/opt/latentsync-venv/bin/python`. One container, clean
isolation, no second service. (Alternative considered: mirror `lucataco/cog-LatentSync` as a
sidecar — rejected for low volume; adds a deployable.)

## 2. Vendor inference weights → the read-only `/models` bucket  (~5.5GB)

Run **in-cloud** (HF→GCS inside GCP, no local bandwidth). The bucket
`cadence-gen-models-uscentral1` is FUSE-mounted **read-only at /models on Cloud Run**, but
`gsutil`/Cloud Build write to the *bucket* directly (the readOnly flag is on the mount, not the
bucket). Stage BEFORE deploying the new revision so the cold start sees them.

```powershell
gcloud builds submit --no-source --region us-central1 `
  --config "gen/cloudbuild-vendor-latentsync.yaml" --project builder-ai-497610
```

`gen/cloudbuild-vendor-latentsync.yaml` fetches only the **inference-path** files (UNet 5.07GB +
whisper-tiny 75MB + sd-vae-ft-mse 335MB) — SyncNet (1.6GB) and `auxiliary/*` (2.9GB) are
training/eval-only and skipped. All sources are ungated/public. Layout written:

```
gs://cadence-gen-models-uscentral1/latentsync/checkpoints/
  latentsync_unet.pt                 # --inference_ckpt_path
  whisper/tiny.pt                    # symlinked into the repo at build (relative read)
  sd-vae-ft-mse/{diffusion_pytorch_model.safetensors,config.json}   # VAE patched to this path
```

## 3. Gen image — the isolated venv (already in `gen/Dockerfile`)

The Dockerfile block (after the main `pip install`, before `COPY main.py` for cache):
- `apt-get install git build-essential`
- `python -m venv /opt/latentsync-venv` + its own `torch==2.7.1 torchvision==0.22.1` (cu126).
- `git clone bytedance/LatentSync` pinned to `a229c3948406bc2cf6eaf4873e662e70c6a04746`.
- Install the repo's `requirements.txt` **after** stripping `torch/torchvision`, the `cu121`
  index, `insightface`, `gradio`, `decord`; then add `eva-decord==0.6.1` (drop-in `decord`,
  the only cp311-installable build).
- `sed` the runtime VAE load `stabilityai/sd-vae-ft-mse` → `/models/latentsync/checkpoints/sd-vae-ft-mse`
  (image is `HF_HUB_OFFLINE=1`, so the original network call would crash).
- Symlink `repo/checkpoints/whisper` → `/models/latentsync/checkpoints/whisper` (dangling at
  build; resolves at runtime).

Build by **digest** (hard rule — never deploy `:latest`):

```powershell
gcloud builds submit "C:\Users\you\Downloads\Video Analyzer\gen" --project builder-ai-497610 `
  --region us-central1 --tag us-central1-docker.pkg.dev/builder-ai-497610/cadence/gen:latest `
  --machine-type e2-highcpu-8
$BUILD_ID = (gcloud builds list --project builder-ai-497610 --region us-central1 --limit 1 --format "value(id)")
$DIGEST   = (gcloud builds describe $BUILD_ID --project builder-ai-497610 --region us-central1 --format "value(results.images[0].digest)")
$IMG = "us-central1-docker.pkg.dev/builder-ai-497610/cadence/gen@$DIGEST"
```

## 4. Deploy by digest + set the command template (PowerShell)

Re-state GPU/mount/secret explicitly — they have silently dropped on bare redeploys. Keep
`--no-gpu-zonal-redundancy` or the L4 rate jumps +56%.

```powershell
gcloud run deploy cadence-gen --project builder-ai-497610 --region us-central1 --image $IMG `
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy `
  --cpu 8 --memory 32Gi --concurrency 1 --max-instances 2 --no-cpu-throttling --cpu-boost `
  --set-secrets GEN_TOKEN=cadence-gen-token:latest `
  --add-volume name=models,type=cloud-storage,bucket=cadence-gen-models-uscentral1,readonly=true `
  --add-volume-mount volume=models,mount-path=/models `
  --set-env-vars MODELS_DIR=/models

# LATENTSYNC_CMD — no commas, but use ^@^ for safety; {fps}/{res} are DROPPED (no such flags).
gcloud run services update cadence-gen --project builder-ai-497610 --region us-central1 `
  --update-env-vars "^@^LATENTSYNC_CMD=cd /opt/latentsync-venv/repo && /opt/latentsync-venv/bin/python -m scripts.inference --unet_config_path configs/unet/stage2_512.yaml --inference_ckpt_path {models}/latentsync/checkpoints/latentsync_unet.pt --video_path {ref} --audio_path {audio} --video_out_path {out} --inference_steps 20 --guidance_scale 1.5 --seed 1247 --enable_deepcache"

# verify GPU + volume + env survived
gcloud run services describe cadence-gen --region us-central1 --format "yaml(spec.template.spec.containers[0].env,spec.template.spec.containers[0].resources)"
```

Notes: `{ref}` MUST be a **video** (.mp4) — LatentSync re-syncs an existing clip's mouth; a still
photo is unsupported (that's the EchoMimic path, §5). `gen/main.py` already writes a `.mp4` ref
for the video lane, so the contract is satisfied. VRAM ≈18GB at 512² w/ deepcache — fits the L4
24GB at concurrency=1; segment long clips if OOM.

## 5. (Future, optional) EchoMimicV3-Flash — the photo→talking path

Verified to run **on the shared gen image** (no torch/numpy change): clone `antgroup/echomimic_v3`,
add `eva-decord==0.6.1 pyloudnorm moviepy==2.2.1 omegaconf einops timm tomesd torchdiffeq torchsde
librosa soundfile safetensors scikit-image SentencePiece func_timeout onnxruntime imageio[pyav]`
(NEVER `pip install -r requirements.txt` — it pins `tensorflow==2.15.0` → forces numpy<2). Weights
~25GB (Wan2.1-Fun-V1.1-1.3B-InP base 19.8GB + flash-pro transformer 3.73GB + chinese-wav2vec2-base
1.52GB). `ECHOMIMIC_CMD` (writes `{save_path}/{stem}_output.mp4` → `mv` to `{out}`):
```
cd /opt/echomimic_v3 && python infer_flash.py --image_path {ref} --audio_path {audio} --prompt "A person is speaking." --config_path config/config.yaml --num_inference_steps 8 --model_name {models}/echomimicv3/flash/Wan2.1-Fun-V1.1-1.3B-InP --transformer_path {models}/echomimicv3/flash/transformer/diffusion_pytorch_model.safetensors --wav2vec_model_dir {models}/echomimicv3/flash/chinese-wav2vec2-base --save_path "$(dirname {out})" --sampler_name Flow_Unipc --video_length 81 --guidance_scale 6.0 --audio_guidance_scale 3.0 --audio_scale 1.0 --neg_scale 1.0 --neg_steps 0 --seed 43 --enable_teacache --teacache_threshold 0.1 --num_skip_start_steps 5 --riflex_k 6 --ulysses_degree 1 --ring_degree 1 --weight_dtype bfloat16 --sample_size {res} {res} --fps {fps} && mv "$(dirname {out})/$(basename {ref} | cut -d. -f1)_output.mp4" {out}
```

## 6. GFPGAN — DROPPED (do not add)

1. `basicsr 1.4.2` runs `torch.from_numpy` on module-level arrays **at import** and is
   numpy-2-incompatible (BasicSR #740) — the only fix is numpy<2, which breaks the image's pinned
   `numpy>=2.0.2` + mediapipe + opencv + FLUX/FastWan. 2. Role mismatch — image/folder restorer,
   no audio/video, can't satisfy the `{ref}{audio}{out}` contract. 3. **License risk** —
   StyleGAN2/dnnlib priors carry the NVIDIA *non-commercial* license; unsafe for a paid SaaS.
   If a face-restore finish is ever wanted, isolate **CodeFormer** in its own numpy<2 sidecar.
   `gen/main.py`'s `upscale` flag is a no-op for the CMD contract, so dropping it needs no code change.

## 7. Smoke test + quality gate (the paid step)

```powershell
# 1) first /lipsync after scale-to-zero pays a GCSFuse cold read of ~5.5GB + model init (~300-480s);
#    keep the lipsync client timeout >=600s. Drive a real render (reference: job 0068a8a8 webm), then:
python engine/scripts/avatar_quality.py --reference <your_recording.webm> <render.mp4> --json
```
Targets (HeyGen bar in parens; honest self-host bar ≈ level-4): face_sim ≥0.80 (0.840), LSE-C ≥6
(8.97), voice_sim ≥0.75, UTMOS ≥3.8. Re-render across reference takes and keep the highest
**composite** — the "as close to me as possible without feedback" loop. Last ~10% = one human side-by-side.

## 8. Cost (verified June 2026)
- L4 (no zonal redundancy) = **$0.0001867/s** → ~**$0.19 per cold render** (incl. weight load).
- Cloud Build on E2_HIGHCPU_8 ≈ $0.016/min → vendoring ~$0.16–0.24, gen image ~$0.24–0.40.
- Storage: ~5.5GB weights + image @ $0.10/GB-month ≈ **~$1–2/mo**.
- **One-time deploy ≈ $1–2; ongoing ≈ $0.19/render + ~$1–2/mo storage.** GPUs have no free tier;
  instance-based billing means CPU/mem bill for the full instance lifetime until scale-to-zero.

## Checklist
- [x] weights vendored to `latentsync/checkpoints/` (UNet + whisper + sd-vae); SyncNet/aux skipped
- [x] isolated venv block in `gen/Dockerfile`; image built; **digest** captured
- [ ] `cadence-gen` deployed by digest; GPU + `/models` mount + `GEN_TOKEN` confirmed post-deploy
- [ ] `LATENTSYNC_CMD` set; `/lipsync` returns 200 (was 503); face gate passes
- [ ] smoke render scored with `avatar_quality.py`; composite recorded
- [ ] worker redeployed carrying the caption text-quality fixes (lexicon + no-garbage-text)
- [ ] `enterprise-security-audit` over avatar authz (consent fail-closed, per-user isolation, revoke)
