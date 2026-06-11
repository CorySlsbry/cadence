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

COPY main.py .

# Weights are NOT in this image: a GCS FUSE volume mounts at /models (MODELS_DIR).
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
