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
RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.03
CHUNK_SAMPLES = int(RATE * CHUNK_DURATION)

# Silero VAD settings
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
SPEECH_START_CHUNKS = 3
SILENCE_END_SECONDS = float(os.getenv("SILENCE_END_SECONDS", "0.6"))
MIN_RECORDING_SECONDS = 0.5

# Gateway config
GATEWAY_BASE = os.getenv("GATEWAY_URL", "http://127.0.0.1:9000/v1/chat").strip().replace("/v1/chat", "")
GATEWAY_TOKEN = os.getenv("GATEWAY_DEVICE_TOKEN", "").strip()
DEVICE_ID = os.getenv("DEVICE_ID", "").strip()
VOICE_MODE = os.getenv("VOICE_MODE", "fast").strip()


# ── Face UI state ──
STATE_FILE = Path("/tmp/vritti-state")


def set_face_state(state: str):
    STATE_FILE.write_text(state)
    logger.info(f"state → {state}")


# ── Silero VAD ──

def load_vad_model():
    logger.info("loading Silero VAD model...")
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )
    logger.info("Silero VAD loaded")
    return model


def is_speech(model, audio_chunk: bytes) -> bool:
    samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
    tensor = torch.from_numpy(samples)
    confidence = model(tensor, RATE).item()
    return confidence > VAD_THRESHOLD


def record_until_silence(vad_model) -> bytes | None:
    """Record from mic until speech ends."""
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
        logger.info(f"too short — {duration:.1f}s, ignoring")
        return None

    logger.info(f"recorded {duration:.1f}s of audio")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
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
    player = shutil.which("mpg123") or shutil.which("ffplay")
    if not player:
        logger.error("no audio player found — install mpg123: sudo apt install mpg123")
        return
    try:
        cmd = [player, "-q", "-"] if "mpg123" in player else [player, "-nodisp", "-autoexit", "-"]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.communicate(input=audio_bytes, timeout=15)
    except Exception as exc:
        logger.error(f"playback error: {exc}")


# ── Gateway voice roundtrip ──

def voice_roundtrip(wav_bytes: bytes):
    """Send audio to gateway, parse NDJSON stream, play audio."""
    audio_bytes, content_type = _compress_audio(wav_bytes)

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
            "x-voice-mode": VOICE_MODE,
        },
    )

    set_face_state("thinking")
    t0 = time.time()

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "stt":
                    logger.info(f"transcript: {msg.get('text', '')}")

                elif msg_type == "audio":
                    set_face_state("speaking")
                    audio = base64.b64decode(msg["data"])
                    _play_audio(audio)

                elif msg_type == "done":
                    elapsed = time.time() - t0
                    logger.info(f"done in {elapsed:.1f}s: {msg.get('text', '')[:80]}")

                elif msg_type == "error":
                    logger.error(f"gateway error: {msg.get('detail', '')}")

    except Exception as exc:
        logger.error(f"voice roundtrip failed: {exc}")

    set_face_state("idle")


# ── Main loop ──

def pipeline_loop():
    logger.info("voice pipeline started")
    logger.info(f"VAD threshold: {VAD_THRESHOLD}, silence: {SILENCE_END_SECONDS}s")
    logger.info(f"gateway: {GATEWAY_BASE}")

    # Check for audio player
    if not (shutil.which("mpg123") or shutil.which("ffplay")):
        logger.warning("no audio player found — install mpg123: sudo apt install mpg123")

    vad_model = load_vad_model()

    # Wait for gateway if configured
    if GATEWAY_TOKEN:
        for _ in range(10):
            try:
                urllib.request.urlopen(f"{GATEWAY_BASE}/health", timeout=3)
                logger.info("gateway reachable")
                break
            except Exception:
                time.sleep(1)
        else:
            logger.warning("gateway not reachable, starting anyway")

    set_face_state("idle")

    while True:
        try:
            audio = record_until_silence(vad_model)
            if not audio:
                continue

            if GATEWAY_TOKEN:
                voice_roundtrip(audio)
            else:
                logger.info("no gateway token configured, audio captured but not sent")
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
