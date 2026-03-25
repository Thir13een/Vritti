from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from config import RuntimeConfig

logger = logging.getLogger("ai_runtime")


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers or {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            try:
                return json.loads(body)
            except (json.JSONDecodeError, ValueError) as exc:
                raise RuntimeError(f"invalid JSON from {url}: {body[:200]}") from exc
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"http {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error calling {url}: {exc}") from exc


def _chat_with_llamacpp(cfg: RuntimeConfig, messages: list[dict[str, str]]) -> str:
    data = _post_json(
        f"{cfg.llamacpp_base}/v1/chat/completions",
        {
            "model": cfg.local_model,
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": cfg.max_tokens,
        },
        timeout_seconds=cfg.local_timeout_seconds,
    )
    choices = data.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message", {}) or {}).get("content", "").strip()


def _chat_with_ollama(cfg: RuntimeConfig, messages: list[dict[str, str]]) -> str:
    data = _post_json(
        f"{cfg.ollama_base}/api/chat",
        {
            "model": cfg.local_model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"num_ctx": cfg.num_ctx, "temperature": 0.6},
        },
        timeout_seconds=cfg.local_timeout_seconds,
    )
    return (data.get("message", {}) or {}).get("content", "").strip()


def local_chat(cfg: RuntimeConfig, prompt: str) -> tuple[str, str]:
    system_text = (
        "You are Vritti, a concise backup AI assistant. "
        "Be warm and conversational. Reply in the same language the user writes in."
    )
    messages = [{"role": "system", "content": system_text}, {"role": "user", "content": prompt}]
    errors: list[str] = []

    def call_backend(name: str) -> str:
        if name == "llamacpp":
            return _chat_with_llamacpp(cfg, messages)
        if name == "ollama":
            return _chat_with_ollama(cfg, messages)
        raise RuntimeError(f"unsupported backend: {name}")

    primary = "ollama"
    secondary = "llamacpp"
    if cfg.local_backend in ("llamacpp", "ollama"):
        primary = cfg.local_backend
        secondary = "ollama" if primary == "llamacpp" else "llamacpp"

    for backend_name in (primary, secondary):
        try:
            text = call_backend(backend_name)
        except RuntimeError as exc:
            errors.append(f"{backend_name}: {exc}")
            logger.warning("local backend error", extra={"backend": backend_name, "error": str(exc)})
            continue
        if text:
            logger.info(
                "local backend success",
                extra={"backend": backend_name},
            )
            return text, backend_name
        errors.append(f"{backend_name}: empty response")

    raise RuntimeError("all local backends failed: " + " | ".join(errors))


def gateway_chat(cfg: RuntimeConfig, prompt: str, conversation_id: str = "") -> str:
    headers = {"Content-Type": "application/json"}
    if cfg.gateway_device_token:
        headers["Authorization"] = f"Bearer {cfg.gateway_device_token}"
    if cfg.device_id:
        headers["x-device-id"] = cfg.device_id

    payload = {"prompt": prompt}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    data = _post_json(cfg.gateway_url, payload, headers, timeout_seconds=cfg.gateway_timeout_seconds)
    return str(data.get("answer", "")).strip()


def generate(cfg: RuntimeConfig, prompt: str, conversation_id: str = "") -> dict[str, Any]:
    prompt_preview = prompt[:160].replace("\n", " ")
    logger.info("generate called", extra={"prompt_preview": prompt_preview})

    gateway_configured = bool(cfg.gateway_url and cfg.gateway_device_token)

    if cfg.force_local_only:
        return _generate_local(cfg, prompt)

    if cfg.gateway_first and gateway_configured:
        try:
            answer = gateway_chat(cfg, prompt, conversation_id=conversation_id)
            if answer:
                logger.info("serving gateway response", extra={"api_polished": True})
                return {
                    "answer": answer,
                    "source": "gateway",
                    "api_polished": True,
                    "reason": "gateway_first",
                    "local_backend_used": None,
                }
            logger.warning("gateway returned empty, falling back to local")
        except RuntimeError as exc:
            logger.warning("gateway failed, falling back to local", extra={"error": str(exc)})

        return _generate_local(cfg, prompt)

    return _generate_local(cfg, prompt)


def _generate_local(cfg: RuntimeConfig, prompt: str) -> dict[str, Any]:
    try:
        text, backend = local_chat(cfg, prompt)
    except RuntimeError as exc:
        logger.error("local backends failed", extra={"error": str(exc)})
        return {
            "answer": "",
            "source": "error",
            "api_polished": False,
            "reason": f"local backend error: {exc}",
            "local_backend_used": None,
        }

    if not text:
        logger.error("empty local response")
        return {
            "answer": "",
            "source": "error",
            "api_polished": False,
            "reason": "empty local response",
            "local_backend_used": None,
        }

    logger.info("serving local response", extra={"backend": backend, "api_polished": False})
    return {
        "answer": text,
        "source": "local",
        "api_polished": False,
        "reason": "",
        "local_backend_used": backend,
    }
