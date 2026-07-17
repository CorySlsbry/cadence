"""B-roll specificity plumbing: build_ai_broll must ground the distiller in the whole
video (topic + full narration + direction) and feed it the already-used scenes so
every cutaway is specific and varied — the fix for 'loosely fitted' generic b-roll."""

from __future__ import annotations

import os

from cadence.synthesis.contextual import build_ai_broll


class FakeGen:
    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, prompt, aspect="9x16", style_refs=None, seed=None,
                 init_image=None, ref_image=None):
        self.prompts.append(prompt)
        # 1x1 PNG
        import base64
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
        )
        return type("R", (), {"image_bytes": png})()


class FakeDistiller:
    def __init__(self):
        self.context = None
        self.prev_seen: list[list[str]] = []
        self.n = 0

    def set_context(self, topic="", full_text="", direction=""):
        self.context = {"topic": topic, "full_text": full_text, "direction": direction}

    def distill(self, snippet, prev_scenes=None):
        self.prev_seen.append(list(prev_scenes or []))
        self.n += 1
        return f"scene {self.n}: Claude Code terminal UI", f"cap{self.n}"


def _words(n=30):
    return [(f"claude code word{i}", i * 1.0, i * 1.0 + 0.8) for i in range(n)]


def test_distiller_receives_video_context_and_prev_scenes(tmp_path):
    gen, dist = FakeGen(), FakeDistiller()
    inserts = build_ai_broll(
        _words(), 30.0, gen, out_dir=str(tmp_path), max_images=3,
        windows=[(2.0, 6.0, None), (10.0, 14.0, None), (20.0, 24.0, None)],
        distiller=dist, context_topic="Claude Code beats every other agent",
        direction="show real product UI",
    )
    assert dist.context["topic"] == "Claude Code beats every other agent"
    assert "claude code word3" in dist.context["full_text"]
    assert dist.context["direction"] == "show real product UI"
    # variety memory: first call sees [], second sees 1 prior scene, third sees 2
    assert [len(p) for p in dist.prev_seen] == [0, 1, 2]
    assert "scene 1" in dist.prev_seen[1][0]
    assert len(inserts) == 3
    assert all(os.path.exists(i.image_path) for i in inserts)


def test_legacy_distiller_without_kwargs_still_works(tmp_path):
    class OldDistiller:
        def distill(self, snippet):  # no prev_scenes kwarg, no set_context
            return "a scene", "cap"

    gen = FakeGen()
    inserts = build_ai_broll(
        _words(), 20.0, gen, out_dir=str(tmp_path), max_images=2,
        windows=[(2.0, 6.0, None), (10.0, 14.0, None)],
        distiller=OldDistiller(), context_topic="anything",
    )
    assert len(inserts) == 2
