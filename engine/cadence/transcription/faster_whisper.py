"""faster-whisper adapter — the production transcriber (word-level timestamps).

Optional dependency: ``pip install "cadence-engine[ml]"``. faster-whisper uses
CTranslate2 (no PyTorch), so it installs light and runs on CPU (int8) or GPU.
"""

from __future__ import annotations

from cadence.errors import DependencyError, TranscriptionError
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Transcript, Word

# Biases the ASR toward the speaker's domain so it stops mishearing "Claude" as
# "cloud", "MCP" as "MTP", etc. Whisper conditions on `initial_prompt`; faster-whisper
# also supports `hotwords` for hard term-biasing.
DOMAIN_GLOSSARY = (
    "The speaker discusses Claude, Anthropic, Claude Code, Claude Cowork, MCP, AI agents, "
    "skills, prompts, Cursor, ChatGPT, OpenAI, GPT, Gemini, automation, and workflows."
)
DOMAIN_HOTWORDS = "Claude Anthropic Claude Code MCP Cowork Cursor Gemini"


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_size: str = "base",
        *,
        device: str = "auto",
        compute_type: str = "int8",
        language: str | None = None,
        vad_min_silence_ms: int = 400,
        beam_size: int = 5,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
    ) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise DependencyError(
                "faster-whisper is not installed. Install with: pip install 'cadence-engine[ml]'"
            ) from exc
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._language = language
        self._vad_min_silence_ms = vad_min_silence_ms
        self._beam_size = beam_size
        # Default to the domain glossary so "Claude" transcribes correctly out of the box.
        self._initial_prompt = DOMAIN_GLOSSARY if initial_prompt is None else initial_prompt
        self._hotwords = DOMAIN_HOTWORDS if hotwords is None else hotwords

    def transcribe(self, path: str, *, ff: FFmpeg | None = None) -> Transcript:
        try:
            kwargs = dict(
                language=self._language,
                word_timestamps=True,
                beam_size=self._beam_size,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": self._vad_min_silence_ms},
            )
            if self._initial_prompt:
                kwargs["initial_prompt"] = self._initial_prompt
            try:
                segments, info = self._model.transcribe(path, **kwargs)
            except TypeError:  # older faster-whisper without a newer kwarg
                kwargs.pop("initial_prompt", None)
                segments, info = self._model.transcribe(path, **kwargs)
            words: list[Word] = []
            for seg in segments:
                for w in seg.words or []:
                    text = w.word.strip()
                    if not text:
                        continue
                    words.append(
                        Word(text=text, start=float(w.start), end=float(w.end), prob=float(w.probability))
                    )
        except Exception as exc:  # pragma: no cover - backend/runtime dependent
            raise TranscriptionError(f"faster-whisper failed on {path}: {exc}") from exc
        return Transcript(words=tuple(words), language=getattr(info, "language", "en"))
