"""Shared pytest fixtures. Real synthetic media is generated once per session."""

from __future__ import annotations

import os

import pytest

from cadence.ffmpeg.runner import FFmpeg
from tests import fixtures


@pytest.fixture(scope="session")
def ff() -> FFmpeg:
    return FFmpeg()


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> str:
    return str(tmp_path_factory.mktemp("cadence_media"))


@pytest.fixture(scope="session")
def reference_video(ff: FFmpeg, media_dir: str) -> str:
    out = os.path.join(media_dir, "reference.mp4")
    fixtures.make_reference_video(ff, out, tmp_dir=media_dir)
    return out


@pytest.fixture(scope="session")
def talking_clip(ff: FFmpeg, media_dir: str) -> str:
    out = os.path.join(media_dir, "aroll.mp4")
    fixtures.make_talking_clip(ff, out)
    return out


@pytest.fixture(scope="session")
def logo_png(media_dir: str) -> str:
    out = os.path.join(media_dir, "logo.png")
    fixtures.make_logo_png(out)
    return out
