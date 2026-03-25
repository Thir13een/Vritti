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

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_apt_packages() {
  local label="$1"
  shift
  doing "Installing ${label}"
  apt-get install -y -qq "$@" 2>&1 | stream_progress
  ok "${label} installed"
}

install_first_available_package() {
  local label="$1"
  shift
  local candidate=""
  for candidate in "$@"; do
    doing "Installing ${label}" 
    if apt-get install -y -qq "$candidate" 2>&1 | stream_progress; then
      ok "${label} installed" "package: ${candidate}"
      return 0
    fi
  done
  fail "No install candidate found for ${label} (tried: $*)"
  exit 1
}

install_chromium_package() {
  ensure_snap_chromium_wrapper() {
    cat > /usr/bin/chromium-browser <<'EOF'
#!/usr/bin/env bash
exec /snap/bin/chromium "$@"
EOF
    chmod 755 /usr/bin/chromium-browser
  }

  if [[ -x /usr/bin/chromium-browser ]]; then
    if [[ -L /usr/bin/chromium-browser ]] && [[ "$(readlink -f /usr/bin/chromium-browser)" == "/usr/bin/snap" ]]; then
      ensure_snap_chromium_wrapper
      ok "Chromium kiosk browser available" "path: /snap/bin/chromium (via chromium-browser wrapper)"
      return 0
    fi
    ok "Chromium kiosk browser available" "path: /usr/bin/chromium-browser"
    return 0
  fi

  if [[ -x /usr/bin/chromium ]]; then
    ln -sf /usr/bin/chromium /usr/bin/chromium-browser
    ok "Chromium kiosk browser available" "path: /usr/bin/chromium"
    return 0
  fi

  if [[ -x /snap/bin/chromium ]]; then
    ensure_snap_chromium_wrapper
    ok "Chromium kiosk browser available" "path: /snap/bin/chromium (via chromium-browser wrapper)"
    return 0
  fi

  if [[ -x /usr/bin/google-chrome ]] || [[ -x /usr/bin/google-chrome-stable ]]; then
    ln -sf "$(command -v google-chrome || command -v google-chrome-stable)" /usr/bin/chromium-browser
    ok "Chromium kiosk browser available" "path: $(command -v google-chrome || command -v google-chrome-stable)"
    return 0
  fi

  doing "Installing Chromium kiosk browser"
  if apt-get install -y -qq chromium-browser 2>&1 | stream_progress; then
    ok "Chromium kiosk browser installed" "package: chromium-browser"
    return 0
  fi

  if apt-get install -y -qq chromium 2>&1 | stream_progress; then
    if [[ -x /usr/bin/chromium && ! -e /usr/bin/chromium-browser ]]; then
      ln -sf /usr/bin/chromium /usr/bin/chromium-browser
    fi
    ok "Chromium kiosk browser installed" "package: chromium"
    return 0
  fi

  fail "Unable to install Chromium browser (tried chromium-browser and chromium)"
  return 1
}

require_cmd_or_fail() {
  local cmd_name="$1" hint="$2"
  if have_cmd "$cmd_name"; then
    ok "Found ${cmd_name}"
  else
    fail "Missing required command: ${cmd_name} (${hint})"
    exit 1
  fi
}

require_file_or_fail() {
  local path="$1" hint="${2:-}"
  if [[ -f "$path" ]]; then
    ok "Verified file" "$path"
  else
    fail "Missing required file: ${path}${hint:+ (${hint})}"
    exit 1
  fi
}

wait_for_http_ok() {
  local url="$1" attempts="${2:-20}" delay_seconds="${3:-1}"
  local attempt=""
  for attempt in $(seq 1 "$attempts"); do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS "$url" >/dev/null 2>&1; then
        return 0
      fi
    else
      python3 - "$url" <<'PY' >/dev/null 2>&1 && return 0 || true
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=3)
PY
    fi
    sleep "$delay_seconds"
  done
  return 1
}

runtime_backend_status() {
  local url="$1"
  python3 - "$url" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=5) as resp:
    data = json.loads(resp.read().decode("utf-8"))

backend = str(data.get("backend", "") or "").strip()
gateway = str(data.get("gateway", "") or "n/a").strip()
local_backend = str(data.get("local_backend", "") or "n/a").strip()
primary = str(data.get("local_backend_primary", "") or "n/a").strip()
secondary = str(data.get("local_backend_secondary", "") or "n/a").strip()
status = str(data.get("status", "") or "unknown").strip()

summary = (
    f"status={status}, backend={backend}, gateway={gateway}, "
    f"local={local_backend}, primary={primary}, secondary={secondary}"
)
if backend != "reachable":
    raise SystemExit(summary)
print(summary)
PY
}

install_runtime_python_deps() {
  local base_requirements="/tmp/ai-runtime-requirements-no-torch.txt"
  grep -vE '^[[:space:]]*torch([[:space:]=<>!~].*)?$' /opt/ai-runtime/requirements.txt > "$base_requirements"

  doing "Installing Python dependencies"
  /opt/ai-runtime/.venv/bin/pip install -q --upgrade pip 2>&1 | stream_progress
  /opt/ai-runtime/.venv/bin/pip install -q -r "$base_requirements" 2>&1 | stream_progress

  doing "Installing Torch runtime"
  if [[ "$(uname -m)" == "x86_64" ]]; then
    /opt/ai-runtime/.venv/bin/pip install -q --index-url https://download.pytorch.org/whl/cpu torch torchaudio 2>&1 | stream_progress
  else
    /opt/ai-runtime/.venv/bin/pip install -q torch torchaudio 2>&1 | stream_progress
  fi
}

install_silero_vad_bundle() {
  local target_dir="$1"
  local repo_url="${SILERO_VAD_REPO:-https://github.com/snakers4/silero-vad.git}"

  doing "Prefetching Silero VAD bundle"
  rm -rf "${target_dir}.tmp"
  if git clone --depth 1 "$repo_url" "${target_dir}.tmp" 2>&1 | stream_progress; then
    rm -rf "$target_dir"
    mv "${target_dir}.tmp" "$target_dir"
    ok "Silero VAD bundle downloaded" "$target_dir"
    return 0
  fi

  rm -rf "${target_dir}.tmp"
  fail "Unable to download Silero VAD bundle from ${repo_url}"
  return 1
}

install_ollama_backend() {
  local model="$1"
  local service_detected=0

  if have_cmd ollama; then
    ok "Ollama local backend available" "$(ollama --version 2>/dev/null | head -1)"
  else
    doing "Installing Ollama local backend"
    if curl -fsSL https://ollama.com/install.sh | sh 2>&1 | stream_progress; then
      ok "Ollama installed"
    else
      warn "Ollama install failed — local fallback will stay unavailable"
      return 1
    fi
  fi

  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files ollama.service 2>/dev/null | grep -q '^ollama.service'; then
    service_detected=1
    doing "Enabling Ollama service"
    systemctl enable ollama >/dev/null 2>&1 || true
    systemctl restart ollama >/dev/null 2>&1 || systemctl start ollama >/dev/null 2>&1 || true
  fi

  doing "Waiting for Ollama API"
  local ready=0
  local _attempt=""
  for _attempt in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done

  if [[ "$ready" -ne 1 ]]; then
    if [[ "$service_detected" -eq 0 ]]; then
      warn "Ollama command installed, but no ready API was found on 127.0.0.1:11434"
    else
      warn "Ollama service did not become ready on 127.0.0.1:11434"
    fi
    return 1
  fi
  ok "Ollama API ready" "http://127.0.0.1:11434"

  if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    ok "Local fallback model available" "$model"
    return 0
  fi

  doing "Pulling local fallback model ${model}"
  if ollama pull "$model" 2>&1 | stream_progress; then
    ok "Local fallback model pulled" "$model"
    return 0
  fi

  warn "Model pull failed for ${model} — Ollama is installed, but local fallback is not ready yet"
  return 1
}

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
  local tmp_file
  touch "$file"
  tmp_file="$(mktemp "${file}.tmp.XXXXXX")"
  awk -F= -v key="$key" -v value="$value" '
    BEGIN { updated=0 }
    $1 == key { print key "=" value; updated=1; next }
    { print }
    END {
      if (!updated) print key "=" value
    }
  ' "$file" > "$tmp_file"
  mv "$tmp_file" "$file"
}

get_env() {
  local file="$1" key="$2"
  awk -F= -v key="$key" '$1==key { print substr($0, index($0, "=") + 1) }' "$file" | tail -n1
}

register_with_gateway() {
  local register_url="$1" bootstrap_secret="$2" device_id="$3"
  python3 - "$register_url" "$bootstrap_secret" "$device_id" <<'PY'
import json, sys, urllib.error, urllib.request
register_url, bootstrap_secret, device_id = sys.argv[1], sys.argv[2], sys.argv[3]
headers = {"Content-Type": "application/json"}
bootstrap_secret = bootstrap_secret.strip()
if bootstrap_secret and bootstrap_secret != "replace_with_bootstrap_secret":
    headers["x-bootstrap-secret"] = bootstrap_secret
req = urllib.request.Request(
    register_url,
    data=json.dumps({"device_id": device_id}).encode("utf-8"),
    headers=headers,
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(body)
    except Exception:
        payload = {"detail": body[:300] or f"http {exc.code}"}
    payload.setdefault("status", "error")
    payload.setdefault("detail", f"http {exc.code}")
    print(json.dumps(payload))
except Exception as exc:
    print(json.dumps({"status": "error", "detail": str(exc)}))
else:
    print(json.dumps(data))
PY
}

json_field() {
  local payload="$1" field="$2"
  python3 - "$field" <<'PY' <<<"$payload"
import json
import sys

field = sys.argv[1]
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    print("")
    raise SystemExit(0)
value = data.get(field, "")
if value is None:
    value = ""
print(value)
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

# Resolve Pi user
PI_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
if ! id "$PI_USER" &>/dev/null; then
  PI_USER="pi"
fi

# Step 1: System packages
step_header 1 "Installing system packages"
info "Installing Python, audio, kiosk, and build dependencies."
echo ""

doing "Updating package lists"
apt-get update -qq 2>&1 | stream_progress
ok "Package lists updated"

install_apt_packages "core packages" \
  python3 python3-venv python3-pip python3-dev curl git build-essential pkg-config
install_apt_packages "audio packages" \
  portaudio19-dev ffmpeg mpg123
install_first_available_package "numeric runtime packages" \
  libatlas-base-dev libopenblas-dev
install_chromium_package

info "Python version: ${BOLD}$(python3 --version 2>/dev/null)${RST}"
require_cmd_or_fail ffmpeg "required for gateway audio compression"
require_cmd_or_fail mpg123 "required for Pi audio playback"
require_cmd_or_fail chromium-browser "required for kiosk mode"
step_done

# Step 2: Model selection
step_header 2 "Choose AI model"
info "Select model for your Pi's hardware."
echo ""
echo "  ${BOLD}${SAFFRON}╭─────────────────────────────────────────────────────────────╮${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}   ${BOLD}${WHITE}[0]  no local model${RST}  ${DIM}(gateway only, no Pi model download)${RST}   ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Best when gateway will always be available${RST}           ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${GREEN}✓${RST} ${CREAM}Fastest install, no model storage usage${RST}             ${BOLD}${SAFFRON}│${RST}"
echo "  ${BOLD}${SAFFRON}│${RST}        ${YELLOW}⚠${RST} ${CREAM}No on-device chat fallback if gateway is down${RST}      ${BOLD}${SAFFRON}│${RST}"
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
  printf "  ${SAFFRON}  ►  ${RST}${WHITE}Enter choice ${BOLD}[0]${RST}${WHITE}, ${BOLD}[1]${RST}${WHITE}, or ${BOLD}[2]${RST}${WHITE} (default: ${BOLD}${SUGGESTED}${RST}${WHITE}): ${RST}"
  read -r MODEL_CHOICE </dev/tty
  MODEL_CHOICE="${MODEL_CHOICE:-$SUGGESTED}"
  case "$MODEL_CHOICE" in
    0) SELECTED_MODEL=""; LOCAL_MODEL_LABEL="none (gateway only)"; break ;;
    1) SELECTED_MODEL="qwen3.5:0.8b"; break ;;
    2) SELECTED_MODEL="qwen3.5:2b";   break ;;
    *) warn "Please enter 0, 1, or 2" ;;
  esac
done

LOCAL_MODEL_LABEL="${LOCAL_MODEL_LABEL:-$SELECTED_MODEL}"
ok "Model selected" "${LOCAL_MODEL_LABEL}"
step_done

# Step 3: ai-runtime
step_header 3 "Installing ai-runtime"
if [[ -n "${SELECTED_MODEL}" ]]; then
  info "Core AI service running ${BOLD}${WHITE}${SELECTED_MODEL}${RST}${CREAM} on port 8000."
else
  info "Core AI service running in ${BOLD}${WHITE}gateway-only${RST}${CREAM} mode on port 8000."
fi
echo ""

doing "Creating /opt/ai-runtime"
mkdir -p /opt/ai-runtime

doing "Creating local model directories"
mkdir -p /opt/ai-runtime/models
chown "${PI_USER}:${PI_USER}" /opt/ai-runtime/models
ok "Model directory ready" "/opt/ai-runtime/models"

doing "Creating shared runtime state directory"
mkdir -p /opt/ai-runtime/run
chown "${PI_USER}:${PI_USER}" /opt/ai-runtime/run
ok "Shared state directory ready" "/opt/ai-runtime/run"

doing "Copying runtime source files"
cp "${REPO_DIR}/ai-runtime/"*.py /opt/ai-runtime/
cp "${REPO_DIR}/ai-runtime/requirements.txt" /opt/ai-runtime/
ok "Copied Python files" "config.py, runtime.py, server.py"
require_file_or_fail /opt/ai-runtime/server.py "runtime entrypoint"
require_file_or_fail /opt/ai-runtime/runtime.py "chat backend orchestration"
require_file_or_fail /opt/ai-runtime/voice_ws.py "browser voice relay"
require_file_or_fail /opt/ai-runtime/voice_pipeline.py "local voice daemon"
require_file_or_fail /opt/ai-runtime/requirements.txt "runtime Python dependencies"

doing "Setting runtime file permissions"
chown -R "${PI_USER}:${PI_USER}" /opt/ai-runtime
find /opt/ai-runtime -maxdepth 1 -type f \( -name '*.py' -o -name 'requirements.txt' \) -exec chmod 644 {} +
ok "Runtime files secured" "owner: ${PI_USER}"

if [[ -d "${REPO_DIR}/face-ui" ]]; then
  doing "Copying face UI (mandala)"
  mkdir -p /opt/face-ui
  cp -r "${REPO_DIR}/face-ui/." /opt/face-ui/
  ok "Face UI copied" "/opt/face-ui"
  chown -R "${PI_USER}:${PI_USER}" /opt/face-ui
  require_file_or_fail /opt/face-ui/index.html "kiosk UI entrypoint"
fi

if [[ -d "${REPO_DIR}/ai-runtime/static" ]]; then
  doing "Copying static files"
  mkdir -p /opt/ai-runtime/static
  cp -r "${REPO_DIR}/ai-runtime/static/." /opt/ai-runtime/static/
  ok "Static files copied" "fallback UI"
  require_file_or_fail /opt/ai-runtime/static/index.html "fallback UI entrypoint"
fi

doing "Creating Python virtual environment"
python3 -m venv /opt/ai-runtime/.venv
ok "Virtual environment created" "/opt/ai-runtime/.venv"

install_runtime_python_deps
PKG_COUNT=$(/opt/ai-runtime/.venv/bin/pip list --format=columns 2>/dev/null | tail -n +3 | wc -l)
ok "Dependencies installed" "${PKG_COUNT} packages (fastapi, uvicorn, pydantic...)"

install_silero_vad_bundle "/opt/ai-runtime/models/silero-vad"

doing "Verifying Python runtime dependencies"
/opt/ai-runtime/.venv/bin/python - <<'PY'
import importlib
modules = ["fastapi", "uvicorn", "pydantic", "numpy", "torch", "torchaudio", "pyaudio"]
missing = [name for name in modules if importlib.import_module(name) is None]
if missing:
    raise SystemExit("missing imports: " + ", ".join(missing))
PY
ok "Python runtime dependencies verified" "fastapi, numpy, torch, torchaudio, pyaudio"

doing "Verifying runtime Python files"
/opt/ai-runtime/.venv/bin/python -m py_compile \
  /opt/ai-runtime/config.py \
  /opt/ai-runtime/runtime.py \
  /opt/ai-runtime/server.py \
  /opt/ai-runtime/voice_ws.py \
  /opt/ai-runtime/voice_pipeline.py
ok "Runtime Python files verified" "py_compile"

doing "Verifying local Silero VAD bundle"
SILERO_VAD_DIR=/opt/ai-runtime/models/silero-vad /opt/ai-runtime/.venv/bin/python - <<'PY'
import os
from pathlib import Path
import torch

repo_dir = Path(os.environ["SILERO_VAD_DIR"])
if not repo_dir.exists():
    raise SystemExit(f"missing Silero VAD directory: {repo_dir}")
model, _ = torch.hub.load(str(repo_dir), "silero_vad", source="local")
if model is None:
    raise SystemExit("Silero VAD model load returned None")
PY
ok "Local Silero VAD bundle verified" "/opt/ai-runtime/models/silero-vad"

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

LOCAL_FALLBACK_READY=0
if [[ -n "${SELECTED_MODEL}" ]]; then
  doing "Setting model to ${SELECTED_MODEL}"
  upsert_env "$RUNTIME_ENV" "LOCAL_MODEL" "$SELECTED_MODEL"
  ok "Model configured" "LOCAL_MODEL=${SELECTED_MODEL}"

  doing "Setting supported local backend to Ollama"
  upsert_env "$RUNTIME_ENV" "LOCAL_BACKEND" "ollama"
  upsert_env "$RUNTIME_ENV" "OLLAMA_BASE" "http://127.0.0.1:11434"
  ok "Local backend target configured" "backend: ollama"

  doing "Provisioning local fallback backend"
  if install_ollama_backend "$SELECTED_MODEL"; then
    LOCAL_FALLBACK_READY=1
    ok "Local fallback configured" "backend: ollama"
  else
    warn "Local fallback backend was not fully provisioned"
  fi
else
  doing "Disabling local model backend"
  upsert_env "$RUNTIME_ENV" "LOCAL_MODEL" ""
  upsert_env "$RUNTIME_ENV" "LOCAL_BACKEND" "none"
  ok "Local model disabled" "gateway-only install"
fi

doing "Finalizing runtime ownership"
chown -R "${PI_USER}:${PI_USER}" /opt/ai-runtime
ok "Runtime ownership finalized" "owner: ${PI_USER}"
step_done

# Step 4: device-agent
step_header 4 "Installing device-agent"
info "Heartbeat agent for gateway connectivity."
echo ""

doing "Creating /opt/device-agent"
mkdir -p /opt/device-agent
chown "${PI_USER}:${PI_USER}" /opt/device-agent

doing "Copying agent source"
cp "${REPO_DIR}/device-agent/agent.py" /opt/device-agent/
ok "Device agent installed" "/opt/device-agent/agent.py"
require_file_or_fail /opt/device-agent/agent.py "device heartbeat worker"

doing "Setting device-agent file permissions"
chown "${PI_USER}:${PI_USER}" /opt/device-agent/agent.py
chmod 644 /opt/device-agent/agent.py
ok "Device agent file secured" "owner: ${PI_USER}"

doing "Verifying device-agent syntax"
python3 -m py_compile /opt/device-agent/agent.py
ok "Device agent verified" "python3 -m py_compile"

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
info "Requesting gateway access for this Pi."
echo ""

DEVICE_ID="$(get_env "$RUNTIME_ENV" "DEVICE_ID" || true)"
if [[ -z "${DEVICE_ID}" || "${DEVICE_ID}" == "pi-001" ]]; then
  DEVICE_ID="$(hostname)"
  upsert_env "$RUNTIME_ENV" "DEVICE_ID" "$DEVICE_ID"
  info "Device ID set to hostname: ${BOLD}${DEVICE_ID}${RST}"
fi
upsert_env "$AGENT_ENV" "DEVICE_ID" "$DEVICE_ID"

TOKEN="$(get_env "$RUNTIME_ENV" "GATEWAY_DEVICE_TOKEN" || true)"
TOKEN_SOURCE="existing"

if [[ -z "${TOKEN}" || "${TOKEN}" == "replace_with_device_token" ]]; then
  REGISTER_URL="$(get_env "$RUNTIME_ENV" "GATEWAY_REGISTER_URL" || true)"
  BOOTSTRAP_SECRET="$(get_env "$RUNTIME_ENV" "GATEWAY_BOOTSTRAP_SECRET" || true)"
  if [[ -n "${REGISTER_URL}" ]]; then
    doing "Requesting device access from gateway"
    info "Register URL: ${REGISTER_URL}"
    info "Device ID: ${DEVICE_ID}"
    REG_RESPONSE="$(register_with_gateway "$REGISTER_URL" "$BOOTSTRAP_SECRET" "$DEVICE_ID")"
    REG_STATE="$(json_field "$REG_RESPONSE" status)"
    REG_TOKEN="$(json_field "$REG_RESPONSE" device_token)"
    REG_DETAIL="$(json_field "$REG_RESPONSE" detail)"
    REG_PAIRING_CODE="$(json_field "$REG_RESPONSE" pairing_code)"
    REG_EXPIRES_AT="$(json_field "$REG_RESPONSE" expires_at)"

    if [[ "${REG_STATE}" == "approved" && -n "${REG_TOKEN}" ]]; then
      TOKEN="${REG_TOKEN}"
      ok "Gateway access approved" "device_id: ${DEVICE_ID}"
      TOKEN_SOURCE="gateway"
    elif [[ "${REG_STATE}" == "pending" ]]; then
      TOKEN="replace_with_device_token"
      TOKEN_SOURCE="pending_approval"
      warn "Gateway access request is pending admin approval"
      info "${REG_DETAIL:-Approve this Pi from the gateway dashboard to continue}"
      if [[ -n "${REG_PAIRING_CODE}" ]]; then
        echo ""
        echo "  ${BOLD}${SAFFRON}╭─────────────────────────────────────────────────────────────╮${RST}"
        echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
        echo "  ${BOLD}${SAFFRON}│${RST}   ${BOLD}${WHITE}Verify This Pi In Dashboard${RST}                              ${BOLD}${SAFFRON}│${RST}"
        echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
        echo "  ${BOLD}${SAFFRON}│${RST}   ${CREAM}Device ID:${RST} ${BOLD}${WHITE}${DEVICE_ID}${RST}"
        echo "  ${BOLD}${SAFFRON}│${RST}   ${CREAM}Pairing code:${RST} ${BOLD}${GREEN}${REG_PAIRING_CODE}${RST}"
        if [[ -n "${REG_EXPIRES_AT}" ]]; then
          echo "  ${BOLD}${SAFFRON}│${RST}   ${CREAM}Expires:${RST} ${DIM}${REG_EXPIRES_AT}${RST}"
        fi
        echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
        echo "  ${BOLD}${SAFFRON}│${RST}   ${YELLOW}Approve only if this code matches the dashboard.${RST} ${BOLD}${SAFFRON}│${RST}"
        echo "  ${BOLD}${SAFFRON}│${RST}                                                             ${BOLD}${SAFFRON}│${RST}"
        echo "  ${BOLD}${SAFFRON}╰─────────────────────────────────────────────────────────────╯${RST}"
        echo ""
      fi
      info "Polling for approval for up to 5 minutes"
      for _attempt in $(seq 1 60); do
        sleep 5
        REG_RESPONSE="$(register_with_gateway "$REGISTER_URL" "$BOOTSTRAP_SECRET" "$DEVICE_ID")"
        REG_STATE="$(json_field "$REG_RESPONSE" status)"
        REG_TOKEN="$(json_field "$REG_RESPONSE" device_token)"
        REG_DETAIL="$(json_field "$REG_RESPONSE" detail)"
        REG_PAIRING_CODE="$(json_field "$REG_RESPONSE" pairing_code)"
        REG_EXPIRES_AT="$(json_field "$REG_RESPONSE" expires_at)"
        if [[ "${REG_STATE}" == "approved" && -n "${REG_TOKEN}" ]]; then
          TOKEN="${REG_TOKEN}"
          TOKEN_SOURCE="gateway"
          ok "Gateway access approved" "device_id: ${DEVICE_ID}"
          break
        fi
        if [[ "${REG_STATE}" == "rejected" ]]; then
          TOKEN="replace_with_device_token"
          TOKEN_SOURCE="rejected"
          warn "Gateway access request was rejected by admin"
          break
        fi
      done
      if [[ "${TOKEN_SOURCE}" == "pending_approval" ]]; then
        warn "Approval not received yet — leaving gateway token unset for now"
      fi
    elif [[ "${REG_STATE}" == "rejected" ]]; then
      TOKEN="replace_with_device_token"
      TOKEN_SOURCE="rejected"
      warn "Gateway access request was rejected by admin"
    else
      warn "Gateway registration failed; leaving gateway token unset"
      if [[ -n "${REG_DETAIL}" ]]; then
        info "Gateway detail: ${REG_DETAIL}"
      fi
      TOKEN="replace_with_device_token"
      TOKEN_SOURCE="registration_failed"
    fi
  else
    info "No GATEWAY_REGISTER_URL configured"
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

if [[ "${TOKEN}" == "replace_with_device_token" && "${LOCAL_FALLBACK_READY}" -ne 1 ]]; then
  fail "No usable backend available: gateway registration failed and local Ollama fallback is not ready"
  echo ""
  cmd "Check network access, available storage/RAM, and Ollama install logs"
  cmd "sudo journalctl -u ollama -n 100 --no-pager"
  exit 1
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
ok "vritti-voice.service installed" "mic → VAD → local chat"

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

doing "Clearing failed service states"
systemctl reset-failed ai-runtime device-agent vritti-voice >/dev/null 2>&1 || true
ok "Failed states cleared"

doing "Enabling services for auto-start on boot"
systemctl enable ai-runtime device-agent vritti-kiosk vritti-voice 2>&1 | stream_progress
ok "Services enabled" "ai-runtime, device-agent, kiosk, voice"

doing "Starting ai-runtime"
systemctl restart ai-runtime
sleep 2
if systemctl is-active --quiet ai-runtime; then
  if wait_for_http_ok "http://127.0.0.1:8000/health" 20 1; then
    ok "ai-runtime is running" "port 8000"
    BACKEND_STATUS=""
    if BACKEND_STATUS="$(runtime_backend_status "http://127.0.0.1:8000/health")"; then
      ok "ai-runtime backend ready" "$BACKEND_STATUS"
    else
      fail "ai-runtime started, but no chat backend is reachable"
      echo ""
      cmd "Inspect runtime health:"
      cmd "curl -s http://127.0.0.1:8000/health"
      exit 1
    fi
  else
    fail "ai-runtime service is active, but /health did not become ready"
    exit 1
  fi
else
  fail "ai-runtime did not start"
  exit 1
fi

doing "Starting device-agent"
require_file_or_fail /opt/device-agent/agent.py "device-agent ExecStart target"
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
result_line "Model:" "${LOCAL_MODEL_LABEL}"
if [[ -n "${SELECTED_MODEL}" ]]; then
  result_line "Local fallback:" "Ollama on 127.0.0.1:11434"
else
  result_line "Local fallback:" "disabled"
fi
result_line "device-agent:" "Heartbeat → gateway every 60s"
result_line "Face UI:" "fullscreen kiosk (Chromium)"
result_line "Voice pipeline:" "mic → VAD → local chat"
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
  if [[ "${TOKEN_SOURCE}" == "pending_approval" ]]; then
    warn "Gateway token not issued yet. Approve this Pi in the gateway dashboard, then run again:"
    echo ""
    cmd "bash <(curl -fsSL https://raw.githubusercontent.com/Thir13een/Vritti/main/install-pi.sh)"
    echo ""
  elif [[ "${TOKEN_SOURCE}" == "rejected" ]]; then
    warn "Gateway access was rejected. Review it in the dashboard, then run again:"
    echo ""
    cmd "bash <(curl -fsSL https://raw.githubusercontent.com/Thir13een/Vritti/main/install-pi.sh)"
    echo ""
  elif [[ "${TOKEN_SOURCE}" == "not_configured" ]]; then
    warn "Gateway registration is not configured for this Pi."
    echo ""
  fi
fi

section_box "Configuration Files" "$MAGENTA"
echo ""
result_line "Runtime config:" "/opt/ai-runtime/.env"
result_line "Agent config:" "/opt/device-agent/.env"
echo ""
info "Key settings in /opt/ai-runtime/.env:"
if [[ -n "${SELECTED_MODEL}" ]]; then
  echo "       ${DIM}LOCAL_BACKEND=ollama${RST}"
  echo "       ${DIM}LOCAL_MODEL=${SELECTED_MODEL}${RST}"
  echo "       ${DIM}GATEWAY_FIRST=true${RST}          ${DIM}# try gateway first, local as backup${RST}"
else
  echo "       ${DIM}LOCAL_BACKEND=none${RST}"
  echo "       ${DIM}LOCAL_MODEL=${RST}"
  echo "       ${DIM}GATEWAY_FIRST=true${RST}          ${DIM}# gateway-only mode${RST}"
fi
echo ""

section_box "Quick Reference" "$CYAN"
echo ""
echo "  ${DIM}Test chat     ${RST} curl -s http://127.0.0.1:8000/v1/chat -H 'Content-Type: application/json' -d '{\"prompt\":\"Hello\"}'"
echo "  ${DIM}Runtime logs  ${RST} sudo journalctl -u ai-runtime -n 100 -f"
echo "  ${DIM}Agent logs    ${RST} sudo journalctl -u device-agent -n 100 -f"
echo "  ${DIM}Voice logs    ${RST} sudo journalctl -u vritti-voice -n 100 -f"
if [[ -n "${SELECTED_MODEL}" ]]; then
  echo "  ${DIM}Ollama logs   ${RST} sudo journalctl -u ollama -n 100 -f"
fi
echo "  ${DIM}Restart       ${RST} sudo systemctl restart ai-runtime device-agent vritti-voice"
echo "  ${DIM}Status        ${RST} sudo systemctl status ai-runtime device-agent vritti-voice"
echo ""
divider
echo ""
echo "  ${SAFFRON}Vritti${RST} ${DIM}— AI for every Indian language${RST}"
echo ""
