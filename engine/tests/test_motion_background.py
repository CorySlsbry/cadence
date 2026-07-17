"""REAL-ffmpeg proof that motion scenes never loop and never reverse.

The shipped defect: a ~2s motion clip was stretched over a ~7s scene window by looping a
forward+reverse PALINDROME pre-pass, so the subject walked up, then walked backward, then
forward again ("make it cohesive, not just make the video go in reverse"). The fix generates
clips that cover their window and holds the LAST FRAME if one still falls short.

These tests render with the real ffmpeg binary, then DECODE the result and measure it, so they
prove behaviour rather than filter-string shape. The probe signal is a clip whose frames carry a
monotonically increasing brightness ramp: if the output ever gets DARKER, time ran backwards
(a reverse) or restarted (a loop). Uniform-luma frames are used deliberately — the Ken-Burns
scale/crop cannot change the mean luma of a flat frame, so the signal survives compositing.

The old palindrome/-stream_loop code fails these: its luma would ramp up, then back down.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

import numpy as np
import pytest

from cadence.matte.replace import build_background_video_mixed

FPS = 30
# Codec + chroma-interpolation wobble on a flat frame is well under a luma level; anything
# larger than this is a real decrease (a reversal drops tens of levels).
_MONOTONIC_EPS = 1.5


@dataclass
class _Ins:
    image_path: str
    start: float
    end: float = 0.0


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg binary not available")


def _ramp_clip(path: str, seconds: float, lo: int, hi: int) -> str:
    """A clip of flat gray frames whose luma ramps LINEARLY from ``lo`` to ``hi``.

    Time is legible in the pixels: frame brightness is a strictly increasing function of time,
    so any decrease downstream means the frame order was disturbed. ``geq`` exposes time as
    uppercase ``T``. Decoding applies a limited->full range expansion (~(v-16)*255/219), which
    is linear and monotonic, so the measured values are scaled but the ordering is untouched.
    """
    slope = (hi - lo) / seconds
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=black:s=128x228:d={seconds}:r={FPS}",
         "-vf", f"geq=lum='clip({lo}+{slope:.4f}*T,0,255)':cb=128:cr=128",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
         "-pix_fmt", "yuv420p", path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    return path


def _still_png(path: str, level: int = 90) -> str:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=gray@1.0:s=128x228:d=1",
         "-vf", f"geq=lum={level}:cb=128:cr=128", "-frames:v", "1", path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    return path


def _frame_luma(path: str) -> np.ndarray:
    """Mean luma per decoded frame — the probe signal, read back out of the real output."""
    w, h = 32, 56
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", path,
         "-vf", f"scale={w}:{h}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    n = len(raw) // (w * h)
    assert n > 0, "decoded no frames"
    return np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, w * h).mean(axis=1)


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()
    return float(out)


def _assert_monotonic(luma: np.ndarray, what: str) -> None:
    drops = np.diff(luma)
    worst = float(drops.min()) if len(drops) else 0.0
    assert worst > -_MONOTONIC_EPS, (
        f"{what}: brightness DECREASED by {-worst:.2f} levels — the clip looped or played "
        f"backwards. Signal head={luma[:5].round(1).tolist()} tail={luma[-5:].round(1).tolist()}"
    )


# --------------------------------------------------------------------------- #
# The boomerang proof
# --------------------------------------------------------------------------- #
def test_clip_shorter_than_window_never_reverses_and_holds_last_frame(tmp_path):
    """A 2s clip in a 6s window (n==1): monotonic, then a HELD last frame — no boomerang."""
    clip = _ramp_clip(str(tmp_path / "clip.mp4"), 2.0, 20, 200)
    ins = _Ins(_still_png(str(tmp_path / "s0.png")), 0.0, 6.0)
    out = str(tmp_path / "bg.mp4")

    build_background_video_mixed([(ins, clip)], 6.0, out, width=128, height=228, fps=FPS)

    luma = _frame_luma(out)
    _assert_monotonic(luma, "single motion scene, clip shorter than window")
    # The tail must HOLD the clip's final frame (a held shot), not loop back to its first.
    assert luma[-1] > 150, f"tail should hold the bright end frame, got {luma[-1]:.1f}"
    assert luma[0] < 60, f"head should start at the clip's dark first frame, got {luma[0]:.1f}"
    # Last third is the frozen tail: flat, and never dipping back toward the clip's start.
    tail = luma[int(len(luma) * 0.66):]
    assert float(tail.max() - tail.min()) < 4.0, "held tail should be visually static"
    assert abs(_duration(out) - 6.0) < 0.12, f"duration drifted: {_duration(out):.3f}"


def test_multi_scene_motion_is_monotonic_and_exactly_duration(tmp_path):
    """Two motion scenes, each clip shorter than its window, joined by the xfade chain.

    Scene 2's ramp CONTINUES scene 1's (100->220 after 20->100), so a correct render is
    monotonic end-to-end THROUGH the crossfade, while any loop/reverse shows up as a dip.
    """
    c0 = _ramp_clip(str(tmp_path / "c0.mp4"), 2.0, 20, 100)
    c1 = _ramp_clip(str(tmp_path / "c1.mp4"), 2.0, 100, 220)
    i0 = _Ins(_still_png(str(tmp_path / "a.png")), 0.0, 5.0)
    i1 = _Ins(_still_png(str(tmp_path / "b.png")), 5.0, 10.0)
    out = str(tmp_path / "bg2.mp4")

    build_background_video_mixed([(i0, c0), (i1, c1)], 10.0, out,
                                 width=128, height=228, fps=FPS)

    _assert_monotonic(_frame_luma(out), "two motion scenes across an xfade")
    # The xfade math must still land the background EXACTLY on `duration` — the narration
    # is synced to it, so overlap compensation drifting would desync the whole video.
    assert abs(_duration(out) - 10.0) < 0.12, f"duration drifted: {_duration(out):.3f}"


def test_clip_longer_than_window_is_trimmed_not_stretched(tmp_path):
    """A clip longer than its window is cut to the window — still forward, still exact."""
    clip = _ramp_clip(str(tmp_path / "long.mp4"), 6.0, 20, 220)
    ins = _Ins(_still_png(str(tmp_path / "s.png")), 0.0, 3.0)
    out = str(tmp_path / "bg3.mp4")

    build_background_video_mixed([(ins, clip)], 3.0, out, width=128, height=228, fps=FPS)

    luma = _frame_luma(out)
    _assert_monotonic(luma, "clip longer than window")
    # Trimmed at ~3s of a 6s ramp -> ends near the ramp's midpoint, nowhere near its end.
    assert luma[-1] < 160, f"expected a trim near the ramp midpoint, got {luma[-1]:.1f}"
    assert abs(_duration(out) - 3.0) < 0.12, f"duration drifted: {_duration(out):.3f}"


def test_mixed_motion_and_still_scenes_hold_exact_duration(tmp_path):
    """A degraded (still) scene beside a motion scene: the stills branch still works."""
    clip = _ramp_clip(str(tmp_path / "m.mp4"), 2.0, 20, 200)
    i0 = _Ins(_still_png(str(tmp_path / "x.png")), 0.0, 4.0)
    i1 = _Ins(_still_png(str(tmp_path / "y.png"), level=120), 4.0, 9.0)
    out = str(tmp_path / "bg4.mp4")

    # scene 0 animates, scene 1 degraded to its still (clip=None)
    build_background_video_mixed([(i0, clip), (i1, None)], 9.0, out,
                                 width=128, height=228, fps=FPS)

    assert os.path.exists(out)
    assert abs(_duration(out) - 9.0) < 0.12, f"duration drifted: {_duration(out):.3f}"


# --------------------------------------------------------------------------- #
# Graph-shape guards — the reversal must not creep back in via a refactor
# --------------------------------------------------------------------------- #
def test_graph_never_loops_or_reverses_motion_clips(tmp_path, monkeypatch):
    """Assert on the actual ffmpeg argv: no -stream_loop, no reverse, and a held tail."""
    captured: list[list[str]] = []

    class _FakeFF:
        def run(self, args, timeout=None):
            captured.append(list(args))

    clip = str(tmp_path / "c.mp4")
    open(clip, "wb").close()
    i0 = _Ins("a.png", 0.0, 5.0)
    i1 = _Ins("b.png", 5.0, 10.0)

    build_background_video_mixed([(i0, clip), (i1, None)], 10.0, str(tmp_path / "o.mp4"),
                                 ff=_FakeFF(), width=1080, height=1920, fps=30)

    # Exactly ONE ffmpeg invocation: the palindrome pre-pass (a second render per clip) is gone.
    assert len(captured) == 1, f"expected a single render, got {len(captured)} ffmpeg calls"
    argv = captured[0]
    joined = " ".join(argv)
    assert "-stream_loop" not in argv, "motion clips must play ONCE — no -stream_loop"
    assert "reverse" not in joined, "no reversal anywhere, ever"
    assert "_pp.mp4" not in joined, "the palindrome pre-pass must be gone"
    graph = argv[argv.index("-filter_complex") + 1]
    # A short clip holds its LAST frame instead of looping.
    assert "tpad=stop_mode=clone" in graph, "a short clip must hold its last frame"
    # Ken-Burns runs on the MOTION segment too, not just the stills branch.
    assert graph.count("eval=frame") == 2, "both segments need the continuous push"
    assert "format=yuv420p,settb=AVTB" in graph  # preserved for the xfade chain
    assert "xfade=transition=fade" in graph      # crossfade chain preserved
