"""Background replacement — segment the speaker out of their real background and
composite them over b-roll instead. Person segmentation runs on-CPU via MediaPipe
Selfie Segmentation (real-time, no GPU needed); the composite is done in FFmpeg
(`alphamerge` + `overlay`) so audio + encoding stay native and fast."""

from __future__ import annotations

from cadence.matte.replace import generate_person_mask, render_background_replaced

__all__ = ["generate_person_mask", "render_background_replaced"]
