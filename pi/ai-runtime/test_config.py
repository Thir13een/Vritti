import os

from config import RuntimeConfig


def test_defaults():
    cfg = RuntimeConfig()
    assert cfg.local_backend == "llamacpp"
    assert cfg.local_model == "qwen3.5:2b"
    assert cfg.ollama_base == "http://127.0.0.1:11434"
    assert cfg.llamacpp_base == "http://127.0.0.1:8080"
    assert cfg.gateway_url == "http://127.0.0.1:9000/v1/chat"
    assert cfg.gateway_device_token == ""
    assert cfg.device_id == ""
    assert cfg.num_ctx == 1024
    assert cfg.gateway_first is True
    assert cfg.force_local_only is False
    assert cfg.local_timeout_seconds == 60
    assert cfg.gateway_timeout_seconds == 30


def test_from_env_defaults(monkeypatch):
    for key in [
        "LOCAL_BACKEND", "LOCAL_MODEL", "OLLAMA_BASE", "LLAMACPP_BASE",
        "GATEWAY_URL", "GATEWAY_DEVICE_TOKEN", "DEVICE_ID", "NUM_CTX",
        "GATEWAY_FIRST", "ALWAYS_USE_GATEWAY", "FORCE_LOCAL_ONLY",
        "FORCE_FALLBACK", "LOCAL_TIMEOUT_SECONDS", "GATEWAY_TIMEOUT_SECONDS",
    ]:
        monkeypatch.delenv(key, raising=False)

    cfg = RuntimeConfig.from_env()
    assert cfg.local_backend == "llamacpp"
    assert cfg.local_model == "qwen3.5:2b"
    assert cfg.num_ctx == 1024
    assert cfg.gateway_first is True
    assert cfg.force_local_only is False


def test_from_env_custom_values(monkeypatch):
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("LOCAL_MODEL", "llama3:8b")
    monkeypatch.setenv("OLLAMA_BASE", "http://10.0.0.1:11434")
    monkeypatch.setenv("LLAMACPP_BASE", "http://10.0.0.2:8080")
    monkeypatch.setenv("GATEWAY_URL", "https://cloud.example.com/v1/chat")
    monkeypatch.setenv("GATEWAY_DEVICE_TOKEN", "my-token")
    monkeypatch.setenv("DEVICE_ID", "pi-kitchen")
    monkeypatch.setenv("NUM_CTX", "2048")
    monkeypatch.setenv("GATEWAY_FIRST", "false")
    monkeypatch.setenv("FORCE_LOCAL_ONLY", "true")
    monkeypatch.setenv("LOCAL_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("GATEWAY_TIMEOUT_SECONDS", "45")

    cfg = RuntimeConfig.from_env()
    assert cfg.local_backend == "ollama"
    assert cfg.local_model == "llama3:8b"
    assert cfg.ollama_base == "http://10.0.0.1:11434"
    assert cfg.llamacpp_base == "http://10.0.0.2:8080"
    assert cfg.gateway_url == "https://cloud.example.com/v1/chat"
    assert cfg.gateway_device_token == "my-token"
    assert cfg.device_id == "pi-kitchen"
    assert cfg.num_ctx == 2048
    assert cfg.gateway_first is False
    assert cfg.force_local_only is True
    assert cfg.local_timeout_seconds == 120
    assert cfg.gateway_timeout_seconds == 45


def test_backward_compat_old_env_vars(monkeypatch):
    """Old env var names still work for existing deployments."""
    monkeypatch.delenv("GATEWAY_FIRST", raising=False)
    monkeypatch.delenv("FORCE_LOCAL_ONLY", raising=False)
    monkeypatch.setenv("ALWAYS_USE_GATEWAY", "false")
    monkeypatch.setenv("FORCE_FALLBACK", "true")

    cfg = RuntimeConfig.from_env()
    assert cfg.gateway_first is False
    assert cfg.force_local_only is True


def test_new_env_vars_override_old(monkeypatch):
    """New env vars take precedence over old ones."""
    monkeypatch.setenv("GATEWAY_FIRST", "true")
    monkeypatch.setenv("ALWAYS_USE_GATEWAY", "false")
    monkeypatch.setenv("FORCE_LOCAL_ONLY", "false")
    monkeypatch.setenv("FORCE_FALLBACK", "true")

    cfg = RuntimeConfig.from_env()
    assert cfg.gateway_first is True
    assert cfg.force_local_only is False


def test_boolean_parsing_true_variants(monkeypatch):
    for val in ("true", "True", "TRUE", "1", "yes", "YES"):
        monkeypatch.setenv("GATEWAY_FIRST", val)
        monkeypatch.setenv("FORCE_LOCAL_ONLY", val)
        cfg = RuntimeConfig.from_env()
        assert cfg.gateway_first is True, f"Expected True for '{val}'"
        assert cfg.force_local_only is True, f"Expected True for '{val}'"


def test_boolean_parsing_false_variants(monkeypatch):
    for val in ("false", "False", "FALSE", "0", "no", "NO", "anything", ""):
        monkeypatch.setenv("GATEWAY_FIRST", val)
        monkeypatch.setenv("FORCE_LOCAL_ONLY", val)
        cfg = RuntimeConfig.from_env()
        assert cfg.gateway_first is False, f"Expected False for '{val}'"
        assert cfg.force_local_only is False, f"Expected False for '{val}'"


def test_strips_whitespace(monkeypatch):
    monkeypatch.setenv("LOCAL_BACKEND", "  ollama  ")
    monkeypatch.setenv("LOCAL_MODEL", "  qwen3.5:2b  ")
    monkeypatch.setenv("OLLAMA_BASE", "  http://localhost:11434  ")
    monkeypatch.setenv("GATEWAY_DEVICE_TOKEN", "  token  ")

    cfg = RuntimeConfig.from_env()
    assert cfg.local_backend == "ollama"
    assert cfg.local_model == "qwen3.5:2b"
    assert cfg.ollama_base == "http://localhost:11434"
    assert cfg.gateway_device_token == "token"


def test_backend_normalized_to_lowercase(monkeypatch):
    monkeypatch.setenv("LOCAL_BACKEND", "OLLAMA")
    cfg = RuntimeConfig.from_env()
    assert cfg.local_backend == "ollama"

    monkeypatch.setenv("LOCAL_BACKEND", "LlamaCpp")
    cfg = RuntimeConfig.from_env()
    assert cfg.local_backend == "llamacpp"
