#!/usr/bin/env bash
# entrypoint.sh — Start the NVIDIA NIM server and the SageMaker wrapper side by side.
#
# Process layout inside the container:
#
#   PID 1  this script
#   ├── NIM server (original NIM entrypoint, runs in background)
#   │     listens on NIM_HTTP_API_PORT (default: 9000) and NIM_GRPC_API_PORT (default: 50051)
#   └── uvicorn (FastAPI wrapper, runs in background)
#         listens on port 8080 — SageMaker's expected port

set -euo pipefail

NIM_HTTP_PORT="${NIM_HTTP_API_PORT:-9000}"
NIM_GRPC_PORT="${NIM_GRPC_API_PORT:-50051}"
WRAPPER_PORT=8080   # SageMaker always expects port 8080

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Nemotron ASR SageMaker Wrapper"
echo ""
echo " NIM HTTP port  : $NIM_HTTP_PORT"
echo " NIM gRPC port  : $NIM_GRPC_PORT"
echo " Wrapper port   : $WRAPPER_PORT  (SageMaker /ping + /invocations)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Start the NIM server ──────────────────────────────────────────────────────
# We try common entrypoint locations for NVIDIA NIM containers.
# If none match, set NIM_START_CMD in your environment to override.
#
# Note: Nemotron ASR Streaming requires NIM_TAGS_SELECTOR="mode=str" to be set
# in the container environment for streaming mode.

start_nim() {
  if [ -n "${NIM_START_CMD:-}" ]; then
    echo "→ Starting NIM via NIM_START_CMD: $NIM_START_CMD"
    eval "$NIM_START_CMD"
  elif [ -f /opt/nim/start-server.sh ]; then
    echo "→ Starting NIM via /opt/nim/start-server.sh ..."
    /opt/nim/start-server.sh
  elif [ -f /opt/nim/start_server.sh ]; then
    echo "→ Starting NIM via /opt/nim/start_server.sh ..."
    /opt/nim/start_server.sh
  elif [ -f /opt/nvidia/nvidia_entrypoint.sh ]; then
    echo "→ Starting NIM via /opt/nvidia/nvidia_entrypoint.sh ..."
    /opt/nvidia/nvidia_entrypoint.sh
  elif command -v nim_start &>/dev/null; then
    echo "→ Starting NIM via nim_start ..."
    nim_start
  else
    echo ""
    echo "ERROR: Could not find NIM start command."
    echo "  Inspect the NIM image to find its entrypoint:"
    echo "    docker inspect nvcr.io/nim/nvidia/nemotron-asr-streaming:latest \\"
    echo "      --format='{{.Config.Entrypoint}} {{.Config.Cmd}}'"
    echo "  Then set NIM_START_CMD in your SageMaker model environment."
    exit 1
  fi
}

start_nim &
NIM_PID=$!
echo "  NIM PID: $NIM_PID"

# ── Start the FastAPI wrapper ─────────────────────────────────────────────────
echo "→ Starting SageMaker wrapper on port $WRAPPER_PORT ..."
cd /opt/wrapper
.venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$WRAPPER_PORT" \
  --log-level info \
  --no-access-log &
UVICORN_PID=$!
echo "  Uvicorn PID: $UVICORN_PID"

echo ""
echo "  Both processes started. NIM is initializing (may take several minutes)."
echo "  SageMaker will poll /ping — it will return 503 until NIM is ready."
echo ""

# ── Supervise: exit if either process dies ────────────────────────────────────
trap 'echo "Shutting down..."; kill "$NIM_PID" "$UVICORN_PID" 2>/dev/null; wait' SIGTERM SIGINT

# Wait for either process to exit; if one dies, kill the other and exit
wait -n "$NIM_PID" "$UVICORN_PID" 2>/dev/null || true

EXIT_CODE=$?
echo "A child process exited (code $EXIT_CODE). Shutting down remaining processes."
kill "$NIM_PID" "$UVICORN_PID" 2>/dev/null || true
wait "$NIM_PID" "$UVICORN_PID" 2>/dev/null || true
exit "$EXIT_CODE"
