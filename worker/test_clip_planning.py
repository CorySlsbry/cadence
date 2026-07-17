"""Faceless motion planning: who pays, who animates, who comes free from the clip library.

This is the TOKEN-ACCOUNTING contract of `cadence_worker._plan_motion_scenes` — the money
decision — plus the model-pinned clip style key. `_plan_motion_scenes` returns the exact
`to_animate` list that `_render_faceless` submits to the animate lanes
(`pool.submit(_animate_one, k, inserts[k]) for k in to_animate`, and the same list is handed
to the premium job), so "not in to_animate" IS "never animated".

Importing the worker needs the engine on the path, plus `supabase` — which the worker imports
at module scope but this unit never touches, so a stand-in covers it where it isn't installed.
"""

from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "engine")))
try:
    # Defer to the real package wherever it's installed — never shadow it for the rest of the
    # session. Probing for Client (not just importability) matters: run from the repo root, the
    # `supabase/` migrations directory imports as an empty NAMESPACE package, which satisfies
    # `import supabase` but has no Client — so the stub has to cover that too.
    from supabase import Client  # noqa: F401
except ImportError:  # cadence_worker imports Client/create_client at module scope
    _stub = types.ModuleType("supabase")
    _stub.Client = type("Client", (), {})
    _stub.create_client = lambda *a, **k: None  # pragma: no cover - never called in this unit
    sys.modules["supabase"] = _stub

from cadence.imagegen.ledger import BudgetExceeded  # noqa: E402
from cadence.models import BrollInsert  # noqa: E402

from asset_library import ClipLibrary  # noqa: E402
from cadence_worker import _clip_style_key, _plan_motion_scenes  # noqa: E402

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"v" * 6000


def _ins(start: float, end: float, prompt: str) -> BrollInsert:
    return BrollInsert(image_path=f"scene_{start}.png", start=start, end=end, prompt=prompt)


class FakeLedger:
    """Records every charge. One charge == one user token (see SupabaseCostLedger.charge)."""

    def __init__(self, allowance: int = 999) -> None:
        self.charges: list[float] = []
        self.allowance = allowance

    def charge(self, cost: float) -> float:
        if len(self.charges) >= self.allowance:
            raise BudgetExceeded("user is out of tokens")
        self.charges.append(cost)
        return sum(self.charges)


class FakeClipLib:
    def __init__(self, hits: dict[str, bytes] | None = None) -> None:
        self.hits = hits or {}
        self.looked_up: list[tuple[str, float]] = []

    def lookup(self, prompt: str, *, min_seconds: float, width: int, height: int):
        self.looked_up.append((prompt, min_seconds))
        return self.hits.get(prompt)


class RogueClipLib:
    """A library that violates its own fail-open contract — the render must survive anyway."""

    def lookup(self, prompt, *, min_seconds, width, height):
        raise RuntimeError("library exploded")


def _plan(inserts, lib, ledger, tmp):
    return _plan_motion_scenes(inserts, clip_lib=lib, ledger=ledger, tmp=str(tmp),
                               clip_w=704, clip_h=1280)


# ------------------------------------------------- (a) a hit costs 0 tokens, 0 GPU


def test_an_all_library_render_charges_nothing_and_animates_nothing(tmp_path):
    inserts = [_ins(0.0, 5.0, "scene A"), _ins(5.0, 10.0, "scene B")]
    ledger = FakeLedger()
    clips, from_library, to_animate = _plan(
        inserts, FakeClipLib({"scene A": MP4, "scene B": MP4}), ledger, tmp_path)

    assert ledger.charges == []          # 0 tokens — the library's whole contract
    assert to_animate == []              # nothing reaches the GPU
    assert from_library == {0, 1}
    assert set(clips) == {0, 1}
    with open(clips[0], "rb") as fh:     # the bytes are staged for the compositor
        assert fh.read() == MP4


def test_a_hit_is_free_while_its_neighbour_still_pays(tmp_path):
    inserts = [_ins(0.0, 5.0, "cached"), _ins(5.0, 10.0, "fresh")]
    ledger = FakeLedger()
    clips, from_library, to_animate = _plan(
        inserts, FakeClipLib({"cached": MP4}), ledger, tmp_path)

    assert from_library == {0}
    assert to_animate == [1]             # the hit is never submitted to animate
    assert len(ledger.charges) == 2      # exactly 2 tokens, all of them scene 1's


# ------------------------------------------------- (b) a miss costs exactly 2 tokens


def test_a_miss_charges_exactly_two_tokens_and_is_submitted(tmp_path):
    inserts = [_ins(0.0, 5.0, "scene A")]
    ledger = FakeLedger()
    clips, from_library, to_animate = _plan(inserts, FakeClipLib(), ledger, tmp_path)

    assert to_animate == [0]
    assert ledger.charges == [0.05, 0.05]   # 2 tokens per animated scene, unchanged
    assert clips == {} and from_library == set()


def test_every_miss_costs_two_tokens(tmp_path):
    inserts = [_ins(i * 5.0, i * 5.0 + 5.0, f"scene {i}") for i in range(4)]
    ledger = FakeLedger()
    _clips, _from_lib, to_animate = _plan(inserts, FakeClipLib(), ledger, tmp_path)

    assert to_animate == [0, 1, 2, 3]
    assert len(ledger.charges) == 8  # 4 scenes x 2 tokens


def test_no_library_is_the_pre_library_behaviour(tmp_path):
    # The CADENCE_CLIP_LIBRARY=0 kill-switch (and the no-Gemini-key path) hands clip_lib=None.
    inserts = [_ins(0.0, 5.0, "A"), _ins(5.0, 10.0, "B")]
    ledger = FakeLedger()
    clips, from_library, to_animate = _plan(inserts, None, ledger, tmp_path)

    assert clips == {} and from_library == set()
    assert to_animate == [0, 1]
    assert len(ledger.charges) == 4


def test_a_scene_with_no_prompt_is_never_looked_up(tmp_path):
    # No asset key -> nothing to match on; it just animates and pays, as it always did.
    inserts = [BrollInsert(image_path="s.png", start=0.0, end=5.0)]
    lib = FakeClipLib({"": MP4})
    ledger = FakeLedger()
    _clips, from_library, to_animate = _plan(inserts, lib, ledger, tmp_path)

    assert lib.looked_up == []
    assert from_library == set() and to_animate == [0]
    assert len(ledger.charges) == 2


# ------------------------------------------------- the budget break is preserved


def test_budget_exhaustion_stops_the_loop_and_the_rest_stay_stills(tmp_path):
    inserts = [_ins(i * 5.0, i * 5.0 + 5.0, f"scene {i}") for i in range(3)]
    ledger = FakeLedger(allowance=2)  # exactly one scene's worth of tokens
    _clips, _from_lib, to_animate = _plan(inserts, FakeClipLib(), ledger, tmp_path)

    assert to_animate == [0]          # scene 1 raised BudgetExceeded -> break
    assert len(ledger.charges) == 2   # nothing charged past the break


def test_library_hits_are_free_even_after_the_budget_is_gone(tmp_path):
    # The lookup runs BEFORE the charge, so an out-of-tokens user still gets cached motion
    # on the scenes the library covers — and the first MISS is what stops the loop.
    inserts = [_ins(0.0, 5.0, "cached"), _ins(5.0, 10.0, "fresh"), _ins(10.0, 15.0, "cached2")]
    ledger = FakeLedger(allowance=0)  # no tokens at all
    clips, from_library, to_animate = _plan(
        inserts, FakeClipLib({"cached": MP4, "cached2": MP4}), ledger, tmp_path)

    assert from_library == {0}        # scene 0 hit for free...
    assert to_animate == []           # ...scene 1 missed, couldn't pay, and broke the loop
    assert ledger.charges == []
    assert set(clips) == {0}


# ------------------------------------------------- (f) fail open


def test_a_rogue_library_never_breaks_the_render(tmp_path):
    inserts = [_ins(0.0, 5.0, "A"), _ins(5.0, 10.0, "B")]
    ledger = FakeLedger()
    clips, from_library, to_animate = _plan(inserts, RogueClipLib(), ledger, tmp_path)

    assert clips == {} and from_library == set()
    assert to_animate == [0, 1]          # every scene animates, exactly as without a library
    assert len(ledger.charges) == 4


def test_an_unstageable_hit_degrades_to_animating_that_scene(tmp_path):
    # The library handed us bytes but we couldn't write them (full disk, bad tmp) — pay and
    # animate rather than lose the scene to a still.
    inserts = [_ins(0.0, 5.0, "cached")]
    ledger = FakeLedger()
    _clips, from_library, to_animate = _plan(
        inserts, FakeClipLib({"cached": MP4}), ledger, os.path.join(str(tmp_path), "nope"))

    assert from_library == set()
    assert to_animate == [0]
    assert len(ledger.charges) == 2


# ------------------------------------------------- min_seconds covers the window


def test_each_scene_asks_for_a_clip_that_covers_its_own_window(tmp_path):
    inserts = [_ins(0.0, 5.0, "A"), _ins(5.0, 8.0, "B")]
    lib = FakeClipLib()
    _plan(inserts, lib, FakeLedger(), tmp_path)

    assert lib.looked_up == [("A", 5.0), ("B", 3.0)]


def test_each_scene_is_keyed_on_its_own_prompt_not_a_shared_one(tmp_path):
    # The regression this guards: anim_prompt is identical for every scene of a video, so
    # keying on it would match every scene to the same clip and make the whole render one shot.
    inserts = [_ins(0.0, 5.0, "a lighthouse"), _ins(5.0, 10.0, "a harbour at dawn")]
    lib = FakeClipLib()
    _plan(inserts, lib, FakeLedger(), tmp_path)

    assert [p for p, _ in lib.looked_up] == ["a lighthouse", "a harbour at dawn"]


# ------------------------------------------------- (e) the model is part of the key


def test_clip_style_key_pins_the_model():
    assert _clip_style_key("photoreal", cinematic=True) == "photoreal|ma14b"
    assert _clip_style_key("photoreal", cinematic=False) == "photoreal|mfastwan"


def test_clip_style_key_keeps_the_direction_hash():
    assert _clip_style_key("anime|dabc12345", cinematic=True) == "anime|dabc12345|ma14b"


def test_the_two_motion_lanes_can_never_share_a_key():
    for style in ("photoreal", "anime|dabc12345", ""):
        assert _clip_style_key(style, cinematic=True) != _clip_style_key(style, cinematic=False)


def test_the_clip_key_extends_the_image_key_rather_than_replacing_it():
    # The image library must keep addressing its own rows — changing lib_style would orphan
    # every still ever stored.
    lib_style = "photoreal|dabc12345"
    assert _clip_style_key(lib_style, cinematic=False).startswith(lib_style + "|m")


# ------------------------------------------------- (c) the REAL library, end to end


class _Exec:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _Storage:
    def from_(self, _bucket):
        return self

    def download(self, _path):
        return MP4


class _Supabase:
    """Enough of the client for ClipLibrary: match_scene_assets + touch_scene_asset."""

    def __init__(self, rows):
        self.rows = rows
        self.storage = _Storage()

    def rpc(self, name, _params):
        return _Exec(self.rows if name == "match_scene_assets" else None)


def _real_clip_lib(rows):
    lib = ClipLibrary(_Supabase(rows), "key", user_id="u", style="photoreal|mfastwan")
    lib._embed = lambda _text: [0.0] * 768  # no network
    return lib


def test_one_stored_clip_serves_one_scene_and_the_rest_pay(tmp_path):
    # The real library + the real planner. Two near-identical scenes, ONE stored clip: the
    # first scene reuses it free, the second must NOT get the same footage again (a repeat
    # reads as a broken video) — it pays its 2 tokens and animates.
    row = {"id": "c1", "storage_path": "library/u/clips/c1.mp4", "similarity": 0.97,
           "width": 704, "height": 1280, "duration_sec": 5.04}
    lib = _real_clip_lib([row])
    ledger = FakeLedger()
    inserts = [_ins(0.0, 5.0, "a lighthouse at dusk"), _ins(5.0, 10.0, "a lighthouse at night")]

    clips, from_library, to_animate = _plan(inserts, lib, ledger, tmp_path)

    assert from_library == {0}
    assert to_animate == [1]
    assert len(ledger.charges) == 2   # only the second scene paid
    with open(clips[0], "rb") as fh:
        assert fh.read() == MP4


def test_a_stored_clip_too_short_for_the_window_is_never_served(tmp_path):
    # 2s of footage cannot carry a 5s scene — the compositor would freeze on its last frame.
    row = {"id": "c1", "storage_path": "library/u/clips/c1.mp4", "similarity": 0.99,
           "width": 704, "height": 1280, "duration_sec": 2.0}
    lib = _real_clip_lib([row])
    ledger = FakeLedger()

    clips, from_library, to_animate = _plan(inserts=[_ins(0.0, 5.0, "a lighthouse")],
                                            lib=lib, ledger=ledger, tmp=tmp_path)

    assert clips == {} and from_library == set()
    assert to_animate == [0] and len(ledger.charges) == 2
