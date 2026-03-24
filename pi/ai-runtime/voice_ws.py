from __future__ import annotations

import asyncio
import base64
import io
import json
import threading
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any, Iterable

from fastapi import WebSocket

from config import RuntimeConfig


def _write_session_status(state_dir: Path, status: str, **details: Any) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "voice_session": {
            "status": status,
            "updated_at": int(time.time()),
            **details,
        }
    }
    (state_dir / "vritti-voice-session.json").write_text(json.dumps(payload))


def _pcm16_to_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(max(8_000, int(sample_rate or 16_000)))
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _iter_gateway_voice_events(
    cfg: RuntimeConfig,
    audio_bytes: bytes,
    mime_type: str,
    mode: str,
    conversation_id: str,
) -> Iterable[dict[str, Any]]:
    boundary = f"vritti-{int(time.time() * 1000)}"
    filename = "audio.wav" if "wav" in mime_type else "audio.webm"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{cfg.gateway_base}/v1/voice",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {cfg.gateway_device_token}",
            "x-device-id": cfg.device_id or "browser-test",
            "x-voice-mode": mode or "fast",
            "x-conversation-id": conversation_id or (cfg.device_id or "browser-default"),
            "User-Agent": "Vritti-Pi/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                yield message


def _decode_audio_chunk(payload: dict[str, Any]) -> tuple[bytes, str, str, int]:
    data_b64 = str(payload.get("data") or "")
    if not data_b64:
        return b"", "webm", "audio/webm", 16_000

    chunk_bytes = base64.b64decode(data_b64)
    fmt = str(payload.get("format") or "webm").strip().lower()
    if fmt == "pcm16":
        sample_rate = int(payload.get("sample_rate") or 16_000)
        return chunk_bytes, "pcm16", "audio/wav", sample_rate

    mime_type = str(payload.get("mime_type") or "audio/webm").strip() or "audio/webm"
    return chunk_bytes, "webm", mime_type, 16_000


async def _stream_gateway_to_client(
    client_ws: WebSocket,
    cfg: RuntimeConfig,
    audio_bytes: bytes,
    mime_type: str,
    mode: str,
    conversation_id: str,
) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def worker() -> None:
        saw_done = False
        try:
            for msg in _iter_gateway_voice_events(cfg, audio_bytes, mime_type, mode, conversation_id):
                if msg.get("type") in {"done", "assistant_done"}:
                    saw_done = True
                loop.call_soon_threadsafe(queue.put_nowait, ("msg", msg))
            if not saw_done:
                loop.call_soon_threadsafe(queue.put_nowait, ("msg", {"type": "assistant_done"}))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            loop.call_soon_threadsafe(queue.put_nowait, ("err", str(exc)))

    threading.Thread(target=worker, daemon=True).start()

    while True:
        kind, payload = await queue.get()
        if kind == "msg":
            await client_ws.send_json(payload)
            continue
        if kind == "err":
            await client_ws.send_json({"type": "error", "detail": str(payload)})
            return
        return


async def relay_voice_session(client_ws: WebSocket, cfg: RuntimeConfig, state_dir: Path) -> None:
    if not cfg.gateway_base or not cfg.gateway_device_token:
        _write_session_status(state_dir, "degraded", reason="gateway voice endpoint is not configured")
        await client_ws.send_json({"type": "error", "detail": "gateway voice endpoint is not configured"})
        await client_ws.close(code=1013)
        return

    mode = "fast"
    conversation_id = cfg.device_id or "browser-default"
    chunk_bytes: list[bytes] = []
    chunk_format = "webm"
    chunk_mime = "audio/webm"
    chunk_rate = 16_000

    _write_session_status(state_dir, "connected", mode=mode, transport="runtime_ws_http_bridge")
    await client_ws.send_json({"type": "session_ready", "mode": mode})

    while True:
        message = await client_ws.receive()
        msg_type = message.get("type")
        if msg_type == "websocket.disconnect":
            _write_session_status(state_dir, "idle", reason="browser disconnected")
            return
        if msg_type != "websocket.receive":
            continue

        text = message.get("text")
        if text is None:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue

        event_type = str(payload.get("type") or "").strip().lower()
        if event_type == "session_start":
            requested_mode = str(payload.get("mode") or mode).strip().lower()
            mode = requested_mode if requested_mode in {"fast", "deep"} else "fast"
            requested_conversation_id = str(payload.get("conversation_id") or "").strip()
            if requested_conversation_id:
                conversation_id = requested_conversation_id
            _write_session_status(state_dir, "connected", mode=mode, transport="runtime_ws_http_bridge")
            await client_ws.send_json({"type": "session_ready", "mode": mode, "conversation_id": conversation_id})
            continue

        if event_type == "speech_started":
            chunk_bytes.clear()
            chunk_format = "webm"
            chunk_mime = "audio/webm"
            chunk_rate = 16_000
            _write_session_status(state_dir, "listening", mode=mode)
            continue

        if event_type == "audio_chunk":
            try:
                raw, fmt, mime, sample_rate = _decode_audio_chunk(payload)
            except Exception as exc:
                await client_ws.send_json({"type": "error", "detail": f"invalid audio chunk: {exc}"})
                continue

            if not raw:
                continue
            if chunk_bytes and fmt != chunk_format:
                chunk_bytes.clear()
            chunk_bytes.append(raw)
            chunk_format = fmt
            chunk_mime = mime
            chunk_rate = sample_rate
            continue

        if event_type == "interrupt":
            chunk_bytes.clear()
            _write_session_status(state_dir, "idle", reason="interrupted")
            await client_ws.send_json({"type": "cancelled"})
            continue

        if event_type == "session_end":
            _write_session_status(state_dir, "idle", reason="session ended")
            return

        if event_type != "speech_ended":
            continue

        if not chunk_bytes:
            _write_session_status(state_dir, "idle", reason="empty utterance")
            await client_ws.send_json({"type": "cancelled", "detail": "no audio captured"})
            continue

        merged = b"".join(chunk_bytes)
        chunk_bytes.clear()

        outbound_bytes = merged
        outbound_mime = chunk_mime
        if chunk_format == "pcm16":
            outbound_bytes = _pcm16_to_wav(merged, chunk_rate)
            outbound_mime = "audio/wav"

        _write_session_status(state_dir, "thinking", mode=mode, audio_bytes=len(outbound_bytes))
        try:
            await _stream_gateway_to_client(client_ws, cfg, outbound_bytes, outbound_mime, mode, conversation_id)
            _write_session_status(state_dir, "idle", mode=mode)
        except Exception as exc:
            _write_session_status(state_dir, "error", reason=str(exc))
            await client_ws.send_json({"type": "error", "detail": str(exc)})
