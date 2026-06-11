"""Scene asset library — semantic reuse of generated b-roll across renders.

Before generating a scene image we embed its prompt (gemini-embedding-001 at
768-dim, ~free) and ask `match_scene_assets` for a same-style, same-kind asset at
>=0.86 cosine similarity owned by this user (or platform-global rows). A hit costs
the user 0 tokens and us $0; a miss generates normally and donates the result back
to the library. Everything here fails OPEN — any error just means "no cache today".
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


class AssetLibrary:
    """lookup/save pair for CachingGenerator, bound to one render's context."""

    def __init__(self, supabase, gemini_key: str, *, user_id: str | None,
                 job_id: str | None = None, style: str = "photoreal",
                 threshold: float = 0.86, timeout: float = 20.0) -> None:
        self.supabase = supabase
        self.gemini_key = gemini_key
        self.user_id = user_id
        self.job_id = job_id
        self.style = style or "photoreal"
        self.threshold = threshold
        self.timeout = timeout
        self._emb_cache: dict[str, list[float]] = {}

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

    def lookup(self, prompt: str, aspect: str) -> bytes | None:
        emb = self._embed(prompt)
        rows = (
            self.supabase.rpc("match_scene_assets", {
                "p_embedding": emb,
                "p_style": self.style,
                "p_kind": "image",
                "p_user": self.user_id,
                "p_threshold": self.threshold,
                "p_limit": 3,
            }).execute().data
            or []
        )
        want_w, want_h = _ASPECT_SIZES.get(aspect, _ASPECT_SIZES["9x16"])
        portrait = want_h >= want_w
        for row in rows:
            w, h = row.get("width") or 0, row.get("height") or 0
            if w and h and ((h >= w) != portrait):
                continue  # never stretch a landscape asset into a portrait slot
            data = self.supabase.storage.from_(_BUCKET).download(row["storage_path"])
            if not data or len(data) < 1000:
                continue
            try:
                self.supabase.rpc("touch_scene_asset", {"p_id": row["id"]}).execute()
            except Exception:  # noqa: BLE001 - usage stats are best-effort
                pass
            print(f"[worker] scene library HIT {row['similarity']:.3f} "
                  f"({row['storage_path']})", flush=True)
            return bytes(data)
        return None

    def save(self, prompt: str, aspect: str, image_bytes: bytes, provider: str) -> None:
        if provider == "library" or len(image_bytes) < 1000:
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
            "kind": "image",
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
