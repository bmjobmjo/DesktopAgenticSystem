import json
import sys

from core.common_data_area import CommonDataArea
from llm.openrouter_client import OpenRouterClient


class _FakeStreamingResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)


def test_openrouter_includes_temperature_setting(monkeypatch):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("openrouter_api_key", "test-key")
    cda.set_setting("openrouter_model", "google/gemini-2.5-flash")
    cda.set_setting("openrouter_temperature", 1.35)
    cda.set_setting("openrouter_top_p", 0.42)
    cda.set_setting("openrouter_seed", "123")
    cda.set_setting("openrouter_provider_order", "Google, Fireworks")
    cda.set_setting("openrouter_allow_fallbacks", False)
    cda.set_setting("openrouter_require_parameters", True)
    cda.set_setting("openrouter_include_reasoning", True)

    captured = {}

    def _fake_urlopen(request, timeout=120):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeStreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n',
                b'data: {"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n',
                b"data: [DONE]\n",
            ]
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = OpenRouterClient(cda)
    monkeypatch.setattr(client, "_log_usage", lambda *args, **kwargs: None)

    out = client.generate("hello")

    assert out == "ok"
    assert captured["payload"]["temperature"] == 1.35
    assert captured["payload"]["top_p"] == 0.42
    assert captured["payload"]["seed"] == 123
    assert captured["payload"]["include_reasoning"] is True
    assert captured["payload"]["provider"]["order"] == ["Google", "Fireworks"]
    assert captured["payload"]["provider"]["allow_fallbacks"] is False
    assert captured["payload"]["provider"]["require_parameters"] is True


def test_openrouter_temperature_is_clamped(monkeypatch):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("openrouter_api_key", "test-key")
    cda.set_setting("openrouter_model", "google/gemini-2.5-flash")
    cda.set_setting("openrouter_temperature", 9.0)
    cda.set_setting("openrouter_top_p", 9.0)
    cda.set_setting("openrouter_include_reasoning", False)

    captured = {}

    def _fake_urlopen(request, timeout=120):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeStreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n',
                b"data: [DONE]\n",
            ]
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = OpenRouterClient(cda)
    monkeypatch.setattr(client, "_log_usage", lambda *args, **kwargs: None)

    client.generate("hello")

    assert captured["payload"]["temperature"] == 2.0
    assert captured["payload"]["top_p"] == 1.0
    assert "include_reasoning" not in captured["payload"]


def test_openrouter_handles_missing_stdout(monkeypatch):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("openrouter_api_key", "test-key")
    cda.set_setting("openrouter_model", "google/gemini-2.5-flash")

    def _fake_urlopen(request, timeout=120):
        return _FakeStreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n',
                b'data: {"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n',
                b"data: [DONE]\n",
            ]
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr(sys, "stdout", None)
    client = OpenRouterClient(cda)
    monkeypatch.setattr(client, "_log_usage", lambda *args, **kwargs: None)

    assert client.generate("hello") == "ok"
