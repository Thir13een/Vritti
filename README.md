<p align="center">
  <img src="assets/vritti-symbol.png" alt="Vritti" width="200" />
</p>

<h1 align="center">🪷 Vritti</h1>
<p align="center">
  <strong>Voice AI for every Indian language</strong><br/>
  <em>Raspberry Pi on the edge. Gateway in the cloud. Fast voice in simple English.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Raspberry%20Pi-c51a4a?style=for-the-badge&logo=raspberrypi&logoColor=white" alt="Raspberry Pi" />
  <img src="https://img.shields.io/badge/runtime-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/voice-Silero%20VAD-ff6f00?style=for-the-badge" alt="Silero VAD" />
  <img src="https://img.shields.io/badge/install-interactive-1f6feb?style=for-the-badge" alt="Interactive Install" />
</p>

---

## 🌼 What Is Vritti?

Vritti is a voice product for Raspberry Pi devices.

The Pi does the local device work:
- mic input
- speaker playback
- face UI
- voice activity detection
- kiosk mode
- heartbeat to the gateway

The gateway does the heavy work:
- chat
- speech-to-text
- text-to-speech
- device approval
- device tokens
- privacy-first memory
- admin dashboard

This means the Pi stays light, simple, and cheaper to run.

---

## 🧭 How It Works

```text
         YOU
          │
          ▼
   🎤 Speak to Pi
          │
          ▼
 ┌───────────────────────┐
 │ Raspberry Pi Device   │
 │                       │
 │  • Mic / speaker      │
 │  • Silero VAD         │
 │  • Face UI            │
 │  • Local relay        │
 │  • Heartbeat agent    │
 └──────────┬────────────┘
            │
            ▼
 ┌──────────────────────────────┐
 │ Vritti Gateway               │
 │                              │
 │  • Device auth               │
 │  • Chat                      │
 │  • STT                       │
 │  • TTS                       │
 │  • Memory + summaries        │
 │  • Admin dashboard           │
 └──────────┬───────────────────┘
            │
            ▼
   🔊 Audio reply to Pi
            │
            ▼
      🪷 Face reacts
```

---

## ✨ What You Get

| Feature | What it means |
|---|---|
| 🗣️ Multilingual voice | Built for Indian language use cases |
| 🪷 Kiosk face UI | Full-screen mandala display for the Pi |
| 📡 Gateway-first design | Pi uses the gateway first for real work |
| 🧯 Optional local fallback | Pi can run gateway-only or use local Ollama fallback |
| 🔐 Approved device access | A Pi must be approved from the gateway dashboard |
| 🧠 Privacy-first memory | Memory facts and summaries persist, raw transcripts are off by default on the gateway |
| ⚙️ Auto-start services | `systemd` starts the Pi stack on boot |
| 🎛️ Simple installer | One interactive installer for the Pi |

---

## 🧱 Pi Architecture

```text
┌──────────────────────────────────────────────┐
│ Pi Side                                      │
│                                              │
│  ai-runtime      -> local API on :8000       │
│  vritti-voice    -> mic + VAD + shared state │
│  vritti-kiosk    -> Chromium full-screen UI  │
│  device-agent    -> heartbeat to gateway     │
└──────────────────────────────────────────────┘
```

Main files:
- `pi/ai-runtime/`
- `pi/face-ui/`
- `pi/device-agent/`
- `pi/installer/`
- `pi/systemd/`

---

## 🧰 Hardware

| Part | Recommended |
|---|---|
| Board | Raspberry Pi 4 (4 GB+) or Pi 5 |
| Mic | USB mic |
| Speaker | USB or 3.5mm speaker |
| Display | HDMI display for face UI |
| Storage | 16 GB+ microSD |
| Network | Stable Wi‑Fi or Ethernet |

You can still run without a display, but the face UI is part of the intended product experience.

---

## 🚀 Quick Start

### 1. Prepare the Pi

Install Raspberry Pi OS, boot the Pi, and connect it to the internet.

### 2. Run the one-line installer

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Thir13een/Vritti/main/install-pi.sh)
```

The installer does these things:
- installs system packages
- installs Chromium
- copies Pi runtime files into `/opt`
- installs Python dependencies
- sets up `systemd` services
- asks which local model mode you want
- requests gateway access for the Pi

You do not need to manually enter:
- device token
- bootstrap secret
- device id in most cases

### 3. Developer / repo path

If you already cloned the repo and want to run the installer from source:

```bash
git clone https://github.com/Thir13een/Vritti.git
cd Vritti
sudo bash install-pi.sh
```

### 4. Choose Pi model mode

The installer offers:

| Choice | Meaning |
|---|---|
| `0` | no local model, gateway-only |
| `1` | `qwen3.5:0.8b` |
| `2` | `qwen3.5:2b` |

Simple rule:
- choose `0` if you always want gateway mode
- choose `1` for smaller Pis or low RAM
- choose `2` for stronger local fallback on bigger Pis

### 5. Approve the Pi

The installer can request gateway access, but the Pi is not trusted automatically.

Flow:

```text
Pi starts install
   │
   ▼
Pi sends access request
   │
   ▼
Gateway shows device as PENDING with a pairing code
   │
   ▼
You verify the code on the physical Pi
   │
   ▼
You approve it in dashboard
   │
   ▼
Pi receives real device token
```

If the gateway is configured, the installer waits for approval for up to 5 minutes.
The installer also shows the pairing code so you can match it against the dashboard before approving.
After approval, the token is saved automatically on the Pi.

---

## 🔐 Gateway Settings On The Pi

Main runtime config lives at:

```text
/opt/ai-runtime/.env
```

Typical values:

```env
GATEWAY_URL=https://vritti.dev/v1/chat
GATEWAY_VOICE_WS_URL=wss://vritti.dev/v1/voice/ws
GATEWAY_REGISTER_URL=https://vritti.dev/v1/device/register
GATEWAY_DEVICE_TOKEN=<auto-issued after approval>
DEVICE_ID=<hostname or custom id>
```

Optional:

```env
# trusted bootstrap hint, not required for normal onboarding
# GATEWAY_BOOTSTRAP_SECRET=<optional secret>
```

Heartbeat config lives at:

```text
/opt/device-agent/.env
```

---

## 🗂️ Project Layout

```text
pi/
├── ai-runtime/        FastAPI Pi runtime
├── device-agent/      Heartbeat agent
├── face-ui/           Mandala browser UI
├── installer/         Pi installer and env examples
└── systemd/           Service unit files
```

---

## ⚙️ Pi Services

| Service | Purpose |
|---|---|
| `ai-runtime` | local API, face UI serving, gateway relay |
| `vritti-voice` | mic pipeline, VAD, shared runtime state |
| `vritti-kiosk` | Chromium kiosk face UI |
| `device-agent` | heartbeat to gateway |

Check them:

```bash
sudo systemctl status ai-runtime vritti-voice device-agent
```

Restart them:

```bash
sudo systemctl restart ai-runtime vritti-voice device-agent
```

---

## 🧪 Health And Debugging

### Pi runtime health

```bash
curl -s http://127.0.0.1:8000/health
```

You should usually see:
- `status: ok`
- `gateway: reachable`
- `backend: reachable`

### Important note about local fallback

On a machine that is not a real Pi install, local fallback may show as unreachable if local Ollama or llama.cpp is not running.

That is fine if:
- gateway is reachable
- backend is reachable

### Useful logs

```bash
sudo journalctl -u ai-runtime -f
sudo journalctl -u vritti-voice -f
sudo journalctl -u device-agent -f
```

---

## 🎙️ Voice Path

Preferred path:

```text
Browser UI
  -> ws://127.0.0.1:8000/v1/voice/ws
  -> Pi runtime relay
  -> gateway voice endpoint
```

Fallback path:

```text
Browser UI
  -> /v1/voice-proxy
  -> Pi runtime
  -> gateway
```

This gives lower latency when the streaming path is available.

---

## 🛠️ Useful Commands

### Test chat

```bash
curl -s http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Namaste"}'
```

### Check config summary

```bash
curl -s http://127.0.0.1:8000/v1/config
```

### Check mode

```bash
curl -s http://127.0.0.1:8000/v1/mode
```

---

## 🧾 Important Config Values

| Variable | Meaning |
|---|---|
| `LOCAL_BACKEND` | `ollama` or `none` |
| `LOCAL_MODEL` | local Ollama model if enabled |
| `GATEWAY_URL` | chat endpoint |
| `GATEWAY_VOICE_WS_URL` | streaming voice endpoint |
| `GATEWAY_REGISTER_URL` | approval request endpoint |
| `GATEWAY_DEVICE_TOKEN` | approved device token |
| `DEVICE_ID` | Pi identifier |
| `VAD_THRESHOLD` | voice detection sensitivity |
| `VOICE_STREAM_FRAME_MS` | browser voice chunk size |
| `VRITTI_FACE_UI_SOURCE` | face UI source selection |

---

## 🧠 Gateway-Only vs Local Fallback

```text
Option A: Gateway-only
Pi -> Gateway

Option B: Gateway-first + local fallback
Pi -> Gateway
     └─ if unavailable -> local Ollama
```

Recommended:
- use gateway-only if your network is stable and you want the simplest setup
- use local fallback if you want some device-side resilience

---

## 🧩 Tech Stack

| Layer | Technology |
|---|---|
| Pi API | FastAPI + Uvicorn |
| Voice detection | Silero VAD |
| Kiosk browser | Chromium |
| Local fallback | Ollama + Qwen 3.5 |
| Service management | systemd |
| Face UI | HTML + Canvas |

---

## 🛟 Troubleshooting

### Installer says the device is still pending

Open the gateway dashboard and approve the Pi.

### `backend` is unreachable

Check:
- gateway URL
- token
- internet access
- gateway health

### Mic problems

Check:

```bash
arecord -l
aplay -l
```

### Kiosk does not open

Check:

```bash
sudo systemctl status vritti-kiosk
```

---

## 🔗 Related Repo

Gateway repo:
- `Vritti-Gateway`

That repo handles:
- device approval
- dashboard
- chat/STT/TTS
- memory
- privacy and cleanup

---

<p align="center">
  <strong>🪷 Vritti</strong><br/>
  <em>Simple voice product for Raspberry Pi devices</em>
</p>

## 👥 Team

| Member | GitHub |
|---|---|
| Krish | [@Thir13een](https://github.com/Thir13een) |
| Shweta | [@shwetabankar54](https://github.com/shwetabankar54) |



<br/>

<div align="center">

<h3>🤝 Built By</h3>

<a href="https://github.com/Thir13een">
  <img src="https://github.com/Thir13een.png" width="70" style="border-radius:50%"/>
  <br/><sub><b>Krish</b></sub>
</a>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://github.com/shwetabankar54">
  <img src="https://github.com/shwetabankar54.png" width="70" style="border-radius:50%"/>
  <br/><sub><b>Shweta</b></sub>
</a>

</div>
