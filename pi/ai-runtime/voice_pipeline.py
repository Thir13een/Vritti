"""Voice pipeline: mic → VAD → local chat."""
from __future__ import annotations

import io
import json
import logging
import os
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

# Local runtime
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


# ── Face UI state control ──
STATE_FILE = Path("/tmp/vritti-state")


def set_face_state(state: str):
    """Update mandala face state."""
    STATE_FILE.write_text(state)
    logger.info(f"state → {state}")


# ── Silero VAD ──

def load_vad_model():
    """Load Silero VAD model."""
    logger.info("loading Silero VAD model...")
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )
    logger.info("Silero VAD loaded")
    return model


def is_speech(model, audio_chunk: bytes) -> bool:
    """Check if audio chunk contains speech."""
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


def pipeline_loop():
    """Main voice pipeline loop."""
    logger.info("voice pipeline started")
    logger.info(f"VAD threshold: {VAD_THRESHOLD}")

    vad_model = load_vad_model()

    # Wait for local runtime
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

            logger.info("audio captured, ready for processing")
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
