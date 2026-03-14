from __future__ import annotations

import hmac
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import RuntimeConfig
from runtime import generate

app = FastAPI(title="Pi AI Runtime", version="0.1.0")
cfg = RuntimeConfig.from_env()

CHAT_TOKEN = os.getenv("CHAT_API_TOKEN", "").strip()


class ChatRequest(BaseModel):
    prompt: str = Field(..., max_length=50_000)


@app.get("/health")
def health() -> dict:
    result: dict[str, str] = {"status": "ok"}
    try:
        if cfg.local_backend == "llamacpp":
            urllib.request.urlopen(f"{cfg.llamacpp_base}/health", timeout=3)
        else:
            urllib.request.urlopen(f"{cfg.ollama_base}/api/tags", timeout=3)
        result["backend"] = "reachable"
    except Exception:
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


# Serve chat UI at / (must be after API routes)
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
