#!/usr/bin/env bash
# create_endpoint.sh — Create a SageMaker endpoint config and deploy the endpoint
#
# Combines both steps (endpoint config + endpoint creation) since they are
# always done together. Waits until the endpoint reaches InService.
#
# Usage:
#   ./scripts/create_endpoint.sh              # interactive prompt to choose NIM
#   ./scripts/create_endpoint.sh magpie       # Magpie TTS
#   ./scripts/create_endpoint.sh nemotron-asr # Nemotron ASR Streaming

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
  echo "Which NIM endpoint would you like to deploy?"
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
    ENDPOINT_CONFIG_NAME="${SAGEMAKER_MAGPIE_ENDPOINT_CONFIG_NAME:-}"
    ENDPOINT_NAME="${SAGEMAKER_MAGPIE_ENDPOINT_NAME:-}"
    INSTANCE_TYPE="${SAGEMAKER_MAGPIE_INSTANCE_TYPE:-}"
    INSTANCE_COUNT="${SAGEMAKER_MAGPIE_INSTANCE_COUNT:-}"
    MODEL_NAME_VAR="SAGEMAKER_MAGPIE_MODEL_NAME  ← run scripts/create_model.sh magpie first"
    ;;
  nemotron-asr)
    MODEL_NAME="${SAGEMAKER_ASR_MODEL_NAME:-}"
    ENDPOINT_CONFIG_NAME="${SAGEMAKER_ASR_ENDPOINT_CONFIG_NAME:-}"
    ENDPOINT_NAME="${SAGEMAKER_ASR_ENDPOINT_NAME:-}"
    INSTANCE_TYPE="${SAGEMAKER_ASR_INSTANCE_TYPE:-}"
    INSTANCE_COUNT="${SAGEMAKER_ASR_INSTANCE_COUNT:-}"
    MODEL_NAME_VAR="SAGEMAKER_ASR_MODEL_NAME  ← run scripts/create_model.sh nemotron-asr first"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/create_endpoint.sh magpie"
    echo "    ./scripts/create_endpoint.sh nemotron-asr"
    echo ""
    exit 1
    ;;
esac

# ── Validate required vars ────────────────────────────────────────────────────
MISSING=()
[ -z "${AWS_ACCESS_KEY_ID:-}" ]   && MISSING+=("AWS_ACCESS_KEY_ID")
[ -z "${AWS_SECRET_ACCESS_KEY:-}" ] && MISSING+=("AWS_SECRET_ACCESS_KEY")
[ -z "${AWS_REGION:-}" ]          && MISSING+=("AWS_REGION")
[ -z "$MODEL_NAME" ]              && MISSING+=("$MODEL_NAME_VAR")
[ -z "$ENDPOINT_CONFIG_NAME" ]    && MISSING+=("${NIM_TYPE^^}_ENDPOINT_CONFIG_NAME  (e.g. SAGEMAKER_ASR_ENDPOINT_CONFIG_NAME)")
[ -z "$ENDPOINT_NAME" ]           && MISSING+=("${NIM_TYPE^^}_ENDPOINT_NAME  (e.g. SAGEMAKER_ASR_ENDPOINT_NAME)")
[ -z "$INSTANCE_TYPE" ]           && MISSING+=("${NIM_TYPE^^}_INSTANCE_TYPE  (e.g. SAGEMAKER_ASR_INSTANCE_TYPE)")
[ -z "$INSTANCE_COUNT" ]          && MISSING+=("${NIM_TYPE^^}_INSTANCE_COUNT  (e.g. SAGEMAKER_ASR_INSTANCE_COUNT)")

if [ ${#MISSING[@]} -gt 0 ]; then
  echo ""
  echo "ERROR: Missing required variables in .env:"
  for VAR in "${MISSING[@]}"; do echo "  - $VAR"; done
  echo ""
  exit 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Creating SageMaker Endpoint  [$NIM_TYPE]"
echo ""
echo " Model          : $MODEL_NAME"
echo " Endpoint config: $ENDPOINT_CONFIG_NAME"
echo " Endpoint name  : $ENDPOINT_NAME"
echo " Instance type  : $INSTANCE_TYPE"
echo " Instance count : $INSTANCE_COUNT"
echo " Startup timeout: ${SAGEMAKER_CONTAINER_STARTUP_TIMEOUT:-3600}s (NIM can take up to 60 min)"
echo " Region         : $AWS_REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -r -p "Continue? [y/N]: " CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && echo "Aborted." && exit 0
echo ""

# ── Check if resources already exist ──────────────────────────────────────────
ALREADY_EXISTS=()

if aws sagemaker describe-endpoint-config \
    --endpoint-config-name "$ENDPOINT_CONFIG_NAME" \
    --region "$AWS_REGION" &>/dev/null; then
  ALREADY_EXISTS+=("Endpoint config : $ENDPOINT_CONFIG_NAME")
fi

if aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$AWS_REGION" &>/dev/null; then
  ALREADY_EXISTS+=("Endpoint        : $ENDPOINT_NAME")
fi

if [ ${#ALREADY_EXISTS[@]} -gt 0 ]; then
  echo ""
  echo "ERROR: The following resources already exist:"
  for RES in "${ALREADY_EXISTS[@]}"; do echo "  - $RES"; done
  echo ""
  echo "  Delete them first: ./scripts/delete_endpoint.sh $NIM_TYPE"
  exit 1
fi

# ── Create endpoint configuration ─────────────────────────────────────────────
echo "→ Creating endpoint configuration '$ENDPOINT_CONFIG_NAME' ..."

# ContainerStartupHealthCheckTimeoutInSeconds: how long SageMaker waits for the
# container to pass /ping health checks before declaring deployment failed.
# NIM downloads model weights at startup — NVIDIA docs say up to 60 minutes.
# We default to 3600s (60 min). Raise SAGEMAKER_CONTAINER_STARTUP_TIMEOUT in
# .env if your instance or network is slower.
STARTUP_TIMEOUT="${SAGEMAKER_CONTAINER_STARTUP_TIMEOUT:-3600}"

aws sagemaker create-endpoint-config \
  --endpoint-config-name "$ENDPOINT_CONFIG_NAME" \
  --production-variants "[{
    \"VariantName\": \"primary\",
    \"ModelName\": \"$MODEL_NAME\",
    \"InstanceType\": \"$INSTANCE_TYPE\",
    \"InitialInstanceCount\": $INSTANCE_COUNT,
    \"ContainerStartupHealthCheckTimeoutInSeconds\": $STARTUP_TIMEOUT
  }]" \
  --region "$AWS_REGION" \
  > /dev/null

echo "  Done."

# ── Deploy endpoint ───────────────────────────────────────────────────────────
echo "→ Deploying endpoint '$ENDPOINT_NAME' ..."
echo "  (NIM downloads model weights at startup — allow up to 60 minutes)"

aws sagemaker create-endpoint \
  --endpoint-name "$ENDPOINT_NAME" \
  --endpoint-config-name "$ENDPOINT_CONFIG_NAME" \
  --region "$AWS_REGION" \
  > /dev/null

# ── Wait for InService ────────────────────────────────────────────────────────
echo ""
echo "  Waiting for endpoint to become InService ..."
echo "  (polling every 30 seconds — press Ctrl+C to stop waiting;"
echo "   the deployment will continue in the background)"
echo ""

DOTS=""
while true; do
  STATUS=$(aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$AWS_REGION" \
    --query 'EndpointStatus' \
    --output text)

  if [ "$STATUS" = "InService" ]; then
    echo ""
    echo "✓ Endpoint '$ENDPOINT_NAME' is InService."
    echo ""
    echo "  Console: https://${AWS_REGION}.console.aws.amazon.com/sagemaker/home?region=${AWS_REGION}#/endpoints/${ENDPOINT_NAME}"
    echo ""
    echo "  Next step: test the endpoint — see client/README.md for test client usage."
    break
  elif [ "$STATUS" = "Failed" ]; then
    echo ""
    FAILURE_REASON=$(aws sagemaker describe-endpoint \
      --endpoint-name "$ENDPOINT_NAME" \
      --region "$AWS_REGION" \
      --query 'FailureReason' \
      --output text)
    echo "ERROR: Endpoint deployment failed."
    echo "  Reason: $FAILURE_REASON"
    echo ""
    echo "  Check the SageMaker console for details:"
    echo "  https://${AWS_REGION}.console.aws.amazon.com/sagemaker/home?region=${AWS_REGION}#/endpoints/${ENDPOINT_NAME}"
    exit 1
  else
    DOTS="${DOTS}."
    printf "\r  Status: %-20s %s" "$STATUS" "$DOTS"
    sleep 30
  fi
done
