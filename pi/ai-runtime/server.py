from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import RuntimeConfig
from runtime import generate
from voice_ws import relay_voice_session

_LOG = logging.getLogger("vritti.face_ui")


def _load_env_files() -> None:
    """Load runtime env files."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for p in (
        Path("/opt/ai-runtime/.env"),
        Path(__file__).resolve().parent / ".env",
    ):
        if p.is_file():
            load_dotenv(p, override=False)


_load_env_files()

app = FastAPI(title="Pi AI Runtime", version="0.1.0")
cfg = RuntimeConfig.from_env()

CHAT_TOKEN = os.getenv("CHAT_API_TOKEN", "").strip()

# Optional GitHub face UI source.
_DEFAULT_GITHUB_FACE_UI = (
    "https://raw.githubusercontent.com/Thir13een/Vritti/main/pi/face-ui/index.html"
)

STATE_DIR = Path(
    os.getenv(
        "VRITTI_SHARED_STATE_DIR",
        str((Path("/opt/ai-runtime") if Path("/opt/ai-runtime").exists() else Path(__file__).resolve().parent) / "run"),
    )
)
MODE_FILE = STATE_DIR / "vritti-mode"
STATE_FILE = STATE_DIR / "vritti-state"
VOICE_HEALTH_FILE = STATE_DIR / "vritti-voice-health.json"
VOICE_SESSION_FILE = STATE_DIR / "vritti-voice-session.json"


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
    conversation_id: str = Field("", max_length=120)


VALID_MODES = ("fast", "deep")


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _face_ui_github_enabled() -> bool:
    v = os.getenv("VRITTI_FACE_UI_SOURCE", "").strip().lower()
    return v in ("github", "remote", "1", "true", "yes")


def _seed_face_ui_favicons(cache_dir: Path) -> None:
    """Seed cached favicons."""
    static = Path(__file__).resolve().parent / "static"
    pairs = [
        ("favicon.png", "favicon-32x32.png"),
        ("favicon-32x32.png", "favicon-32x32.png"),
        ("favicon-16x16.png", "favicon-16x16.png"),
    ]
    for dest_name, src_name in pairs:
        dest = cache_dir / dest_name
        if dest.exists():
            continue
        src = static / src_name
        if src.exists():
            try:
                shutil.copyfile(src, dest)
            except OSError:
                pass


def _fetch_github_face_ui_to_cache() -> Path | None:
    """Cache face UI from GitHub."""
    if not _face_ui_github_enabled():
        return None
    url = os.getenv("VRITTI_FACE_UI_GITHUB_URL", _DEFAULT_GITHUB_FACE_UI).strip() or _DEFAULT_GITHUB_FACE_UI
    cache_dir = STATE_DIR / "face-ui-github"
    _ensure_state_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / "index.html"
    min_bytes = 400
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Vritti-Pi/ai-runtime (face-ui cache)"},
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        if len(data) < min_bytes:
            _LOG.warning("face UI: GitHub response too small (%d bytes), url=%s", len(data), url)
        else:
            target.write_bytes(data)
            _seed_face_ui_favicons(cache_dir)
            _LOG.info("face UI: cached from GitHub (%d bytes) -> %s", len(data), target)
            return cache_dir
    except (OSError, urllib.error.URLError, ValueError) as exc:
        _LOG.warning("face UI: GitHub fetch failed (%s): %s", url, exc)

    if target.is_file() and target.stat().st_size >= min_bytes:
        _seed_face_ui_favicons(cache_dir)
        _LOG.info("face UI: using stale GitHub cache (%s)", target)
        return cache_dir
    return None


def _resolve_face_ui_static_dir() -> Path | None:
    """Resolve face UI source."""
    opt_face = Path("/opt/face-ui")
    dev_face = Path(__file__).resolve().parent.parent / "face-ui"
    bundled = Path(__file__).resolve().parent / "static"
    if opt_face.exists():
        return opt_face
    if dev_face.exists():
        return dev_face
    gh = _fetch_github_face_ui_to_cache()
    if gh is not None:
        return gh
    if bundled.exists():
        return bundled
    return None


def _read_voice_health() -> dict:
    try:
        data = json.loads(VOICE_HEALTH_FILE.read_text())
    except FileNotFoundError:
        return {"voice": {"status": "unknown", "reason": "voice health file not found"}}
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return {"voice": {"status": "error", "reason": f"invalid voice health file: {exc}"}}

    voice = data.get("voice")
    if isinstance(voice, dict):
        return {"voice": voice}
    return {"voice": {"status": "error", "reason": "voice health payload missing voice object"}}


def _read_voice_session() -> dict:
    try:
        data = json.loads(VOICE_SESSION_FILE.read_text())
    except FileNotFoundError:
        return {"voice_session": {"status": "idle"}}
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return {"voice_session": {"status": "error", "reason": f"invalid voice session file: {exc}"}}

    voice_session = data.get("voice_session")
    if isinstance(voice_session, dict):
        return {"voice_session": voice_session}
    return {"voice_session": {"status": "error", "reason": "voice session payload missing voice_session object"}}


def _probe_backend_url(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _probe_local_backends() -> dict[str, bool]:
    probes = {
        "llamacpp": _probe_backend_url(f"{cfg.llamacpp_base}/health"),
        "ollama": _probe_backend_url(f"{cfg.ollama_base}/api/tags"),
    }
    if cfg.local_backend not in probes:
        probes[cfg.local_backend] = False
    return probes


def _probe_gateway() -> bool | None:
    if cfg.force_local_only or not cfg.gateway_base or not cfg.gateway_device_token:
        return None
    try:
        req = urllib.request.Request(
            f"{cfg.gateway_base}/health",
            headers={"Authorization": f"Bearer {cfg.gateway_device_token}"},
        )
        urllib.request.urlopen(req, timeout=3)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _voice_optional_for_browser_kiosk(voice: dict[str, object], gateway_ok: bool | None) -> bool:
    if gateway_ok is not True:
        return False
    mic_state = str(voice.get("mic", "")).strip().lower()
    reason = str(voice.get("reason", "")).strip().lower()
    return (
        mic_state in {"retrying", "unavailable", "stopped"}
        or "microphone unavailable" in reason
        or "invalid input device" in reason
    )


@app.get("/v1/state")
def get_state() -> dict:
    """Current face state from voice pipeline."""
    try:
        return {"state": STATE_FILE.read_text().strip()}
    except FileNotFoundError:
        return {"state": "idle"}


@app.get("/v1/config")
def get_runtime_config() -> dict:
    return {
        "voice_stream_sample_rate": cfg.voice_stream_sample_rate,
        "voice_stream_frame_ms": cfg.voice_stream_frame_ms,
        "voice_playback_buffer_ms": cfg.voice_playback_buffer_ms,
    }


@app.get("/v1/mode")
def get_mode() -> dict:
    try:
        mode = MODE_FILE.read_text().strip()
        if mode in VALID_MODES:
            return {"mode": mode}
    except FileNotFoundError:
        pass
    return {"mode": "fast"}


class ModeRequest(BaseModel):
    mode: str


@app.post("/v1/mode")
def set_mode(req: ModeRequest) -> dict:
    mode = req.mode.strip().lower()
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"invalid mode, use: {', '.join(VALID_MODES)}")
    _ensure_state_dir()
    MODE_FILE.write_text(mode)
    return {"mode": mode}


@app.get("/health")
def health() -> dict:
    result: dict[str, object] = {"status": "ok"}
    local_probes = _probe_local_backends()
    local_ok = any(local_probes.values())
    gateway_ok = _probe_gateway()
    primary_backend = cfg.local_backend if cfg.local_backend in local_probes else "llamacpp"
    secondary_backend = "ollama" if primary_backend == "llamacpp" else "llamacpp"
    result["local_backend"] = "reachable" if local_ok else "unreachable"
    result["local_backend_primary"] = f"{primary_backend}:{'reachable' if local_probes.get(primary_backend) else 'unreachable'}"
    result["local_backend_secondary"] = (
        f"{secondary_backend}:{'reachable' if local_probes.get(secondary_backend) else 'unreachable'}"
    )
    if gateway_ok is not None:
        result["gateway"] = "reachable" if gateway_ok else "unreachable"

    if gateway_ok is None:
        result["backend"] = "reachable" if local_ok else "unreachable"
        if not local_ok:
            result["status"] = "degraded"
    else:
        result["fallback_backend"] = "reachable" if local_ok else "unreachable"
        if gateway_ok:
            result["backend"] = "reachable"
        elif local_ok:
            result["backend"] = "reachable"
            result["status"] = "degraded"
        else:
            result["backend"] = "unreachable"
            result["status"] = "error"

    voice_health = _read_voice_health()
    result.update(voice_health)
    result.update(_read_voice_session())

    voice = dict(voice_health.get("voice") or {})
    voice_status = str(voice.get("status", "unknown"))
    if voice and _voice_optional_for_browser_kiosk(voice, gateway_ok):
        voice["scope"] = "local_pipeline"
        voice["optional_for_browser_kiosk"] = True
        result["voice"] = voice
        if result["status"] == "error":
            result["status"] = "degraded"
        return result
    if voice_status in {"error", "unknown"}:
        result["status"] = "error"
    elif voice_status == "degraded" and result["status"] == "ok":
        result["status"] = "degraded"

    return result


@app.post("/v1/chat")
def chat(req: ChatRequest, authorization: str | None = Header(default=None)) -> dict:
    if CHAT_TOKEN:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token or not hmac.compare_digest(token, CHAT_TOKEN):
            raise HTTPException(status_code=401, detail="invalid or missing token")
    return generate(cfg, req.prompt.strip(), conversation_id=req.conversation_id.strip())


@app.post("/v1/voice-proxy")
async def voice_proxy(
    file: UploadFile = File(...),
    x_voice_mode: str | None = Header(default=None),
    x_conversation_id: str | None = Header(default=None),
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
            "x-conversation-id": (x_conversation_id or "").strip() or (cfg.device_id or "browser-default"),
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


@app.websocket("/v1/voice/ws")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        await relay_voice_session(websocket, cfg, STATE_DIR)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "detail": str(exc)})
        except Exception:
            pass
        await websocket.close(code=1011)


@app.on_event("startup")
def _startup_runtime() -> None:
    _ensure_state_dir()
    try:
        VOICE_SESSION_FILE.write_text(
            json.dumps({"voice_session": {"status": "idle", "updated_at": int(time.time()), "reason": "runtime startup"}})
        )
    except OSError:
        pass

    static_dir = _resolve_face_ui_static_dir()
    if static_dir is None:
        _LOG.warning("face UI: no static directory (GitHub cache, /opt/face-ui, face-ui, or static missing)")
        return
    label = "GitHub cache" if static_dir.name == "face-ui-github" else str(static_dir)
    _LOG.info("face UI: mount / -> %s", label)
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
