#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${VRITTI_REPO_URL:-https://github.com/Thir13een/Vritti.git}"
REPO_REF="${VRITTI_REPO_REF:-main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_INSTALLER="${SCRIPT_DIR}/pi/installer/install.sh"

if [[ "$(id -u)" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    exec sudo -E bash "$0" "$@"
  fi
  echo "This installer needs root. Re-run with sudo." >&2
  exit 1
fi

ensure_cmd() {
  local cmd_name="$1"
  local apt_pkg="${2:-$1}"
  if command -v "$cmd_name" >/dev/null 2>&1; then
    return 0
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq "$apt_pkg"
}

if [[ -x "${LOCAL_INSTALLER}" ]]; then
  exec bash "${LOCAL_INSTALLER}" "$@"
fi

ensure_cmd git git
ensure_cmd mktemp coreutils

WORKDIR="$(mktemp -d /tmp/vritti-pi-install.XXXXXX)"
cleanup() {
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

echo "Bootstrapping Vritti Pi installer..."
git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" "${WORKDIR}/Vritti" >/dev/null 2>&1

if [[ ! -x "${WORKDIR}/Vritti/pi/installer/install.sh" ]]; then
  echo "Failed to bootstrap the Pi installer." >&2
  exit 1
fi

exec bash "${WORKDIR}/Vritti/pi/installer/install.sh" "$@"
