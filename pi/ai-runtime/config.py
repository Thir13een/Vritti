from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    local_backend: str = "llamacpp"
    local_model: str = "qwen3.5:2b"
    ollama_base: str = "http://127.0.0.1:11434"
    llamacpp_base: str = "http://127.0.0.1:8080"
    gateway_url: str = "http://127.0.0.1:9000/v1/chat"
    gateway_device_token: str = ""
    device_id: str = ""
    num_ctx: int = 1024
    gateway_first: bool = True
    max_tokens: int = 512
    force_local_only: bool = False
    local_timeout_seconds: int = 60
    gateway_timeout_seconds: int = 30
    gateway_base: str = ""

    @staticmethod
    def from_env() -> "RuntimeConfig":
        num_ctx = max(1, int(os.getenv("NUM_CTX", "1024")))
        max_tokens = max(1, int(os.getenv("MAX_TOKENS", "512")))
        local_timeout = max(1, int(os.getenv("LOCAL_TIMEOUT_SECONDS", "60")))
        gateway_timeout = max(1, int(os.getenv("GATEWAY_TIMEOUT_SECONDS", "30")))

        gw_first = os.getenv("GATEWAY_FIRST", os.getenv("ALWAYS_USE_GATEWAY", "true"))
        local_only = os.getenv("FORCE_LOCAL_ONLY", os.getenv("FORCE_FALLBACK", "false"))

        return RuntimeConfig(
            local_backend=os.getenv("LOCAL_BACKEND", "llamacpp").strip().lower(),
            local_model=os.getenv("LOCAL_MODEL", "qwen3.5:2b").strip(),
            ollama_base=os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434").strip(),
            llamacpp_base=os.getenv("LLAMACPP_BASE", "http://127.0.0.1:8080").strip(),
            gateway_url=os.getenv("GATEWAY_URL", "http://127.0.0.1:9000/v1/chat").strip(),
            gateway_device_token=os.getenv("GATEWAY_DEVICE_TOKEN", "").strip(),
            device_id=os.getenv("DEVICE_ID", "").strip(),
            num_ctx=num_ctx,
            max_tokens=max_tokens,
            gateway_first=gw_first.strip().lower() in ("1", "true", "yes"),
            force_local_only=local_only.strip().lower() in ("1", "true", "yes"),
            local_timeout_seconds=local_timeout,
            gateway_timeout_seconds=gateway_timeout,
            gateway_base=os.getenv("GATEWAY_URL", "").strip().replace("/v1/chat", ""),
        )
