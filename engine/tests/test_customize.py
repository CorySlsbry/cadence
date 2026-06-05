"""Unit tests for parse_customization — the single source of truth that turns the
Studio control-panel JSON into engine configs + cinematography + feature toggles.
The web client and the render worker both depend on this mapping being exact."""

from __future__ import annotations

import pytest

from cadence.customize import parse_customization


def test_defaults_are_production_safe():
    c = parse_customization({})
    assert c.cleaning.remove_silence is True
    assert c.cleaning.detect_retakes is True
    assert c.cleaning.remove_fillers is True
    assert c.synthesis.smart_zoom is True
    assert c.toggles.captions is True
    assert c.toggles.watermark is True
    assert c.broll_mode == "ai"
    assert c.toggles.background_replace is False
    assert c.toggles.letterbox is False


def test_grade_intensity_defaults_to_seventy_percent():
    assert parse_customization({}).grade_intensity == pytest.approx(0.7)


def test_grade_intensity_is_normalized_to_unit_interval():
    assert parse_customization({"grade_intensity": 50}).grade_intensity == pytest.approx(0.5)


def test_auto_clean_off_gates_every_cleaning_stage():
    c = parse_customization({"auto_clean": False})
    assert c.cleaning.remove_silence is False
    assert c.cleaning.detect_retakes is False
    assert c.cleaning.remove_fillers is False
    assert c.toggles.auto_clean is False


def test_cut_sensitivity_maps_to_silence_thresholds():
    gentle = parse_customization({"cut_sensitivity": "gentle"}).cleaning
    aggressive = parse_customization({"cut_sensitivity": "aggressive"}).cleaning
    assert gentle.min_silence_sec == pytest.approx(0.45)
    assert aggressive.min_silence_sec == pytest.approx(0.22)
    # A higher (less-negative) floor means more audio is treated as silence -> more cuts.
    assert aggressive.silence_db > gentle.silence_db


def test_word_snap_stays_on_by_default():
    assert parse_customization({}).cleaning.snap_cuts_to_words is True


def test_film_stock_grade_override_matches_the_stock_recipe():
    c = parse_customization({"film_stock": "teal_orange"})
    assert c.grade_override == {
        "saturation": 1.18,
        "temperature": 0.22,
        "shadow_balance": -0.18,
    }


def test_longer_lens_biases_a_stronger_punch_in():
    short = parse_customization({"lens": "35mm"}).synthesis.zoom_factor
    long = parse_customization({"lens": "85mm"}).synthesis.zoom_factor
    assert long == pytest.approx(1.15)
    assert short == pytest.approx(1.12)  # max(default 1.12, 35mm bias 1.10)
    assert long > short


def test_color_grade_toggle_off_disables_reference_grade():
    c = parse_customization({"color_grade": False})
    assert c.toggles.color_grade is False
    assert c.synthesis.color_grade_to_reference is False


def test_letterbox_can_be_set_by_framing_or_flag():
    assert parse_customization({"framing": "letterbox_239"}).toggles.letterbox is True
    assert parse_customization({"letterbox": True}).toggles.letterbox is True
    assert parse_customization({}).toggles.letterbox is False


def test_background_broll_mode_sets_the_replace_toggle():
    c = parse_customization({"broll_mode": "background"})
    assert c.toggles.background_replace is True
    assert c.broll_mode == "background"


def test_broll_paths_pass_through_for_the_worker():
    c = parse_customization({"broll_paths": ["u/a.png", "u/b.png"]})
    assert c.broll_paths == ["u/a.png", "u/b.png"]


def test_preset_bundle_applies_then_explicit_field_overrides_win():
    # cinematic_film = anamorphic + vision3 + letterbox; caller overrides just the lens.
    c = parse_customization({"preset": "cinematic_film", "lens": "50mm"})
    assert c.cinematography.film_stock == "vision3"   # from the preset
    assert c.toggles.letterbox is True                # preset framing == letterbox_239
    assert c.cinematography.film_grain_amount == pytest.approx(16.0)  # spec §D value
    assert c.cinematography.lens == "50mm"            # explicit override beats the preset


def test_clean_ugc_preset_turns_ai_broll_off():
    c = parse_customization({"preset": "clean_ugc"})
    assert c.toggles.ai_broll is False


def test_engine_presets_match_spec_values():
    # A preset-only API call must render identically to the Studio. These specific
    # values had drifted between engine PRESETS and the spec §D / UI.
    cf = parse_customization({"preset": "cinematic_film"})
    assert cf.cinematography.aperture == pytest.approx(2.8)
    assert cf.cinematography.film_grain_amount == pytest.approx(16.0)
    ugc = parse_customization({"preset": "clean_ugc"})
    assert ugc.cinematography.lighting == "high_key"
    assert ugc.cinematography.aperture == pytest.approx(5.6)
    assert parse_customization({"preset": "cinematic"}).cinematography.lighting == "soft_natural"


def test_crossfade_ms_overrides_the_default_when_provided():
    assert parse_customization({"crossfade_ms": 35}).synthesis.audio_crossfade_ms == 35
    assert parse_customization({"audio_crossfade": False, "crossfade_ms": 35}).synthesis.audio_crossfade_ms == 0
    assert parse_customization({}).synthesis.audio_crossfade_ms == 18  # config default untouched
