"""Human-sounding voiceover in a cloned voice — THE BLEND.

Pipeline: text -> Gemini "Charon" TTS (best *flow*) -> ElevenLabs Speech-to-Speech into
the clone (swaps *timbre* to the owner, keeps Charon's cadence). Adapted verbatim from the
validated cory-voice recipe (2026-06-05). Keys come from the environment so it runs on
Cloud Run (GEMINI_API_KEY + ELEVENLABS_API_KEY as secrets); HTTP is stdlib urllib to keep
the engine dependency-light. The TTS + STS steps are injected, so ``VoiceSynth.blend`` is
fully unit-testable with stubs (no network).

INTERNAL: wired for the owner's voice only and gated behind an admin flag — not exposed
to platform users.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
import uuid
import wave
from typing import Protocol

from cadence.errors import DependencyError

# Defaults from the validated recipe (override per-voice if ever generalized).
CORY_VOICE_ID = "3JjargZRw9ecYaHWSzUq"
GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_VOICE = "Charon"
GEMINI_STYLE = "Read in a warm, confident, conversational male voice, like a friendly expert narrator:"
STS_MODEL = "eleven_multilingual_sts_v2"
STS_SETTINGS = {"stability": 0.4, "similarity_boost": 0.85, "style": 0.0, "use_speaker_boost": True}
EL_FORMAT = "mp3_44100_192"


class VoiceError(Exception):
    """Raised on a voice-synthesis API failure."""


def _read_url(req: urllib.request.Request, *, timeout: int = 180, retries: int = 3) -> bytes:
    """HTTP with retry+backoff — long STS/TTS reads occasionally time out or 5xx."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:  # client error — won't fix on retry
                raise VoiceError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}") from e
            last = e
        except (urllib.error.URLError, TimeoutError) as e:  # noqa: PERF203
            last = e
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))
    raise VoiceError(f"request failed after {retries} retries: {last}")


class TTS(Protocol):
    def synth(self, text: str) -> bytes: ...  # -> WAV bytes


class STS(Protocol):
    def convert(self, wav: bytes) -> bytes: ...  # -> MP3 bytes


class GeminiCharonTTS:
    """Gemini native TTS (Charon voice) -> mono 16-bit WAV bytes."""

    def __init__(self, api_key: str | None = None, *, model: str = GEMINI_TTS_MODEL,
                 voice: str = GEMINI_VOICE, style: str = GEMINI_STYLE) -> None:
        self.key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.key:
            raise DependencyError("GEMINI_API_KEY not set for voice synthesis.")
        self.model, self.voice, self.style = model, voice, style

    def synth(self, text: str) -> bytes:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}"
        body = json.dumps({
            "contents": [{"parts": [{"text": f"{self.style} {text}"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice}}},
            },
        }).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        d = json.loads(_read_url(req))
        part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(part["data"])
        rate = 24000
        if "rate=" in part.get("mimeType", ""):
            try:
                rate = int(part["mimeType"].split("rate=")[1].split(";")[0])
            except (ValueError, IndexError):
                pass
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
        return buf.getvalue()


class ElevenLabsSTS:
    """ElevenLabs Speech-to-Speech (Voice Changer): WAV -> the clone -> MP3 bytes."""

    def __init__(self, api_key: str | None = None, *, voice_id: str = CORY_VOICE_ID,
                 model: str = STS_MODEL, settings: dict | None = None, fmt: str = EL_FORMAT) -> None:
        self.key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self.key:
            raise DependencyError("ELEVENLABS_API_KEY not set for voice synthesis.")
        self.voice_id, self.model, self.settings, self.fmt = voice_id, model, settings or dict(STS_SETTINGS), fmt

    def convert(self, wav: bytes) -> bytes:
        boundary = uuid.uuid4().hex
        buf = bytearray()
        for k, v in {"model_id": self.model, "voice_settings": json.dumps(self.settings)}.items():
            buf += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        buf += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="src.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode() + wav + b"\r\n"
        buf += f"--{boundary}--\r\n".encode()
        url = f"https://api.elevenlabs.io/v1/speech-to-speech/{self.voice_id}?output_format={self.fmt}"
        req = urllib.request.Request(url, data=bytes(buf), method="POST", headers={
            "xi-api-key": self.key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "audio/mpeg",
        })
        return _read_url(req)


class VoiceSynth:
    """The blend: ``blend(text)`` -> MP3 bytes in the cloned voice."""

    def __init__(self, tts: TTS | None = None, sts: STS | None = None) -> None:
        self._tts = tts or GeminiCharonTTS()
        self._sts = sts or ElevenLabsSTS()

    def blend(self, text: str) -> bytes:
        text = " ".join((text or "").split())
        if not text:
            raise VoiceError("empty narration text")
        return self._sts.convert(self._tts.synth(text))

    def blend_to_file(self, text: str, out_path: str) -> str:
        with open(out_path, "wb") as fh:
            fh.write(self.blend(text))
        return out_path
