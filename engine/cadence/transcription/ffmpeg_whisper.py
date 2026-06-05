"""Zero-pip transcriber using FFmpeg's built-in whisper.cpp filter.

This engine's FFmpeg build ships ``--enable-whisper``, so transcription needs no
Python ML deps at all — only a ggml model file. Word timing is approximated by
distributing each transcribed segment evenly across its duration (segment-level,
coarser than faster-whisper's true word timestamps, but real and dependency-free).
"""

from __future__ import annotations

import json
import os
import tempfile

from cadence.errors import DependencyError, TranscriptionError
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Transcript, Word


def _hms_to_seconds(value: str) -> float:
    # "HH:MM:SS,mmm" or "HH:MM:SS.mmm"
    value = value.replace(",", ".")
    parts = value.split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return h * 3600 + m * 60 + s


def _parse_segments(data: object) -> list[tuple[float, float, str]]:
    """Normalize the various whisper JSON shapes into (start, end, text) seconds."""
    segments: list[tuple[float, float, str]] = []
    items: list = []
    if isinstance(data, dict):
        for key in ("transcription", "segments", "result"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    elif isinstance(data, list):
        items = data

    for it in items:
        if not isinstance(it, dict):
            continue
        text = (it.get("text") or it.get("transcription") or "").strip()
        if not text:
            continue
        start = end = None
        if "offsets" in it and isinstance(it["offsets"], dict):  # whisper.cpp ms offsets
            start = float(it["offsets"].get("from", 0)) / 1000.0
            end = float(it["offsets"].get("to", 0)) / 1000.0
        elif "timestamps" in it and isinstance(it["timestamps"], dict):
            start = _hms_to_seconds(str(it["timestamps"].get("from", "0")))
            end = _hms_to_seconds(str(it["timestamps"].get("to", "0")))
        elif "start" in it and "end" in it:
            start, end = float(it["start"]), float(it["end"])
        if start is None or end is None or end < start:
            continue
        segments.append((start, end, text))
    return segments


def _segments_to_words(segments: list[tuple[float, float, str]]) -> list[Word]:
    words: list[Word] = []
    for start, end, text in segments:
        tokens = text.split()
        if not tokens:
            continue
        span = max(end - start, 1e-3)
        step = span / len(tokens)
        for i, tok in enumerate(tokens):
            ws = start + i * step
            words.append(Word(text=tok, start=round(ws, 3), end=round(ws + step, 3), prob=1.0))
    return words


class FfmpegWhisperTranscriber:
    def __init__(self, model_path: str, *, language: str = "auto", queue: int = 10) -> None:
        if not os.path.isfile(model_path):
            raise DependencyError(
                f"whisper ggml model not found: {model_path}. Download e.g. ggml-base.en.bin "
                "from https://huggingface.co/ggerganov/whisper.cpp"
            )
        self._model_path = model_path
        self._language = language
        self._queue = queue

    def transcribe(self, path: str, *, ff: FFmpeg | None = None) -> Transcript:
        ff = ff or FFmpeg()
        if "whisper" not in _filter_names(ff):
            raise DependencyError("this ffmpeg build has no 'whisper' filter (needs --enable-whisper)")
        out_json = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        model = self._model_path.replace("\\", "/")
        dest = out_json.replace("\\", "/")
        af = (
            f"whisper=model={model}:language={self._language}"
            f":format=json:destination={dest}:queue={self._queue}"
        )
        try:
            ff.run(["-i", path, "-vn", "-af", af, "-f", "null", "-"], timeout=1800)
            with open(out_json, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            raise TranscriptionError(f"ffmpeg whisper failed on {path}: {exc}") from exc
        finally:
            try:
                os.unlink(out_json)
            except OSError:
                pass
        words = _segments_to_words(_parse_segments(data))
        return Transcript(words=tuple(words), language=self._language if self._language != "auto" else "en")


def _filter_names(ff: FFmpeg) -> set[str]:
    import subprocess

    proc = subprocess.run(
        [ff.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-filters"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    names: set[str] = set()
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            names.add(parts[1])
    return names
