#!/usr/bin/env bash
# delete_endpoint.sh — Delete a SageMaker endpoint and its endpoint configuration
#
# Also deletes the endpoint configuration, since it is tied to this endpoint
# and has no use once the endpoint is gone.
#
# Usage:
#   ./scripts/delete_endpoint.sh                        # interactive prompt to choose NIM
#   ./scripts/delete_endpoint.sh magpie                 # uses SAGEMAKER_MAGPIE_ENDPOINT_NAME from .env
#   ./scripts/delete_endpoint.sh nemotron-asr           # uses SAGEMAKER_ASR_ENDPOINT_NAME from .env

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
  echo "Which NIM endpoint would you like to delete?"
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
    ENDPOINT_NAME="${SAGEMAKER_MAGPIE_ENDPOINT_NAME:-}"
    ENDPOINT_CONFIG_NAME="${SAGEMAKER_MAGPIE_ENDPOINT_CONFIG_NAME:-}"
    ;;
  nemotron-asr)
    ENDPOINT_NAME="${SAGEMAKER_ASR_ENDPOINT_NAME:-}"
    ENDPOINT_CONFIG_NAME="${SAGEMAKER_ASR_ENDPOINT_CONFIG_NAME:-}"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/delete_endpoint.sh magpie"
    echo "    ./scripts/delete_endpoint.sh nemotron-asr"
    echo ""
    exit 1
    ;;
esac

AWS_REGION="${AWS_REGION:-us-west-2}"

if [ -z "$ENDPOINT_NAME" ]; then
  echo ""
  echo "ERROR: No endpoint name found."
  echo "  Set the appropriate variable in .env:"
  echo "    magpie       → SAGEMAKER_MAGPIE_ENDPOINT_NAME"
  echo "    nemotron-asr → SAGEMAKER_ASR_ENDPOINT_NAME"
  echo ""
  exit 1
fi

# ── Check what actually exists ────────────────────────────────────────────────
ENDPOINT_EXISTS=false
CONFIG_EXISTS=false

if aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$AWS_REGION" &>/dev/null; then
  ENDPOINT_EXISTS=true
  STATUS=$(aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$AWS_REGION" \
    --query 'EndpointStatus' \
    --output text)
fi

if [ -n "$ENDPOINT_CONFIG_NAME" ] && aws sagemaker describe-endpoint-config \
    --endpoint-config-name "$ENDPOINT_CONFIG_NAME" \
    --region "$AWS_REGION" &>/dev/null; then
  CONFIG_EXISTS=true
fi

LOG_GROUP="/aws/sagemaker/Endpoints/${ENDPOINT_NAME}"
LOGS_EXIST=false
FOUND_LOG=$(aws logs describe-log-groups \
    --log-group-name-prefix "$LOG_GROUP" \
    --region "$AWS_REGION" \
    --query "logGroups[?logGroupName=='${LOG_GROUP}'].logGroupName | [0]" \
    --output text 2>/dev/null) || true
if [ "$FOUND_LOG" = "$LOG_GROUP" ]; then
  LOGS_EXIST=true
fi

if ! $ENDPOINT_EXISTS && ! $CONFIG_EXISTS && ! $LOGS_EXIST; then
  echo ""
  echo "ERROR: Neither endpoint '$ENDPOINT_NAME' nor config '$ENDPOINT_CONFIG_NAME' nor its logs found in region '$AWS_REGION'."
  echo "  Run ./scripts/list_endpoints.sh to see available endpoints."
  echo ""
  exit 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
DELETE_LOGS=false
if $LOGS_EXIST; then
  read -r -p "Delete CloudWatch logs for this endpoint ($LOG_GROUP)? [y/N]: " CONFIRM_LOGS
  [[ "$CONFIRM_LOGS" =~ ^[Yy]$ ]] && DELETE_LOGS=true
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Deleting SageMaker Endpoint  [$NIM_TYPE]"
echo ""
if $ENDPOINT_EXISTS; then
  echo " Endpoint       : $ENDPOINT_NAME  (currently: $STATUS)"
else
  echo " Endpoint       : $ENDPOINT_NAME  (not found — skipping)"
fi
if [ -n "$ENDPOINT_CONFIG_NAME" ]; then
  if $CONFIG_EXISTS; then
    echo " Endpoint config: $ENDPOINT_CONFIG_NAME  (will be deleted)"
  else
    echo " Endpoint config: $ENDPOINT_CONFIG_NAME  (not found — skipping)"
  fi
fi
if $LOGS_EXIST; then
  if $DELETE_LOGS; then
    echo " Log group      : $LOG_GROUP  (will be deleted)"
  else
    echo " Log group      : $LOG_GROUP  (skipping)"
  fi
fi
echo " Region         : $AWS_REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -r -p "Continue? [y/N]: " CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && echo "Aborted." && exit 0
echo ""

# ── Delete endpoint ───────────────────────────────────────────────────────────
if $ENDPOINT_EXISTS; then
  echo "→ Deleting endpoint '$ENDPOINT_NAME' ..."
  aws sagemaker delete-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$AWS_REGION"
  echo "  Done."
fi

# ── Delete endpoint configuration ─────────────────────────────────────────────
if $CONFIG_EXISTS; then
  echo "→ Deleting endpoint configuration '$ENDPOINT_CONFIG_NAME' ..."
  aws sagemaker delete-endpoint-config \
    --endpoint-config-name "$ENDPOINT_CONFIG_NAME" \
    --region "$AWS_REGION"
  echo "  Done."
fi

# ── Delete CloudWatch log group ───────────────────────────────────────────────
if $DELETE_LOGS; then
  echo "→ Deleting CloudWatch log group '$LOG_GROUP' ..."
  aws logs delete-log-group \
    --log-group-name "$LOG_GROUP" \
    --region "$AWS_REGION"
  echo "  Done."
fi

echo ""
echo "✓ Cleanup complete."
echo "  Note: the SageMaker Model and ECR image are NOT deleted."
echo "  To delete the model: ./scripts/delete_model.sh $NIM_TYPE"
