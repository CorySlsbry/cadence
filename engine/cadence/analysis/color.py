"""Module A.1 — colour profiling via seeded K-means++ + exposure grading.

A compact, deterministic K-means++ in numpy (no opencv/sklearn dependency) so the
palette is reproducible and unit-testable. Operates on sampled frames; the heavy
lifting is vectorised so a 60s clip at 1 fps stays well under a second.
"""

from __future__ import annotations

import numpy as np

from cadence.models import (
    ColorProfile,
    ColorSwatch,
    ExposureLabel,
    ExposureStats,
    RGBColor,
)

_REC709 = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


def _luma(pixels: np.ndarray) -> np.ndarray:
    """Rec.709 luma for an ``(M, 3)`` float pixel array → ``(M,)``."""
    return pixels @ _REC709


def _kmeans_pp_init(pixels: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """K-means++ seeding: pick spread-out initial centers (deterministic via rng)."""
    n = pixels.shape[0]
    first = int(rng.integers(0, n))
    centers = [pixels[first]]
    closest_sq = np.sum((pixels - centers[0]) ** 2, axis=1)
    for _ in range(1, k):
        total = float(closest_sq.sum())
        if total <= 0.0:  # all pixels identical — duplicate a center
            centers.append(pixels[int(rng.integers(0, n))])
            continue
        probs = closest_sq / total
        idx = int(rng.choice(n, p=probs))
        centers.append(pixels[idx])
        dist_sq = np.sum((pixels - pixels[idx]) ** 2, axis=1)
        closest_sq = np.minimum(closest_sq, dist_sq)
    return np.stack(centers, axis=0)


def kmeans(
    pixels: np.ndarray, k: int, *, iters: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """Lloyd's algorithm. Returns ``(centers (k,3), labels (M,))``.

    Empty clusters are re-seeded to the point furthest from its center so ``k``
    swatches are always produced for non-degenerate inputs.
    """
    rng = np.random.default_rng(seed)
    pixels = pixels.astype(np.float64)
    k = max(1, min(k, pixels.shape[0]))
    centers = _kmeans_pp_init(pixels, k, rng)
    labels = np.zeros(pixels.shape[0], dtype=np.int64)
    for _ in range(iters):
        # Assign: squared euclidean distance to each center.
        d = np.sum((pixels[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        new_labels = np.argmin(d, axis=1)
        if np.array_equal(new_labels, labels) and _ > 0:
            labels = new_labels
            break
        labels = new_labels
        for c in range(k):
            mask = labels == c
            if mask.any():
                centers[c] = pixels[mask].mean(axis=0)
            else:
                # Re-seed empty cluster to the worst-fit pixel.
                dmin = np.min(d, axis=1)
                centers[c] = pixels[int(np.argmax(dmin))]
    return centers, labels


def _exposure_label(mean_luma: float) -> ExposureLabel:
    if mean_luma < 50:
        return ExposureLabel.DARK
    if mean_luma < 95:
        return ExposureLabel.LOW
    if mean_luma < 160:
        return ExposureLabel.BALANCED
    if mean_luma < 205:
        return ExposureLabel.HIGH
    return ExposureLabel.BRIGHT


def compute_exposure(frames: np.ndarray) -> ExposureStats:
    pixels = frames.reshape(-1, 3).astype(np.float64)
    lum = _luma(pixels)
    mean = float(lum.mean())
    return ExposureStats(
        mean_luma=mean,
        std_luma=float(lum.std()),
        p05_luma=float(np.percentile(lum, 5)),
        p95_luma=float(np.percentile(lum, 95)),
        label=_exposure_label(mean),
    )


def compute_color_profile(
    frames: np.ndarray,
    *,
    k: int = 5,
    iters: int = 25,
    seed: int = 1234,
    max_pixels: int = 60_000,
) -> ColorProfile:
    """Extract a weighted dominant palette + exposure from sampled frames.

    ``frames`` is ``(N, H, W, 3)`` uint8. Pixels are deterministically subsampled
    to ``max_pixels`` to bound runtime without changing results meaningfully.
    """
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError(f"expected (N,H,W,3) frames, got shape {frames.shape}")
    pixels = frames.reshape(-1, 3)
    if pixels.shape[0] > max_pixels:
        rng = np.random.default_rng(seed)
        idx = rng.choice(pixels.shape[0], size=max_pixels, replace=False)
        sample = pixels[idx]
    else:
        sample = pixels

    centers, labels = kmeans(sample, k, iters=iters, seed=seed)
    counts = np.bincount(labels, minlength=centers.shape[0]).astype(np.float64)
    weights = counts / counts.sum()

    order = np.argsort(weights)[::-1]
    swatches: list[ColorSwatch] = []
    for c in order:
        if weights[c] <= 0.0:
            continue
        r, g, b = (int(round(v)) for v in np.clip(centers[c], 0, 255))
        swatches.append(ColorSwatch(color=RGBColor(r, g, b), weight=float(weights[c])))

    return ColorProfile(palette=tuple(swatches), exposure=compute_exposure(frames))
