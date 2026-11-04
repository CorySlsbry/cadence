"""Module A.2 — transition / cut detection and TYPE classification.

Implements the AdaptiveDetector idea (HSV content delta + rolling-window ratio)
in pure numpy so it is deterministic and dependency-light, then classifies each
detected boundary by the SHAPE of the raw content curve:

  * isolated single-frame spike (ratio >> neighbours) -> HARD_CUT
  * multi-frame elevated plateau                       -> CROSSFADE / DISSOLVE
  * mean-luma collapsing toward black                  -> FADE_TO_BLACK / FROM_BLACK

Only the 1-D content & luma curves are retained while streaming frames, so memory
stays bounded on long inputs.
"""

from __future__ import annotations

import numpy as np

from cadence.analysis.frames import iter_frames
from cadence.config import AnalyzerConfig
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Transition, TransitionType

# --------------------------------------------------------------------------- #
# Colour-space + similarity primitives (pure, unit-tested)
# --------------------------------------------------------------------------- #
def rgb_to_hsv255(frame: np.ndarray) -> np.ndarray:
    """Vectorised RGB->HSV with every channel scaled to 0..255 float.

    ``frame`` is ``(H, W, 3)`` uint8. Hue is mapped 0..255 (so it can be diffed on
    the same scale as S and V); saturation and value are 0..255.
    """
    f = frame.astype(np.float64) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    maxc = np.max(f, axis=-1)
    minc = np.min(f, axis=-1)
    delta = maxc - minc

    v = maxc
    s = np.where(maxc > 0, delta / np.where(maxc == 0, 1, maxc), 0.0)

    # Hue in [0, 6) then scaled to [0,255).
    hue = np.zeros_like(maxc)
    nz = delta > 1e-12
    # Avoid div-by-zero by masking.
    d = np.where(nz, delta, 1.0)
    rc = (maxc - r) / d
    gc = (maxc - g) / d
    bc = (maxc - b) / d
    hue = np.where(maxc == r, bc - gc, hue)
    hue = np.where((maxc == g) & (maxc != r), 2.0 + rc - bc, hue)
    hue = np.where((maxc == b) & (maxc != r) & (maxc != g), 4.0 + gc - rc, hue)
    hue = (hue / 6.0) % 1.0
    hue = np.where(nz, hue, 0.0)

    return np.stack([hue * 255.0, s * 255.0, v * 255.0], axis=-1)


def content_delta(hsv_a: np.ndarray, hsv_b: np.ndarray, weights: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> float:
    """PySceneDetect-style content score between two HSV(0..255) frames (0..255)."""
    dh = np.abs(hsv_a[..., 0] - hsv_b[..., 0])
    dh = np.where(dh > 127.5, 255.0 - dh, dh)  # hue is circular
    ds = np.abs(hsv_a[..., 1] - hsv_b[..., 1])
    dv = np.abs(hsv_a[..., 2] - hsv_b[..., 2])
    wh, ws, wv = weights
    num = wh * dh + ws * ds + wv * dv
    return float(num.mean() / (wh + ws + wv))


def to_gray(frame: np.ndarray) -> np.ndarray:
    return frame.astype(np.float64) @ np.array([0.299, 0.587, 0.114])


def ssim(a: np.ndarray, b: np.ndarray, *, data_range: float = 255.0) -> float:
    """Global structural similarity index between two grayscale arrays (-1..1)."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    c1 = (0.01 * data_range) ** 2
    c2 = (0.03 * data_range) ** 2
    mu_a, mu_b = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = ((a - mu_a) * (b - mu_b)).mean()
    num = (2 * mu_a * mu_b + c1) * (2 * cov + c2)
    den = (mu_a**2 + mu_b**2 + c1) * (va + vb + c2)
    return float(num / den)


# --------------------------------------------------------------------------- #
# Detector
# --------------------------------------------------------------------------- #
def detect_from_curves(
    content: np.ndarray,
    luma: np.ndarray,
    *,
    sample_fps: float,
    cfg: AnalyzerConfig,
) -> tuple[Transition, ...]:
    """Pure detector over precomputed 1-D curves (fully unit-testable).

    ``content[i]`` is the content delta between frame ``i`` and ``i+1``; ``luma[i]``
    is the mean luma of frame ``i`` (len == len(content)+1).
    """
    n = content.shape[0]
    if n == 0:
        return ()
    radius = max(1, cfg.neighbor_frames)
    min_gap = max(1, int(round(cfg.min_scene_len_sec * sample_fps)))

    # Rolling neighbourhood mean (excluding the candidate frame itself).
    ratios = np.zeros(n)
    for i in range(n):
        lo, hi = max(0, i - radius), min(n, i + radius + 1)
        neigh = np.concatenate([content[lo:i], content[i + 1 : hi]])
        nmean = float(neigh.mean()) if neigh.size else 0.0
        ratios[i] = content[i] / (nmean + 1e-6)

    candidates: list[int] = []
    for i in range(n):
        strong = content[i] >= cfg.content_threshold
        adaptive = content[i] >= cfg.min_content_val and ratios[i] >= cfg.adaptive_ratio
        if strong or adaptive:
            candidates.append(i)

    # Non-maximum suppression: within min_gap keep the highest-content frame.
    candidates.sort(key=lambda i: content[i], reverse=True)
    chosen: list[int] = []
    for i in candidates:
        if all(abs(i - j) >= min_gap for j in chosen):
            chosen.append(i)
    chosen.sort()

    transitions: list[Transition] = []
    peak = float(content.max()) if n else 0.0
    for i in chosen:
        ttype, conf = _classify(content, luma, i, peak, cfg)
        # The cut lands between frame i and i+1; report the boundary time.
        ts = (i + 1) / sample_fps
        transitions.append(
            Transition(timestamp=round(ts, 3), type=ttype, confidence=round(conf, 3), score=round(float(content[i]), 3))
        )
    return tuple(transitions)


def _classify(
    content: np.ndarray,
    luma: np.ndarray,
    i: int,
    peak: float,
    cfg: AnalyzerConfig,
) -> tuple[TransitionType, float]:
    n = content.shape[0]
    # Fade detection: very dark frame on one side of the boundary.
    left_luma = luma[i]
    right_luma = luma[min(i + 1, len(luma) - 1)]
    if right_luma < cfg.fade_luma_threshold:
        return TransitionType.FADE_TO_BLACK, 0.9
    if left_luma < cfg.fade_luma_threshold:
        return TransitionType.FADE_FROM_BLACK, 0.9

    # Plateau detection: count contiguous elevated frames around i.
    thr = cfg.dissolve_peak_frac * max(content[i], peak)
    run = 1
    j = i - 1
    while j >= 0 and content[j] >= thr:
        run += 1
        j -= 1
    j = i + 1
    while j < n and content[j] >= thr:
        run += 1
        j += 1
    if run >= cfg.dissolve_min_frames:
        return TransitionType.DISSOLVE, min(1.0, run / (cfg.dissolve_min_frames * 2))

    conf = min(1.0, content[i] / (cfg.content_threshold * 1.5))
    return TransitionType.HARD_CUT, max(0.5, conf)


def detect_transitions(
    path: str,
    *,
    cfg: AnalyzerConfig | None = None,
    ff: FFmpeg | None = None,
    analysis_width: int = 192,
    analysis_height: int = 192,
) -> tuple[Transition, ...]:
    """Stream frames, build the content/luma curves, and detect transitions."""
    cfg = cfg or AnalyzerConfig()
    ff = ff or FFmpeg()
    content: list[float] = []
    luma: list[float] = []
    prev_hsv: np.ndarray | None = None
    for frame in iter_frames(path, fps=cfg.transition_sample_fps, width=analysis_width, height=analysis_height, ff=ff):
        hsv = rgb_to_hsv255(frame)
        luma.append(float(hsv[..., 2].mean()))
        if prev_hsv is not None:
            content.append(content_delta(prev_hsv, hsv))
        prev_hsv = hsv
    if not content:
        return ()
    return detect_from_curves(
        np.asarray(content),
        np.asarray(luma),
        sample_fps=cfg.transition_sample_fps,
        cfg=cfg,
    )
