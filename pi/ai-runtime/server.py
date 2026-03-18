from __future__ import annotations

import hmac
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
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
    """Return current face state set by voice pipeline."""
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


# Serve face UI (mandala)
# /opt/face-ui (installed) → ../face-ui (dev) → ./static (fallback)
_opt_face = Path("/opt/face-ui")
_dev_face = Path(__file__).resolve().parent.parent / "face-ui"
_static = Path(__file__).resolve().parent / "static"
static_dir = _opt_face if _opt_face.exists() else (_dev_face if _dev_face.exists() else _static)
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
