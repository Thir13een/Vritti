from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    local_backend: str = "ollama"
    local_model: str = "qwen3.5:2b"
    ollama_base: str = "http://127.0.0.1:11434"
    llamacpp_base: str = "http://127.0.0.1:8080"
    gateway_url: str = "http://127.0.0.1:9000/v1/chat"
    gateway_voice_ws_url: str = ""
    gateway_device_token: str = ""
    device_id: str = ""
    num_ctx: int = 1024
    gateway_first: bool = True
    max_tokens: int = 512
    force_local_only: bool = False
    local_timeout_seconds: int = 60
    gateway_timeout_seconds: int = 30
    gateway_base: str = ""
    voice_stream_sample_rate: int = 16000
    voice_stream_frame_ms: int = 250
    voice_playback_buffer_ms: int = 200

    @staticmethod
    def from_env() -> "RuntimeConfig":
        num_ctx = max(1, int(os.getenv("NUM_CTX", "1024")))
        max_tokens = max(1, int(os.getenv("MAX_TOKENS", "512")))
        local_timeout = max(1, int(os.getenv("LOCAL_TIMEOUT_SECONDS", "60")))
        gateway_timeout = max(1, int(os.getenv("GATEWAY_TIMEOUT_SECONDS", "30")))
        voice_stream_sample_rate = max(8000, int(os.getenv("VOICE_STREAM_SAMPLE_RATE", "16000")))
        voice_stream_frame_ms = max(20, int(os.getenv("VOICE_STREAM_FRAME_MS", "250")))
        voice_playback_buffer_ms = max(50, int(os.getenv("VOICE_PLAYBACK_BUFFER_MS", "200")))

        gw_first = os.getenv("GATEWAY_FIRST", os.getenv("ALWAYS_USE_GATEWAY", "true"))
        local_only = os.getenv("FORCE_LOCAL_ONLY", os.getenv("FORCE_FALLBACK", "false"))
        gateway_url = os.getenv("GATEWAY_URL", "http://127.0.0.1:9000/v1/chat").strip()
        gateway_base = gateway_url.replace("/v1/chat", "")
        gateway_voice_ws_url = os.getenv("GATEWAY_VOICE_WS_URL", "").strip()
        if not gateway_voice_ws_url and gateway_base:
            http_base = gateway_base.rstrip("/")
            if http_base.startswith("https://"):
                gateway_voice_ws_url = "wss://" + http_base[len("https://"):] + "/v1/voice/ws"
            elif http_base.startswith("http://"):
                gateway_voice_ws_url = "ws://" + http_base[len("http://"):] + "/v1/voice/ws"

        return RuntimeConfig(
            local_backend=os.getenv("LOCAL_BACKEND", "ollama").strip().lower(),
            local_model=os.getenv("LOCAL_MODEL", "qwen3.5:2b").strip(),
            ollama_base=os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434").strip(),
            llamacpp_base=os.getenv("LLAMACPP_BASE", "http://127.0.0.1:8080").strip(),
            gateway_url=gateway_url,
            gateway_voice_ws_url=gateway_voice_ws_url,
            gateway_device_token=os.getenv("GATEWAY_DEVICE_TOKEN", "").strip(),
            device_id=os.getenv("DEVICE_ID", "").strip(),
            num_ctx=num_ctx,
            max_tokens=max_tokens,
            gateway_first=gw_first.strip().lower() in ("1", "true", "yes"),
            force_local_only=local_only.strip().lower() in ("1", "true", "yes"),
            local_timeout_seconds=local_timeout,
            gateway_timeout_seconds=gateway_timeout,
            gateway_base=gateway_base,
            voice_stream_sample_rate=voice_stream_sample_rate,
            voice_stream_frame_ms=voice_stream_frame_ms,
            voice_playback_buffer_ms=voice_playback_buffer_ms,
        )
