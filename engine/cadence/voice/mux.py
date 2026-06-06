"""Mux a synthesized voiceover onto a rendered clip (video-follows-voice).

Output length = the voiceover length: the visuals loop if shorter and are trimmed if
longer, and the original audio is replaced by the VO. Used by the hidden voiceover mode.
"""

from __future__ import annotations

from cadence.ffmpeg.runner import FFmpeg


def _audio_duration(ff: FFmpeg, path: str) -> float:
    out = ff.probe_raw(
        ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path]
    ).strip()
    return float(out) if out else 0.0


def build_voiceover_args(video_path: str, vo_path: str, out_path: str, duration: float, *, crf: int = 18) -> list[str]:
    """The ffmpeg argv: loop the visuals to fill the VO, take audio from the VO, cap to
    the VO duration. Pure (no I/O) so it's unit-testable."""
    return [
        "-y",
        "-stream_loop", "-1", "-i", video_path,  # loop visuals to cover the VO
        "-i", vo_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        out_path,
    ]


def mux_voiceover(video_path: str, vo_path: str, out_path: str, *, ff: FFmpeg | None = None) -> str:
    ff = ff or FFmpeg()
    dur = _audio_duration(ff, vo_path)
    if dur <= 0:
        raise ValueError(f"voiceover has non-positive duration: {vo_path}")
    ff.run(build_voiceover_args(video_path, vo_path, out_path, dur), timeout=900)
    return out_path
