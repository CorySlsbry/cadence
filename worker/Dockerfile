# syntax=docker/dockerfile:1
# Cadence render worker (Python + FFmpeg + faster-whisper + MediaPipe + Imagen).
# Build context: repo ROOT  ->  docker build -f worker/Dockerfile .

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models/hf \
    CADENCE_WHISPER_MODEL=medium.en

# ffmpeg (built with libx264 + libass on Debian) and the shared libs MediaPipe needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (pinned to the tested set) so this layer caches across code edits.
COPY worker/requirements.txt ./worker/requirements.txt
RUN pip install -r worker/requirements.txt

# Engine package — its deps are already satisfied above, so --no-deps keeps the
# resolved version set identical to what the test suite ran against.
COPY engine ./engine
RUN pip install --no-deps ./engine

# Worker source.
COPY worker ./worker

# Bake the ML models into the image so scale-to-zero cold starts never download them.
RUN python worker/prefetch_models.py

WORKDIR /app/worker
# Cloud Run injects $PORT (default 8080). Concurrency is pinned to 1 at deploy time
# (renders are CPU-bound — one per instance), and Scheduler drives /process.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
