"""Vritti Voice Pipeline — mic → gateway STT → gateway chat → gateway TTS → speaker.

Thin client: all AI processing happens on the gateway.
Pi only handles mic capture, VAD, audio playback, and mandala state.
"""
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tempfile
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

# Gateway URL (all STT/TTS/chat goes through gateway)
GATEWAY_BASE = os.getenv("GATEWAY_URL", "").strip().replace("/v1/chat", "").rstrip("/")
GATEWAY_TOKEN = os.getenv("GATEWAY_DEVICE_TOKEN", "").strip()
DEVICE_ID = os.getenv("DEVICE_ID", "").strip()

# Local runtime (for health check and state)
LOCAL_API = os.getenv("API_BASE", "http://127.0.0.1:8000")

# Audio settings
RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.03  # 30ms chunks
CHUNK_SAMPLES = int(RATE * CHUNK_DURATION)

# Silero VAD settings
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
SPEECH_START_CHUNKS = 3
SILENCE_END_SECONDS = 1.2
MIN_RECORDING_SECONDS = 0.5


def _gw_headers() -> dict[str, str]:
    """Headers for gateway requests (auth + device ID)."""
    h: dict[str, str] = {"Content-Type": "application/json"}
    if GATEWAY_TOKEN:
        h["Authorization"] = f"Bearer {GATEWAY_TOKEN}"
    if DEVICE_ID:
        h["x-device-id"] = DEVICE_ID
    return h


def _gw_auth_headers() -> dict[str, str]:
    """Auth headers without Content-Type (for multipart)."""
    h: dict[str, str] = {}
    if GATEWAY_TOKEN:
        h["Authorization"] = f"Bearer {GATEWAY_TOKEN}"
    if DEVICE_ID:
        h["x-device-id"] = DEVICE_ID
    return h


# ── Face UI state control ──
STATE_FILE = Path("/tmp/vritti-state")


def set_face_state(state: str):
    """Set mandala state via state file."""
    STATE_FILE.write_text(state)
    logger.info(f"state → {state}")


# ── Silero VAD ──

def load_vad_model():
    """Load Silero VAD model (downloads ~2MB on first run)."""
    logger.info("loading Silero VAD model...")
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )
    logger.info("Silero VAD loaded")
    return model


def is_speech(model, audio_chunk: bytes) -> bool:
    """Check if audio chunk contains speech using Silero VAD."""
    samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
    tensor = torch.from_numpy(samples)
    confidence = model(tensor, RATE).item()
    return confidence > VAD_THRESHOLD


def record_until_silence(vad_model) -> bytes | None:
    """Record from mic until speech ends. Returns WAV bytes or None."""
    try:
        import pyaudio
    except ImportError:
        logger.error("pyaudio not installed — run: pip install pyaudio")
        return None

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK_SAMPLES,
    )

    logger.info("listening for speech...")
    set_face_state("idle")

    frames: list[bytes] = []
    speech_started = False
    speech_count = 0
    silence_chunks = 0
    silence_limit = int(SILENCE_END_SECONDS / CHUNK_DURATION)

    try:
        while True:
            data = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
            speech = is_speech(vad_model, data)

            if not speech_started:
                if speech:
                    speech_count += 1
                    if speech_count >= SPEECH_START_CHUNKS:
                        speech_started = True
                        set_face_state("listening")
                        logger.info("speech detected, recording...")
                        frames.append(data)
                else:
                    speech_count = 0
            else:
                frames.append(data)
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
        logger.info(f"too short ({duration:.1f}s), ignoring")
        return None

    logger.info(f"recorded {duration:.1f}s of audio")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
    return buf.getvalue()


def transcribe(audio_wav: bytes) -> str:
    """Send audio to gateway STT."""
    set_face_state("listening")

    boundary = "----VrittiAudioBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + audio_wav + f"\r\n--{boundary}--\r\n".encode()

    headers = _gw_auth_headers()
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    req = urllib.request.Request(
        f"{GATEWAY_BASE}/v1/stt",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    transcript = data.get("transcript", "").strip()
    logger.info(f"transcript: {transcript[:80]}")
    return transcript


def chat(prompt: str) -> str:
    """Send prompt to gateway chat."""
    set_face_state("thinking")

    payload = json.dumps({"prompt": prompt}).encode()
    headers = _gw_headers()

    req = urllib.request.Request(
        f"{GATEWAY_BASE}/v1/chat",
        data=payload,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    answer = data.get("answer", "").strip()
    logger.info(f"answer: {answer[:80]}")
    return answer


def speak(text: str):
    """Send text to gateway TTS and play through speakers."""
    set_face_state("speaking")

    payload = json.dumps({"text": text}).encode()
    headers = _gw_headers()

    req = urllib.request.Request(
        f"{GATEWAY_BASE}/v1/tts",
        data=payload,
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        audio_data = resp.read()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_data)
        tmp_path = f.name

    try:
        for player in ["mpv --no-video --really-quiet", "ffplay -nodisp -autoexit -loglevel quiet"]:
            cmd = player.split() + [tmp_path]
            try:
                subprocess.run(cmd, check=True, timeout=120)
                break
            except (FileNotFoundError, subprocess.SubprocessError):
                continue
        else:
            logger.error("no audio player found — install mpv or ffmpeg")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def pipeline_loop():
    """Main voice pipeline loop."""
    logger.info("voice pipeline started")
    logger.info(f"gateway: {GATEWAY_BASE}")
    logger.info(f"device: {DEVICE_ID}")
    logger.info(f"VAD threshold: {VAD_THRESHOLD}")

    if not GATEWAY_BASE:
        logger.error("GATEWAY_URL not set — cannot reach gateway")
        return

    # Load Silero VAD
    vad_model = load_vad_model()

    # Wait for local runtime (serves face UI)
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{LOCAL_API}/health", timeout=3)
            break
        except Exception:
            time.sleep(1)
    else:
        logger.warning("local runtime not reachable, starting anyway")

    set_face_state("idle")

    while True:
        try:
            audio = record_until_silence(vad_model)
            if not audio:
                continue

            transcript = transcribe(audio)
            if not transcript:
                logger.info("empty transcript, ignoring")
                set_face_state("idle")
                continue

            answer = chat(transcript)
            if not answer:
                logger.warning("empty answer")
                set_face_state("error")
                time.sleep(2)
                continue

            speak(answer)
            set_face_state("idle")

        except KeyboardInterrupt:
            logger.info("pipeline stopped")
            set_face_state("idle")
            break
        except Exception as exc:
            logger.error(f"pipeline error: {exc}")
            set_face_state("error")
            time.sleep(3)
            set_face_state("idle")


if __name__ == "__main__":
    pipeline_loop()
