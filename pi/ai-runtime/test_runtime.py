import pytest

from config import RuntimeConfig
from runtime import generate, local_chat, gateway_chat


def _cfg(**overrides):
    base = RuntimeConfig()
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ── local_chat ─────────────────────────────────────────────────────────────


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


# ── gateway_chat ───────────────────────────────────────────────────────────


def test_gateway_chat_sends_correct_headers(monkeypatch):
    cfg = _cfg(
        gateway_url="http://server/v1/chat",
        gateway_device_token="secret-token",
        device_id="pi-01",
    )
    captured = {}

    def fake_post_json(url, payload, headers, timeout_seconds):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"answer": "response"}

    monkeypatch.setattr("runtime._post_json", fake_post_json)

    result = gateway_chat(cfg, "hello")
    assert result == "response"
    assert captured["url"] == "http://server/v1/chat"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["headers"]["x-device-id"] == "pi-01"
    assert captured["payload"] == {"prompt": "hello"}


def test_gateway_chat_omits_auth_when_no_token(monkeypatch):
    cfg = _cfg(gateway_url="http://server/v1/chat", gateway_device_token="", device_id="")
    captured = {}

    def fake_post_json(url, payload, headers, timeout_seconds):
        captured["headers"] = headers
        return {"answer": "ok"}

    monkeypatch.setattr("runtime._post_json", fake_post_json)

    gateway_chat(cfg, "hello")
    assert "Authorization" not in captured["headers"]
    assert "x-device-id" not in captured["headers"]


def test_gateway_chat_returns_empty_when_no_answer(monkeypatch):
    cfg = _cfg(gateway_url="http://server/v1/chat", gateway_device_token="t")

    def fake_post_json(url, payload, headers, timeout_seconds):
        return {}

    monkeypatch.setattr("runtime._post_json", fake_post_json)

    result = gateway_chat(cfg, "hello")
    assert result == ""


# ── generate (gateway-first flow) ─────────────────────────────────────────


def test_generate_gateway_first_success(monkeypatch):
    cfg = _cfg(gateway_first=True, gateway_url="http://server/v1/chat", gateway_device_token="t")

    def fake_gateway(_cfg, prompt):
        assert prompt == "hello"
        return "gateway answer"

    monkeypatch.setattr("runtime.gateway_chat", fake_gateway)

    out = generate(cfg, "hello")
    assert out["answer"] == "gateway answer"
    assert out["source"] == "gateway"
    assert out["api_polished"] is True
    assert out["reason"] == "gateway_first"
    assert out["local_backend_used"] is None


def test_generate_gateway_first_fails_local_succeeds(monkeypatch):
    cfg = _cfg(gateway_first=True, gateway_url="http://server/v1/chat", gateway_device_token="t")

    def failing_gateway(_cfg, _prompt):
        raise RuntimeError("gateway down")

    def fake_local(_cfg, _prompt):
        return "local answer", "ollama"

    monkeypatch.setattr("runtime.gateway_chat", failing_gateway)
    monkeypatch.setattr("runtime.local_chat", fake_local)

    out = generate(cfg, "hello")
    assert out["answer"] == "local answer"
    assert out["source"] == "local"
    assert out["api_polished"] is False
    assert out["local_backend_used"] == "ollama"


def test_generate_gateway_first_empty_local_succeeds(monkeypatch):
    cfg = _cfg(gateway_first=True, gateway_url="http://server/v1/chat", gateway_device_token="t")

    def empty_gateway(_cfg, _prompt):
        return ""

    def fake_local(_cfg, _prompt):
        return "local answer", "llamacpp"

    monkeypatch.setattr("runtime.gateway_chat", empty_gateway)
    monkeypatch.setattr("runtime.local_chat", fake_local)

    out = generate(cfg, "hello")
    assert out["answer"] == "local answer"
    assert out["source"] == "local"


def test_generate_force_local_only_skips_gateway(monkeypatch):
    cfg = _cfg(force_local_only=True, gateway_url="http://server/v1/chat", gateway_device_token="t")
    gateway_called = []

    def spy_gateway(_cfg, _prompt):
        gateway_called.append(True)
        return "should not reach"

    def fake_local(_cfg, _prompt):
        return "local answer", "llamacpp"

    monkeypatch.setattr("runtime.gateway_chat", spy_gateway)
    monkeypatch.setattr("runtime.local_chat", fake_local)

    out = generate(cfg, "hello")
    assert out["answer"] == "local answer"
    assert out["source"] == "local"
    assert gateway_called == []


def test_generate_gateway_not_configured_uses_local(monkeypatch):
    cfg = _cfg(gateway_first=True, gateway_url="", gateway_device_token="")

    def fake_local(_cfg, _prompt):
        return "local answer", "ollama"

    monkeypatch.setattr("runtime.local_chat", fake_local)

    out = generate(cfg, "hello")
    assert out["answer"] == "local answer"
    assert out["source"] == "local"
    assert out["api_polished"] is False


def test_generate_local_fails_returns_error(monkeypatch):
    cfg = _cfg(gateway_first=False)

    def failing_local(_cfg, _prompt):
        raise RuntimeError("boom")

    monkeypatch.setattr("runtime.local_chat", failing_local)

    out = generate(cfg, "hello")
    assert out["source"] == "error"
    assert "local backend error" in out["reason"]


def test_generate_gateway_and_local_both_fail(monkeypatch):
    cfg = _cfg(gateway_first=True, gateway_url="http://server/v1/chat", gateway_device_token="t")

    def failing_gateway(_cfg, _prompt):
        raise RuntimeError("gateway down")

    def failing_local(_cfg, _prompt):
        raise RuntimeError("local down")

    monkeypatch.setattr("runtime.gateway_chat", failing_gateway)
    monkeypatch.setattr("runtime.local_chat", failing_local)

    out = generate(cfg, "hello")
    assert out["source"] == "error"
    assert "local backend error" in out["reason"]


def test_generate_local_empty_returns_error(monkeypatch):
    cfg = _cfg(gateway_first=False)

    def fake_local(_cfg, _prompt):
        return "", "ollama"

    monkeypatch.setattr("runtime.local_chat", fake_local)

    out = generate(cfg, "hello")
    assert out["source"] == "error"
    assert out["reason"] == "empty local response"
