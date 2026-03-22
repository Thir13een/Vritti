from __future__ import annotations

import hmac
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import RuntimeConfig
from runtime import generate

app = FastAPI(title="Pi AI Runtime", version="0.1.0")
cfg = RuntimeConfig.from_env()

CHAT_TOKEN = os.getenv("CHAT_API_TOKEN", "").strip()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


class ChatRequest(BaseModel):
    prompt: str = Field(..., max_length=50_000)


@app.get("/v1/state")
def get_state() -> dict:
    """Current face state from voice pipeline."""
    try:
        return {"state": Path("/tmp/vritti-state").read_text().strip()}
    except FileNotFoundError:
        return {"state": "idle"}


@app.get("/health")
def health() -> dict:
    result: dict[str, str] = {"status": "ok"}
    try:
        if cfg.local_backend == "llamacpp":
            urllib.request.urlopen(f"{cfg.llamacpp_base}/health", timeout=3)
        else:
            urllib.request.urlopen(f"{cfg.ollama_base}/api/tags", timeout=3)
        result["backend"] = "reachable"
    except (urllib.error.URLError, OSError, ValueError):
        result["status"] = "degraded"
        result["backend"] = "unreachable"
    return result


@app.post("/v1/chat")
def chat(req: ChatRequest, authorization: str | None = Header(default=None)) -> dict:
    if CHAT_TOKEN:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token or not hmac.compare_digest(token, CHAT_TOKEN):
            raise HTTPException(status_code=401, detail="invalid or missing token")
    return generate(cfg, req.prompt.strip())


@app.post("/v1/voice-proxy")
async def voice_proxy(
    file: UploadFile = File(...),
    x_voice_mode: str | None = Header(default=None),
):
    """Proxy audio to gateway /v1/voice and stream NDJSON back."""
    if not cfg.gateway_base or not cfg.gateway_device_token:
        raise HTTPException(status_code=503, detail="gateway not configured")

    audio_bytes = await file.read()
    boundary = secrets.token_hex(16)
    filename = file.filename or "audio.webm"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {file.content_type or 'audio/webm'}\r\n\r\n"
    ).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    url = f"{cfg.gateway_base}/v1/voice"
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {cfg.gateway_device_token}",
            "x-device-id": cfg.device_id or "browser-test",
            "x-voice-mode": x_voice_mode or "fast",
            "User-Agent": "Vritti-Pi/1.0",
        },
        method="POST",
    )

    import io as _io
    def stream():
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for line in resp:
                    yield line
        except Exception as e:
            import json
            yield json.dumps({"type": "error", "detail": str(e)}).encode() + b"\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# Face UI static files
_opt_face = Path("/opt/face-ui")
_dev_face = Path(__file__).resolve().parent.parent / "face-ui"
_static = Path(__file__).resolve().parent / "static"
static_dir = _opt_face if _opt_face.exists() else (_dev_face if _dev_face.exists() else _static)
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
