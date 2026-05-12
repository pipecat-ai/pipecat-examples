#!/usr/bin/env bash
# pull_nim.sh — Pull a NIM container from NVIDIA NGC
#
# Usage:
#   ./scripts/pull_nim.sh                     # interactive prompt to choose NIM
#   ./scripts/pull_nim.sh magpie              # pulls Magpie TTS :latest
#   ./scripts/pull_nim.sh magpie 1.7.0        # pulls a specific Magpie TTS tag
#   ./scripts/pull_nim.sh nemotron-asr        # pulls Nemotron ASR Streaming :latest
#   ./scripts/pull_nim.sh nemotron-asr latest # pulls a specific Nemotron ASR tag
#
# Requires NGC_API_KEY to be set in .env or exported in the shell.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Load .env if present ─────────────────────────────────────────────────────
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
  echo "Which NIM would you like to pull?"
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
    IMAGE_NAME="nvcr.io/nim/nvidia/magpie-tts-multilingual"
    TAG="${2:-${MAGPIE_IMAGE_TAG:-latest}}"
    NGC_DEPLOY_URL="https://build.nvidia.com/nvidia/magpie-tts-multilingual/deploy"
    NGC_TAGS_URL="https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/magpie-tts-multilingual/tags?version=latest"
    ;;
  nemotron-asr)
    IMAGE_NAME="nvcr.io/nim/nvidia/nemotron-asr-streaming"
    TAG="${2:-${NEMOTRON_ASR_IMAGE_TAG:-latest}}"
    NGC_DEPLOY_URL="https://build.nvidia.com/nvidia/nemotron-asr-streaming/deploy"
    NGC_TAGS_URL="https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/nemotron-asr-streaming/tags?version=latest"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/pull_nim.sh magpie [tag]"
    echo "    ./scripts/pull_nim.sh nemotron-asr [tag]"
    echo ""
    exit 1
    ;;
esac

FULL_IMAGE="$IMAGE_NAME:$TAG"

# SageMaker GPU instances run linux/amd64. Always pull that platform explicitly
# so the image is correct regardless of the host machine (e.g. Apple Silicon).
PLATFORM="linux/amd64"

# ── Validate NGC_API_KEY ──────────────────────────────────────────────────────
if [ -z "${NGC_API_KEY:-}" ]; then
  echo ""
  echo "ERROR: NGC_API_KEY is not set."
  echo ""
  echo "  Set it in your .env file:"
  echo "    NGC_API_KEY=<your_key>"
  echo ""
  echo "  To generate an API key:"
  echo "    1. Visit $NGC_DEPLOY_URL"
  echo "    2. Click 'Get API Key' and follow the steps."
  echo ""
  echo "  To see all available image versions (tags):"
  echo "    $NGC_TAGS_URL"
  echo ""
  exit 1
fi

# ── Login to NVIDIA NGC ───────────────────────────────────────────────────────
echo "→ Logging in to nvcr.io ..."
# Username must be the literal string '$oauthtoken' (not a shell variable)
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin

# ── Pull the image ────────────────────────────────────────────────────────────
echo "→ Pulling $FULL_IMAGE (platform: $PLATFORM) ..."
if ! docker pull --platform "$PLATFORM" "$FULL_IMAGE"; then
  echo ""
  echo "ERROR: Failed to pull $FULL_IMAGE"
  echo ""
  echo "  Possible causes:"
  echo "    - Your NGC_API_KEY is invalid or expired."
  echo "    - Tag '$TAG' does not exist."
  echo ""
  echo "  To rotate your API key or check your account:"
  echo "    $NGC_DEPLOY_URL"
  echo ""
  echo "  To list all available tags:"
  echo "    $NGC_TAGS_URL"
  echo ""
  exit 1
fi

echo ""
echo "✓ Successfully pulled: $FULL_IMAGE ($PLATFORM)"
