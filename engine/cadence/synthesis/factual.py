"""Factual-image guardrail: show the REAL product UI, not a hallucination.

A generative model (Imagen) cannot render a real product UI accurately — it
invents chrome and garbles on-screen text. So when a talking point names a real,
guarded thing ("Claude Code", "Cowork", "Skills", any brand/product term Cory
configures), we override the AI b-roll for that moment with an EXACT curated
screenshot instead of generating one.

This module is the data-driven core:

* :class:`FactualAsset` — one curated real image + the trigger phrases that map to it.
* :func:`match_factual_asset` — the pure matcher (longest phrase first, word-boundary,
  case-insensitive, punctuation-tolerant). Fully unit-tested; no I/O.
* :func:`load_factual_assets` — read a manifest JSON (the screenshot library's
  ``manifest.json``) and skip entries whose image isn't present yet, so the pipeline
  degrades gracefully before the library is captured.
* :func:`compose_factual_asset` — fit the (usually landscape) UI screenshot into the
  9:16 frame WITHOUT cropping the UI away — contain it, centered, over a blurred fill.

The match happens as a pre-step inside ``build_ai_broll``; a hit skips the generator
entirely (so it burns 0 AI tokens) and emits a ``BrollInsert(source="factual")``.
"""

from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FactualAsset:
    """A curated real image and the phrases that should trigger it."""

    key: str                          # canonical id, e.g. "claude-skills"
    asset_path: str                   # absolute local path (or URL) to the real screenshot
    aliases: tuple[str, ...] = ()     # trigger phrases (matched case-insensitively)
    variant: str = ""                 # e.g. "skills-tab" — which screen/variant this is
    alt: str = ""                     # human/accessibility description

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "asset_path": self.asset_path,
            "aliases": list(self.aliases),
            "variant": self.variant,
            "alt": self.alt,
        }


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase, collapse every run of non-alphanumerics to a single space, and pad
    with a leading/trailing space so a word-boundary test is a simple ``" alias "``
    substring check. ``"Claude-Code!"`` -> ``" claude code "``."""
    return " " + _NON_ALNUM.sub(" ", text.lower()).strip() + " "


def match_factual_asset(text: str, assets) -> FactualAsset | None:
    """Return the curated asset whose trigger phrase appears in ``text``, or ``None``.

    Most-specific wins: aliases are tested longest-first so ``"claude code"`` beats a
    bare ``"code"``. Matching is on word boundaries (``"skills"`` won't match
    ``"skillset"``), case-insensitive, and tolerant of punctuation/hyphenation.
    Pure — no I/O, safe to unit-test exhaustively.
    """
    if not text or not assets:
        return None
    haystack = _normalize(text)
    # (normalized alias, asset) pairs, longest alias first for specificity.
    candidates: list[tuple[str, FactualAsset]] = []
    for asset in assets:
        for alias in asset.aliases:
            na = _normalize(alias).strip()
            if na:
                candidates.append((na, asset))
    candidates.sort(key=lambda pair: len(pair[0]), reverse=True)
    for na, asset in candidates:
        if f" {na} " in haystack:
            return asset
    return None


def load_factual_assets(manifest_path: str, *, base_dir: str | None = None, require_files: bool = True):
    """Load :class:`FactualAsset` entries from a manifest JSON.

    Manifest shape: ``{"assets": [{"key","asset_path","aliases":[...],"variant","alt"}]}``.
    ``asset_path`` is resolved relative to ``base_dir`` (default: the manifest's own
    directory). When ``require_files`` (default), entries whose image is missing are
    skipped — so the worker never crashes before the screenshot library exists. Entries
    with no aliases are dropped (they can never match).
    """
    if not manifest_path or not os.path.exists(manifest_path):
        return []
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    base = base_dir or os.path.dirname(os.path.abspath(manifest_path))
    out: list[FactualAsset] = []
    for entry in data.get("assets", []):
        rel = entry.get("asset_path") or entry.get("file") or ""
        if not rel:
            continue
        path = rel if (os.path.isabs(rel) or "://" in rel) else os.path.join(base, rel)
        aliases = tuple(a for a in entry.get("aliases", []) if a)
        if not aliases:
            continue
        if require_files and "://" not in path and not os.path.exists(path):
            continue
        out.append(
            FactualAsset(
                key=entry.get("key", ""),
                asset_path=path,
                aliases=aliases,
                variant=entry.get("variant", ""),
                alt=entry.get("alt", ""),
            )
        )
    return out


def default_manifest_path() -> str:
    """The shipped manifest location inside the package: ``cadence/assets/factual/manifest.json``.
    Override at runtime with the ``CADENCE_FACTUAL_MANIFEST`` env var (e.g. to point at a
    synced or downloaded asset folder)."""
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets", "factual", "manifest.json"))


def compose_factual_asset(
    image_bytes: bytes,
    out_path: str,
    *,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Render a (usually landscape) UI screenshot into the vertical frame with the WHOLE
    UI visible — contain-fit centered over a blurred, darkened cover of itself (no black
    bars, premium look). This is what makes the guardrail useful: the real UI stays
    fully legible instead of being cropped away by a 9:16 cover-crop."""
    from PIL import Image, ImageEnhance, ImageFilter

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Blurred cover-fit background fills the frame edge-to-edge.
    cover = max(width / img.width, height / img.height)
    bg = img.resize((max(1, round(img.width * cover)), max(1, round(img.height * cover))))
    bx, by = (bg.width - width) // 2, (bg.height - height) // 2
    bg = bg.crop((bx, by, bx + width, by + height)).filter(ImageFilter.GaussianBlur(48))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)  # darken so the foreground UI pops

    # Foreground: contain-fit so the entire UI is shown, centered.
    fit = min(width / img.width, height / img.height)
    fw, fh = max(1, round(img.width * fit)), max(1, round(img.height * fit))
    fg = img.resize((fw, fh))
    bg.paste(fg, ((width - fw) // 2, (height - fh) // 2))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    bg.save(out_path, format="PNG")
    return out_path
