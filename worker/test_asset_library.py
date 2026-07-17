"""AssetLibrary + ClipLibrary lookup/save: within-render dedup, orientation guard,
clip duration floor, and model-pinned style isolation (no network)."""

from __future__ import annotations

import asset_library
from asset_library import AssetLibrary, ClipLibrary

PNG = b"\x89PNG" + b"x" * 2000
ROW = {"id": "a1", "storage_path": "library/u/a1.png", "similarity": 0.95,
       "width": 768, "height": 1344}
LANDSCAPE = {"id": "a2", "storage_path": "library/u/a2.png", "similarity": 0.94,
             "width": 1344, "height": 768}

# A stored clip must clear the 5KB floor the /animate contract already uses for "real video".
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"v" * 6000
TINY_MP4 = b"\x00\x00\x00\x18ftypmp42"  # a truncated/broken artifact, not an asset
CLIP = {"id": "c1", "storage_path": "library/u/clips/c1.mp4", "similarity": 0.96,
        "width": 704, "height": 1280, "duration_sec": 5.04}
CLIP2 = {"id": "c2", "storage_path": "library/u/clips/c2.mp4", "similarity": 0.95,
         "width": 704, "height": 1280, "duration_sec": 5.04}
SHORT_CLIP = {"id": "c3", "storage_path": "library/u/clips/c3.mp4", "similarity": 0.99,
              "width": 704, "height": 1280, "duration_sec": 2.0}
LANDSCAPE_CLIP = {"id": "c4", "storage_path": "library/u/clips/c4.mp4", "similarity": 0.98,
                  "width": 1280, "height": 704, "duration_sec": 5.04}


class _Exec:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeSupabase:
    """Records every rpc/insert so tests can assert on what the library ASKED for."""

    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, dict]] = []
        self.inserts: list[dict] = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _Exec(self.rows if name == "match_scene_assets" else None)

    def table(self, name):
        return self

    def insert(self, row):
        self.inserts.append(row)
        return _Exec(None)

    def storage(self):  # pragma: no cover - replaced by from_
        raise AssertionError

    @property
    def _storage(self):
        raise AssertionError


class StyleFilteringSupabase(FakeSupabase):
    """Mirrors match_scene_assets' server-side `style = p_style AND kind = p_kind` filter,
    so a mismatched row is genuinely unreachable rather than merely un-asked-for."""

    def rpc(self, name, params):
        self.calls.append((name, params))
        if name != "match_scene_assets":
            return _Exec(None)
        return _Exec([r for r in self.rows
                      if r.get("style") == params["p_style"]
                      and r.get("kind") == params["p_kind"]])


class FakeStorage:
    def __init__(self, payload=PNG):
        self.payload = payload
        self.uploads: list[tuple[str, bytes, dict]] = []

    def from_(self, bucket):
        return self

    def download(self, path):
        return self.payload

    def upload(self, path, data, opts):
        self.uploads.append((path, data, opts))


def _lib(rows):
    sb = FakeSupabase(rows)
    sb.storage = FakeStorage()
    lib = AssetLibrary(sb, "key", user_id="u", style="cinematic")
    lib._embed = lambda text: [0.0] * 768  # no network
    return lib


def _clip_lib(rows, *, style="cinematic|mfastwan", payload=MP4, supabase_cls=FakeSupabase):
    sb = supabase_cls(rows)
    sb.storage = FakeStorage(payload)
    lib = ClipLibrary(sb, "key", user_id="u", style=style)
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


def test_image_library_still_asks_for_kind_image():
    lib = _lib([dict(ROW)])
    lib.lookup("a scene", "9x16")
    name, params = lib.supabase.calls[0]
    assert name == "match_scene_assets"
    assert params["p_kind"] == "image"
    assert params["p_style"] == "cinematic"  # no |m suffix — stills stay model-portable


# ---------------------------------------------------------------- ClipLibrary


def test_clip_long_enough_to_cover_its_window_is_a_hit():
    lib = _clip_lib([dict(CLIP)])
    assert lib.lookup("scene one", min_seconds=5.0, width=704, height=1280) == MP4


def test_clip_shorter_than_its_window_is_rejected():
    # A 2s clip in a 5s window can't cover it — the compositor would hold a frozen tail.
    # Note the row is the BEST semantic match (0.99): duration must veto similarity.
    lib = _clip_lib([dict(SHORT_CLIP)])
    assert lib.lookup("scene one", min_seconds=5.0, width=704, height=1280) is None


def test_clip_exactly_covering_its_window_is_accepted():
    lib = _clip_lib([dict(CLIP)])  # 5.04s
    assert lib.lookup("scene one", min_seconds=5.04, width=704, height=1280) == MP4


def test_same_clip_never_reused_within_one_render():
    lib = _clip_lib([dict(CLIP)])
    assert lib.lookup("scene one", min_seconds=2.0, width=704, height=1280) == MP4
    assert lib.lookup("scene two, nearly identical", min_seconds=2.0,
                      width=704, height=1280) is None


def test_second_scene_falls_through_to_the_next_unused_clip():
    lib = _clip_lib([dict(CLIP), dict(CLIP2)])
    assert lib.lookup("scene one", min_seconds=2.0, width=704, height=1280) == MP4
    assert lib.lookup("scene two", min_seconds=2.0, width=704, height=1280) == MP4
    assert lib._used_ids == {"c1", "c2"}


def test_landscape_clip_skipped_for_portrait_slot():
    lib = _clip_lib([dict(LANDSCAPE_CLIP)])
    assert lib.lookup("a scene", min_seconds=2.0, width=704, height=1280) is None


def test_undersized_stored_clip_is_not_a_hit():
    lib = _clip_lib([dict(CLIP)], payload=TINY_MP4)
    assert lib.lookup("a scene", min_seconds=2.0, width=704, height=1280) is None
    assert lib._used_ids == set()  # a broken blob must not burn the row for this render


def test_clip_lookup_asks_for_kind_clip_and_the_model_pinned_style():
    lib = _clip_lib([], style="cinematic|ma14b")
    lib.lookup("a scene", min_seconds=2.0, width=720, height=1280)
    name, params = lib.supabase.calls[0]
    assert name == "match_scene_assets"
    assert params["p_kind"] == "clip"
    assert params["p_style"] == "cinematic|ma14b"


def test_fastwan_clip_is_unreachable_from_a_cinematic_a14b_render():
    # The paid A14B lane must never be served the free lane's FastWan motion (and vice
    # versa). match_scene_assets filters `style = p_style` server-side, so the model
    # suffix in the key makes those rows genuinely unreachable.
    stored = dict(CLIP, style="cinematic|mfastwan", kind="clip")
    a14b = _clip_lib([stored], style="cinematic|ma14b", supabase_cls=StyleFilteringSupabase)
    assert a14b.lookup("a scene", min_seconds=2.0, width=720, height=1280) is None

    # ...and the same row IS reachable from the free lane that produced it.
    free = _clip_lib([stored], style="cinematic|mfastwan", supabase_cls=StyleFilteringSupabase)
    assert free.lookup("a scene", min_seconds=2.0, width=704, height=1280) == MP4


def test_clip_lookup_fails_open_when_the_library_explodes():
    lib = _clip_lib([dict(CLIP)])

    def _boom(_text):
        raise RuntimeError("embedding service down")

    lib._embed = _boom
    assert lib.lookup("a scene", min_seconds=2.0, width=704, height=1280) is None


def test_clip_save_records_kind_duration_and_dimensions():
    lib = _clip_lib([])
    lib.save("a scene", MP4, seconds=5.04, width=704, height=1280)
    (path, data, opts), = lib.supabase.storage.uploads
    assert path.startswith("library/u/clips/") and path.endswith(".mp4")
    assert data == MP4
    assert opts == {"content-type": "video/mp4"}
    row, = lib.supabase.inserts
    assert row["kind"] == "clip"
    assert row["duration_sec"] == 5.04
    assert (row["width"], row["height"]) == (704, 1280)
    assert row["style"] == "cinematic|mfastwan"
    assert row["storage_path"] == path


def test_clip_save_skips_an_undersized_clip():
    lib = _clip_lib([])
    lib.save("a scene", TINY_MP4, seconds=5.0, width=704, height=1280)
    assert lib.supabase.inserts == [] and lib.supabase.storage.uploads == []


def test_clip_save_skips_an_oversized_clip():
    # Never let a too-big upload raise into a render — the bucket caps at 50MB.
    lib = _clip_lib([])
    lib.save("a scene", b"v" * (asset_library._MAX_CLIP_BYTES + 1), seconds=5.0,
             width=704, height=1280)
    assert lib.supabase.inserts == [] and lib.supabase.storage.uploads == []


def test_clip_save_fails_open_when_storage_explodes():
    lib = _clip_lib([])

    def _boom(*_a, **_k):
        raise RuntimeError("bucket on fire")

    lib.supabase.storage.upload = _boom
    lib.save("a scene", MP4, seconds=5.0, width=704, height=1280)  # must not raise
    assert lib.supabase.inserts == []
