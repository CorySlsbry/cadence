"""Unit tests for per-platform social caption generation + hard limit enforcement."""

from __future__ import annotations

from cadence.social.captions import (
    LIMITS,
    StubCaptionWriter,
    build_social_captions,
    clean_hashtags,
    clean_mentions,
    normalize,
    to_post_text,
    trim_text,
)


def test_clean_hashtags_dedupes_caps_and_forces_prefix():
    tags = ["creator", "#Creator", "short form!", "#video", "#video", "ai", "extra"]
    out = clean_hashtags(tags, 5)
    assert out == ["#creator", "#shortform", "#video", "#ai", "#extra"]  # de-duped, '#'-prefixed, capped at 5


def test_clean_hashtags_ensure_is_present_and_counts_toward_cap():
    out = clean_hashtags(["#a", "#b", "#c"], 3, ensure=["#Shorts"])
    assert out[0] == "#Shorts"
    assert len(out) == 3 and "#c" not in out  # #Shorts guaranteed, total still capped at 3


def test_clean_mentions_forces_at_prefix_and_dedupes():
    assert clean_mentions(["@cory", "cory", "Brand", "@brand "], 5) == ["@cory", "@Brand"]


def test_trim_text_breaks_on_word_boundary():
    text = "the quick brown fox jumps over the lazy dog"
    out = trim_text(text, 18)
    assert len(out) <= 18 and not out.endswith(" ") and " " in out and text.startswith(out)


def test_normalize_enforces_every_limit_and_youtube_shorts_tag():
    raw = {
        "tiktok": {"caption": "x" * 5000, "hashtags": [f"#t{i}" for i in range(12)], "mentions": ["@a", "@b", "@c", "@d"]},
        "instagram": {"caption": "hi", "hashtags": [f"#i{i}" for i in range(9)], "mentions": []},
        "youtube": {"title": "y" * 200, "description": "d" * 9000, "hashtags": ["#one", "#two"]},
    }
    n = normalize(raw)
    assert len(n["tiktok"]["caption"]) <= LIMITS["tiktok"]["caption"]
    assert len(n["tiktok"]["hashtags"]) == 5 and len(n["tiktok"]["mentions"]) == 3
    assert len(n["instagram"]["hashtags"]) == 5
    assert len(n["youtube"]["title"]) <= 100 and len(n["youtube"]["description"]) <= 5000
    assert n["youtube"]["hashtags"][0] == "#Shorts"  # always injected, even when absent from the draft


def test_build_social_captions_with_stub_returns_full_structure():
    caps = build_social_captions("Today I tested three AI video tools. Here is what won.", StubCaptionWriter(), product="Cadence")
    assert set(caps) == {"tiktok", "instagram", "youtube"}
    assert caps["youtube"]["title"] and caps["tiktok"]["caption"].endswith("Made with Cadence.")
    assert caps["youtube"]["hashtags"][0] == "#Shorts"


def test_build_falls_back_when_writer_raises():
    class Boom:
        def write(self, *a, **k):
            raise RuntimeError("llm down")

    caps = build_social_captions("hello world", Boom())  # must not raise
    assert caps["tiktok"]["caption"]  # fell back to the deterministic stub draft


def test_to_post_text_assembles_per_platform():
    tt = {"caption": "Watch this", "hashtags": ["#a", "#b"], "mentions": ["@x"]}
    assert to_post_text("tiktok", tt) == "Watch this\n\n@x #a #b"
    yt = {"title": "T", "description": "Desc here", "hashtags": ["#Shorts"]}
    assert to_post_text("youtube", yt) == "Desc here\n\n#Shorts"  # title is separate; text = description + tags
