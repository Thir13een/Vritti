import types

from config import RuntimeConfig
from runtime import needs_fallback, generate


def _cfg(**overrides):
    base = RuntimeConfig()
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


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


def test_generate_returns_error_when_local_backends_fail(monkeypatch):
    cfg = _cfg()

    def failing_local_chat(_cfg, _prompt):
        raise RuntimeError("boom")

    monkeypatch.setattr("runtime.local_chat", failing_local_chat)

    out = generate(cfg, "hello")
    assert out["source"] == "error"
    assert out["fallback_used"] is False
    assert "local backend error" in out["reason"]


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
    assert out["fallback_used"] is True
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
        assert reason == "Server polish (gateway configured)"
        return "polished answer"

    monkeypatch.setattr("runtime.local_chat", fake_local_chat)
    monkeypatch.setattr("runtime.gateway_fallback", fake_gateway_fallback)

    out = generate(cfg, "hi")
    assert out["answer"] == "polished answer"
    assert out["source"] == "gateway"
    assert out["fallback_used"] is True


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
    assert out["fallback_used"] is False
    assert "gateway unavailable or failed" in out["reason"]

