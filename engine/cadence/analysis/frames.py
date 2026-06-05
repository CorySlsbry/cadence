"""Decode video frames and audio into numpy arrays via ffmpeg raw pipes.

Frames are *streamed* (one at a time) for the dense transition pass so memory
stays bounded on long inputs; the sparse 1 fps colour pass materialises a small
list. Audio is decoded to mono float32 in [-1, 1].
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterator

import numpy as np

from cadence.errors import FFmpegError, InvalidMediaError
from cadence.ffmpeg.runner import FFmpeg


def iter_frames(
    path: str,
    *,
    fps: float,
    width: int,
    height: int,
    ff: FFmpeg | None = None,
) -> Iterator[np.ndarray]:
    """Yield successive RGB frames as ``(height, width, 3)`` uint8 arrays.

    Frames are resampled to ``fps`` and scaled to ``width``x``height`` by ffmpeg,
    then read off stdout one frame at a time.
    """
    ff = ff or FFmpeg()
    frame_size = width * height * 3
    cmd = [
        ff.ffmpeg_bin, "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", path,
        "-an",
        "-vf", f"fps={fps},scale={width}:{height}:flags=bilinear",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    # Drain stderr concurrently so a verbose ffmpeg (per-frame decode/DTS warnings on
    # a long or partially-corrupt input) cannot fill the OS pipe buffer and deadlock
    # the stdout frame loop. Without this, ffmpeg blocks on its stderr write, stops
    # producing frames, and the reader hangs forever.
    stderr_chunks: list[bytes] = []
    drainer = threading.Thread(target=_drain, args=(proc.stderr, stderr_chunks), daemon=True)
    drainer.start()
    interrupted = False
    try:
        while True:
            buf = _read_exact(proc.stdout, frame_size)
            if buf is None:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3)
    except GeneratorExit:
        interrupted = True
        raise
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.poll() is None:
            # Early break / consumer stopped: don't wait on a still-producing ffmpeg.
            if interrupted:
                proc.kill()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        drainer.join(timeout=5)
        code = proc.returncode
        if code not in (0, None) and not interrupted:
            text = b"".join(stderr_chunks).decode("utf-8", "replace")
            if "Error" in text or "Invalid" in text:
                raise FFmpegError(f"frame decode failed ({code})", command=cmd, stderr=text)


def _drain(stream, sink: list[bytes]) -> None:
    if stream is None:
        return
    try:
        for chunk in iter(lambda: stream.read(65536), b""):
            sink.append(chunk)
    except (ValueError, OSError):
        pass


def _read_exact(stream, n: int) -> bytes | None:
    """Read exactly ``n`` bytes; return None at clean EOF."""
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            return None if not chunks else b"".join(chunks).ljust(n, b"\x00")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def extract_frames(
    path: str,
    *,
    fps: float,
    width: int,
    height: int,
    ff: FFmpeg | None = None,
) -> np.ndarray:
    """Materialise all sampled frames into one ``(N, H, W, 3)`` uint8 array."""
    frames = list(iter_frames(path, fps=fps, width=width, height=height, ff=ff))
    if not frames:
        raise InvalidMediaError(f"no frames decoded from {path}")
    return np.stack(frames, axis=0)


def extract_audio(
    path: str,
    *,
    sample_rate: int = 16000,
    ff: FFmpeg | None = None,
) -> tuple[np.ndarray, int]:
    """Decode audio to mono float32 in [-1, 1]. Returns ``(samples, sample_rate)``.

    Returns an empty array when the input has no audio stream.
    """
    ff = ff or FFmpeg()
    cmd = [
        ff.ffmpeg_bin, "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", path,
        "-vn",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("audio decode timed out", command=cmd) from exc
    if proc.returncode != 0:
        text = proc.stderr.decode("utf-8", "replace")
        # No audio stream is not an error for our purposes.
        if "does not contain any stream" in text or "Output file does not contain" in text:
            return np.zeros(0, dtype=np.float32), sample_rate
        raise FFmpegError("audio decode failed", command=cmd, stderr=text)
    pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return pcm, sample_rate
