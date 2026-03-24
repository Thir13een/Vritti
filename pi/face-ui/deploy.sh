#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: sudo bash pi/face-ui/deploy.sh [--no-restart]

Copies the face UI from this repo into /opt/face-ui.
By default it restarts vritti-kiosk if the service exists.
EOF
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash pi/face-ui/deploy.sh [--no-restart]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="/opt/face-ui"
RESTART_KIOSK=1

if [[ "${1:-}" == "--no-restart" ]]; then
  RESTART_KIOSK=0
fi

install -d -m 755 "${DEST_DIR}"
cp -a "${SCRIPT_DIR}/." "${DEST_DIR}/"

echo "Deployed face UI:"
echo "  source: ${SCRIPT_DIR}"
echo "  target: ${DEST_DIR}"

if [[ "${RESTART_KIOSK}" -eq 1 ]] && command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files vritti-kiosk.service >/dev/null 2>&1; then
    systemctl restart vritti-kiosk || true
    echo "Restarted: vritti-kiosk"
  fi
fi

echo "Check the served UI with:"
echo "  curl -s http://127.0.0.1:8000/ | sed -n '1,20p'"
