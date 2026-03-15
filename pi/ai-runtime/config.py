from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    local_backend: str = "llamacpp"
    local_model: str = "qwen3.5:2b"
    ollama_base: str = "http://127.0.0.1:11434"
    llamacpp_base: str = "http://127.0.0.1:8080"
    gateway_url: str = "http://127.0.0.1:9000/v1/fallback"
    gateway_device_token: str = ""
    device_id: str = ""
    num_ctx: int = 1024
    # When True and gateway_url + gateway_device_token are set, every response is sent to the server for polish (9B). When False, server is only used if FORCE_FALLBACK=true.
    always_use_gateway: bool = True
    max_tokens: int = 512
    force_fallback: bool = False
    local_timeout_seconds: int = 60
    gateway_timeout_seconds: int = 30

    @staticmethod
    def from_env() -> "RuntimeConfig":
        num_ctx = max(1, int(os.getenv("NUM_CTX", "1024")))
        max_tokens = max(1, int(os.getenv("MAX_TOKENS", "512")))
        local_timeout = max(1, int(os.getenv("LOCAL_TIMEOUT_SECONDS", "60")))
        gateway_timeout = max(1, int(os.getenv("GATEWAY_TIMEOUT_SECONDS", "30")))
        return RuntimeConfig(
            local_backend=os.getenv("LOCAL_BACKEND", "llamacpp").strip().lower(),
            local_model=os.getenv("LOCAL_MODEL", "qwen3.5:2b").strip(),
            ollama_base=os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434").strip(),
            llamacpp_base=os.getenv("LLAMACPP_BASE", "http://127.0.0.1:8080").strip(),
            gateway_url=os.getenv("GATEWAY_URL", "http://127.0.0.1:9000/v1/fallback").strip(),
            gateway_device_token=os.getenv("GATEWAY_DEVICE_TOKEN", "").strip(),
            device_id=os.getenv("DEVICE_ID", "").strip(),
            num_ctx=num_ctx,
            max_tokens=max_tokens,
            always_use_gateway=os.getenv("ALWAYS_USE_GATEWAY", "true").strip().lower() in ("1", "true", "yes"),
            force_fallback=os.getenv("FORCE_FALLBACK", "false").strip().lower() in ("1", "true", "yes"),
            local_timeout_seconds=local_timeout,
            gateway_timeout_seconds=gateway_timeout,
        )
