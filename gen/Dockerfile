# cadence-gen: self-hosted generation on Cloud Run GPU (1x NVIDIA L4).
# Base = PyTorch's official runtime image (torch 2.7.1 + CUDA 12.6 + cuDNN9 preinstalled,
# python 3.11): the proven Cloud Run GPU lane — no hand-rolled CUDA/python stack.
FROM pytorch/pytorch:2.7.1-cuda12.6-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Avatar lip-sync lane — LatentSync 1.6 (ByteDance) in a FULLY ISOLATED numpy<2 venv.
# It CANNOT share this image's interpreter: its decord==0.6.0 / numpy==1.26.4 pins are a
# hard ABI clash with the pinned numpy>=2.0.2 that FLUX/FastWan/mediapipe require. So
# /lipsync shells out to /opt/latentsync-venv/bin/python via the LATENTSYNC_CMD template.
# Weights (UNet, whisper-tiny, sd-vae-ft-mse) are vendored to the read-only /models mount.
# This layer is placed before `COPY main.py` so app edits don't rebust the heavy venv cache.
# ============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential curl unzip \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv (NO --system-site-packages: must not see this image's numpy 2), with its
# own torch 2.7.1+cu126 (works on the L4 / sm_89; the repo's 2.5.1 pin is unnecessary).
RUN python -m venv /opt/latentsync-venv \
    && /opt/latentsync-venv/bin/pip install --no-cache-dir -U pip \
    && /opt/latentsync-venv/bin/pip install --no-cache-dir \
         torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu126

# Repo (pinned) holds scripts/, latentsync/, configs/ — inference runs from its root.
RUN git clone https://github.com/bytedance/LatentSync /opt/latentsync-venv/repo \
    && cd /opt/latentsync-venv/repo \
    && git checkout a229c3948406bc2cf6eaf4873e662e70c6a04746

# Install the repo's pinned deps WITHOUT downgrading torch. Strip: decord (no cp311 wheel ->
# eva-decord below), gradio (unused), insightface (built separately below with --no-deps so its
# deps can't shadow opencv-headless / fight onnxruntime-gpu). KEEP onnxruntime-gpu (insightface
# face detection runs on it). numpy stays 1.26.4 (the isolation goal).
RUN cd /opt/latentsync-venv/repo \
    && sed -i -E '/^(torch|torchvision)([=<> ]|$)/d; /download\.pytorch\.org\/whl\/cu121/d; /--extra-index-url/d; /^insightface/d; /^gradio/d; /^decord/d' requirements.txt \
    && /opt/latentsync-venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /opt/latentsync-venv/bin/pip install --no-cache-dir eva-decord==0.6.1

# Point the runtime VAE load at the pre-baked local dir (image is HF_HUB_OFFLINE=1).
RUN cd /opt/latentsync-venv/repo \
    && grep -rl "stabilityai/sd-vae-ft-mse" . \
       | xargs -r sed -i "s#stabilityai/sd-vae-ft-mse#/models/latentsync/checkpoints/sd-vae-ft-mse#g"

# whisper is read from the literal relative 'checkpoints/whisper/tiny.pt' -> symlink it to
# the read-only mount (dangling at build; resolves at runtime when /models is attached).
RUN mkdir -p /opt/latentsync-venv/repo/checkpoints \
    && ln -sfn /models/latentsync/checkpoints/whisper /opt/latentsync-venv/repo/checkpoints/whisper

# LatentSync's INFERENCE face detector (latentsync/utils/face_detector.py) uses insightface's
# FaceAnalysis (detection + landmark_2d_106) — it IS on the inference path. Build under the venv's
# numpy<2 (--no-build-isolation so its old setup.py sees the installed numpy+cython); --no-deps so
# it can't pull opencv-python (would shadow opencv-headless -> libGL crash) or CPU onnxruntime
# (would fight onnxruntime-gpu). Add only the pure deps FaceAnalysis needs.
# wheel+setuptools must be in the venv: --no-build-isolation builds insightface here, and its
# setup.py needs bdist_wheel (cython compiles mesh_core_cython fine; only wheel-packaging was missing).
RUN /opt/latentsync-venv/bin/pip install --no-cache-dir cython wheel setuptools \
    && /opt/latentsync-venv/bin/pip install --no-cache-dir --no-build-isolation --no-deps insightface==0.7.3 \
    && /opt/latentsync-venv/bin/pip install --no-cache-dir onnx easydict prettytable scikit-learn \
    && sed -i '/from .mask_renderer import/d' /opt/latentsync-venv/lib/python3.11/site-packages/insightface/app/__init__.py

# Degrade gracefully if the CUDA execution provider can't init (don't crash the render).
RUN sed -i 's/providers=\["CUDAExecutionProvider"\]/providers=["CUDAExecutionProvider", "CPUExecutionProvider"]/' \
    /opt/latentsync-venv/repo/latentsync/utils/face_detector.py

# insightface buffalo_l pack (det_10g + 2d106det) at root="checkpoints/auxiliary" -> models/buffalo_l.
# Pre-baked at build (egress available) so there is NO runtime download against the read-only mount.
RUN mkdir -p /tmp/bl /opt/latentsync-venv/repo/checkpoints/auxiliary/models/buffalo_l \
    && curl -fsSL -o /tmp/buffalo_l.zip https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip \
    && unzip -oq /tmp/buffalo_l.zip -d /tmp/bl \
    && if [ -d /tmp/bl/buffalo_l ]; then cp /tmp/bl/buffalo_l/*.onnx /opt/latentsync-venv/repo/checkpoints/auxiliary/models/buffalo_l/; else cp /tmp/bl/*.onnx /opt/latentsync-venv/repo/checkpoints/auxiliary/models/buffalo_l/; fi \
    && rm -rf /tmp/bl /tmp/buffalo_l.zip \
    && ls -la /opt/latentsync-venv/repo/checkpoints/auxiliary/models/buffalo_l

# SyncNet LSE-C eval weights (the /syncscore quality metric) — symlink to the read-only mount.
# syncnet_v2.model + sfd_face.pth are vendored under .../auxiliary; buffalo_l stays baked alongside.
RUN ln -sfn /models/latentsync/checkpoints/auxiliary/syncnet_v2.model /opt/latentsync-venv/repo/checkpoints/auxiliary/syncnet_v2.model \
    && ln -sfn /models/latentsync/checkpoints/auxiliary/sfd_face.pth /opt/latentsync-venv/repo/checkpoints/auxiliary/sfd_face.pth

# Build-time venv health check (free, no GPU): the inference risky-imports (decord under numpy<2,
# diffusers AutoencoderKL+DDIMScheduler, insightface) AND the eval chain (SyncNet LSE-C scorer).
# Prints LS_DEPS_OK / EVAL_IMPORTS_OK so a broken venv is caught here, never on a paid render.
RUN /opt/latentsync-venv/bin/python -c "import numpy,torch,diffusers,decord,omegaconf,einops,librosa,insightface; from diffusers import AutoencoderKL,DDIMScheduler; from insightface.app import FaceAnalysis; print('LS_DEPS_OK numpy=%s torch=%s diffusers=%s insightface=%s' % (numpy.__version__, torch.__version__, diffusers.__version__, insightface.__version__))" \
    && cd /opt/latentsync-venv/repo && /opt/latentsync-venv/bin/python -c "from eval.syncnet import SyncNetEval; from eval.syncnet_detect import SyncNetDetector; print('EVAL_IMPORTS_OK')"

COPY main.py .

# Weights are NOT in this image: a GCS FUSE volume mounts at /models (MODELS_DIR).
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
