"""Module A orchestrator — turn a reference video into a :class:`ReferenceAnalysis`."""

from __future__ import annotations

from cadence.analysis.color import compute_color_profile
from cadence.analysis.frames import extract_frames
from cadence.analysis.pacing import compute_pacing
from cadence.analysis.text_overlay import OcrBackend, detect_text_overlays
from cadence.analysis.transitions import detect_transitions
from cadence.config import AnalyzerConfig
from cadence.errors import AnalysisError
from cadence.ffmpeg.probe import probe_media
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import ReferenceAnalysis, Transcript
from cadence.transcription.base import Transcriber


def analyze_reference(
    path: str,
    *,
    cfg: AnalyzerConfig | None = None,
    ff: FFmpeg | None = None,
    transcriber: Transcriber | None = None,
    ocr: OcrBackend | None = None,
) -> ReferenceAnalysis:
    """Analyse a reference video's aesthetics + pacing.

    ``transcriber`` and ``ocr`` are optional ports: when supplied they enrich the
    result with a transcript (better pacing / WPM) and literal caption text.
    """
    cfg = cfg or AnalyzerConfig()
    ff = ff or FFmpeg()

    media = probe_media(path, ff)
    if media.duration <= 0:
        raise AnalysisError(f"reference has non-positive duration: {path}")

    # Colour @ ~1 fps (sparse, cheap).
    frames = extract_frames(
        path,
        fps=cfg.sample_fps,
        width=cfg.analysis_width,
        height=cfg.analysis_height,
        ff=ff,
    )
    color_profile = compute_color_profile(
        frames, k=cfg.palette_k, iters=cfg.kmeans_iters, seed=cfg.kmeans_seed
    )

    transitions = detect_transitions(path, cfg=cfg, ff=ff)
    text_overlays = detect_text_overlays(path, cfg=cfg, ff=ff)

    transcript: Transcript | None = None
    if transcriber is not None and media.has_audio:
        transcript = transcriber.transcribe(path, ff=ff)

    pacing = compute_pacing(transitions, media.duration, transcript)

    return ReferenceAnalysis(
        media=media,
        color_profile=color_profile,
        transitions=transitions,
        text_overlays=text_overlays,
        pacing=pacing,
        transcript=transcript,
    )
