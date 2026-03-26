#!/usr/bin/env bash
# Start Pi chat cleanly.
# Usage: ./start-pi-chat.sh
# Set SKIP_OLLAMA=1 to skip restart.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use sudo for Docker if needed.
DOCKER="${DOCKER:-docker}"
if ! $DOCKER info &>/dev/null; then
  DOCKER="sudo docker"
fi

# Clear old ports and processes.
echo "Closing any existing Pi chat / Ollama processes..."

# Stop old Pi runtime containers.
$DOCKER ps -q --filter "ancestor=vritti-ai-runtime" | xargs -r $DOCKER stop --time 5 2>/dev/null || true

# Clear port 8000.
while true; do
  PIDS=$(sudo lsof -ti:8000 2>/dev/null || true)
  [[ -z "$PIDS" ]] && break
  echo "  Killing process(es) on port 8000: $PIDS"
  echo "$PIDS" | xargs -r sudo kill -9 2>/dev/null || true
  sleep 1
done

# Clear port 11434.
while true; do
  PIDS=$(sudo lsof -ti:11434 2>/dev/null || true)
  [[ -z "$PIDS" ]] && break
  echo "  Killing process(es) on port 11434: $PIDS"
  echo "$PIDS" | xargs -r sudo kill -9 2>/dev/null || true
  sleep 1
done

sleep 2
echo "Ports 8000 and 11434 are free. Starting fresh."
echo ""

# Restart Ollama unless skipped.
if [[ "${SKIP_OLLAMA:-}" != "1" ]]; then
  if command -v ollama &>/dev/null; then
    echo "Restarting Ollama on 0.0.0.0:11434..."
    sudo lsof -ti:11434 | xargs -r sudo kill 2>/dev/null || true
    sleep 2
    OLLAMA_HOST=0.0.0.0 nohup ollama serve >> /tmp/ollama.log 2>&1 &
    sleep 2
    echo "Ollama started (logs: /tmp/ollama.log)."
  else
    echo "Note: ollama not in PATH. Ensure Ollama is running with: OLLAMA_HOST=0.0.0.0 ollama serve"
  fi
else
  echo "Skipping Ollama restart (SKIP_OLLAMA=1)."
fi

# 3) Build image if missing
if ! $DOCKER images -q vritti-ai-runtime | grep -q .; then
  echo "Building vritti-ai-runtime image..."
  $DOCKER build -t vritti-ai-runtime .
fi

# 4) Run Pi runtime container
echo "Starting Pi chat at http://localhost:8000/"
exec $DOCKER run --rm \
  --add-host=host.docker.internal:host-gateway \
  -p 8000:8000 \
  -e LOCAL_BACKEND=ollama \
  vritti-ai-runtime
