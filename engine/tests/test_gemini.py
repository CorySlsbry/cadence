"""Tests for the robust Gemini JSON helper — the lenient parse + backoff retry + model
fallback that stops a transient 503 or a trailing-comma reply from silently demoting a
creator feature to its stub.

These reproduce the failures observed live on Cloud Run:
  * ``find_clip_moments`` -> JSONDecodeError on a trailing comma (parse must tolerate it)
  * ``find_clip_moments`` / ``build_repurpose`` -> 503 UNAVAILABLE: gemini-2.5-flash overloads
    intermittently (retry, then fall over to a less-loaded model)
"""

from __future__ import annotations

import pytest

from cadence._gemini import (
    _FALLBACK_MODELS,
    gemini_json,
    is_model_unavailable,
    is_retryable,
    lenient_json_loads,
)

_PRIMARY = "gemini-2.5-flash"  # not in _FALLBACK_MODELS, so fallback count is deterministic


class _Resp:
    def __init__(self, text: str | None) -> None:
        self.text = text


class _Models:
    """Fake ``client.models``. ``script`` maps a model name -> a single outcome or a list of
    per-call outcomes (str reply text, or an Exception to raise); ``default`` covers models not
    in ``script``. A model's last scripted outcome repeats. Records every model called, in order."""

    def __init__(self, script: dict | None = None, default=None) -> None:
        self.script = script or {}
        self.default = default
        self.calls: list[str] = []

    def generate_content(self, *, model, contents, config):  # noqa: ANN001 - test stub
        self.calls.append(model)
        outcomes = self.script.get(model, self.default)
        if outcomes is None:
            raise AssertionError(f"no scripted outcome for model {model!r}")
        seq = outcomes if isinstance(outcomes, list) else [outcomes]
        outcome = seq[min(self.calls.count(model) - 1, len(seq) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return _Resp(outcome)


class _Client:
    def __init__(self, script: dict | None = None, default=None) -> None:
        self.models = _Models(script, default)


_NOSLEEP = lambda _d: None  # noqa: E731 - retry without real delay in tests
_503 = Exception("503 UNAVAILABLE: model is experiencing high demand")
_400 = Exception("400 INVALID_ARGUMENT")
_404 = Exception("404 NOT_FOUND: model models/gemini-x is not found")


class TestLenientJsonLoads:
    def test_parses_plain_object(self):
        assert lenient_json_loads('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}

    def test_strips_markdown_fences(self):
        assert lenient_json_loads('```json\n{"a": 1}\n```') == {"a": 1}

    def test_tolerates_trailing_comma(self):
        # The exact live failure: Gemini emitted a trailing comma before the closing brace.
        assert lenient_json_loads('{"clips": [{"start": 1}], }') == {"clips": [{"start": 1}]}

    def test_tolerates_trailing_comma_in_array(self):
        assert lenient_json_loads('{"hooks": ["a", "b",]}') == {"hooks": ["a", "b"]}

    def test_extracts_object_from_surrounding_prose(self):
        assert lenient_json_loads('Sure! Here you go:\n{"ok": true}\nHope that helps.') == {"ok": True}

    def test_non_dict_top_level_becomes_empty_dict(self):
        assert lenient_json_loads("[1, 2, 3]") == {}

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_empty_raises_value_error(self, bad):
        with pytest.raises(ValueError):
            lenient_json_loads(bad)

    def test_unparseable_raises_value_error(self):
        with pytest.raises(ValueError):
            lenient_json_loads("definitely not json {")


class TestIsRetryable:
    @pytest.mark.parametrize("msg", [
        "503 UNAVAILABLE high demand",
        "429 RESOURCE_EXHAUSTED",
        "model is overloaded, please try again",
        "500 INTERNAL",
    ])
    def test_transient_api_errors_are_retryable(self, msg):
        assert is_retryable(Exception(msg)) is True

    def test_empty_or_garbled_json_is_retryable(self):
        assert is_retryable(ValueError("empty Gemini response")) is True

    @pytest.mark.parametrize("msg", [
        "400 INVALID_ARGUMENT",
        "403 PERMISSION_DENIED",
        "404 NOT_FOUND",
    ])
    def test_client_errors_are_not_retryable(self, msg):
        assert is_retryable(Exception(msg)) is False


class TestIsModelUnavailable:
    @pytest.mark.parametrize("msg", [
        "404 NOT_FOUND: model not found",
        "model models/gemini-x does not exist",
        "this model is not supported",
    ])
    def test_unavailable_model_errors(self, msg):
        assert is_model_unavailable(Exception(msg)) is True

    @pytest.mark.parametrize("msg", ["503 UNAVAILABLE", "400 INVALID_ARGUMENT", "403 PERMISSION_DENIED"])
    def test_other_errors_are_not_model_unavailable(self, msg):
        assert is_model_unavailable(Exception(msg)) is False


class TestGeminiJson:
    def test_returns_parsed_dict_on_first_success(self):
        client = _Client(default='{"scene": "kitchen"}')
        assert gemini_json(client, _PRIMARY, "p", sleep=_NOSLEEP) == {"scene": "kitchen"}
        assert client.models.calls == [_PRIMARY]

    def test_parses_trailing_comma_without_retry(self):
        client = _Client(default='{"a": 1,}')
        assert gemini_json(client, _PRIMARY, "p", sleep=_NOSLEEP) == {"a": 1}
        assert client.models.calls == [_PRIMARY]  # lenient parse fixes it in place

    def test_retries_transient_503_on_same_model_then_succeeds(self):
        client = _Client(script={_PRIMARY: [_503, '{"ok": true}']})
        assert gemini_json(client, _PRIMARY, "p", attempts=2, sleep=_NOSLEEP) == {"ok": True}
        assert client.models.calls == [_PRIMARY, _PRIMARY]

    def test_retries_empty_reply_then_succeeds(self):
        client = _Client(script={_PRIMARY: ["", '{"ok": true}']})
        assert gemini_json(client, _PRIMARY, "p", attempts=2, sleep=_NOSLEEP) == {"ok": True}
        assert client.models.calls == [_PRIMARY, _PRIMARY]

    def test_falls_over_to_next_model_when_primary_stays_overloaded(self):
        # The live failure: primary 503s through its retries; a less-loaded model serves it.
        client = _Client(script={_PRIMARY: _503, _FALLBACK_MODELS[0]: '{"ok": true}'})
        assert gemini_json(client, _PRIMARY, "p", attempts=2, sleep=_NOSLEEP) == {"ok": True}
        assert client.models.calls == [_PRIMARY, _PRIMARY, _FALLBACK_MODELS[0]]

    def test_falls_over_on_404_without_retrying_that_model(self):
        # A 404 (deprecated/uncallable model) must skip to the next model, not retry or abort.
        client = _Client(script={_PRIMARY: _404, _FALLBACK_MODELS[0]: '{"ok": true}'})
        assert gemini_json(client, _PRIMARY, "p", attempts=2, sleep=_NOSLEEP) == {"ok": True}
        assert client.models.calls == [_PRIMARY, _FALLBACK_MODELS[0]]  # primary tried once, no retry

    def test_does_not_retry_or_fall_over_on_client_error(self):
        client = _Client(script={_PRIMARY: _400}, default='{"ok": true}')
        with pytest.raises(Exception, match="400"):
            gemini_json(client, _PRIMARY, "p", attempts=2, sleep=_NOSLEEP)
        assert client.models.calls == [_PRIMARY]  # bail immediately, no fallback

    def test_gives_up_after_all_models_and_raises_last(self):
        client = _Client(default=_503)  # every model overloaded
        with pytest.raises(Exception, match="503"):
            gemini_json(client, _PRIMARY, "p", attempts=2, sleep=_NOSLEEP)
        expected_models = 1 + len(_FALLBACK_MODELS)  # _PRIMARY is not itself a fallback
        assert len(client.models.calls) == expected_models * 2
        assert set(client.models.calls) == {_PRIMARY, *_FALLBACK_MODELS}
