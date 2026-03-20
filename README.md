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
  🟠 [Pi] Mic → Silero VAD (neural speech detection)
     ↓
  🧠 [Pi / Cloud] AI Chat (local Qwen or gateway)
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

> 💡 The installer will guide you through model selection, dependency install, and gateway registration.

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
| 🎤 `vritti-voice` | Voice pipeline — mic → VAD → local chat |
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
| `GATEWAY_DEVICE_TOKEN` | Auth token (auto-issued on registration) |
| `DEVICE_ID` | Pi identifier (defaults to hostname) |
| `LOCAL_MODEL` | Ollama model (`qwen3.5:0.8b` or `qwen3.5:2b`) |
| `LOCAL_BACKEND` | `ollama` or `llamacpp` |
| `VAD_THRESHOLD` | Speech detection sensitivity (default: `0.5`) |

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|-----------|
| 🎤 Voice detection | Silero VAD (PyTorch, ~2MB) |
| 💬 Chat AI | Sarvam AI / OpenRouter (gateway) or local Qwen |
| 🧠 Local model | Qwen 3.5 (0.8B / 2B via Ollama) |
| 🖥️ Pi server | FastAPI + Uvicorn |
| 🪷 Face display | HTML5 Canvas mandala animation |
| ⚙️ Process manager | systemd |

---

<p align="center">
  <strong>🪷 Vritti</strong> — <em>AI for every Indian language</em>
</p>
