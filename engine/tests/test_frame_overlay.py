"""apply_frame: composites a transparent PNG frame over a video, preserving audio."""

from __future__ import annotations

import os

import pytest
from PIL import Image, ImageDraw

from cadence.ffmpeg.runner import FFmpeg
from cadence.frame import apply_frame


@pytest.fixture(scope="module")
def ff() -> FFmpeg:
    try:
        return FFmpeg()
    except Exception:  # noqa: BLE001 - environment without ffmpeg
        pytest.skip("ffmpeg not on PATH")


def _tiny_inputs(tmp_path, ff: FFmpeg) -> tuple[str, str]:
    video = str(tmp_path / "in.mp4")
    ff.run([
        "-f", "lavfi", "-i", "testsrc=size=216x384:rate=12:duration=0.5",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", video,
    ])
    frame_png = str(tmp_path / "frame.png")
    img = Image.new("RGBA", (108, 192), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([0, 0, 107, 191], outline=(255, 0, 0, 255), width=8)
    img.save(frame_png)
    return video, frame_png


def test_apply_frame_outputs_video_with_audio(tmp_path, ff):
    video, frame_png = _tiny_inputs(tmp_path, ff)
    out = str(tmp_path / "framed.mp4")
    apply_frame(ff, video, frame_png, out)
    assert os.path.exists(out) and os.path.getsize(out) > 5_000
    # dimensions unchanged and the audio stream survived
    import json
    import subprocess

    probe = subprocess.run(
        [ff.ffprobe_bin, "-v", "error", "-show_streams", "-of", "json", out],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    kinds = {s["codec_type"] for s in streams}
    vid = next(s for s in streams if s["codec_type"] == "video")
    assert kinds == {"video", "audio"}
    assert (vid["width"], vid["height"]) == (216, 384)


def test_apply_frame_missing_frame_raises(tmp_path, ff):
    video, _ = _tiny_inputs(tmp_path, ff)
    with pytest.raises(FileNotFoundError):
        apply_frame(ff, video, str(tmp_path / "nope.png"), str(tmp_path / "o.mp4"))
