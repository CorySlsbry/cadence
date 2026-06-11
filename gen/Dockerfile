# cadence-gen: self-hosted generation on Cloud Run GPU (1x NVIDIA L4).
# Cloud Run L4 hosts run driver 535.x (CUDA 12.2): cu12.8 wheels work via the
# forward-compatibility package (cuda-compat-12-8) per Google's GPU docs.
FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/usr/local/cuda/compat:/usr/local/cuda/lib64:$LD_LIBRARY_PATH \
    HF_HUB_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.11 python3.11-venv python3-pip ffmpeg espeak-ng cuda-compat-12-8 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3.11 -m pip install --no-cache-dir --upgrade pip && \
    python3.11 -m pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Weights are NOT in this image: a GCS FUSE volume mounts at /models (MODELS_DIR).
EXPOSE 8080
CMD ["python3.11", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
