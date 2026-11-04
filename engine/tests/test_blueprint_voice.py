"""Brand-blueprint personalization: the prompt-context formatter and the voice
pass-through on hooks / repurpose / captions builders."""

from __future__ import annotations

from cadence.social import build_hooks, build_repurpose, build_social_captions
from cadence.social.blueprint import blueprint_context
from cadence.social.captions import StubCaptionWriter

BP = {
    "icp": {"who": "busy contractors", "pains": ["no time", "bad books"], "goals": ["growth"], "watches": "job-site shorts"},
    "pillars": [{"name": "AI for trades", "why": "lived it"}, {"name": "Back office", "why": "expert"}],
    "voice": {"tone": "direct, warm", "pov": "blue-collar tech translator", "phrases": ["here's the play", "no fluff"]},
}


class CapturingLLM:
    def __init__(self, raw):
        self.raw = raw
        self.prompt = ""

    def complete(self, prompt):
        self.prompt = prompt
        return self.raw


def test_blueprint_context_formats_all_sections():
    ctx = blueprint_context(BP)
    assert "CREATOR VOICE" in ctx
    assert "busy contractors" in ctx
    assert "AI for trades; Back office" in ctx
    assert "direct, warm" in ctx
    assert "here's the play" in ctx


def test_blueprint_context_empty_inputs_are_noop():
    assert blueprint_context(None) == ""
    assert blueprint_context({}) == ""
    assert blueprint_context({"icp": {}, "pillars": [], "voice": {}}) == ""


def test_build_hooks_injects_voice_into_prompt():
    llm = CapturingLLM({"hooks": ["a"], "cold_open": {"line": "x", "why": "y"}})
    ctx = blueprint_context(BP)
    build_hooks("Some transcript text.", llm, voice=ctx)
    assert "CREATOR VOICE" in llm.prompt and "Transcript:" in llm.prompt
    # voice block sits between the instructions and the transcript
    assert llm.prompt.index("CREATOR VOICE") < llm.prompt.index("Transcript:")


def test_build_repurpose_injects_voice_into_prompt():
    llm = CapturingLLM({"carousel": ["a"], "thread": ["b"], "newsletter": "c", "quote_cards": ["d"]})
    build_repurpose("Some transcript text.", llm, voice=blueprint_context(BP))
    assert "CREATOR VOICE" in llm.prompt


def test_build_social_captions_voice_passthrough_safe_with_stub():
    # The stub writer accepts (and ignores) voice — captions still normalize fine.
    out = build_social_captions("Hello world. More text.", StubCaptionWriter(), voice=blueprint_context(BP))
    assert out["tiktok"]["caption"]


def test_builders_without_voice_unchanged():
    llm = CapturingLLM({"hooks": ["a"], "cold_open": {"line": "x", "why": "y"}})
    build_hooks("Some transcript text.", llm)
    assert "CREATOR VOICE" not in llm.prompt
