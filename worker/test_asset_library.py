"""AssetLibrary lookup: within-render dedup + orientation guard (no network)."""

from __future__ import annotations

import asset_library
from asset_library import AssetLibrary

PNG = b"\x89PNG" + b"x" * 2000
ROW = {"id": "a1", "storage_path": "library/u/a1.png", "similarity": 0.95,
       "width": 768, "height": 1344}
LANDSCAPE = {"id": "a2", "storage_path": "library/u/a2.png", "similarity": 0.94,
             "width": 1344, "height": 768}


class _Exec:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeSupabase:
    def __init__(self, rows):
        self.rows = rows

    def rpc(self, name, params):
        return _Exec(self.rows if name == "match_scene_assets" else None)

    def storage(self):  # pragma: no cover - replaced by from_
        raise AssertionError

    @property
    def _storage(self):
        raise AssertionError


class FakeStorage:
    def from_(self, bucket):
        return self

    def download(self, path):
        return PNG


def _lib(rows):
    sb = FakeSupabase(rows)
    sb.storage = FakeStorage()
    lib = AssetLibrary(sb, "key", user_id="u", style="cinematic")
    lib._embed = lambda text: [0.0] * 768  # no network
    return lib


def test_same_asset_never_reused_within_one_render():
    lib = _lib([dict(ROW)])
    assert lib.lookup("scene one", "9x16") == PNG
    assert lib.lookup("scene two, nearly identical", "9x16") is None


def test_landscape_asset_skipped_for_portrait_slot():
    lib = _lib([dict(LANDSCAPE)])
    assert lib.lookup("a scene", "9x16") is None


def test_default_threshold_is_above_sibling_similarity():
    assert AssetLibrary(object(), "k", user_id=None).threshold >= 0.92
