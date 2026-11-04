"""Bake ML models into the worker image at build time.

Cloud Run instances are stateless and scale to zero, so any model downloaded at
runtime would be re-fetched on every cold start. Running this during `docker build`
pulls them into the image instead: the faster-whisper weights (into HF_HOME) and the
MediaPipe selfie-segmenter .tflite (into ~/.cache/cadence, where the matte module
looks). Build runs as root, and the worker runs as root, so the cache paths match.
"""

from __future__ import annotations

import os


def main() -> None:
    model = os.environ.get("CADENCE_WHISPER_MODEL", "base.en")
    print(f"prefetch: faster-whisper '{model}' -> {os.environ.get('HF_HOME')}", flush=True)
    from faster_whisper import WhisperModel

    WhisperModel(model, device="cpu", compute_type="int8")

    print("prefetch: mediapipe selfie segmenter", flush=True)
    from cadence.matte.replace import _ensure_model

    path = _ensure_model()
    print(f"prefetch: done (segmenter at {path})", flush=True)


if __name__ == "__main__":
    main()
