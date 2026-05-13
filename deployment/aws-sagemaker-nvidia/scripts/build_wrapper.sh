#!/usr/bin/env bash
# build_wrapper.sh — Build a SageMaker wrapper Docker image
#
# Extends a locally cached NVIDIA NIM image with a FastAPI layer that
# translates SageMaker's /ping and /invocations into the NIM's actual API.
#
# Docker uses the locally cached NIM image — it does NOT re-pull from NVIDIA's
# registry. Run pull_nim.sh first to ensure the image is present locally.
#
# Usage:
#   ./scripts/build_wrapper.sh                    # interactive prompt to choose NIM
#   ./scripts/build_wrapper.sh magpie             # Magpie TTS, uses MAGPIE_IMAGE_TAG or 'latest'
#   ./scripts/build_wrapper.sh magpie 1.7.0       # Magpie TTS, specific NIM version
#   ./scripts/build_wrapper.sh nemotron-asr       # Nemotron ASR, uses NEMOTRON_ASR_IMAGE_TAG or 'latest'
#   ./scripts/build_wrapper.sh nemotron-asr latest # Nemotron ASR, specific NIM version

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT_DIR/.env"
  set +a
fi

# ── Resolve NIM type ──────────────────────────────────────────────────────────
NIM_TYPE="${1:-}"

if [ -z "$NIM_TYPE" ]; then
  echo ""
  echo "Which NIM wrapper would you like to build?"
  echo ""
  echo "  1) magpie       — Magpie TTS (text-to-speech)"
  echo "  2) nemotron-asr — Nemotron ASR Streaming (speech-to-text)"
  echo ""
  read -rp "Enter choice [1/2] or name [magpie/nemotron-asr]: " NIM_CHOICE
  echo ""
  case "$NIM_CHOICE" in
    1|magpie)        NIM_TYPE="magpie" ;;
    2|nemotron-asr)  NIM_TYPE="nemotron-asr" ;;
    *)
      echo "ERROR: Invalid choice '$NIM_CHOICE'. Aborting."
      exit 1
      ;;
  esac
fi

case "$NIM_TYPE" in
  magpie)
    TAG="${2:-${MAGPIE_IMAGE_TAG:-latest}}"
    NIM_IMAGE="nvcr.io/nim/nvidia/magpie-tts-multilingual:$TAG"
    WRAPPER_REPO="${ECR_MAGPIE_WRAPPER_REPO_NAME:-magpie-tts-sagemaker}"
    DOCKERFILE="$ROOT_DIR/sagemaker-wrapper/magpie/Dockerfile"
    PULL_HINT="./scripts/pull_nim.sh magpie $TAG"
    ;;
  nemotron-asr)
    TAG="${2:-${NEMOTRON_ASR_IMAGE_TAG:-latest}}"
    NIM_IMAGE="nvcr.io/nim/nvidia/nemotron-asr-streaming:$TAG"
    WRAPPER_REPO="${ECR_ASR_WRAPPER_REPO_NAME:-nemotron-asr-sagemaker}"
    DOCKERFILE="$ROOT_DIR/sagemaker-wrapper/nemotron-asr/Dockerfile"
    PULL_HINT="./scripts/pull_nim.sh nemotron-asr $TAG"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/build_wrapper.sh magpie [tag]"
    echo "    ./scripts/build_wrapper.sh nemotron-asr [tag]"
    echo ""
    exit 1
    ;;
esac

WRAPPER_IMAGE="$WRAPPER_REPO:$TAG"

echo ""
echo "NIM base image : $NIM_IMAGE  (local cache)"
echo "Wrapper image  : $WRAPPER_IMAGE"
echo ""

# ── Check NIM image exists locally ───────────────────────────────────────────
if ! docker image inspect "$NIM_IMAGE" &>/dev/null; then
  echo "ERROR: NIM image '$NIM_IMAGE' not found locally."
  echo "  Run first: $PULL_HINT"
  exit 1
fi

# ── Auto-detect NIM entrypoint ────────────────────────────────────────────────
# Inspect the local NIM image to find its original ENTRYPOINT + CMD.
# Baked in as NIM_START_CMD so entrypoint.sh knows how to start NIM.
#
# Note: docker inspect returns empty Config for manifest-list images (multi-arch
# images stored with the containerd backend). In that case we fall back to
# running the image and probing well-known start-script paths.
NIM_ENTRYPOINT=$(docker inspect "$NIM_IMAGE" \
  --format='{{range .Config.Entrypoint}}{{.}} {{end}}' 2>/dev/null | xargs || true)
NIM_CMD=$(docker inspect "$NIM_IMAGE" \
  --format='{{range .Config.Cmd}}{{.}} {{end}}' 2>/dev/null | xargs || true)

if [ -n "$NIM_ENTRYPOINT" ]; then
  NIM_START_CMD="$NIM_ENTRYPOINT $NIM_CMD"
elif [ -n "$NIM_CMD" ]; then
  NIM_START_CMD="$NIM_CMD"
else
  NIM_START_CMD=""
fi
NIM_START_CMD=$(echo "$NIM_START_CMD" | xargs)

# Fallback: probe well-known paths inside the container when docker inspect
# returned nothing (happens with manifest-list images on containerd backends).
if [ -z "$NIM_START_CMD" ]; then
  echo "  docker inspect returned empty config (manifest-list image). Probing container..."
  NIM_START_CMD=$(docker run --rm --platform linux/amd64 \
    --entrypoint /bin/sh "$NIM_IMAGE" \
    -c 'for f in /opt/nim/start_server.sh /opt/nim/start-server.sh; do
          [ -f "$f" ] && echo "$f" && exit 0
        done' 2>/dev/null | tr -d '[:space:]' || true)
fi

if [ -n "$NIM_START_CMD" ]; then
  echo "  Detected NIM start command: $NIM_START_CMD"
else
  echo "  WARNING: Could not detect NIM start command."
  echo "  entrypoint.sh will try common paths at runtime."
fi

# ── Build ─────────────────────────────────────────────────────────────────────
echo ""
echo "→ Building wrapper image (platform: linux/amd64) ..."
echo "  This may take a few minutes ..."
echo ""

docker build \
  --platform linux/amd64 \
  --provenance=false \
  --build-arg "NIM_IMAGE=$NIM_IMAGE" \
  --build-arg "NIM_START_CMD=$NIM_START_CMD" \
  --file "$DOCKERFILE" \
  --tag "$WRAPPER_IMAGE" \
  "$ROOT_DIR"

echo ""
echo "✓ Built: $WRAPPER_IMAGE"
echo ""
echo "  Next step: push to ECR:"
echo "    ./scripts/push_to_ecr.sh $NIM_TYPE $TAG"
