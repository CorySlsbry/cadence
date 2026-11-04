"""4K render plumbing: the `resolution` customization drives SynthesisConfig dims,
which carry through the GenerationPlan (renderer/captions/b-roll all read plan.width)."""

from __future__ import annotations

from cadence.customize import parse_customization


def test_default_resolution_is_1080p():
    ctrl = parse_customization({})
    assert (ctrl.synthesis.width, ctrl.synthesis.height) == (1080, 1920)


def test_4k_resolution_sets_2160x3840():
    for alias in ("4k", "4K", "2160p", "UHD"):
        ctrl = parse_customization({"resolution": alias})
        assert (ctrl.synthesis.width, ctrl.synthesis.height) == (2160, 3840), alias


def test_unknown_resolution_falls_back_to_1080p():
    ctrl = parse_customization({"resolution": "720p"})
    assert (ctrl.synthesis.width, ctrl.synthesis.height) == (1080, 1920)


def test_4k_composes_with_preset():
    ctrl = parse_customization({"preset": "cinematic", "resolution": "4k"})
    assert (ctrl.synthesis.width, ctrl.synthesis.height) == (2160, 3840)
    assert ctrl.toggles.captions  # preset untouched by the resolution override
