from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import RuntimeConfig
from runtime import generate

app = FastAPI(title="Pi AI Runtime", version="0.1.0")
cfg = RuntimeConfig.from_env()

# API routes first so they take precedence over static files
class ChatRequest(BaseModel):
    prompt: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat")
def chat(req: ChatRequest) -> dict:
    return generate(cfg, req.prompt.strip())


# Serve chat UI at / (must be after API routes)
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
