"""Multi-clip: one (longer) recording → the best self-contained short-form moments.

Feeds the word-timed transcript to the LLM as timestamped lines, asks for the top-N
postable moments (a complete thought with a hook + payoff), and returns validated, clamped,
non-overlapping time ranges. The worker then trims the recording to each range and runs the
normal clean→render pipeline per moment — so every clip is independently cleaned, graded,
captioned. LLM injected (unit-testable); returns [] on failure so the worker falls back to a
single full render.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_CLIPS = 5
MIN_CLIP_SEC = 8.0
MAX_CLIP_SEC = 90.0


@dataclass(frozen=True, slots=True)
class ClipMoment:
    start: float
    end: float
    title: str
    hook: str

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "title": self.title, "hook": self.hook}


def _timestamped(transcript, max_chars: int = 8000) -> str:
    """Render the transcript as `[12.3] sentence…` lines so the LLM can pick time ranges."""
    words = list(getattr(transcript, "words", []) or [])
    lines: list[str] = []
    buf: list[str] = []
    start: float | None = None
    for w in words:
        if start is None:
            start = w.start
        buf.append(w.text)
        if w.text.endswith((".", "?", "!")) or len(buf) >= 14:
            lines.append(f"[{start:.1f}] {' '.join(buf)}")
            buf, start = [], None
    if buf and start is not None:
        lines.append(f"[{start:.1f}] {' '.join(buf)}")
    text = "\n".join(lines)
    return text[:max_chars]


_PROMPT = """You are a short-form video editor. Below is a TIMESTAMPED transcript (each line starts \
with its [start-second]) of a {dur:.0f}-second video. Identify the BEST up to {n} self-contained \
moments to cut into standalone vertical shorts — each a complete thought with a strong hook and a payoff.

Return STRICT JSON: {{"clips": [{{"start": <sec>, "end": <sec>, "title": "...", "hook": "..."}}]}}
Rules: each clip {min:.0f}-{max:.0f}s long; non-overlapping; ordered by start; `start`/`end` are seconds \
within the video; `title` = 3-6 word label; `hook` = the punchy opening line. JSON only, no preamble."""


def normalize_moments(raw: dict[str, Any], duration: float, *, max_clips: int = MAX_CLIPS,
                      min_sec: float = MIN_CLIP_SEC, max_sec: float = MAX_CLIP_SEC) -> list[ClipMoment]:
    """Validate, clamp to [0,duration], enforce length, drop overlaps, cap to max_clips."""
    raw = raw if isinstance(raw, dict) else {}
    cand: list[ClipMoment] = []
    for c in raw.get("clips") or []:
        try:
            s = max(0.0, float(c.get("start")))
            e = min(float(duration), float(c.get("end")))
        except (TypeError, ValueError):
            continue
        if e - s < min_sec:
            continue
        if e - s > max_sec:
            e = round(s + max_sec, 3)
        title = " ".join(str(c.get("title", "") or "").split())[:60]
        hook = " ".join(str(c.get("hook", "") or "").split())[:120]
        cand.append(ClipMoment(round(s, 3), round(e, 3), title, hook))
    cand.sort(key=lambda m: m.start)
    out: list[ClipMoment] = []
    last_end = -1.0
    for m in cand:
        if m.start >= last_end:  # non-overlapping (keep earliest)
            out.append(m)
            last_end = m.end
        if len(out) >= max_clips:
            break
    return out


def find_clip_moments(transcript, duration: float | None = None, *, max_clips: int = MAX_CLIPS,
                      min_sec: float = MIN_CLIP_SEC, llm=None) -> list[ClipMoment]:
    """Return the top clip moments, or [] if none / no LLM / failure (→ single full render)."""
    words = list(getattr(transcript, "words", []) or [])
    if not words:
        return []
    if duration is None:
        duration = max((w.end for w in words), default=0.0)
    if duration < min_sec * 1.5 or llm is None:
        return []  # too short to split, or no LLM available
    try:
        prompt = _PROMPT.format(dur=duration, n=max_clips, min=min_sec, max=MAX_CLIP_SEC)
        raw = llm.complete(prompt + "\n\nTranscript:\n" + _timestamped(transcript))
        return normalize_moments(raw, duration, max_clips=max_clips, min_sec=min_sec)
    except Exception as exc:  # noqa: BLE001
        print(f"[cadence] find_clip_moments LLM failed -> single render: {exc!r}", flush=True)
        return []
