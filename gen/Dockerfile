# cadence-gen: self-hosted generation on Cloud Run GPU (1x NVIDIA L4).
# Cloud Run L4 hosts run driver 535.x (CUDA 12.2): cu12.8 wheels work via the
# forward-compatibility package (cuda-compat-12-8) per Google's GPU docs.
FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/usr/local/cuda/compat:/usr/local/cuda/lib64:$LD_LIBRARY_PATH \
    HF_HUB_OFFLINE=1

# Ubuntu 22.04's apt python3.11 is the broken 3.11.0rc1 — use deadsnakes for a real 3.11.x.
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
      python3.11 python3.11-venv python3.11-distutils curl ffmpeg espeak-ng cuda-compat-12-8 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# torch FIRST and EXCLUSIVELY from the cu128 index (--index-url, not --extra-index-url:
# otherwise pip resolves PyPI's default cu13x wheel, which the L4 driver rejects).
RUN python3.11 -m pip install --no-cache-dir --upgrade pip && \
    python3.11 -m pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128 && \
    python3.11 -m pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Weights are NOT in this image: a GCS FUSE volume mounts at /models (MODELS_DIR).
EXPOSE 8080
CMD ["python3.11", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
