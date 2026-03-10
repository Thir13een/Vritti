# AI Appliance Starter (Pi + Gateway)

This repo now contains a deployable starter architecture:

- `pi/ai-runtime/`: runs on Raspberry Pi, calls local **Qwen 3.5 2B** first, then gateway fallback only when needed.
- `cloud/gateway/`: cloud API that serves fallback using **local Ollama** (default **Qwen 3.5 9B**). Run `ollama pull qwen3.5:9b` on the server; see `docs/GOOD_MODELS_AND_INFERENCE.md`.
- `cloud/gateway/web/`: Next.js admin dashboard UI.
- `pi/device-agent/`: optional heartbeat service from Pi to gateway.
- `pi/installer/`: one-command installer for Pi.
- `pi/systemd/`: service units for auto-start on boot.

## 1) Run Gateway (your server)

**Quick install (recommended):** See **[docs/INSTALL_SERVER.md](docs/INSTALL_SERVER.md)** for the full server guide. One-command installer:

```bash
bash cloud/gateway/install-server.sh
```

Then ensure Ollama is running with `qwen3.5:9b` on the server and start with Docker or uvicorn (see the guide).

**Manual run (no installer):**

```bash
cd cloud/gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash bootstrap.sh
set -a && source .env && set +a
uvicorn app:app --host 0.0.0.0 --port 9000
```

Required gateway env values:
- `DEVICE_REGISTER_SECRET` (bootstrap secret used during Pi provisioning)
- `DATABASE_URL` (PostgreSQL DSN for device/token storage)
- `TOKEN_HASH_SECRET` (pepper used for hashing device tokens in DB)
- `ADMIN_SECRET` (for protected admin APIs/dashboard actions)

### Gateway with Docker Compose (recommended)

```bash
cd cloud/gateway
bash bootstrap.sh
# ensure Ollama is running with qwen3.5:9b (or set OLLAMA_BASE/OLLAMA_MODEL in .env)
docker compose up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f gateway
docker compose logs -f web
```

Dashboard:

```text
http://localhost:3000/
```

Admin dashboard flow:
- Login from UI using `ADMIN_SECRET` (calls `POST /v1/admin/login`)
- UI stores bearer token in memory for admin APIs
- Admin APIs: `GET /v1/admin/devices`, `POST /v1/admin/devices/{device_id}/revoke`

Stop:

```bash
docker compose down
```

## 2) Install on Raspberry Pi (friend machine)

Copy this repo to Pi and run:

```bash
cd Vritti
sudo bash pi/installer/install.sh
```

Then edit:

- `/opt/ai-runtime/.env`
- `/opt/device-agent/.env`

Set:

- `GATEWAY_URL=https://<your-server>/v1/fallback`
- `GATEWAY_REGISTER_URL=https://<your-server>/v1/device/register`
- `GATEWAY_BOOTSTRAP_SECRET=<same as gateway DEVICE_REGISTER_SECRET>`
- backend values (`LOCAL_BACKEND=ollama` or `llamacpp`)

Installer will auto-register device and fetch `GATEWAY_DEVICE_TOKEN`.
Each registration issues a token and gateway stores only its hash.

Restart:

```bash
sudo systemctl restart ai-runtime device-agent
```

Check logs:

```bash
sudo journalctl -u ai-runtime -n 200 --no-pager
sudo journalctl -u device-agent -n 200 --no-pager
```

## 3) Test Runtime

From Pi:

```bash
curl -s http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hindi me 2 line ka intro do"}'
```

## Notes

- Fallback runs on the server via local Ollama (Qwen 3.5 9B); no API key required.
- Runtime does local-first; fallback is conditional.
- `FORCE_FALLBACK=true` in `/opt/ai-runtime/.env` can be used for testing.
