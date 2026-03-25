<p align="center">
  <img src="assets/vritti-symbol.png" alt="Vritti" width="200" />
</p>

<h1 align="center">🪷 Vritti</h1>
<p align="center">
  <strong>AI voice assistant for every Indian language</strong><br/>
  <em>Runs on Raspberry Pi — listens, thinks, and speaks.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Raspberry%20Pi-c51a4a?style=for-the-badge&logo=raspberrypi&logoColor=white" alt="Raspberry Pi" />
  <img src="https://img.shields.io/badge/python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/voice-Silero%20VAD-ff6f00?style=for-the-badge" alt="Silero VAD" />

</p>

---

## 🌟 What is Vritti?

Vritti is an open-source voice assistant **built for India**. Plug a mic and speaker into a Raspberry Pi, run the installer, and you have a device that understands and responds in **your language**.

> 🗣️ Hindi · English · Tamil · Telugu · Bengali · Marathi · Gujarati · Kannada · Malayalam · Punjabi — and more

The Pi is a **thin client** — it captures your voice and plays back audio. All the heavy lifting happens on the Vritti cloud gateway:

```
  🎤 You speak
     ↓
  🟠 [Pi] Mic → Silero VAD + streaming voice relay
     ↓
  🧠 [Cloud] Streaming STT → fast LLM → streaming TTS
     ↓
  🪷 Mandala face animates throughout
```

---

## ✨ Features

| | Feature | Details |
|---|---------|---------|
| 🗣️ | **Multilingual** | 10+ Indian languages, auto-detects and responds in your language |
| 🧠 | **Neural VAD** | Silero voice activity detection (~2MB), no false triggers |
| 📡 | **Thin client** | No API keys on device, no GPU needed on Pi |
| 🧯 | **Gateway fallback** | Gateway-first with local Ollama fallback on the Pi |
| 🪷 | **Mandala face** | Living animated display reacts to conversation state |
| ⚡ | **One-command install** | Interactive installer with model selection |
| 🔄 | **Auto-start** | systemd services — boots ready to talk |
| 🔐 | **Secure** | Device token auth, hashed tokens, no secrets on Pi |

---

## 🔧 Hardware

| Component | Requirement |
|-----------|-------------|
| 🖥️ **Board** | Raspberry Pi 4 (4GB+) or Pi 5 |
| 🎤 **Mic** | USB microphone |
| 🔊 **Speaker** | 3.5mm or USB speaker |
| 📺 **Display** | HDMI screen for mandala face *(optional)* |
| 💾 **Storage** | 16GB+ SD card |

---

## 🚀 Quick Start

### 1️⃣ Flash Raspberry Pi OS and boot your Pi

### 2️⃣ Clone and install

```bash
git clone https://github.com/Thir13een/Vritti.git
cd Vritti
sudo bash pi/installer/install.sh
```

> 💡 The installer will guide you through model selection, dependency install, Ollama local fallback setup, and gateway registration.
> It now fails the install if it cannot leave the Pi with at least one reachable chat backend: gateway or local Ollama.

### 3️⃣ Connect to gateway

Edit `/opt/ai-runtime/.env`:

```env
GATEWAY_URL=https://<your-gateway>/v1/chat
GATEWAY_REGISTER_URL=https://<your-gateway>/v1/device/register
GATEWAY_BOOTSTRAP_SECRET=<secret from gateway admin>
```

```bash
sudo systemctl restart ai-runtime device-agent vritti-voice
```

🎉 **That's it — start talking!**

---

## 📁 Project Structure

```
pi/
├── ai-runtime/       🧠 FastAPI server + voice pipeline + local AI
├── face-ui/          🪷 Living mandala display (HTML/JS Canvas)
├── device-agent/     📡 Heartbeat agent for gateway connectivity
├── installer/        ⚡ One-command interactive setup
└── systemd/          🔄 Service units (auto-start on boot)
```

---

## ⚙️ Services

| Service | Description |
|---------|-------------|
| 🧠 `ai-runtime` | Local API server (port 8000), serves face UI, exposes voice state |
| 🎤 `vritti-voice` | Voice pipeline — mic → VAD → shared state + local diagnostics |
| 🪷 `vritti-kiosk` | Fullscreen Chromium kiosk showing mandala face |
| 📡 `device-agent` | Heartbeat to gateway every 60s |

---

## 🛠️ Useful Commands

```bash
# 📊 Status
sudo systemctl status ai-runtime vritti-voice device-agent

# 📋 Logs
sudo journalctl -u vritti-voice -f

# 💬 Test chat
curl -s http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Namaste, kaise ho?"}'

# 🔄 Restart
sudo systemctl restart ai-runtime vritti-voice device-agent
```

---

## 📝 Configuration

Runtime config: `/opt/ai-runtime/.env`

| Variable | Description |
|----------|-------------|
| `GATEWAY_URL` | Gateway chat endpoint |
| `GATEWAY_VOICE_WS_URL` | Gateway streaming voice WebSocket endpoint |
| `GATEWAY_DEVICE_TOKEN` | Auth token (auto-issued on registration) |
| `DEVICE_ID` | Pi identifier (defaults to hostname) |
| `LOCAL_MODEL` | Ollama fallback model (`qwen3.5:0.8b` or `qwen3.5:2b`) |
| `LOCAL_BACKEND` | Local backend, defaults to `ollama` on Pi installs |
| `VAD_THRESHOLD` | Speech detection sensitivity (default: `0.5`) |
| `VOICE_STREAM_FRAME_MS` | Browser voice stream chunk size for gateway relay |
| `VRITTI_FACE_UI_SOURCE` | Set to `github` to serve the face UI from GitHub raw (cached on startup) instead of `/opt/face-ui` |
| `VRITTI_FACE_UI_GITHUB_URL` | Optional raw URL to `index.html` (default: `Thir13een/Vritti` main `pi/face-ui/index.html`) |

---

## Voice Streaming

The Pi UI now prefers a local WebSocket relay at `ws://127.0.0.1:8000/v1/voice/ws` and falls back to the older batch `/v1/voice-proxy` path if the gateway voice WebSocket is unavailable.

For the low-latency path, your gateway must expose a streaming voice endpoint compatible with `GATEWAY_VOICE_WS_URL`.

Recommended voice model split:

- Voice / talk mode: `Sarvam 30B`
- Build / deep reasoning mode: `Sarvam 105B`

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|-----------|
| 🎤 Voice detection | Silero VAD (PyTorch, ~2MB) |
| 💬 Chat AI | Sarvam AI / OpenRouter (gateway) or local Qwen |
| 🧠 Local model | Qwen 3.5 (0.8B / 2B via Ollama fallback) |
| 🖥️ Pi server | FastAPI + Uvicorn |
| 🪷 Face display | HTML5 Canvas mandala animation |
| ⚙️ Process manager | systemd |

---

<p align="center">
  <strong>🪷 Vritti</strong> — <em>AI for every Indian language</em>
</p>
