<p align="center">
  <img src="assets/vritti-symbol.png" alt="Vritti" width="120" />
</p>

<h1 align="center">Vritti</h1>
<p align="center"><strong>AI voice assistant for every Indian language</strong></p>
<p align="center">
  Runs on Raspberry Pi — listens, thinks, and speaks in Hindi, Tamil, Telugu, Bengali, Marathi, and more.
</p>

---

## What is Vritti?

Vritti is an open-source voice assistant built for India. Plug a mic and speaker into a Raspberry Pi, run the installer, and you have a device that understands and responds in your language.

The Pi is a **thin client** — it captures your voice, detects speech, and plays back audio. All the heavy lifting (speech-to-text, AI chat, text-to-speech with a custom cloned voice) happens on the Vritti cloud gateway.

### Voice Pipeline

```
  You speak
    ↓
  [Pi] Mic capture → Silero VAD (neural speech detection)
    ↓
  [Cloud] Speech-to-Text → AI Chat → Text-to-Speech
    ↓
  [Pi] Speaker plays response
```

A living mandala face animates on the Pi's display throughout — **idle**, **listening**, **thinking**, **speaking**.

---

## Features

- **Multilingual** — Hindi, English, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, and more
- **Voice cloning** — custom TTS voice via XTTS-v2 (sounds like whoever you want)
- **Neural VAD** — Silero voice activity detection, no false triggers
- **Thin client** — no API keys on the device, no GPU needed on Pi
- **Mandala face** — animated display reacts to conversation state
- **One-command install** — interactive installer with model selection
- **Auto-start** — systemd services, boots ready to talk
- **Secure** — device token auth, no secrets on Pi, hashed tokens on server

---

## Hardware

| Component | Requirement |
|-----------|-------------|
| **Board** | Raspberry Pi 4 (4GB+) or Pi 5 |
| **Mic** | USB microphone |
| **Speaker** | 3.5mm or USB speaker |
| **Display** | HDMI screen for mandala face (optional) |
| **Storage** | 16GB+ SD card |

---

## Quick Start

### 1. Flash Raspberry Pi OS and boot your Pi

### 2. Clone and install

```bash
git clone https://github.com/Thir13een/Vritti.git
cd Vritti
sudo bash pi/installer/install.sh
```

The installer will:
- Install system packages
- Let you choose a local AI model (Qwen 3.5 0.8B or 2B)
- Set up voice pipeline, face UI, device agent
- Register with the gateway (if configured)
- Enable all services to start on boot

### 3. Connect to gateway

Edit `/opt/ai-runtime/.env`:

```
GATEWAY_URL=https://<your-gateway>/v1/chat
GATEWAY_REGISTER_URL=https://<your-gateway>/v1/device/register
GATEWAY_BOOTSTRAP_SECRET=<secret from gateway admin>
```

```bash
sudo systemctl restart ai-runtime device-agent vritti-voice
```

That's it — start talking.

---

## Project Structure

```
pi/
  ai-runtime/       FastAPI server + voice pipeline + local AI
  face-ui/           Living mandala display (HTML/JS)
  device-agent/      Heartbeat agent for gateway connectivity
  installer/         One-command interactive setup
  systemd/           Service units (auto-start on boot)
assets/              Logo and branding
```

## Services

| Service | Description |
|---------|-------------|
| `ai-runtime` | Local API server (port 8000), serves face UI, exposes voice state |
| `vritti-voice` | Voice pipeline — mic → VAD → STT → chat → TTS → speaker |
| `vritti-kiosk` | Fullscreen Chromium kiosk showing mandala face |
| `device-agent` | Heartbeat to gateway every 60s |

---

## Useful Commands

```bash
# Status
sudo systemctl status ai-runtime vritti-voice device-agent

# Logs
sudo journalctl -u vritti-voice -f

# Test chat
curl -s http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Namaste, kaise ho?"}'

# Restart
sudo systemctl restart ai-runtime vritti-voice device-agent
```

---

## Configuration

Runtime: `/opt/ai-runtime/.env`

| Variable | Description |
|----------|-------------|
| `GATEWAY_URL` | Gateway chat endpoint |
| `GATEWAY_DEVICE_TOKEN` | Auth token (auto-issued on registration) |
| `DEVICE_ID` | Pi identifier (defaults to hostname) |
| `LOCAL_MODEL` | Ollama model (`qwen3.5:0.8b` or `qwen3.5:2b`) |
| `LOCAL_BACKEND` | `ollama` or `llamacpp` |
| `VAD_THRESHOLD` | Speech detection sensitivity (default: `0.5`) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Voice detection | Silero VAD (PyTorch, ~2MB) |
| Speech-to-text | Sarvam AI (Indian language STT) |
| Chat AI | Sarvam AI / OpenRouter |
| Text-to-speech | XTTS-v2 (self-hosted, voice cloning) |
| Local model | Qwen 3.5 (0.8B / 2B via Ollama) |
| Pi server | FastAPI + Uvicorn |
| Face display | HTML5 Canvas mandala animation |
| Process manager | systemd |

---

## License

MIT
