import json

import pytest

from config import RuntimeConfig
from runtime import needs_fallback, generate, local_chat, gateway_fallback, _post_json


def _cfg(**overrides):
    base = RuntimeConfig()
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ── needs_fallback ──────────────────────────────────────────────────────────


def test_needs_fallback_never_auto_triggers():
    """Fallback is disabled by default; only FORCE_FALLBACK can trigger it."""
    needs, reason = needs_fallback("Please answer in Hindi", "Here is your answer in English only.")
    assert needs is False
    assert reason == ""


def test_needs_fallback_false_for_any_prompt_draft():
    prompt = "Tell me a joke in English"
    draft = "Here is a short joke in English."
    needs, reason = needs_fallback(prompt, draft)
    assert needs is False
    assert reason == ""


# ── local_chat ──────────────────────────────────────────────────────────────


def test_local_chat_primary_succeeds(monkeypatch):
    cfg = _cfg(local_backend="llamacpp")

    def fake_llamacpp(cfg, messages):
        return "answer from llamacpp"

    monkeypatch.setattr("runtime._chat_with_llamacpp", fake_llamacpp)

    text, backend = local_chat(cfg, "hello")
    assert text == "answer from llamacpp"
    assert backend == "llamacpp"


def test_local_chat_primary_fails_secondary_succeeds(monkeypatch):
    cfg = _cfg(local_backend="llamacpp")

    def failing_llamacpp(cfg, messages):
        raise RuntimeError("llamacpp down")

    def fake_ollama(cfg, messages):
        return "answer from ollama"

    monkeypatch.setattr("runtime._chat_with_llamacpp", failing_llamacpp)
    monkeypatch.setattr("runtime._chat_with_ollama", fake_ollama)

    text, backend = local_chat(cfg, "hello")
    assert text == "answer from ollama"
    assert backend == "ollama"


def test_local_chat_primary_empty_falls_to_secondary(monkeypatch):
    cfg = _cfg(local_backend="ollama")

    def empty_ollama(cfg, messages):
        return ""

    def fake_llamacpp(cfg, messages):
        return "llamacpp answer"

    monkeypatch.setattr("runtime._chat_with_ollama", empty_ollama)
    monkeypatch.setattr("runtime._chat_with_llamacpp", fake_llamacpp)

    text, backend = local_chat(cfg, "hello")
    assert text == "llamacpp answer"
    assert backend == "llamacpp"


def test_local_chat_both_fail(monkeypatch):
    cfg = _cfg(local_backend="llamacpp")

    def fail(cfg, messages):
        raise RuntimeError("down")

    monkeypatch.setattr("runtime._chat_with_llamacpp", fail)
    monkeypatch.setattr("runtime._chat_with_ollama", fail)

    with pytest.raises(RuntimeError, match="all local backends failed"):
        local_chat(cfg, "hello")


def test_local_chat_ollama_primary_uses_llamacpp_secondary(monkeypatch):
    cfg = _cfg(local_backend="ollama")
    calls = []

    def failing_ollama(cfg, messages):
        calls.append("ollama")
        raise RuntimeError("down")

    def fake_llamacpp(cfg, messages):
        calls.append("llamacpp")
        return "ok"

    monkeypatch.setattr("runtime._chat_with_ollama", failing_ollama)
    monkeypatch.setattr("runtime._chat_with_llamacpp", fake_llamacpp)

    text, backend = local_chat(cfg, "hello")
    assert calls == ["ollama", "llamacpp"]
    assert backend == "llamacpp"


# ── gateway_fallback ────────────────────────────────────────────────────────


def test_gateway_fallback_sends_correct_headers(monkeypatch):
    cfg = _cfg(
        gateway_url="http://server/v1/fallback",
        gateway_device_token="secret-token",
        device_id="pi-01",
    )
    captured = {}

    def fake_post_json(url, payload, headers, timeout_seconds):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"answer": "polished"}

    monkeypatch.setattr("runtime._post_json", fake_post_json)

    result = gateway_fallback(cfg, "prompt", "draft", "reason")
    assert result == "polished"
    assert captured["url"] == "http://server/v1/fallback"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["headers"]["x-device-id"] == "pi-01"
    assert captured["payload"] == {"prompt": "prompt", "draft": "draft", "reason": "reason"}


def test_gateway_fallback_omits_auth_when_no_token(monkeypatch):
    cfg = _cfg(
        gateway_url="http://server/v1/fallback",
        gateway_device_token="",
        device_id="",
    )

    captured = {}

    def fake_post_json(url, payload, headers, timeout_seconds):
        captured["headers"] = headers
        return {"answer": "ok"}

    monkeypatch.setattr("runtime._post_json", fake_post_json)

    gateway_fallback(cfg, "p", "d", "r")
    assert "Authorization" not in captured["headers"]
    assert "x-device-id" not in captured["headers"]


def test_gateway_fallback_returns_empty_when_no_answer(monkeypatch):
    cfg = _cfg(gateway_url="http://server/v1/fallback", gateway_device_token="t")

    def fake_post_json(url, payload, headers, timeout_seconds):
        return {}

    monkeypatch.setattr("runtime._post_json", fake_post_json)

    result = gateway_fallback(cfg, "p", "d", "r")
    assert result == ""


# ── generate ────────────────────────────────────────────────────────────────


def test_generate_returns_error_when_local_backends_fail(monkeypatch):
    cfg = _cfg()

    def failing_local_chat(_cfg, _prompt):
        raise RuntimeError("boom")

    monkeypatch.setattr("runtime.local_chat", failing_local_chat)

    out = generate(cfg, "hello")
    assert out["source"] == "error"
    assert out["api_polished"] is False
    assert "local backend error" in out["reason"]
    assert out["local_backend_used"] is None


def test_generate_uses_gateway_when_local_backends_fail_and_gateway_is_configured(monkeypatch):
    cfg = _cfg(gateway_url="http://server/v1/fallback", gateway_device_token="secret")

    def failing_local_chat(_cfg, _prompt):
        raise RuntimeError("boom")

    def fake_gateway_fallback(_cfg, prompt, draft, reason):
        assert prompt == "hello"
        assert draft == ""
        assert reason == "local model unavailable"
        return "gateway answer"

    monkeypatch.setattr("runtime.local_chat", failing_local_chat)
    monkeypatch.setattr("runtime.gateway_fallback", fake_gateway_fallback)

    out = generate(cfg, "hello")
    assert out["answer"] == "gateway answer"
    assert out["source"] == "gateway"
    assert out["api_polished"] is True
    assert out["reason"] == "local model unavailable"
    assert out["local_backend_used"] is None


def test_generate_returns_error_when_local_and_gateway_fail(monkeypatch):
    cfg = _cfg(gateway_url="http://server/v1/fallback", gateway_device_token="secret")

    def failing_local_chat(_cfg, _prompt):
        raise RuntimeError("boom")

    def failing_gateway_fallback(_cfg, _prompt, _draft, _reason):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("runtime.local_chat", failing_local_chat)
    monkeypatch.setattr("runtime.gateway_fallback", failing_gateway_fallback)

    out = generate(cfg, "hello")
    assert out["answer"] == ""
    assert out["source"] == "error"
    assert out["api_polished"] is False
    assert "local model unavailable" in out["reason"]
    assert "gateway unavailable or failed: gateway down" in out["reason"]
    assert out["local_backend_used"] is None


def test_generate_uses_gateway_when_needed(monkeypatch):
    cfg = _cfg(force_fallback=False)

    def fake_local_chat(_cfg, _prompt):
        return "draft answer", "ollama"

    def fake_needs_fallback(prompt, draft):
        assert prompt == "hi"
        assert draft == "draft answer"
        return True, "test reason"

    def fake_gateway_fallback(_cfg, prompt, draft, reason):
        assert prompt == "hi"
        assert draft == "draft answer"
        assert reason == "test reason"
        return "gateway answer"

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)
    monkeypatch.setattr("runtime.needs_fallback", fake_needs_fallback)
    monkeypatch.setattr("runtime.gateway_fallback", fake_gateway_fallback)

    out = generate(cfg, "hi")
    assert out["answer"] == "gateway answer"
    assert out["source"] == "gateway"
    assert out["api_polished"] is True
    assert out["local_backend_used"] == "ollama"


def test_generate_uses_gateway_when_always_use_gateway_configured(monkeypatch):
    """When ALWAYS_USE_GATEWAY is true and gateway URL + token are set, every response goes to server for polish."""
    cfg = _cfg(
        force_fallback=False,
        always_use_gateway=True,
        gateway_url="http://server/v1/fallback",
        gateway_device_token="secret",
    )

    def fake_local_chat(_cfg, _prompt):
        return "draft answer", "ollama"

    def fake_gateway_fallback(_cfg, prompt, draft, reason):
        assert reason == "API polish via gateway (Sarvam/OpenRouter)"
        return "polished answer"

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)
    monkeypatch.setattr("runtime.gateway_fallback", fake_gateway_fallback)

    out = generate(cfg, "hi")
    assert out["answer"] == "polished answer"
    assert out["source"] == "gateway"
    assert out["api_polished"] is True


def test_generate_falls_back_to_local_when_gateway_fails(monkeypatch):
    cfg = _cfg(always_use_gateway=True, gateway_url="http://x/v1/fallback", gateway_device_token="t")

    def fake_local_chat(_cfg, _prompt):
        return "draft answer", "ollama"

    def failing_gateway_fallback(_cfg, _prompt, _draft, _reason):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)
    monkeypatch.setattr("runtime.gateway_fallback", failing_gateway_fallback)

    out = generate(cfg, "hi")
    assert out["answer"] == "draft answer"
    assert out["source"] == "local"
    assert out["api_polished"] is False
    assert "gateway unavailable or failed" in out["reason"]


def test_generate_with_force_fallback(monkeypatch):
    cfg = _cfg(
        force_fallback=True,
        gateway_url="http://server/v1/fallback",
        gateway_device_token="t",
    )

    def fake_local_chat(_cfg, _prompt):
        return "local draft", "llamacpp"

    captured_reason = {}

    def fake_gateway_fallback(_cfg, prompt, draft, reason):
        captured_reason["reason"] = reason
        return "forced fallback answer"

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)
    monkeypatch.setattr("runtime.gateway_fallback", fake_gateway_fallback)

    out = generate(cfg, "hi")
    assert out["answer"] == "forced fallback answer"
    assert out["source"] == "gateway"
    assert out["api_polished"] is True
    assert captured_reason["reason"] == "forced fallback for testing"


def test_generate_serves_local_when_no_fallback_needed(monkeypatch):
    cfg = _cfg(force_fallback=False, always_use_gateway=False)

    def fake_local_chat(_cfg, _prompt):
        return "local answer", "llamacpp"

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)

    out = generate(cfg, "hi")
    assert out["answer"] == "local answer"
    assert out["source"] == "local"
    assert out["api_polished"] is False
    assert out["local_backend_used"] == "llamacpp"
    assert out["reason"] == ""


def test_generate_empty_draft_returns_error(monkeypatch):
    cfg = _cfg()

    def fake_local_chat(_cfg, _prompt):
        return "", "ollama"

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)

    out = generate(cfg, "hi")
    assert out["source"] == "error"
    assert out["reason"] == "empty local response"
    assert out["local_backend_used"] is None


def test_generate_gateway_returns_empty_falls_back_to_local(monkeypatch):
    cfg = _cfg(
        always_use_gateway=True,
        gateway_url="http://server/v1/fallback",
        gateway_device_token="t",
    )

    def fake_local_chat(_cfg, _prompt):
        return "local draft", "ollama"

    def empty_gateway(_cfg, _prompt, _draft, _reason):
        return ""

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)
    monkeypatch.setattr("runtime.gateway_fallback", empty_gateway)

    out = generate(cfg, "hi")
    assert out["answer"] == "local draft"
    assert out["source"] == "local"
    assert out["reason"] == "gateway returned empty"
