"""The O(n) cumsum box-blur must be numerically identical to the old O(n*k) separable
convolution it replaces (zero-padded 'same' edges) — proven against that independent oracle."""

from __future__ import annotations

import numpy as np
import pytest

from cadence.matte.replace import _box_blur


def _convolve_reference(a: np.ndarray, k: int) -> np.ndarray:
    """The original implementation — the independent oracle."""
    k = max(1, int(k))
    kern = np.ones(k) / k
    out = np.apply_along_axis(lambda m: np.convolve(m, kern, mode="same"), 1, a)
    out = np.apply_along_axis(lambda m: np.convolve(m, kern, mode="same"), 0, out)
    return out


@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 7, 9])
def test_box_blur_matches_convolution_reference(k):
    rng = np.random.default_rng(1000 + k)
    a = rng.random((29, 37)).astype(np.float32)
    assert np.allclose(_box_blur(a, k), _convolve_reference(a, k), atol=1e-5)


def test_box_blur_preserves_constant_interior():
    # With zero-padded edges, a uniform interior must come back unchanged (window fully inside).
    a = np.ones((12, 12), dtype=np.float64)
    out = _box_blur(a, 3)
    assert np.allclose(out[2:-2, 2:-2], 1.0)


def test_box_blur_k1_is_identity():
    rng = np.random.default_rng(7)
    a = rng.random((8, 5)).astype(np.float32)
    assert np.allclose(_box_blur(a, 1), a, atol=1e-6)


def test_resolve_mask_stride(monkeypatch):
    from cadence.matte.replace import _resolve_mask_stride

    monkeypatch.delenv("CADENCE_MASK_STRIDE", raising=False)
    assert _resolve_mask_stride(None) == 1          # default = every frame
    assert _resolve_mask_stride(3) == 3             # explicit
    assert _resolve_mask_stride(0) == 1             # clamped to >= 1
    assert _resolve_mask_stride(-5) == 1
    monkeypatch.setenv("CADENCE_MASK_STRIDE", "4")
    assert _resolve_mask_stride(None) == 4          # from env
    assert _resolve_mask_stride(2) == 2             # explicit overrides env
    monkeypatch.setenv("CADENCE_MASK_STRIDE", "garbage")
    assert _resolve_mask_stride(None) == 1          # bad env → safe default
