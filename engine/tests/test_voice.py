"""Unit tests for the voiceover blend orchestration (no network — TTS/STS are stubbed)."""

from __future__ import annotations

import urllib.error

import pytest

from cadence.voice import VoiceError, VoiceSynth, build_voiceover_args
from cadence.voice import synth as synth_mod


class _StubTTS:
    def __init__(self) -> None:
        self.seen: str | None = None

    def synth(self, text: str) -> bytes:
        self.seen = text
        return b"WAVDATA"


class _StubSTS:
    def __init__(self) -> None:
        self.seen: bytes | None = None

    def convert(self, wav: bytes) -> bytes:
        self.seen = wav
        return b"MP3DATA"


def test_blend_pipes_tts_output_into_sts():
    tts, sts = _StubTTS(), _StubSTS()
    out = VoiceSynth(tts, sts).blend("Hello there")
    assert out == b"MP3DATA"
    assert tts.seen == "Hello there"
    assert sts.seen == b"WAVDATA"  # the WAV from TTS is exactly what STS converts


def test_blend_collapses_whitespace_before_synthesis():
    tts, sts = _StubTTS(), _StubSTS()
    VoiceSynth(tts, sts).blend("  one\n  two\t three  ")
    assert tts.seen == "one two three"


def test_blend_rejects_empty_text():
    with pytest.raises(VoiceError):
        VoiceSynth(_StubTTS(), _StubSTS()).blend("   \n  ")


def test_voiceover_args_loop_video_take_vo_audio_and_cap_to_vo_length():
    args = build_voiceover_args("vid.mp4", "vo.mp3", "out.mp4", 18.9)
    assert args[:3] == ["-y", "-stream_loop", "-1"]      # loop the visuals to cover the VO
    assert args[args.index("-t") + 1] == "18.900"        # output length = VO length
    assert "0:v:0" in args and "1:a:0" in args           # video from input 0, audio from the VO (input 1)
    assert args.index("0:v:0") < args.index("1:a:0")     # video mapped before audio
    assert args[-1] == "out.mp4"


def test_read_url_raises_immediately_on_4xx_without_retry(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, _Fp(b"nope"))

    monkeypatch.setattr(synth_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(VoiceError):
        synth_mod._read_url(synth_mod.urllib.request.Request("https://x"), retries=3)
    assert calls["n"] == 1  # 4xx is fatal — no retry storm


def test_read_url_retries_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, _Fp(b"retry"))
        return _Ctx(b"OK")

    monkeypatch.setattr(synth_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(synth_mod.urllib.request, "urlopen", fake_urlopen)
    out = synth_mod._read_url(synth_mod.urllib.request.Request("https://x"), retries=3)
    assert out == b"OK" and calls["n"] == 3


class _Fp:
    def __init__(self, data: bytes) -> None:
        self._d = data

    def read(self) -> bytes:
        return self._d

    def close(self) -> None:  # HTTPError holds this as its fp and closes it on GC
        pass


class _Ctx:
    def __init__(self, data: bytes) -> None:
        self._d = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self) -> bytes:
        return self._d
