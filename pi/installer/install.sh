#!/usr/bin/env bash
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Vritti Pi Installer                                                    ║
# ║  Sets up ai-runtime + device-agent + systemd on Raspberry Pi.           ║
# ║                                                                         ║
# ║  Usage:  sudo bash pi/installer/install.sh                              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash pi/installer/install.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_ENV="/opt/ai-runtime/.env"
AGENT_ENV="/opt/device-agent/.env"
TOTAL_STEPS=7
SECONDS=0

# ── Color & formatting ───────────────────────────────────────────────────────
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  RST="$(tput sgr0)"
  BOLD="$(tput bold)"
  DIM="$(tput dim)"
  UL="$(tput smul)"
  GREEN="$(tput setaf 2)"
  YELLOW="$(tput setaf 3)"
  RED="$(tput setaf 1)"
  CYAN="$(tput setaf 6)"
  BLUE="$(tput setaf 4)"
  MAGENTA="$(tput setaf 5)"
  WHITE="$(tput setaf 7)"
  BG_BLUE="$(tput setab 4)"
else
  RST="" BOLD="" DIM="" UL=""
  GREEN="" YELLOW="" RED="" CYAN="" BLUE="" MAGENTA="" WHITE=""
  BG_BLUE=""
fi

# ── Output helpers ────────────────────────────────────────────────────────────
divider() {
  echo "${DIM}  ─────────────────────────────────────────────────────────────────${RST}"
}

step_header() {
  local n="$1" title="$2"
  echo ""
  echo "  ${BOLD}${BG_BLUE}${WHITE} STEP ${n}/${TOTAL_STEPS} ${RST} ${BOLD}${BLUE}${title}${RST}"
  divider
}

ok()    { echo "  ${GREEN}  ✓  ${RST}${BOLD}$1${RST}${DIM}${2:+  — $2}${RST}"; }
info()  { echo "  ${CYAN}  ℹ  ${RST}${DIM}$*${RST}"; }
doing() { echo "  ${BLUE}  ►  ${RST}$*${DIM}...${RST}"; }
warn()  { echo "  ${YELLOW}  ⚠  ${RST}${YELLOW}$*${RST}"; }
fail()  { echo "  ${RED}  ✗  ${RST}${RED}${BOLD}$*${RST}" >&2; }
cmd()   { echo "       ${DIM}\$ $*${RST}"; }

section_box() {
  local title="$1"
  local color="${2:-$CYAN}"
  echo ""
  echo "  ${BOLD}${color}╭───────────────────────────────────────────────────────────╮${RST}"
  printf "  ${BOLD}${color}│${RST} ${BOLD}%-57s${RST} ${BOLD}${color}│${RST}\n" "$title"
  echo "  ${BOLD}${color}╰───────────────────────────────────────────────────────────╯${RST}"
}

result_line() {
  local label="$1" value="$2"
  printf "  ${BOLD}  %-18s${RST} %s\n" "$label" "$value"
}

# ── Utility functions ─────────────────────────────────────────────────────────
generate_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
  fi
}

upsert_env() {
  local file="$1" key="$2" value="$3"
  touch "$file"
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf "%s=%s\n" "$key" "$value" >>"$file"
  fi
}

get_env() {
  local file="$1" key="$2"
  awk -F= -v key="$key" '$1==key {print $2}' "$file" | tail -n1
}

register_with_gateway() {
  local register_url="$1" bootstrap_secret="$2" device_id="$3"
  python3 - "$register_url" "$bootstrap_secret" "$device_id" <<'PY'
import json, sys, urllib.request
register_url, bootstrap_secret, device_id = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(
    register_url,
    data=json.dumps({"device_id": device_id}).encode("utf-8"),
    headers={"Content-Type": "application/json", "x-bootstrap-secret": bootstrap_secret},
    method="POST",
)
with urllib.request.urlopen(req, timeout=20) as resp:
    data = json.loads(resp.read().decode("utf-8"))
print((data.get("device_token") or "").strip())
PY
}

# ══════════════════════════════════════════════════════════════════════════════
#   START
# ══════════════════════════════════════════════════════════════════════════════

echo ""
echo "${BOLD}${CYAN}"
echo "  ┌───────────────────────────────────────────────────────────────────┐"
echo "  │                                                                   │"
echo "  │    ██╗   ██╗██████╗ ██╗████████╗████████╗██╗                      │"
echo "  │    ██║   ██║██╔══██╗██║╚══██╔══╝╚══██╔══╝██║                      │"
echo "  │    ██║   ██║██████╔╝██║   ██║      ██║   ██║                      │"
echo "  │    ╚██╗ ██╔╝██╔══██╗██║   ██║      ██║   ██║                      │"
echo "  │     ╚████╔╝ ██║  ██║██║   ██║      ██║   ██║                      │"
echo "  │      ╚═══╝  ╚═╝  ╚═╝╚═╝   ╚═╝      ╚═╝   ╚═╝                      │"
echo "  │                                                                   │"
echo "  │          ${WHITE}P I   I N S T A L L E R${CYAN}                                │"
echo "  │          ${DIM}${WHITE}ai-runtime  ·  device-agent  ·  systemd${RST}${BOLD}${CYAN}             │"
echo "  │                                                                   │"
echo "  └───────────────────────────────────────────────────────────────────┘"
echo "${RST}"

info "Source directory: ${BOLD}${REPO_DIR}${RST}"
info "Hostname: ${BOLD}$(hostname)${RST}"
info "Time: $(date '+%Y-%m-%d %H:%M:%S')"

# ── Step 1: System packages ──────────────────────────────────────────────────
step_header 1 "Installing system packages"
info "Getting the basics: Python, pip, curl."
echo ""

doing "Updating package lists"
apt-get update -qq 2>&1 | tail -1 | while IFS= read -r line; do info "$line"; done
ok "Package lists updated"

doing "Installing python3, python3-venv, python3-pip, curl"
apt-get install -y -qq python3 python3-venv python3-pip curl 2>&1 | tail -3 | while IFS= read -r line; do
  info "$line"
done
ok "System packages installed"

info "Python version: ${BOLD}$(python3 --version 2>/dev/null)${RST}"

# ── Step 2: ai-runtime ──────────────────────────────────────────────────────
step_header 2 "Installing ai-runtime"
info "This is the core AI service. It runs a local Qwen 2B model and"
info "handles chat requests on port 8000."
echo ""

doing "Creating /opt/ai-runtime"
mkdir -p /opt/ai-runtime

doing "Copying runtime source files"
cp "${REPO_DIR}/ai-runtime/"*.py /opt/ai-runtime/
cp "${REPO_DIR}/ai-runtime/requirements.txt" /opt/ai-runtime/
ok "Copied Python files" "config.py, runtime.py, server.py"

if [[ -d "${REPO_DIR}/ai-runtime/static" ]]; then
  doing "Copying chat UI static files"
  mkdir -p /opt/ai-runtime/static
  cp -r "${REPO_DIR}/ai-runtime/static/." /opt/ai-runtime/static/
  ok "Static files copied" "local web chat UI"
fi

doing "Creating Python virtual environment"
python3 -m venv /opt/ai-runtime/.venv
ok "Virtual environment created" "/opt/ai-runtime/.venv"

doing "Installing Python dependencies"
/opt/ai-runtime/.venv/bin/pip install -q --upgrade pip
/opt/ai-runtime/.venv/bin/pip install -q -r /opt/ai-runtime/requirements.txt
PKG_COUNT=$(/opt/ai-runtime/.venv/bin/pip list --format=columns 2>/dev/null | tail -n +3 | wc -l)
ok "Dependencies installed" "${PKG_COUNT} packages (fastapi, uvicorn, pydantic...)"

if [[ ! -f "$RUNTIME_ENV" ]]; then
  doing "Creating runtime .env from example"
  cp "${REPO_DIR}/installer/runtime.env.example" "$RUNTIME_ENV"
  ok "Runtime config created" "$RUNTIME_ENV"
else
  ok "Runtime config exists" "$RUNTIME_ENV"
fi

# ── Step 3: device-agent ─────────────────────────────────────────────────────
step_header 3 "Installing device-agent"
info "The device agent sends a heartbeat to the server every 60 seconds"
info "so the admin dashboard knows this Pi is online."
echo ""

doing "Creating /opt/device-agent"
mkdir -p /opt/device-agent

doing "Copying agent source"
cp "${REPO_DIR}/device-agent/agent.py" /opt/device-agent/
ok "Device agent installed" "/opt/device-agent/agent.py"

if [[ ! -f "$AGENT_ENV" ]]; then
  doing "Creating agent .env from example"
  cp "${REPO_DIR}/installer/device-agent.env.example" "$AGENT_ENV"
  ok "Agent config created" "$AGENT_ENV"
else
  ok "Agent config exists" "$AGENT_ENV"
fi

# ── Step 4: Device registration & token ──────────────────────────────────────
step_header 4 "Device registration & token"
info "Each Pi needs a unique token to talk to the server. If the gateway"
info "is reachable, we'll register automatically and get one."
echo ""

TOKEN="$(get_env "$RUNTIME_ENV" "GATEWAY_DEVICE_TOKEN" || true)"
TOKEN_SOURCE="existing"

if [[ -z "${TOKEN}" || "${TOKEN}" == "replace_with_device_token" ]]; then
  REGISTER_URL="$(get_env "$RUNTIME_ENV" "GATEWAY_REGISTER_URL" || true)"
  BOOTSTRAP_SECRET="$(get_env "$RUNTIME_ENV" "GATEWAY_BOOTSTRAP_SECRET" || true)"
  DEVICE_ID="$(get_env "$RUNTIME_ENV" "DEVICE_ID" || true)"

  if [[ -z "${DEVICE_ID}" || "${DEVICE_ID}" == "pi-001" ]]; then
    DEVICE_ID="$(hostname)"
    upsert_env "$RUNTIME_ENV" "DEVICE_ID" "$DEVICE_ID"
    info "Device ID set to hostname: ${BOLD}${DEVICE_ID}${RST}"
  fi
  upsert_env "$AGENT_ENV" "DEVICE_ID" "$DEVICE_ID"

  if [[ -n "${REGISTER_URL}" && -n "${BOOTSTRAP_SECRET}" ]]; then
    doing "Registering device with gateway"
    info "Register URL: ${REGISTER_URL}"
    info "Device ID: ${DEVICE_ID}"
    set +e
    TOKEN="$(register_with_gateway "$REGISTER_URL" "$BOOTSTRAP_SECRET" "$DEVICE_ID")"
    REG_STATUS=$?
    set -e
    if [[ $REG_STATUS -ne 0 || -z "${TOKEN}" ]]; then
      warn "Gateway registration failed; leaving gateway token unset"
      TOKEN="replace_with_device_token"
      TOKEN_SOURCE="registration_failed"
    else
      ok "Registered with gateway" "device_id: ${DEVICE_ID}"
      TOKEN_SOURCE="gateway"
    fi
  else
    info "No GATEWAY_REGISTER_URL or GATEWAY_BOOTSTRAP_SECRET configured"
    TOKEN="replace_with_device_token"
    TOKEN_SOURCE="not_configured"
  fi
fi

upsert_env "$RUNTIME_ENV" "GATEWAY_DEVICE_TOKEN" "$TOKEN"
upsert_env "$AGENT_ENV" "GATEWAY_DEVICE_TOKEN" "$TOKEN"

# Derive heartbeat URL from the runtime's GATEWAY_URL so both services
# point at the same server without manual editing.
GATEWAY_URL="$(get_env "$RUNTIME_ENV" "GATEWAY_URL" || true)"
if [[ -n "${GATEWAY_URL}" && "${GATEWAY_URL}" != *"your-gateway-domain"* ]]; then
  HEARTBEAT_URL="${GATEWAY_URL%/v1/fallback}/v1/device/heartbeat"
  upsert_env "$AGENT_ENV" "GATEWAY_HEARTBEAT_URL" "$HEARTBEAT_URL"
  info "Heartbeat URL synced: ${HEARTBEAT_URL}"
fi
ok "Device token saved" "source: ${TOKEN_SOURCE}"
if [[ "${TOKEN}" == "replace_with_device_token" ]]; then
  info "Gateway token is currently unset"
else
  info "Token preview: ${BOLD}${TOKEN:0:16}${RST}${DIM}...${RST}"
fi

if [[ "${TOKEN}" == "replace_with_device_token" ]]; then
  upsert_env "$RUNTIME_ENV" "ALWAYS_USE_GATEWAY" "false"
  ok "Gateway polish disabled" "ALWAYS_USE_GATEWAY=false until registration succeeds"
else
  upsert_env "$RUNTIME_ENV" "ALWAYS_USE_GATEWAY" "true"
  ok "Gateway polish enabled" "ALWAYS_USE_GATEWAY=true"
fi

# ── Step 5: systemd services ────────────────────────────────────────────────
step_header 5 "Installing systemd services"
info "Systemd will manage both services so they start automatically on boot"
info "and restart if they crash."
echo ""

# Detect the real (non-root) user who invoked the installer.
PI_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
if ! id "$PI_USER" &>/dev/null; then
  PI_USER="pi"
fi
info "Services will run as user: ${BOLD}${PI_USER}${RST}"

doing "Copying ai-runtime.service"
sed "s/^User=.*/User=${PI_USER}/" "${REPO_DIR}/systemd/ai-runtime.service" \
  > /etc/systemd/system/ai-runtime.service
ok "ai-runtime.service installed" "/etc/systemd/system/"

doing "Copying device-agent.service"
sed "s/^User=.*/User=${PI_USER}/" "${REPO_DIR}/systemd/device-agent.service" \
  > /etc/systemd/system/device-agent.service
ok "device-agent.service installed" "/etc/systemd/system/"

# ── Step 6: Enable & start services ─────────────────────────────────────────
step_header 6 "Enabling and starting services"
info "Starting everything up and making sure it survives reboots."
echo ""

doing "Reloading systemd daemon"
systemctl daemon-reload
ok "systemd reloaded"

doing "Enabling ai-runtime and device-agent for auto-start on boot"
systemctl enable ai-runtime device-agent 2>&1 | while IFS= read -r line; do info "$line"; done
ok "Services enabled" "auto-start on boot"

doing "Starting ai-runtime"
systemctl restart ai-runtime
sleep 2
if systemctl is-active --quiet ai-runtime; then
  ok "ai-runtime is running" "port 8000"
else
  warn "ai-runtime may not have started, check the logs below"
fi

doing "Starting device-agent"
systemctl restart device-agent
sleep 1
if systemctl is-active --quiet device-agent; then
  ok "device-agent is running" "heartbeat every 60s"
else
  warn "device-agent may not have started, check the logs below"
fi

# ── Step 7: Summary ─────────────────────────────────────────────────────────
step_header 7 "Installation complete"

ELAPSED=$SECONDS
MINS=$((ELAPSED / 60))
SECS=$((ELAPSED % 60))

echo ""
echo "  ${BOLD}${GREEN}"
echo "  ┌───────────────────────────────────────────────────────────────────┐"
echo "  │                                                                   │"
echo "  │              ✓  PI SETUP COMPLETE                                 │"
echo "  │                                                                   │"
echo "  └───────────────────────────────────────────────────────────────────┘"
echo "  ${RST}"

section_box "Services Running" "$GREEN"
echo ""
result_line "ai-runtime:" "http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):8000"
result_line "device-agent:" "Heartbeat → gateway every 60s"
result_line "Chat UI:" "http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):8000/"
echo ""

section_box "Device Token" "$BLUE"
echo ""
result_line "Source:" "${TOKEN_SOURCE}"
if [[ "${TOKEN}" == "replace_with_device_token" ]]; then
  result_line "Token:" "not issued"
else
  result_line "Token:" "${TOKEN:0:16}..."
fi
echo ""
if [[ "${TOKEN}" == "replace_with_device_token" ]]; then
  warn "Gateway token not issued yet. To connect this Pi to the server:"
  echo ""
  cmd "Edit /opt/ai-runtime/.env:"
  echo "       ${DIM}GATEWAY_URL=http://<server-ip>:9000/v1/fallback${RST}"
  echo "       ${DIM}GATEWAY_REGISTER_URL=http://<server-ip>:9000/v1/device/register${RST}"
  echo "       ${DIM}GATEWAY_BOOTSTRAP_SECRET=<DEVICE_REGISTER_SECRET from server .env>${RST}"
  echo ""
  cmd "Then re-run this installer:"
  cmd "sudo bash pi/installer/install.sh"
  echo ""
fi

section_box "Configuration Files" "$MAGENTA"
echo ""
result_line "Runtime config:" "/opt/ai-runtime/.env"
result_line "Agent config:" "/opt/device-agent/.env"
echo ""
info "Key settings in /opt/ai-runtime/.env:"
echo "       ${DIM}LOCAL_BACKEND=llamacpp${RST}       ${DIM}# or ollama${RST}"
echo "       ${DIM}LOCAL_MODEL=qwen3.5:2b${RST}"
echo "       ${DIM}ALWAYS_USE_GATEWAY=true${RST}    ${DIM}# send every response to server for polish${RST}"
echo ""

section_box "Quick Reference" "$CYAN"
echo ""
echo "  ${DIM}Test chat     ${RST} curl -s http://127.0.0.1:8000/v1/chat -H 'Content-Type: application/json' -d '{\"prompt\":\"Hello\"}'"
echo "  ${DIM}Runtime logs  ${RST} sudo journalctl -u ai-runtime -n 100 -f"
echo "  ${DIM}Agent logs    ${RST} sudo journalctl -u device-agent -n 100 -f"
echo "  ${DIM}Restart       ${RST} sudo systemctl restart ai-runtime device-agent"
echo "  ${DIM}Status        ${RST} sudo systemctl status ai-runtime device-agent"
echo ""
divider
echo ""
echo "  ${DIM}Finished in ${BOLD}${MINS}m ${SECS}s${RST}"
echo ""
