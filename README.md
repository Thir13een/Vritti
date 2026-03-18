# Vritti — AI for Every Indian Language

Vritti is an AI-powered voice assistant that runs on Raspberry Pi. It listens, thinks, and speaks — in any Indian language.

The Pi is a thin client: all AI processing (speech-to-text, chat, text-to-speech) happens on the Vritti cloud gateway. The Pi handles mic capture, voice activity detection, and audio playback.

## What's Inside

```
pi/
  ai-runtime/       Local runtime server (FastAPI) + voice pipeline
  face-ui/           Mandala face display (reacts to voice state)
  device-agent/      Heartbeat agent for gateway connectivity
  installer/         One-command Pi setup
  systemd/           Auto-start services on boot
```

## Install on Raspberry Pi

```bash
sudo bash pi/installer/install.sh
```

The installer will:
1. Install system packages (Python, pip)
2. Let you choose a local AI model (Qwen 3.5 0.8B or 2B)
3. Set up ai-runtime, device-agent, face UI, and voice pipeline
4. Register with the Vritti gateway (if configured)
5. Enable all services to start on boot

After install, edit `/opt/ai-runtime/.env`:

```
GATEWAY_URL=https://<gateway-server>/v1/chat
GATEWAY_REGISTER_URL=https://<gateway-server>/v1/device/register
GATEWAY_BOOTSTRAP_SECRET=<secret from gateway admin>
```

Then restart:

```bash
sudo systemctl restart ai-runtime device-agent vritti-voice
```

## How It Works

```
  You speak
    ↓
  [Pi] Mic → Silero VAD (speech detection)
    ↓
  [Gateway] STT → Chat AI → TTS
    ↓
  [Pi] Speaker plays response
    ↓
  Mandala face animates throughout
```

- **Voice Activity Detection**: Silero VAD (neural, ~2MB) detects when you start/stop speaking
- **Speech-to-Text**: Sarvam AI (supports Indian languages)
- **Chat**: Sarvam AI / OpenRouter (multilingual)
- **Text-to-Speech**: XTTS-v2 with custom voice cloning
- **Face UI**: Mandala animation reacts to pipeline state (idle → listening → thinking → speaking)

## Services

| Service | Port | Description |
|---------|------|-------------|
| `ai-runtime` | 8000 | Local API server, serves face UI, exposes voice state |
| `device-agent` | — | Sends heartbeat to gateway every 60s |
| `vritti-voice` | — | Voice pipeline: mic → STT → chat → TTS → speaker |
| `vritti-kiosk` | — | Fullscreen Chromium displaying mandala face |

## Quick Commands

```bash
# Check status
sudo systemctl status ai-runtime device-agent vritti-voice

# View logs
sudo journalctl -u vritti-voice -n 100 -f

# Test chat
curl -s http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hindi me 2 line ka intro do"}'

# Restart everything
sudo systemctl restart ai-runtime device-agent vritti-voice
```

## Hardware

- Raspberry Pi 4 (4GB+) or Pi 5 recommended
- USB microphone
- Speaker (3.5mm or USB)
- Display for mandala face (HDMI)

## Configuration

Runtime config: `/opt/ai-runtime/.env`

| Variable | Description |
|----------|-------------|
| `GATEWAY_URL` | Gateway chat endpoint |
| `GATEWAY_DEVICE_TOKEN` | Device auth token (auto-issued on registration) |
| `DEVICE_ID` | This Pi's identifier (defaults to hostname) |
| `LOCAL_MODEL` | Local Ollama model (qwen3.5:0.8b or qwen3.5:2b) |
| `LOCAL_BACKEND` | ollama or llamacpp |
| `VAD_THRESHOLD` | Voice detection sensitivity (default: 0.5) |
