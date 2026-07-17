# cadence-gen-premium: Wan 2.2 I2V-A14B batch renderer on Cloud Run JOBS
# (1x NVIDIA RTX PRO 6000 Blackwell 96GB, us-central1).
# Base = torch 2.8.0 + CUDA 12.8 (cu128 wheels carry native sm_120/Blackwell kernels —
# the L4 image's cu126 does NOT). Weights are NOT in this image: GCS FUSE mounts at /models.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Cloud Run JOB: runs to completion, no port.
ENTRYPOINT ["python", "main.py"]
