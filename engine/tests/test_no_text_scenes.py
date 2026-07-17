"""Generated scenes must never contain text — the burned-in captions carry all the words.

Owner's rule after a render shipped a garbled title and a fake chat UI: "The text is garbled.
If we cant do text, dont. Rely on the captioning."

Text got into frame from THREE places, and each is guarded here:
  1. the scene-prompt templates, which ordered the caption rendered onto a screen/sign;
  2. the self-host anti-text rule, which permitted "soft, blurred, illegible" text — i.e. it
     licensed gibberish;
  3. the Gemini distiller, which ASKED for a product's "ACTUAL user interface" (a chat thread,
     a CLI pane, a "model picker reading the model name") — the real origin of the garbling.
"""

from __future__ import annotations

from cadence.imagegen.distill import _SYSTEM
from cadence.imagegen.selfhost import _ANTI_TEXT, _ANTI_TEXT_MARK, _augment_prompt
from cadence.synthesis.contextual import (
    _NO_TEXT_RULE,
    build_ai_broll,
    build_ai_prompt,
    build_ai_prompt_scene,
)
from tests.test_scene_styles import _CaptureGen, _WORDS

# Words that must never appear as an ORDER in a prompt. "illegible"/"blurred" are the subtle
# ones: permitting unreadable text is permitting text, and the model duly drew gibberish.
_LICENSING_WORDS = ("illegible", "blurred", "garbled")


# --------------------------------------------------------------------------- #
# 1. The self-host anti-text rule + its double-append guard
# --------------------------------------------------------------------------- #
def test_anti_text_is_absolute_and_never_licenses_unreadable_text():
    low = _ANTI_TEXT.lower()
    for word in _LICENSING_WORDS:
        assert word not in low, f"_ANTI_TEXT must not say {word!r} — it invites gibberish text"
    assert "no text anywhere" in low


def test_augment_prompt_appends_the_rule():
    out = _augment_prompt("a cat on a wall")
    assert _ANTI_TEXT.strip() in out
    assert out.startswith("a cat on a wall")


def test_augment_prompt_does_not_double_append():
    """The guard, forward: augmenting twice must be identical to augmenting once."""
    once = _augment_prompt("a cat on a wall")
    twice = _augment_prompt(once)
    assert once == twice
    assert once.lower().count(_ANTI_TEXT_MARK.lower()) == 1


def test_augment_prompt_guard_sentinel_is_actually_present_in_the_rule():
    """The guard, backward: the sentinel MUST appear in the text it guards.

    This is the invariant the old guard lost. It sniffed for the word "illegible", which was
    an incidental adjective — re-wording _ANTI_TEXT silently stopped the guard matching and
    would have double-appended forever. If someone re-words _ANTI_TEXT and drops the mark,
    fail HERE rather than in production.
    """
    assert _ANTI_TEXT_MARK in _ANTI_TEXT, "the guard sentinel must appear in the rule it guards"
    # ...and must not false-positive on an un-augmented prompt, or fresh prompts would silently
    # skip augmentation altogether (the guard failing "open" instead of "closed").
    assert _ANTI_TEXT_MARK not in "a courier sprinting a package down a sunlit street"
    assert _ANTI_TEXT.strip() in _augment_prompt("a courier sprinting down a sunlit street")


def test_augment_prompt_handles_empty_and_none():
    """Degenerate inputs still carry the rule (they leave a cosmetic leading '.', which is
    pre-existing and unreachable in practice — prompts are never empty)."""
    for value in ("", None):
        out = _augment_prompt(value)  # type: ignore[arg-type]
        assert _ANTI_TEXT_MARK in out
        assert out.endswith("objects.")


# --------------------------------------------------------------------------- #
# 2. The scene-prompt templates
# --------------------------------------------------------------------------- #
def test_no_text_rule_names_the_offenders_and_the_alternative():
    low = _NO_TEXT_RULE.lower()
    for banned in ("letters", "words", "headlines", "titles", "captions", "signage",
                   "chat windows", "screens with writing"):
        assert banned in low, f"_NO_TEXT_RULE should name {banned!r}"
    # Affirmative-negative: say what to do INSTEAD, not just what to avoid.
    for alt in ("people", "places", "action", "objects"):
        assert alt in low


def test_scene_prompt_never_orders_the_caption_rendered():
    """Both branches: the caption is for the PIL overlay, never for the model."""
    photo = build_ai_prompt_scene("a courier sprinting downhill", "Ship Fast")
    clay = build_ai_prompt_scene("a courier sprinting downhill", "Ship Fast",
                                 style_override="handcrafted claymation stop-motion scene")
    for prompt in (photo, clay):
        assert "Ship Fast" not in prompt, "the caption must never reach the image model"
        assert _NO_TEXT_RULE in prompt
        assert "typography" not in prompt.lower()
    # ...and the styles still do their job (the look is untouched by the no-text fix).
    assert "hyperrealistic" in photo
    assert "claymation" in clay and "hyperrealistic" not in clay


def test_legacy_lexical_prompt_carries_the_rule_too():
    p = build_ai_prompt("claude skills", "Claude Skills")
    assert _NO_TEXT_RULE in p
    assert "Claude Skills" not in p


def test_generated_prompts_never_ask_for_text_end_to_end(tmp_path):
    """The real path: whatever build_ai_broll sends a generator must carry the no-text rule."""
    gen = _CaptureGen()
    build_ai_broll(_WORDS, 8.0, gen, out_dir=str(tmp_path), windows=[(0.0, 4.0, None)])
    assert gen.prompts, "expected a generated prompt"
    for prompt in gen.prompts:
        assert _NO_TEXT_RULE in prompt
        low = prompt.lower()
        for word in _LICENSING_WORDS:
            # "no garbled text" used to appear as a (useless) negative; the rule is absolute now.
            assert word not in low, f"prompt should not mention {word!r}"


# --------------------------------------------------------------------------- #
# 3. The distiller — where the garbled chat UI actually came from
# --------------------------------------------------------------------------- #
def test_distiller_never_asks_for_a_ui_or_a_screen():
    low = _SYSTEM.lower()
    # The exact instructions that produced the shipped defect must be gone.
    assert "actual user interface" not in low
    assert "model picker reading the model name" not in low
    assert "its chat ui" not in low
    assert "message bubbles" not in low
    # ...replaced by an explicit ban.
    assert "no-text contract" in low
    for banned in ("chat windows", "terminals", "signage", "headlines"):
        assert banned in low, f"the distiller should explicitly forbid {banned!r}"
    # Depict through people/places/action/objects instead.
    for alt in ("people", "places", "action", "objects"):
        assert alt in low


def test_distiller_keeps_the_specificity_contract():
    """The no-text fix must not regress into generic stock imagery — that was a prior bug."""
    low = _SYSTEM.lower()
    assert "specificity contract" in low
    assert "never substitute a generic metaphor" in low
    assert "server racks" in low  # still named as the thing NOT to do
    assert "variety" in low


def test_distiller_caption_is_marked_as_never_rendered():
    low = _SYSTEM.lower()
    assert "never rendered into the scene" in low
