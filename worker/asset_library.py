"""Scene asset library — semantic reuse of generated b-roll across renders.

Before generating a scene image we embed its prompt (gemini-embedding-001 at
768-dim, ~free) and ask `match_scene_assets` for a same-style, same-kind asset at
>=0.86 cosine similarity owned by this user (or platform-global rows). A hit costs
the user 0 tokens and us $0; a miss generates normally and donates the result back
to the library. Everything here fails OPEN — any error just means "no cache today".

Two kinds of artifact share the plumbing in :class:`_SceneAssetLibrary` (the embed
cache, the `match_scene_assets` call, `touch_scene_asset`, and the
one-appearance-per-render guard) and differ only in their lookup/save contract:

* :class:`AssetLibrary` — ``kind="image"``, the generated stills. Wrapped by
  ``cadence.imagegen.cache.CachingGenerator``, which owns its fail-open behaviour.
* :class:`ClipLibrary` — ``kind="clip"``, the animated MOTION clips. Clips are by far
  the most expensive artifact we produce (~2 min of GPU per scene vs ~5s for a still),
  so a hit is a big win. The worker calls it directly (there is no CachingGenerator for
  video), so it fails open on its own.
"""

from __future__ import annotations

import json
import urllib.request
import uuid

_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-embedding-001:embedContent?key={key}"
)
_BUCKET = "assets"

_ASPECT_SIZES = {
    "9x16": (768, 1344),
    "16x9": (1344, 768),
    "1x1": (1024, 1024),
    "3x4": (896, 1152),
    "4x3": (1152, 896),
}

# Bucket limit is 50MB — stay under it so an oversized clip is SKIPPED here rather than
# raising a storage error up into a render. A 5s 704x1280 h264 clip is ~1-3MB, so this
# only ever trips on something pathological.
_MAX_CLIP_BYTES = 48 * 1024 * 1024


class _SceneAssetLibrary:
    """Shared plumbing for the kind-specific libraries; not used directly.

    Subclasses set ``kind`` (the `scene_assets.kind` / `match_scene_assets` filter) and
    ``min_bytes`` (the floor below which a stored blob is a broken artifact, not an asset),
    then express their own lookup/save contract on top.
    """

    kind = "image"
    min_bytes = 1000

    def __init__(self, supabase, gemini_key: str, *, user_id: str | None,
                 job_id: str | None = None, style: str = "photoreal",
                 threshold: float = 0.92, timeout: float = 20.0) -> None:
        # 0.92: sibling scenes of ONE video embed ~0.87-0.94 apart (shared topic +
        # style boilerplate), so 0.86 made every scene reuse scene 0's image. Only
        # near-identical prompts from PAST renders should match.
        self.supabase = supabase
        self.gemini_key = gemini_key
        self.user_id = user_id
        self.job_id = job_id
        self.style = style or "photoreal"
        self.threshold = threshold
        self.timeout = timeout
        self._emb_cache: dict[str, list[float]] = {}
        self._used_ids: set[str] = set()  # variety within one render is sacred

    def _embed(self, text: str) -> list[float]:
        if text in self._emb_cache:
            return self._emb_cache[text]
        body = json.dumps({
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": text[:6000]}]},
            "outputDimensionality": 768,  # matches scene_assets vector(768)
        }).encode()
        req = urllib.request.Request(
            _EMBED_URL.format(key=self.gemini_key), data=body, method="POST",
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            values = json.loads(resp.read())["embedding"]["values"]
        self._emb_cache[text] = values
        return values

    def _match(self, emb: list[float], *, limit: int = 3) -> list[dict]:
        """Same-style, same-kind rows above the similarity threshold, best first."""
        return (
            self.supabase.rpc("match_scene_assets", {
                "p_embedding": emb,
                "p_style": self.style,
                "p_kind": self.kind,
                "p_user": self.user_id,
                "p_threshold": self.threshold,
                "p_limit": limit,
            }).execute().data
            or []
        )

    def _orientation_ok(self, row: dict, want_w: int, want_h: int) -> bool:
        """Never stretch a landscape asset into a portrait slot (or vice versa).
        Unknown dimensions are trusted — the row predates the width/height columns."""
        w, h = row.get("width") or 0, row.get("height") or 0
        if not (w and h):
            return True
        return (h >= w) == (want_h >= want_w)

    def _download(self, storage_path: str) -> bytes | None:
        """Asset bytes, or None if the blob is missing/truncated (i.e. not an asset)."""
        data = self.supabase.storage.from_(_BUCKET).download(storage_path)
        if not data or len(data) < self.min_bytes:
            return None
        return bytes(data)

    def _touch(self, asset_id: str) -> None:
        try:
            self.supabase.rpc("touch_scene_asset", {"p_id": asset_id}).execute()
        except Exception:  # noqa: BLE001 - usage stats are best-effort
            pass


class AssetLibrary(_SceneAssetLibrary):
    """lookup/save pair for CachingGenerator, bound to one render's context."""

    kind = "image"
    min_bytes = 1000

    def lookup(self, prompt: str, aspect: str) -> bytes | None:
        emb = self._embed(prompt)
        rows = self._match(emb)
        want_w, want_h = _ASPECT_SIZES.get(aspect, _ASPECT_SIZES["9x16"])
        for row in rows:
            if row["id"] in self._used_ids:
                continue  # one appearance per render — repeats read as a broken video
            if not self._orientation_ok(row, want_w, want_h):
                continue  # never stretch a landscape asset into a portrait slot
            data = self._download(row["storage_path"])
            if data is None:
                continue
            self._used_ids.add(row["id"])
            self._touch(row["id"])
            print(f"[worker] scene library HIT {row['similarity']:.3f} "
                  f"({row['storage_path']})", flush=True)
            return data
        return None

    def save(self, prompt: str, aspect: str, image_bytes: bytes, provider: str) -> None:
        if provider == "library" or len(image_bytes) < self.min_bytes:
            return
        emb = self._embed(prompt)  # cached from the lookup that just missed
        w, h = _ASPECT_SIZES.get(aspect, _ASPECT_SIZES["9x16"])
        owner = self.user_id or "global"
        path = f"library/{owner}/{uuid.uuid4().hex}.png"
        self.supabase.storage.from_(_BUCKET).upload(
            path, image_bytes, {"content-type": "image/png"},
        )
        self.supabase.table("scene_assets").insert({
            "user_id": self.user_id,
            "kind": self.kind,
            "style": self.style,
            "description": prompt[:500],
            "prompt": prompt,
            "storage_path": path,
            "width": w,
            "height": h,
            "embedding": emb,
            "source_job_id": self.job_id,
        }).execute()
        print(f"[worker] scene library SAVE {path} ({provider})", flush=True)


class ClipLibrary(_SceneAssetLibrary):
    """Reuse of generated MOTION clips across renders — the expensive artifact.

    Keyed on the SCENE's own prompt (not the video-level motion prompt, which is identical
    for every scene of a video and would collapse a whole render onto one clip). The style
    key must therefore also pin the MODEL — see the worker's ``|m{model}`` suffix: a free
    FastWan-5B clip must never be served into a paid Cinematic/A14B render, nor vice versa.

    Unlike :class:`AssetLibrary` there is no CachingGenerator wrapper for video, so both
    methods swallow their own errors: a broken library means "no cache today", never a
    broken render.
    """

    kind = "clip"
    # 5KB: the /animate contract already treats a sub-5KB response as a failed render
    # (cadence.imagegen.selfhost.animate_image) — the same floor applies to a stored clip.
    min_bytes = 5000

    def lookup(self, prompt: str, *, min_seconds: float, width: int, height: int) -> bytes | None:
        """A stored clip that can carry this scene, or None (=> generate it)."""
        try:
            emb = self._embed(prompt)
            for row in self._match(emb):
                if row["id"] in self._used_ids:
                    continue  # one appearance per render — repeats read as a broken video
                dur = float(row.get("duration_sec") or 0.0)
                if dur < min_seconds:
                    # A clip shorter than its window can't cover it: the compositor would
                    # hold its last frame for the remainder, i.e. a frozen tail. Worthless.
                    continue
                if not self._orientation_ok(row, width, height):
                    continue  # never stretch a landscape clip into a portrait slot
                data = self._download(row["storage_path"])
                if data is None:
                    continue
                self._used_ids.add(row["id"])
                self._touch(row["id"])
                print(f"[worker] clip library HIT {row['similarity']:.3f} "
                      f"({dur:.1f}s >= {min_seconds:.1f}s, {row['storage_path']})", flush=True)
                return data
        except Exception as exc:  # noqa: BLE001 - a library problem is never a render problem
            print(f"[worker] clip library lookup failed ({exc!r}); animating", flush=True)
        return None

    def save(self, prompt: str, clip_bytes: bytes, *, seconds: float,
             width: int, height: int) -> None:
        """Donate a freshly generated clip back to the library. Best-effort, always."""
        try:
            size = len(clip_bytes or b"")
            if size < self.min_bytes:
                print(f"[worker] clip library SKIP save ({size}B < {self.min_bytes}B)", flush=True)
                return
            if size > _MAX_CLIP_BYTES:
                print(f"[worker] clip library SKIP save ({size // 1024}KB over the bucket "
                      f"limit)", flush=True)
                return
            emb = self._embed(prompt)  # cached from the lookup that just missed
            owner = self.user_id or "global"
            path = f"library/{owner}/clips/{uuid.uuid4().hex}.mp4"
            self.supabase.storage.from_(_BUCKET).upload(
                path, clip_bytes, {"content-type": "video/mp4"},
            )
            self.supabase.table("scene_assets").insert({
                "user_id": self.user_id,
                "kind": self.kind,
                "style": self.style,
                "description": prompt[:500],
                "prompt": prompt,
                "storage_path": path,
                "width": width,
                "height": height,
                "duration_sec": seconds,
                "embedding": emb,
                "source_job_id": self.job_id,
            }).execute()
            print(f"[worker] clip library SAVE {path} ({seconds:.1f}s, "
                  f"{size // 1024}KB)", flush=True)
        except Exception as exc:  # noqa: BLE001 - donation is best-effort, never a render problem
            print(f"[worker] clip library save failed ({exc!r})", flush=True)
