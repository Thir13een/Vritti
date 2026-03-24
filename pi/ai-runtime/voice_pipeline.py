"""Voice pipeline — mic → VAD → gateway → speaker."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import secrets
import shutil
import subprocess
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np
import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voice")

# Audio settings
TARGET_RATE = 16000
CHANNELS = 1
MIN_VAD_SAMPLES = 512
CHUNK_DURATION = max(float(os.getenv("VOICE_CHUNK_DURATION", "0.03")), MIN_VAD_SAMPLES / TARGET_RATE)
TARGET_CHUNK_SAMPLES = int(TARGET_RATE * CHUNK_DURATION)
PREFERRED_INPUT_RATES = [TARGET_RATE, 48000, 44100, 32000, 24000, 22050, 8000]

# Silero VAD settings
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
SPEECH_START_CHUNKS = max(1, int(os.getenv("SPEECH_START_CHUNKS", "2")))
SILENCE_END_SECONDS = float(os.getenv("SILENCE_END_SECONDS", "0.35"))
MIN_RECORDING_SECONDS = 0.5
MIC_RETRY_SECONDS = max(1, int(os.getenv("MIC_RETRY_SECONDS", "5")))
GATEWAY_HEALTH_RETRIES = max(1, int(os.getenv("GATEWAY_HEALTH_RETRIES", "10")))

# Gateway config
GATEWAY_BASE = os.getenv("GATEWAY_URL", "http://127.0.0.1:9000/v1/chat").strip().replace("/v1/chat", "")
GATEWAY_TOKEN = os.getenv("GATEWAY_DEVICE_TOKEN", "").strip()
DEVICE_ID = os.getenv("DEVICE_ID", "").strip()
VOICE_CONVERSATION_ID = os.getenv("VOICE_CONVERSATION_ID", "").strip() or ((DEVICE_ID or "device") + "-voice")
STATE_DIR = Path(
    os.getenv(
        "VRITTI_SHARED_STATE_DIR",
        str((Path("/opt/ai-runtime") if Path("/opt/ai-runtime").exists() else Path(__file__).resolve().parent) / "run"),
    )
)
MODE_FILE = STATE_DIR / "vritti-mode"
STATE_FILE = STATE_DIR / "vritti-state"
VOICE_HEALTH_FILE = STATE_DIR / "vritti-voice-health.json"
DEFAULT_VAD_DIR = (
    Path("/opt/ai-runtime/models/silero-vad")
    if Path("/opt/ai-runtime").exists()
    else Path(__file__).resolve().parent / "models" / "silero-vad"
)
VAD_REPO_DIR = Path(os.getenv("SILERO_VAD_DIR", str(DEFAULT_VAD_DIR))).expanduser()
PLAYER_CMD = shutil.which("mpg123") or shutil.which("ffplay")


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _get_voice_mode() -> str:
    try:
        mode = MODE_FILE.read_text().strip()
        if mode in ("fast", "deep"):
            return mode
    except FileNotFoundError:
        pass
    return os.getenv("VOICE_MODE", "fast").strip()


# ── Face UI state ──
def set_face_state(state: str):
    _ensure_state_dir()
    STATE_FILE.write_text(state)
    logger.info(f"state → {state}")


def set_voice_health(status: str, **details: str) -> None:
    _ensure_state_dir()
    payload = {
        "voice": {
            "status": status,
            **details,
            "updated_at": str(int(time.time())),
        }
    }
    VOICE_HEALTH_FILE.write_text(json.dumps(payload))


def _load_pyaudio_module():
    try:
        import pyaudio
    except ImportError as exc:
        raise RuntimeError("pyaudio is not installed in the runtime environment") from exc
    return pyaudio


def _candidate_input_rates(pyaudio_instance) -> list[int]:
    rates: list[int] = []
    try:
        info = pyaudio_instance.get_default_input_device_info()
    except Exception:
        info = None

    if isinstance(info, dict):
        default_rate = info.get("defaultSampleRate")
        if default_rate:
            try:
                rates.append(int(float(default_rate)))
            except (TypeError, ValueError):
                pass

    for rate in PREFERRED_INPUT_RATES:
        if rate not in rates:
            rates.append(rate)
    return rates


def _resample_to_target(audio_chunk: bytes, input_rate: int) -> bytes:
    if input_rate == TARGET_RATE:
        return audio_chunk
    samples = np.frombuffer(audio_chunk, dtype=np.int16)
    if samples.size == 0:
        return audio_chunk
    target_count = max(1, int(round(samples.size * TARGET_RATE / input_rate)))
    source_positions = np.linspace(0, samples.size - 1, num=samples.size)
    target_positions = np.linspace(0, samples.size - 1, num=target_count)
    converted = np.interp(target_positions, source_positions, samples.astype(np.float32))
    return np.clip(converted, -32768, 32767).astype(np.int16).tobytes()


def _open_input_stream(pyaudio_module):
    pa = pyaudio_module.PyAudio()
    last_exc: Exception | None = None
    for input_rate in _candidate_input_rates(pa):
        chunk_samples = max(1, int(input_rate * CHUNK_DURATION))
        try:
            stream = pa.open(
                format=pyaudio_module.paInt16,
                channels=CHANNELS,
                rate=input_rate,
                input=True,
                frames_per_buffer=chunk_samples,
            )
            return pa, stream, input_rate, chunk_samples
        except Exception as exc:
            last_exc = exc
    pa.terminate()
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unable to open microphone input stream")


def _wait_for_microphone(pyaudio_module) -> None:
    while True:
        try:
            pa, stream, input_rate, _chunk_samples = _open_input_stream(pyaudio_module)
        except Exception as exc:
            set_voice_health("degraded", mic="retrying", reason=f"microphone unavailable: {exc}")
            logger.warning(f"microphone not ready, retrying in {MIC_RETRY_SECONDS}s: {exc}")
            set_face_state("error")
            time.sleep(MIC_RETRY_SECONDS)
            continue
        stream.stop_stream()
        stream.close()
        pa.terminate()
        set_voice_health("ok", mic="ready", mic_sample_rate=str(input_rate))
        logger.info(f"microphone input is ready at {input_rate} Hz")
        return


# ── Silero VAD ──

def load_vad_model():
    logger.info(f"loading Silero VAD model from {VAD_REPO_DIR}")
    if not VAD_REPO_DIR.exists():
        raise FileNotFoundError(
            f"Silero VAD bundle not found at {VAD_REPO_DIR}. "
            "Run the installer to prefetch the local VAD model."
        )
    model, _utils = torch.hub.load(
        repo_or_dir=str(VAD_REPO_DIR),
        model="silero_vad",
        source="local",
    )
    logger.info("Silero VAD loaded")
    return model


def is_speech(model, audio_chunk: bytes) -> bool:
    samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
    tensor = torch.from_numpy(samples)
    confidence = model(tensor, TARGET_RATE).item()
    return confidence > VAD_THRESHOLD


def _silence_chunk_limit() -> int:
    return max(1, int(SILENCE_END_SECONDS / CHUNK_DURATION))


def record_until_silence(vad_model, pyaudio_module) -> bytes | None:
    """Record from mic until speech ends."""
    pa, stream, input_rate, chunk_samples = _open_input_stream(pyaudio_module)
    listen_started_at = time.time()

    logger.info(f"listening for speech at {input_rate} Hz...")
    set_face_state("idle")

    frames: list[bytes] = []
    speech_started = False
    speech_count = 0
    silence_chunks = 0
    silence_limit = _silence_chunk_limit()

    try:
        while True:
            data = stream.read(chunk_samples, exception_on_overflow=False)
            target_data = _resample_to_target(data, input_rate)
            speech = is_speech(vad_model, target_data)

            if not speech_started:
                if speech:
                    speech_count += 1
                    if speech_count >= SPEECH_START_CHUNKS:
                        speech_started = True
                        set_face_state("listening")
                        logger.info("speech detected, recording...")
                        frames.append(target_data)
                else:
                    speech_count = 0
            else:
                frames.append(target_data)
                if not speech:
                    silence_chunks += 1
                    if silence_chunks >= silence_limit:
                        break
                else:
                    silence_chunks = 0
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    if not frames:
        return None

    duration = len(frames) * CHUNK_DURATION
    if duration < MIN_RECORDING_SECONDS:
        logger.info(f"too short — {duration:.1f}s, ignoring")
        return None

    logger.info(
        "recorded audio clip",
        extra={
            "record_seconds": round(duration, 2),
            "time_to_capture_seconds": round(time.time() - listen_started_at, 2),
        },
    )

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_RATE)
        wf.writeframes(b"".join(frames))
    return buf.getvalue()


# ── Audio compression ──

def _compress_audio(wav_bytes: bytes) -> tuple[bytes, str]:
    """Compress WAV to OGG/Opus via ffmpeg."""
    if not shutil.which("ffmpeg"):
        return wav_bytes, "audio/wav"
    try:
        proc = subprocess.run(
            ["ffmpeg", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "24k",
             "-f", "ogg", "pipe:1"],
            input=wav_bytes, capture_output=True, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout:
            logger.info(f"compressed {len(wav_bytes)} → {len(proc.stdout)} bytes")
            return proc.stdout, "audio/ogg"
    except (subprocess.TimeoutExpired, OSError):
        pass
    return wav_bytes, "audio/wav"


# ── Audio playback ──

def _play_audio(audio_bytes: bytes):
    """Play MP3 audio via mpg123 — falls back to ffplay."""
    if not PLAYER_CMD:
        set_voice_health("degraded", audio_player="missing", reason="no audio player installed")
        logger.warning("audio playback skipped because no player is installed")
        return
    try:
        cmd = [PLAYER_CMD, "-q", "-"] if "mpg123" in PLAYER_CMD else [PLAYER_CMD, "-nodisp", "-autoexit", "-"]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.communicate(input=audio_bytes, timeout=15)
    except Exception as exc:
        logger.error(f"playback error: {exc}")


# ── Gateway voice roundtrip ──

def voice_roundtrip(wav_bytes: bytes):
    """Send audio to gateway, parse NDJSON stream, play audio."""
    started_at = time.time()
    audio_bytes, content_type = _compress_audio(wav_bytes)
    compressed_at = time.time()

    boundary = secrets.token_hex(16)
    ext = "ogg" if "ogg" in content_type else "wav"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audio.{ext}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + audio_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{GATEWAY_BASE}/v1/voice",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {GATEWAY_TOKEN}",
            "x-device-id": DEVICE_ID,
            "x-voice-mode": _get_voice_mode(),
            "x-conversation-id": VOICE_CONVERSATION_ID,
        },
    )

    set_face_state("thinking")
    upload_started_at = time.time()
    first_event_at: float | None = None
    first_audio_at: float | None = None
    transcript_text = ""
    gateway_ok = False

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw_line in resp:
                gateway_ok = True
                if first_event_at is None:
                    first_event_at = time.time()
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "stt":
                    transcript_text = msg.get("text", "")
                    logger.info(f"transcript: {transcript_text}")

                elif msg_type == "audio":
                    if first_audio_at is None:
                        first_audio_at = time.time()
                    set_face_state("speaking")
                    audio = base64.b64decode(msg["data"])
                    _play_audio(audio)

                elif msg_type == "done":
                    finished_at = time.time()
                    set_voice_health(
                        "ok" if PLAYER_CMD else "degraded",
                        mic="ready",
                        audio_player="available" if PLAYER_CMD else "missing",
                        gateway_voice="reachable",
                    )
                    logger.info(
                        "voice roundtrip complete",
                        extra={
                            "compress_seconds": round(compressed_at - started_at, 2),
                            "gateway_total_seconds": round(finished_at - upload_started_at, 2),
                            "time_to_first_event_seconds": round((first_event_at or finished_at) - upload_started_at, 2),
                            "time_to_first_audio_seconds": round((first_audio_at or finished_at) - upload_started_at, 2),
                            "end_to_end_seconds": round(finished_at - started_at, 2),
                            "transcript_preview": transcript_text[:80],
                            "answer_preview": str(msg.get("text", ""))[:80],
                        },
                    )

                elif msg_type == "error":
                    set_voice_health(
                        "degraded",
                        mic="ready",
                        audio_player="available" if PLAYER_CMD else "missing",
                        gateway_voice="reachable" if gateway_ok else "unreachable",
                        reason=f"gateway error: {msg.get('detail', '')}",
                    )
                    logger.error(f"gateway error: {msg.get('detail', '')}")

    except Exception as exc:
        set_voice_health(
            "degraded",
            mic="ready",
            audio_player="available" if PLAYER_CMD else "missing",
            gateway_voice="reachable" if gateway_ok else "unreachable",
            reason=f"voice roundtrip failed: {exc}",
        )
        logger.error(f"voice roundtrip failed: {exc}")

    set_face_state("idle")


# ── Main loop ──

def pipeline_loop():
    logger.info("voice pipeline started")
    logger.info(
        f"VAD threshold: {VAD_THRESHOLD}, speech start chunks: {SPEECH_START_CHUNKS}, "
        f"silence: {SILENCE_END_SECONDS}s"
    )
    logger.info(f"gateway: {GATEWAY_BASE}")

    if PLAYER_CMD:
        set_voice_health("degraded", audio_player="available", reason="initializing voice pipeline")
        logger.info(f"audio playback enabled via {Path(PLAYER_CMD).name}")
    else:
        set_voice_health("degraded", audio_player="missing", reason="no audio player installed")
        logger.warning("no audio player found; replies will not be spoken")

    try:
        vad_model = load_vad_model()
    except Exception as exc:
        set_voice_health("error", vad="missing", reason=f"failed to load local Silero VAD bundle: {exc}")
        logger.error(f"failed to load local Silero VAD bundle: {exc}")
        set_face_state("error")
        raise SystemExit(1) from exc

    try:
        pyaudio_module = _load_pyaudio_module()
    except RuntimeError as exc:
        set_voice_health("error", mic="unavailable", reason=str(exc))
        logger.error(str(exc))
        set_face_state("error")
        raise SystemExit(1) from exc

    _wait_for_microphone(pyaudio_module)

    # Wait for gateway if configured
    if GATEWAY_TOKEN:
        for _ in range(GATEWAY_HEALTH_RETRIES):
            try:
                urllib.request.urlopen(f"{GATEWAY_BASE}/health", timeout=3)
                set_voice_health(
                    "ok" if PLAYER_CMD else "degraded",
                    mic="ready",
                    audio_player="available" if PLAYER_CMD else "missing",
                    gateway_voice="reachable",
                )
                logger.info("gateway reachable")
                break
            except Exception:
                time.sleep(1)
        else:
            set_voice_health(
                "degraded",
                mic="ready",
                audio_player="available" if PLAYER_CMD else "missing",
                gateway_voice="unreachable",
                reason="gateway health check failed",
            )
            logger.warning("gateway not reachable, starting anyway")
    else:
        set_voice_health(
            "degraded" if not PLAYER_CMD else "ok",
            mic="ready",
            audio_player="available" if PLAYER_CMD else "missing",
            gateway_voice="not_configured",
            reason="gateway token not configured",
        )
        logger.info("gateway token not configured; voice pipeline will capture audio but skip roundtrip")

    set_face_state("idle")

    while True:
        try:
            audio = record_until_silence(vad_model, pyaudio_module)
            if not audio:
                continue

            if GATEWAY_TOKEN:
                voice_roundtrip(audio)
            else:
                logger.info("no gateway token configured, audio captured but not sent")
                set_face_state("idle")

        except KeyboardInterrupt:
            set_voice_health(
                "degraded" if not PLAYER_CMD else "ok",
                mic="stopped",
                audio_player="available" if PLAYER_CMD else "missing",
                gateway_voice="reachable" if GATEWAY_TOKEN else "not_configured",
                reason="pipeline stopped",
            )
            logger.info("pipeline stopped")
            set_face_state("idle")
            break
        except Exception as exc:
            set_voice_health(
                "degraded",
                mic="retrying",
                audio_player="available" if PLAYER_CMD else "missing",
                gateway_voice="reachable" if GATEWAY_TOKEN else "not_configured",
                reason=f"pipeline error: {exc}",
            )
            logger.error(f"pipeline error, retrying microphone in {MIC_RETRY_SECONDS}s: {exc}")
            set_face_state("error")
            time.sleep(MIC_RETRY_SECONDS)
            _wait_for_microphone(pyaudio_module)
            set_voice_health(
                "degraded" if not PLAYER_CMD else "ok",
                mic="ready",
                audio_player="available" if PLAYER_CMD else "missing",
                gateway_voice="reachable" if GATEWAY_TOKEN else "not_configured",
            )
            set_face_state("idle")


if __name__ == "__main__":
    pipeline_loop()
