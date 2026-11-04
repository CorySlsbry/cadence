"""Tests for the self-host /lipsync client (cadence.avatar.lipsync)."""

from __future__ import annotations

import base64
import json
import urllib.request

import pytest

from cadence.avatar.lipsync import LipsyncClient, LipsyncResult
from cadence.imagegen.ledger import BudgetExceeded


class _Resp:
    def __init__(self, data: bytes) -> None:
        self._d = data

    def read(self) -> bytes:
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Ledger:
    def __init__(self, budget: float) -> None:
        self.budget = budget
        self.spent = 0.0

    def can_spend(self, c: float) -> bool:
        return self.spent + c <= self.budget

    def charge(self, c: float) -> None:
        self.spent += c


def test_posts_video_payload_strips_crlf_and_meters(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        captured["token"] = req.headers.get("X-gen-token")
        return _Resp(b"\x00" * 2000)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    led = _Ledger(1.0)
    client = LipsyncClient("https://gen.example.com/", "tok\r\n", ledger=led)
    out = client.synth(audio=b"AUD", reference=b"VID", is_video=True, fps=25, res=720)

    assert isinstance(out, LipsyncResult)
    assert len(out.video_bytes) == 2000
    assert captured["url"].endswith("/lipsync")
    assert captured["token"] == "tok"  # CRLF stripped (urllib rejects \r\n)
    assert captured["body"]["video_b64"] == base64.b64encode(b"VID").decode()
    assert captured["body"]["audio_b64"] == base64.b64encode(b"AUD").decode()
    assert "image_b64" not in captured["body"]
    assert led.spent == client.cost_per_render


def test_image_branch_sends_image_b64(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _Resp(b"x" * 2000)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    LipsyncClient("http://gen.test", "t").synth(audio=b"A", reference=b"IMG", is_video=False)
    assert "image_b64" in captured["body"] and "video_b64" not in captured["body"]


def test_budget_cap_raises_before_any_post(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not POST when over budget")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(BudgetExceeded):
        LipsyncClient("http://gen.test", "t", ledger=_Ledger(0.0)).synth(audio=b"A", reference=b"V", is_video=True)


def test_empty_video_raises_and_does_not_charge(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(b"tiny"))
    led = _Ledger(1.0)
    with pytest.raises(RuntimeError):
        LipsyncClient("http://gen.test", "t", ledger=led).synth(audio=b"A", reference=b"V", is_video=True)
    assert led.spent == 0.0


def test_fallback_used_on_gpu_error(monkeypatch):
    def boom(req, timeout=None):
        raise RuntimeError("gpu down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    class _FB:
        name = "hosted"

        def __init__(self) -> None:
            self.called = False

        def synth(self, **kw) -> LipsyncResult:
            self.called = True
            return LipsyncResult(b"H" * 2000, 0.1, "hosted")

    fb = _FB()
    out = LipsyncClient("http://gen.test", "t", fallback=fb).synth(audio=b"A", reference=b"V", is_video=True)
    assert fb.called and out.provider == "hosted"
