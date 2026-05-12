#!/usr/bin/env bash
# logs_endpoint.sh — Stream or tail CloudWatch logs for a SageMaker endpoint
#
# SageMaker writes all container stdout/stderr to CloudWatch under:
#   /aws/sagemaker/Endpoints/<endpoint-name>/<instance-id>/...
#
# Usage:
#   ./scripts/logs_endpoint.sh              # interactive prompt to choose NIM
#   ./scripts/logs_endpoint.sh magpie       # uses SAGEMAKER_MAGPIE_ENDPOINT_NAME from .env
#   ./scripts/logs_endpoint.sh nemotron-asr # uses SAGEMAKER_ASR_ENDPOINT_NAME from .env
#   ./scripts/logs_endpoint.sh magpie --no-follow       # print recent logs and exit
#   ./scripts/logs_endpoint.sh nemotron-asr --no-follow # print recent logs and exit

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

# ── Parse args ────────────────────────────────────────────────────────────────
NIM_TYPE=""
FOLLOW=true

for ARG in "$@"; do
  case "$ARG" in
    --no-follow)   FOLLOW=false ;;
    --follow)      FOLLOW=true  ;;
    magpie)        NIM_TYPE="magpie" ;;
    nemotron-asr)  NIM_TYPE="nemotron-asr" ;;
    -*)            echo "Unknown option: $ARG"; exit 1 ;;
    *)             echo "Unknown argument: $ARG"; exit 1 ;;
  esac
done

# ── Resolve NIM type ──────────────────────────────────────────────────────────
if [ -z "$NIM_TYPE" ]; then
  echo ""
  echo "Which NIM endpoint logs would you like to view?"
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
    ;;
  nemotron-asr)
    ENDPOINT_NAME="${SAGEMAKER_ASR_ENDPOINT_NAME:-}"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    exit 1
    ;;
esac

if [ -z "$ENDPOINT_NAME" ]; then
  echo ""
  echo "ERROR: No endpoint name found."
  echo "  Set the appropriate variable in .env:"
  echo "    magpie       → SAGEMAKER_MAGPIE_ENDPOINT_NAME"
  echo "    nemotron-asr → SAGEMAKER_ASR_ENDPOINT_NAME"
  echo ""
  exit 1
fi

REGION="${AWS_REGION:-us-west-2}"
LOG_GROUP="/aws/sagemaker/Endpoints/${ENDPOINT_NAME}"

# ── Validate required vars ────────────────────────────────────────────────────
MISSING=()
[ -z "${AWS_ACCESS_KEY_ID:-}" ]     && MISSING+=("AWS_ACCESS_KEY_ID")
[ -z "${AWS_SECRET_ACCESS_KEY:-}" ] && MISSING+=("AWS_SECRET_ACCESS_KEY")
[ -z "${AWS_REGION:-}" ]            && MISSING+=("AWS_REGION")

if [ ${#MISSING[@]} -gt 0 ]; then
  echo ""
  echo "ERROR: Missing required environment variables:"
  for VAR in "${MISSING[@]}"; do echo "  - $VAR"; done
  echo ""
  exit 1
fi

# ── Check endpoint exists ─────────────────────────────────────────────────────
echo ""
if ! aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$REGION" &>/dev/null; then
  echo "ERROR: Endpoint '$ENDPOINT_NAME' not found in region $REGION."
  echo "  Run ./scripts/list_endpoints.sh to see available endpoints."
  exit 1
fi

ENDPOINT_STATUS=$(aws sagemaker describe-endpoint \
  --endpoint-name "$ENDPOINT_NAME" \
  --region "$REGION" \
  --query 'EndpointStatus' \
  --output text)

# ── For failed endpoints: always print, never follow ──────────────────────────
if [ "$ENDPOINT_STATUS" = "Failed" ]; then
  FOLLOW=false
fi

# ── Encode log group name for CloudWatch console URL ──────────────────────────
LOG_GROUP_ENCODED=$(echo "$LOG_GROUP" | sed 's|/|%2F|g')
CW_URL="https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#logsV2:log-groups/log-group/${LOG_GROUP_ENCODED}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " SageMaker Endpoint Logs  [$NIM_TYPE]"
echo ""
echo " Endpoint  : $ENDPOINT_NAME  ($ENDPOINT_STATUS)"
echo " Log group : $LOG_GROUP"
echo " Console   : $CW_URL"
echo " Region    : $REGION"
if $FOLLOW; then
  echo " Mode      : follow  (Ctrl+C to stop)"
else
  echo " Mode      : recent logs (pass nothing or --follow to tail live)"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Show SageMaker failure reason if endpoint is failed ───────────────────────
if [ "$ENDPOINT_STATUS" = "Failed" ]; then
  FAILURE_REASON=$(aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$REGION" \
    --query 'FailureReason' \
    --output text)
  echo "  SageMaker failure reason: $FAILURE_REASON"
  echo ""
fi

# ── Stream logs ───────────────────────────────────────────────────────────────
# Failed endpoints: use a 24h window so logs aren't missed if deployment was slow.
# Live endpoints: 1h is enough for recent activity.
if [ "$ENDPOINT_STATUS" = "Failed" ]; then
  SINCE="24h"
else
  SINCE="1h"
fi

TAIL_ARGS=(
  "$LOG_GROUP"
  --since "$SINCE"
  --format short
  --region "$REGION"
)
$FOLLOW && TAIL_ARGS+=(--follow)

if ! aws logs tail "${TAIL_ARGS[@]}"; then
  echo ""
  echo "  Could not read logs from CloudWatch."
  echo ""
  if [ "$ENDPOINT_STATUS" = "Failed" ]; then
    echo "  The log group may not exist — the container may never have started."
    echo "  This usually means an image pull failure or IAM permission issue."
    echo "  Verify:"
    echo "    - The ECR image URI is correct (run ./scripts/push_to_ecr.sh $NIM_TYPE)"
    echo "    - The execution role has ecr:GetAuthorizationToken and ecr:BatchGetImage"
  else
    echo "  If the endpoint is still deploying, wait a few minutes and try again."
  fi
  echo ""
  echo "  Open CloudWatch directly: $CW_URL"
fi
