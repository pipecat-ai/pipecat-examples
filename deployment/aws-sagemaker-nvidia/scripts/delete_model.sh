#!/usr/bin/env bash
# delete_model.sh — Delete a SageMaker Model
#
# Note: you must delete (or update) any endpoints using this model first.
# Run ./scripts/delete_endpoint.sh before this script.
#
# Usage:
#   ./scripts/delete_model.sh              # interactive prompt to choose NIM
#   ./scripts/delete_model.sh magpie       # uses SAGEMAKER_MAGPIE_MODEL_NAME from .env
#   ./scripts/delete_model.sh nemotron-asr # uses SAGEMAKER_ASR_MODEL_NAME from .env

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
  echo "Which NIM model would you like to delete?"
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
    MODEL_NAME="${SAGEMAKER_MAGPIE_MODEL_NAME:-}"
    ;;
  nemotron-asr)
    MODEL_NAME="${SAGEMAKER_ASR_MODEL_NAME:-}"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/delete_model.sh magpie"
    echo "    ./scripts/delete_model.sh nemotron-asr"
    echo ""
    exit 1
    ;;
esac

AWS_REGION="${AWS_REGION:-us-west-2}"

if [ -z "$MODEL_NAME" ]; then
  echo ""
  echo "ERROR: No model name found."
  echo "  Set the appropriate variable in .env:"
  echo "    magpie       → SAGEMAKER_MAGPIE_MODEL_NAME"
  echo "    nemotron-asr → SAGEMAKER_ASR_MODEL_NAME"
  echo ""
  exit 1
fi

# ── Check the model exists ────────────────────────────────────────────────────
if ! aws sagemaker describe-model \
      --model-name "$MODEL_NAME" \
      --region "$AWS_REGION" &>/dev/null; then
  echo ""
  echo "ERROR: Model '$MODEL_NAME' not found in region '$AWS_REGION'."
  echo ""
  exit 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Deleting SageMaker Model  [$NIM_TYPE]"
echo ""
echo " Model   : $MODEL_NAME"
echo " Region  : $AWS_REGION"
echo ""
echo " NOTE: The ECR image will NOT be deleted."
echo "       Make sure no active endpoints are using this model."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -r -p "Continue? [y/N]: " CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && echo "Aborted." && exit 0
echo ""

# ── Delete model ──────────────────────────────────────────────────────────────
echo "→ Deleting model '$MODEL_NAME' ..."
aws sagemaker delete-model \
  --model-name "$MODEL_NAME" \
  --region "$AWS_REGION"

echo ""
echo "✓ Model '$MODEL_NAME' deleted."
