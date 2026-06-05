"""Subprocess wrapper around ffmpeg with hardware-encoder validation + fallback.

Why a class and not bare ``subprocess.run`` calls: every render path needs the
SAME behaviour — capture stderr, raise a typed :class:`FFmpegError` with the
command attached, and (critically) pick a *working* encoder rather than one that
merely appears in ``-encoders``. Presence in the encoder list does NOT mean the
GPU/driver can actually use it, so we validate with a 1-frame smoke encode and
cache the first encoder that survives. This is the mechanism behind §5's
"fallback to software rendering gracefully without crashing".
"""

from __future__ import annotations

import shutil
import subprocess

from cadence.errors import DependencyError, FFmpegError


class FFmpeg:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self._encoders: frozenset[str] | None = None
        self._ensure_present()

    def _ensure_present(self) -> None:
        if shutil.which(self.ffmpeg_bin) is None:
            raise DependencyError(
                f"ffmpeg binary {self.ffmpeg_bin!r} not found on PATH. Install FFmpeg 8.x."
            )
        if shutil.which(self.ffprobe_bin) is None:
            raise DependencyError(
                f"ffprobe binary {self.ffprobe_bin!r} not found on PATH. Install FFmpeg 8.x."
            )

    # -- low-level execution ------------------------------------------------ #
    def run(
        self,
        args: list[str],
        *,
        timeout: float = 600.0,
        input_bytes: bytes | None = None,
        capture_stdout: bool = False,
    ) -> bytes:
        """Run ``ffmpeg <args>``; raise :class:`FFmpegError` on non-zero exit.

        Returns captured stdout bytes when ``capture_stdout`` is set (used for
        raw-frame piping), else ``b""``.
        """
        cmd = [self.ffmpeg_bin, "-hide_banner", "-nostdin", *args]
        try:
            proc = subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing dependent
            raise FFmpegError(f"ffmpeg timed out after {timeout}s", command=cmd) from exc
        if proc.returncode != 0:
            raise FFmpegError(
                f"ffmpeg exited with code {proc.returncode}",
                command=cmd,
                stderr=proc.stderr.decode("utf-8", "replace"),
            )
        return proc.stdout or b""

    def probe_raw(self, args: list[str], *, timeout: float = 60.0) -> str:
        """Run ffprobe and return stdout text."""
        cmd = [self.ffprobe_bin, "-hide_banner", *args]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if proc.returncode != 0:
            raise FFmpegError(
                f"ffprobe exited with code {proc.returncode}",
                command=cmd,
                stderr=proc.stderr.decode("utf-8", "replace"),
            )
        return proc.stdout.decode("utf-8", "replace")

    # -- encoder discovery + validation ------------------------------------ #
    def available_encoders(self) -> frozenset[str]:
        # Lazily cached on the instance (NOT lru_cache on the bound method, which
        # would pin the instance and thrash at maxsize=1 across instances).
        if self._encoders is not None:
            return self._encoders
        proc = subprocess.run(
            [self.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if proc.returncode != 0:
            raise FFmpegError(
                "ffmpeg -encoders failed",
                command=[self.ffmpeg_bin, "-encoders"],
                stderr=proc.stderr.decode("utf-8", "replace"),
            )
        text = proc.stdout.decode("utf-8", "replace")
        names: set[str] = set()
        for line in text.splitlines():
            parts = line.split()
            # Encoder lines look like: " V....D h264_nvenc   NVIDIA ..."
            if len(parts) >= 2 and parts[0][:1] in {"V", "A", "S"} and "." in parts[0]:
                names.add(parts[1])
        self._encoders = frozenset(names)
        return self._encoders

    def has_encoder(self, name: str) -> bool:
        return name in self.available_encoders()

    def encoder_smoke_test(self, name: str, *, timeout: float = 30.0) -> bool:
        """Validate an encoder actually runs on this machine via a 1-frame encode.

        This catches the common case where e.g. ``h264_nvenc`` is compiled in but
        no NVIDIA GPU/driver is present, so the real render would fail.
        """
        if not self.has_encoder(name):
            return False
        args = [
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1:r=1",
            "-frames:v", "1", "-c:v", name, "-f", "null", "-",
        ]
        try:
            self.run(args, timeout=timeout)
            return True
        except FFmpegError:
            return False

    def working_video_encoder(
        self,
        priority: tuple[str, ...],
        software: str,
        *,
        prefer_hardware: bool = True,
    ) -> tuple[str, bool]:
        """Return ``(encoder_name, used_hardware)`` — the first encoder that both
        exists and passes a smoke test, falling back to the software encoder.
        """
        if prefer_hardware:
            for name in priority:
                if self.encoder_smoke_test(name):
                    return name, True
        if self.encoder_smoke_test(software) or self.has_encoder(software):
            return software, False
        raise DependencyError(
            f"No usable video encoder found (tried {list(priority)} then {software!r})."
        )
