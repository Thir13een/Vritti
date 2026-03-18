#!/usr/bin/env bash
# Vritti Pi Installer
# Usage: sudo bash pi/installer/install.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash pi/installer/install.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_ENV="/opt/ai-runtime/.env"
AGENT_ENV="/opt/device-agent/.env"
TOTAL_STEPS=8
SECONDS=0

# Colors
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 256 ]]; then
  RST="$(tput sgr0)"  BOLD="$(tput bold)"  DIM="$(tput dim)"  UL="$(tput smul)"
  SAFFRON="$(tput setaf 208)"
  SAFFRON_DARK="$(tput setaf 172)"
  WHITE="$(tput setaf 255)"
  CREAM="$(tput setaf 230)"
  GREEN="$(tput setaf 82)"
  GREEN_DARK="$(tput setaf 34)"
  RED="$(tput setaf 196)"
  YELLOW="$(tput setaf 220)"
  BLUE="$(tput setaf 75)"
  CYAN="$(tput setaf 87)"
  MAGENTA="$(tput setaf 213)"
  BG_SAFFRON="$(tput setab 208)"
  BG_GREEN="$(tput setab 34)"
elif [[ -t 1 ]] && command -v tput &>/dev/null && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  RST="$(tput sgr0)"  BOLD="$(tput bold)"  DIM="$(tput dim)"  UL="$(tput smul)"
  SAFFRON="$(tput setaf 3)"  SAFFRON_DARK="$(tput setaf 3)"
  WHITE="$(tput setaf 7)"    CREAM="$(tput setaf 7)"
  GREEN="$(tput setaf 2)"    GREEN_DARK="$(tput setaf 2)"
  RED="$(tput setaf 1)"      YELLOW="$(tput setaf 3)"
  BLUE="$(tput setaf 6)"     CYAN="$(tput setaf 6)"
  MAGENTA="$(tput setaf 5)"
  BG_SAFFRON="$(tput setab 3)"  BG_GREEN="$(tput setab 2)"
else
  RST="" BOLD="" DIM="" UL=""
  SAFFRON="" SAFFRON_DARK="" WHITE="" CREAM=""
  GREEN="" GREEN_DARK="" RED="" YELLOW="" BLUE="" CYAN="" MAGENTA=""
  BG_SAFFRON="" BG_GREEN=""
fi

# Output helpers
divider()    { echo "${SAFFRON_DARK}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RST}"; }
step_header() {
  local n="$1" title="$2"
  echo ""
  echo "  ${BOLD}${BG_SAFFRON}${WHITE} STEP ${n}/${TOTAL_STEPS} ${RST} ${BOLD}${SAFFRON}${title}${RST}"
  divider
}
step_done() {
  echo ""
  echo "  ${GREEN}  ━━ Step complete ━━${RST}"
  sleep 0.3
}

ok()    { echo "  ${GREEN}  ✓  ${RST}${BOLD}${WHITE}$1${RST}${CREAM}${2:+  — $2}${RST}"; }
info()  { echo "  ${BLUE}  ℹ  ${RST}${CREAM}$*${RST}"; }
doing() { echo "  ${SAFFRON}  ►  ${RST}${WHITE}$*${DIM}...${RST}"; }
warn()  { echo "  ${YELLOW}  ⚠  ${RST}${YELLOW}$*${RST}"; }
fail()  { echo "  ${RED}  ✗  ${RST}${RED}${BOLD}$*${RST}" >&2; }
cmd()   { echo "       ${DIM}\$ $*${RST}"; }

SPINNER_CHARS="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
stream_progress() {
  local spin_idx=0 line=""
  while IFS= read -r line; do
    local spin="${SPINNER_CHARS:spin_idx:1}"
    printf "\r  ${SAFFRON}  %s  ${RST}${DIM}%-68s${RST}" "$spin" "${line:0:68}"
    spin_idx=$(( (spin_idx + 1) % ${#SPINNER_CHARS} ))
  done
  printf "\r%-80s\r" ""
}

section_box() {
  local title="$1" color="${2:-$SAFFRON}"
  echo ""
  echo "  ${BOLD}${color}╭───────────────────────────────────────────────────────────╮${RST}"
  printf "  ${BOLD}${color}│${RST} ${BOLD}${WHITE}%-57s${RST} ${BOLD}${color}│${RST}\n" "$title"
  echo "  ${BOLD}${color}╰───────────────────────────────────────────────────────────╯${RST}"
}

result_line() { printf "  ${BOLD}${SAFFRON}  %-18s${RST} %s\n" "$1" "$2"; }

# Utility functions
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

# Start

echo ""
echo "${BOLD}${SAFFRON}"
echo "  ┌───────────────────────────────────────────────────────────────────┐"
echo "  │                                                                   │"
echo "  │    ${WHITE}██╗   ██╗${SAFFRON}██████╗ ${GREEN}██╗${SAFFRON}████████╗${GREEN}████████╗${WHITE}██╗${SAFFRON}                      │"
echo "  │    ${WHITE}██║   ██║${SAFFRON}██╔══██╗${GREEN}██║${SAFFRON}╚══██╔══╝${GREEN}╚══██╔══╝${WHITE}██║${SAFFRON}                      │"
echo "  │    ${WHITE}██║   ██║${SAFFRON}██████╔╝${GREEN}██║${SAFFRON}   ██║   ${GREEN}   ██║   ${WHITE}██║${SAFFRON}                      │"
echo "  │    ${WHITE}╚██╗ ██╔╝${SAFFRON}██╔══██╗${GREEN}██║${SAFFRON}   ██║   ${GREEN}   ██║   ${WHITE}██║${SAFFRON}                      │"
echo "  │    ${WHITE} ╚████╔╝ ${SAFFRON}██║  ██║${GREEN}██║${SAFFRON}   ██║   ${GREEN}   ██║   ${WHITE}██║${SAFFRON}                      │"
echo "  │    ${WHITE}  ╚═══╝  ${SAFFRON}╚═╝  ╚═╝${GREEN}╚═╝${SAFFRON}   ╚═╝   ${GREEN}   ╚═╝   ${WHITE}╚═╝${SAFFRON}                      │"
echo "  │                                                                   │"
echo "  │          ${WHITE}P I   I N S T A L L E R${SAFFRON}                                │"
echo "  │          ${CREAM}ai-runtime  ·  device-agent  ·  systemd${SAFFRON}              │"
echo "  │                                                                   │"
echo "  └───────────────────────────────────────────────────────────────────┘"
echo "${RST}"

info "Source directory : ${BOLD}${WHITE}${REPO_DIR}${RST}"
info "Hostname         : ${BOLD}${WHITE}$(hostname)${RST}"
info "Time             : $(date '+%Y-%m-%d %H:%M:%S')"

# Detect non-root user early (needed for chown in later steps)
PI_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
if ! id "$PI_USER" &>/dev/null; then
  PI_USER="pi"
fi

# Step 1: System packages
step_header 1 "Installing system packages"
info "Installing Python, pip, curl."
echo ""

doing "Updating package lists"
apt-get update -qq 2>&1 | stream_progress
ok "Package lists updated"

doing "Installing python3, python3-venv, python3-pip, curl"
apt-get install -y -qq python3 python3-venv python3-pip curl 2>&1 | stream_progress
ok "System packages installed"

info "Python version: ${BOLD}$(python3 --version 2>/dev/null)${RST}"
step_done

# Step 2: Model selection
step_header 2 "Choose AI model"
info "Select model for your Pi's hardware."
echo ""
echo "  ${BOLD}${SAFFRON}╭─────────────────────────────────────────────────────────────╮${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}   ${BOLD}${WHITE}[1]  qwen3.5:0.8b${RST}   ${DIM}(1.0 GB download)${RST}                     ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Runs on Pi Zero 2W, Pi 3, Pi 4 (1 GB+)${RST}          ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Fast inference, low memory usage${RST}                   ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Best for quick Q&A, simple tasks${RST}                   ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${YELLOW}⚠${RST} ${CREAM}Less accurate on complex reasoning${RST}                ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}   ${BOLD}${WHITE}[2]  qwen3.5:2b${RST}    ${DIM}(2.7 GB download)${RST}                     ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Better reasoning and language quality${RST}              ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Stronger multilingual support${RST}                      ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Recommended for Pi 4 (4 GB+) / Pi 5${RST}               ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${YELLOW}⚠${RST} ${CREAM}Slower on low-RAM devices, needs 4 GB+${RST}           ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}╰─────────────────────────────────────────────────────────────╯${RST}"
echo ""

# Auto-suggest based on RAM
TOTAL_RAM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)
if [[ "$TOTAL_RAM_MB" -ge 3500 ]]; then
  SUGGESTED=2
  info "Detected ${BOLD}${WHITE}${TOTAL_RAM_MB} MB${RST}${CREAM} RAM — recommending ${BOLD}${WHITE}qwen3.5:2b${RST}"
else
  SUGGESTED=1
  info "Detected ${BOLD}${WHITE}${TOTAL_RAM_MB} MB${RST}${CREAM} RAM — recommending ${BOLD}${WHITE}qwen3.5:0.8b${RST}"
fi
echo ""

while true; do
  printf "  ${SAFFRON}  ►  ${RST}${WHITE}Enter choice ${BOLD}[1]${RST}${WHITE} or ${BOLD}[2]${RST}${WHITE} (default: ${BOLD}${SUGGESTED}${RST}${WHITE}): ${RST}"
  read -r MODEL_CHOICE </dev/tty
  MODEL_CHOICE="${MODEL_CHOICE:-$SUGGESTED}"
  case "$MODEL_CHOICE" in
    1) SELECTED_MODEL="qwen3.5:0.8b"; break ;;
    2) SELECTED_MODEL="qwen3.5:2b";   break ;;
    *) warn "Please enter 1 or 2" ;;
  esac
done

ok "Model selected" "${SELECTED_MODEL}"
step_done

# Step 3: ai-runtime
step_header 3 "Installing ai-runtime"
info "Core AI service running ${BOLD}${WHITE}${SELECTED_MODEL}${RST}${CREAM} on port 8000."
echo ""

doing "Creating /opt/ai-runtime"
mkdir -p /opt/ai-runtime

doing "Copying runtime source files"
cp "${REPO_DIR}/ai-runtime/"*.py /opt/ai-runtime/
cp "${REPO_DIR}/ai-runtime/requirements.txt" /opt/ai-runtime/
ok "Copied Python files" "config.py, runtime.py, server.py"

if [[ -d "${REPO_DIR}/face-ui" ]]; then
  doing "Copying face UI (mandala)"
  mkdir -p /opt/face-ui
  cp -r "${REPO_DIR}/face-ui/." /opt/face-ui/
  ok "Face UI copied" "/opt/face-ui"
fi

if [[ -d "${REPO_DIR}/ai-runtime/static" ]]; then
  doing "Copying static files"
  mkdir -p /opt/ai-runtime/static
  cp -r "${REPO_DIR}/ai-runtime/static/." /opt/ai-runtime/static/
  ok "Static files copied" "fallback UI"
fi

doing "Creating Python virtual environment"
python3 -m venv /opt/ai-runtime/.venv
ok "Virtual environment created" "/opt/ai-runtime/.venv"

doing "Installing Python dependencies"
/opt/ai-runtime/.venv/bin/pip install -q --upgrade pip 2>&1 | stream_progress
/opt/ai-runtime/.venv/bin/pip install -q -r /opt/ai-runtime/requirements.txt 2>&1 | stream_progress
PKG_COUNT=$(/opt/ai-runtime/.venv/bin/pip list --format=columns 2>/dev/null | tail -n +3 | wc -l)
ok "Dependencies installed" "${PKG_COUNT} packages (fastapi, uvicorn, pydantic...)"

if [[ ! -f "$RUNTIME_ENV" ]]; then
  doing "Creating runtime .env from example"
  cp "${REPO_DIR}/installer/runtime.env.example" "$RUNTIME_ENV"
  ok "Runtime config created" "$RUNTIME_ENV"
else
  ok "Runtime config exists" "$RUNTIME_ENV"
fi

doing "Securing .env file permissions"
chown "${PI_USER}:${PI_USER}" "$RUNTIME_ENV"
chmod 600 "$RUNTIME_ENV"
ok "Runtime .env secured" "owner-only read/write (600)"

doing "Setting model to ${SELECTED_MODEL}"
upsert_env "$RUNTIME_ENV" "LOCAL_MODEL" "$SELECTED_MODEL"
ok "Model configured" "LOCAL_MODEL=${SELECTED_MODEL}"
step_done

# Step 4: device-agent
step_header 4 "Installing device-agent"
info "Heartbeat agent for gateway connectivity."
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

doing "Securing .env file permissions"
chown "${PI_USER}:${PI_USER}" "$AGENT_ENV"
chmod 600 "$AGENT_ENV"
ok "Agent .env secured" "owner-only read/write (600)"
step_done

# Step 5: Device registration
step_header 5 "Device registration & token"
info "Registering with gateway to get a device token."
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

  # Ask for bootstrap secret if not already configured
  if [[ -z "${BOOTSTRAP_SECRET}" || "${BOOTSTRAP_SECRET}" == "replace_with_bootstrap_secret" ]]; then
    echo ""
    echo "  ${BOLD}${SAFFRON}╭─────────────────────────────────────────────────────────────╮${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}   ${BOLD}${WHITE}Device Registration${RST}                                       ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}   ${CREAM}To register this Pi, you need the device secret${RST}         ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}   ${CREAM}from your gateway dashboard or server .env file.${RST}        ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}   ${DIM}Find it at: dashboard → Settings → Device Secret${RST}        ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}   ${DIM}Or in: gateway server .env → DEVICE_REGISTER_SECRET${RST}     ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}   ${YELLOW}Press Enter to skip (gateway will be disabled)${RST}         ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
    echo "  ${BOLD}${SAFFRON}╰─────────────────────────────────────────────────────────────╯${RST}"
    echo ""
    printf "  ${SAFFRON}  ►  ${RST}${WHITE}Paste device secret: ${RST}"
    read -r BOOTSTRAP_SECRET </dev/tty
    BOOTSTRAP_SECRET="${BOOTSTRAP_SECRET// /}"
    if [[ -n "${BOOTSTRAP_SECRET}" ]]; then
      upsert_env "$RUNTIME_ENV" "GATEWAY_BOOTSTRAP_SECRET" "$BOOTSTRAP_SECRET"
      ok "Device secret saved"
    fi
  fi

  if [[ -n "${REGISTER_URL}" && -n "${BOOTSTRAP_SECRET}" && "${BOOTSTRAP_SECRET}" != "replace_with_bootstrap_secret" ]]; then
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
    if [[ -z "${BOOTSTRAP_SECRET}" || "${BOOTSTRAP_SECRET}" == "replace_with_bootstrap_secret" ]]; then
      info "No device secret provided — skipping gateway registration"
    else
      info "No GATEWAY_REGISTER_URL configured"
    fi
    TOKEN="replace_with_device_token"
    TOKEN_SOURCE="not_configured"
  fi
fi

upsert_env "$RUNTIME_ENV" "GATEWAY_DEVICE_TOKEN" "$TOKEN"
upsert_env "$AGENT_ENV" "GATEWAY_DEVICE_TOKEN" "$TOKEN"

# Derive heartbeat URL from GATEWAY_URL
GATEWAY_URL="$(get_env "$RUNTIME_ENV" "GATEWAY_URL" || true)"
if [[ -n "${GATEWAY_URL}" && "${GATEWAY_URL}" != *"your-gateway-domain"* ]]; then
  HEARTBEAT_URL="${GATEWAY_URL%/v1/chat}/v1/device/heartbeat"
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
  upsert_env "$RUNTIME_ENV" "GATEWAY_FIRST" "false"
  ok "Gateway disabled" "GATEWAY_FIRST=false until registration succeeds"
else
  upsert_env "$RUNTIME_ENV" "GATEWAY_FIRST" "true"
  ok "Gateway enabled" "GATEWAY_FIRST=true"
fi
step_done

# Step 6: systemd
step_header 6 "Installing systemd services"
info "Auto-start on boot, auto-restart on crash."
echo ""

info "Services will run as user: ${BOLD}${PI_USER}${RST}"

doing "Copying ai-runtime.service"
sed "s/^User=.*/User=${PI_USER}/" "${REPO_DIR}/systemd/ai-runtime.service" \
  > /etc/systemd/system/ai-runtime.service
ok "ai-runtime.service installed" "/etc/systemd/system/"

doing "Copying device-agent.service"
sed "s/^User=.*/User=${PI_USER}/" "${REPO_DIR}/systemd/device-agent.service" \
  > /etc/systemd/system/device-agent.service
ok "device-agent.service installed" "/etc/systemd/system/"

doing "Copying vritti-kiosk.service"
sed -e "s/^User=.*/User=${PI_USER}/" \
    -e "s|/home/pi|/home/${PI_USER}|g" \
    "${REPO_DIR}/systemd/vritti-kiosk.service" \
  > /etc/systemd/system/vritti-kiosk.service
ok "vritti-kiosk.service installed" "fullscreen mandala on boot"

doing "Copying vritti-voice.service"
sed "s/^User=.*/User=${PI_USER}/" "${REPO_DIR}/systemd/vritti-voice.service" \
  > /etc/systemd/system/vritti-voice.service
ok "vritti-voice.service installed" "mic → STT → chat → TTS → speaker"

doing "Disabling screen blanking"
if command -v xset &>/dev/null; then
  su - "${PI_USER}" -c "DISPLAY=:0 xset s off -dpms" 2>/dev/null || true
fi
# Persist via lightdm config
LIGHTDM_CONF="/etc/lightdm/lightdm.conf"
if [[ -f "$LIGHTDM_CONF" ]] && ! grep -q "xserver-command.*-s 0" "$LIGHTDM_CONF" 2>/dev/null; then
  sed -i '/^\[Seat:\*\]/a xserver-command=X -s 0 -dpms' "$LIGHTDM_CONF" 2>/dev/null || true
fi
ok "Screen blanking disabled" "display stays on"
step_done

# Step 7: Start services
step_header 7 "Enabling and starting services"
info "Starting services."
echo ""

doing "Reloading systemd daemon"
systemctl daemon-reload
ok "systemd reloaded"

doing "Enabling services for auto-start on boot"
systemctl enable ai-runtime device-agent vritti-kiosk vritti-voice 2>&1 | stream_progress
ok "Services enabled" "ai-runtime, device-agent, kiosk, voice"

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

doing "Starting vritti-voice"
systemctl restart vritti-voice
sleep 1
if systemctl is-active --quiet vritti-voice; then
  ok "vritti-voice is running" "voice pipeline active"
else
  warn "vritti-voice may not have started (needs mic + API keys)"
fi
step_done

# Step 8: Summary
step_header 8 "Installation complete"

ELAPSED=$SECONDS
MINS=$((ELAPSED / 60))
SECS=$((ELAPSED % 60))

echo ""
echo "  ${BOLD}${SAFFRON}"
echo "  ┌───────────────────────────────────────────────────────────────────┐"
echo "  │                                                                   │"
echo "  │    ${WHITE}██████╗  ${GREEN}██╗${SAFFRON}       ${WHITE}██████╗ ${GREEN}███████╗${SAFFRON} █████╗ ██████╗ ██╗   ██╗${SAFFRON}   │"
echo "  │    ${WHITE}██╔══██╗ ${GREEN}██║${SAFFRON}       ${WHITE}██╔══██╗${GREEN}██╔════╝${SAFFRON}██╔══██╗██╔══██╗╚██╗ ██╔╝${SAFFRON}   │"
echo "  │    ${WHITE}██████╔╝ ${GREEN}██║${SAFFRON}       ${WHITE}██████╔╝${GREEN}█████╗  ${SAFFRON}███████║██║  ██║ ╚████╔╝ ${SAFFRON}   │"
echo "  │    ${WHITE}██╔═══╝  ${GREEN}██║${SAFFRON}       ${WHITE}██╔══██╗${GREEN}██╔══╝  ${SAFFRON}██╔══██║██║  ██║  ╚██╔╝  ${SAFFRON}   │"
echo "  │    ${WHITE}██║      ${GREEN}██║${SAFFRON}       ${WHITE}██║  ██║${GREEN}███████╗${SAFFRON}██║  ██║██████╔╝   ██║   ${SAFFRON}   │"
echo "  │    ${WHITE}╚═╝      ${GREEN}╚═╝${SAFFRON}       ${WHITE}╚═╝  ╚═╝${GREEN}╚══════╝${SAFFRON}╚═╝  ╚═╝╚═════╝    ╚═╝   ${SAFFRON}   │"
echo "  │                                                                   │"
echo "  │       ${GREEN}✓${RST}${BOLD}${WHITE}  Pi setup complete in ${MINS}m ${SECS}s${SAFFRON}                          │"
echo "  │                                                                   │"
echo "  └───────────────────────────────────────────────────────────────────┘"
echo "  ${RST}"

section_box "Services Running" "$GREEN"
echo ""
result_line "ai-runtime:" "http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):8000"
result_line "Model:" "${SELECTED_MODEL}"
result_line "device-agent:" "Heartbeat → gateway every 60s"
result_line "Face UI:" "fullscreen kiosk (Chromium)"
result_line "Voice pipeline:" "mic → STT → chat → TTS → speaker"
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
  echo "       ${DIM}GATEWAY_URL=http://<server-ip>:9000/v1/chat${RST}"
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
echo "       ${DIM}LOCAL_MODEL=${SELECTED_MODEL}${RST}"
echo "       ${DIM}GATEWAY_FIRST=true${RST}          ${DIM}# try gateway first, local as backup${RST}"
echo ""

section_box "Quick Reference" "$CYAN"
echo ""
echo "  ${DIM}Test chat     ${RST} curl -s http://127.0.0.1:8000/v1/chat -H 'Content-Type: application/json' -d '{\"prompt\":\"Hello\"}'"
echo "  ${DIM}Runtime logs  ${RST} sudo journalctl -u ai-runtime -n 100 -f"
echo "  ${DIM}Agent logs    ${RST} sudo journalctl -u device-agent -n 100 -f"
echo "  ${DIM}Voice logs    ${RST} sudo journalctl -u vritti-voice -n 100 -f"
echo "  ${DIM}Restart       ${RST} sudo systemctl restart ai-runtime device-agent vritti-voice"
echo "  ${DIM}Status        ${RST} sudo systemctl status ai-runtime device-agent vritti-voice"
echo ""
divider
echo ""
echo "  ${SAFFRON}Vritti${RST} ${DIM}— AI for every Indian language${RST}"
echo ""
