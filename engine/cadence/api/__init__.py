"""Local HTTP sidecar — the surface the Flutter client drives."""

from __future__ import annotations

from cadence.api.server import create_app, serve

__all__ = ["create_app", "serve"]
