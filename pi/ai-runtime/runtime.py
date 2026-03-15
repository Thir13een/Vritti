from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from config import RuntimeConfig

logger = logging.getLogger("ai_runtime")


def needs_fallback(prompt: str, draft: str) -> tuple[bool, str]:
    """No heuristic-based fallback. Use ALWAYS_USE_GATEWAY=true (default) with gateway configured to polish every response on the server, or FORCE_FALLBACK=true for testing."""
    return False, ""


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
        # Include at most a small slice of the body to avoid log spam.
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
        "You are Vritti, a helpful AI assistant. CRITICAL: You MUST respond in the EXACT language the user uses or requests. "
        "If the user asks in Hindi, write ONLY in Hindi (Devanagari). If they ask in Hinglish, write ONLY in Hinglish. "
        "If they ask in English, respond in English. NEVER reply in English when Hindi/Hinglish/any Indian language is requested. "
        "Keep answers concise. No chain-of-thought. No preamble like 'Sure!' or 'Here is'—just answer directly in the correct language."
    )
    messages = [{"role": "system", "content": system_text}, {"role": "user", "content": prompt}]
    errors: list[str] = []

    def call_backend(name: str) -> str:
        if name == "llamacpp":
            return _chat_with_llamacpp(cfg, messages)
        if name == "ollama":
            return _chat_with_ollama(cfg, messages)
        raise RuntimeError(f"unsupported backend: {name}")

    # Requested behavior: primary llama.cpp, fallback Ollama on local failure.
    primary = "llamacpp"
    secondary = "ollama"
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


def gateway_fallback(cfg: RuntimeConfig, prompt: str, draft: str, reason: str) -> str:
    headers = {"Content-Type": "application/json"}
    if cfg.gateway_device_token:
        headers["Authorization"] = f"Bearer {cfg.gateway_device_token}"
    if cfg.device_id:
        headers["x-device-id"] = cfg.device_id

    payload = {"prompt": prompt, "draft": draft, "reason": reason}
    data = _post_json(cfg.gateway_url, payload, headers, timeout_seconds=cfg.gateway_timeout_seconds)
    return str(data.get("answer", "")).strip()


def generate(cfg: RuntimeConfig, prompt: str) -> dict[str, Any]:
    prompt_preview = prompt[:160].replace("\n", " ")
    logger.info("generate called", extra={"prompt_preview": prompt_preview})

    gateway_configured = bool(cfg.gateway_url and cfg.gateway_device_token)

    try:
        draft, local_backend_used = local_chat(cfg, prompt)
    except RuntimeError as exc:
        logger.error(
            "local backends failed",
            extra={"error": str(exc)},
        )
        if gateway_configured:
            reason = "local model unavailable"
            try:
                improved = gateway_fallback(cfg, prompt, "", reason)
                if improved:
                    logger.info(
                        "serving gateway response after local failure",
                        extra={"api_polished": True, "polish_reason": reason},
                    )
                    return {
                        "answer": improved,
                        "source": "gateway",
                        "api_polished": True,
                        "reason": reason,
                        "local_backend_used": None,
                    }
            except RuntimeError as gateway_exc:
                logger.error(
                    "gateway fallback failed after local failure",
                    extra={"error": str(gateway_exc)},
                )
                return {
                    "answer": "",
                    "source": "error",
                    "api_polished": False,
                    "reason": f"{reason}; gateway unavailable or failed: {gateway_exc}",
                    "local_backend_used": None,
                }
        return {
            "answer": "",
            "source": "error",
            "api_polished": False,
            "reason": f"local backend error: {exc}",
            "local_backend_used": None,
        }

    if not draft:
        logger.error("empty local response")
        return {
            "answer": "",
            "source": "error",
            "api_polished": False,
            "reason": "empty local response",
            "local_backend_used": None,
        }

    use_backup, reason = needs_fallback(prompt, draft)
    if cfg.force_fallback:
        use_backup = True
        reason = "forced fallback for testing"
    elif cfg.always_use_gateway and gateway_configured:
        use_backup = True
        reason = "API polish via gateway (Sarvam/OpenRouter)"

    if not use_backup:
        logger.info(
            "serving local response",
            extra={"backend": local_backend_used, "api_polished": False},
        )
        return {
            "answer": draft,
            "source": "local",
            "api_polished": False,
            "reason": "",
            "local_backend_used": local_backend_used,
        }

    try:
        improved = gateway_fallback(cfg, prompt, draft, reason)
        if improved:
            logger.info(
                "serving API-polished response",
                extra={"backend": local_backend_used, "api_polished": True, "polish_reason": reason},
            )
            return {
                "answer": improved,
                "source": "gateway",
                "api_polished": True,
                "reason": reason,
                "local_backend_used": local_backend_used,
            }
    except RuntimeError as exc:
        logger.error(
            "API polish failed",
            extra={"error": str(exc)},
        )
        return {
            "answer": draft,
            "source": "local",
            "api_polished": False,
            "reason": f"gateway unavailable or failed: {exc}",
            "local_backend_used": local_backend_used,
        }

    logger.warning(
        "API polish returned empty answer",
        extra={"backend": local_backend_used, "polish_reason": reason},
    )
    return {
        "answer": draft,
        "source": "local",
        "api_polished": False,
        "reason": "gateway returned empty",
        "local_backend_used": local_backend_used,
    }
