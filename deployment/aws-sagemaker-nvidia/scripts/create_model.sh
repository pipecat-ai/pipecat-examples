#!/usr/bin/env bash
# create_model.sh — Register a NIM SageMaker wrapper image as a SageMaker Model
#
# Uses the SageMaker wrapper image (built by build_wrapper.sh, pushed by push_to_ecr.sh)
# which bundles the NIM server + a FastAPI layer that translates SageMaker's interface.
#
# Usage:
#   ./scripts/create_model.sh              # interactive prompt to choose NIM
#   ./scripts/create_model.sh magpie       # Magpie TTS
#   ./scripts/create_model.sh nemotron-asr # Nemotron ASR Streaming

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
  echo "Which NIM model would you like to register?"
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
    ECR_URI="${ECR_MAGPIE_IMAGE_URI:-}"
    CONTAINER_HOSTNAME="magpie-tts-multilingual"
    EXTRA_ENV_VARS=""
    MODEL_NAME_VAR="SAGEMAKER_MAGPIE_MODEL_NAME"
    ECR_URI_VAR="ECR_MAGPIE_IMAGE_URI  ← run scripts/push_to_ecr.sh magpie first"
    ;;
  nemotron-asr)
    MODEL_NAME="${SAGEMAKER_ASR_MODEL_NAME:-}"
    ECR_URI="${ECR_ASR_IMAGE_URI:-}"
    CONTAINER_HOSTNAME="nemotron-asr-streaming"
    # Nemotron ASR Streaming requires mode=str to enable streaming support
    # and CONTAINER_ID to select the nemotron-asr-streaming model profile
    EXTRA_ENV_VARS=",NIM_TAGS_SELECTOR=mode=str,CONTAINER_ID=nemotron-asr-streaming"
    MODEL_NAME_VAR="SAGEMAKER_ASR_MODEL_NAME"
    ECR_URI_VAR="ECR_ASR_IMAGE_URI  ← run scripts/push_to_ecr.sh nemotron-asr first"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/create_model.sh magpie"
    echo "    ./scripts/create_model.sh nemotron-asr"
    echo ""
    exit 1
    ;;
esac

# ── Validate required vars ────────────────────────────────────────────────────
MISSING=()
[ -z "${AWS_ACCESS_KEY_ID:-}" ]            && MISSING+=("AWS_ACCESS_KEY_ID")
[ -z "${AWS_SECRET_ACCESS_KEY:-}" ]        && MISSING+=("AWS_SECRET_ACCESS_KEY")
[ -z "${AWS_REGION:-}" ]                   && MISSING+=("AWS_REGION")
[ -z "$ECR_URI" ]                          && MISSING+=("$ECR_URI_VAR")
[ -z "${SAGEMAKER_EXECUTION_ROLE_ARN:-}" ] && MISSING+=("SAGEMAKER_EXECUTION_ROLE_ARN  ← run scripts/create_iam.sh first")
[ -z "$MODEL_NAME" ]                       && MISSING+=("$MODEL_NAME_VAR")
[ -z "${NGC_API_KEY:-}" ]                  && MISSING+=("NGC_API_KEY  ← needed by the NIM container at runtime")

if [ ${#MISSING[@]} -gt 0 ]; then
  echo ""
  echo "ERROR: Missing required variables in .env:"
  for VAR in "${MISSING[@]}"; do echo "  - $VAR"; done
  echo ""
  exit 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
NIM_HTTP_PORT="${NIM_HTTP_API_PORT:-9000}"
NIM_GRPC_PORT="${NIM_GRPC_API_PORT:-50051}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Creating SageMaker Model  [$NIM_TYPE]"
echo ""
echo " Model name   : $MODEL_NAME"
echo " Image URI    : $ECR_URI"
echo " Exec role    : $SAGEMAKER_EXECUTION_ROLE_ARN"
echo " NIM HTTP port: $NIM_HTTP_PORT  (NIM's internal port, wrapper exposes 8080)"
echo " NIM gRPC port: $NIM_GRPC_PORT"
echo " Region       : $AWS_REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -r -p "Continue? [y/N]: " CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && echo "Aborted." && exit 0

# ── Check if model already exists ─────────────────────────────────────────────
if aws sagemaker describe-model \
    --model-name "$MODEL_NAME" \
    --region "$AWS_REGION" &>/dev/null; then
  echo ""
  echo "ERROR: Model '$MODEL_NAME' already exists."
  echo "  Delete it first: ./scripts/delete_model.sh $NIM_TYPE"
  exit 1
fi

# ── Create the model ──────────────────────────────────────────────────────────
echo ""
echo "→ Creating model '$MODEL_NAME' ..."

# Environment variables passed to the wrapper container at runtime:
#   NGC_API_KEY          — NIM downloads model weights using this key
#   NIM_HTTP_API_PORT    — NIM's internal HTTP port (default 9000)
#   NIM_GRPC_API_PORT    — NIM's gRPC port (default 50051)
#   NIM_TAGS_SELECTOR    — (nemotron-asr only) selects the streaming model profile
#   CONTAINER_ID         — (nemotron-asr only) selects the nemotron-asr-streaming model
#   TORCH_CUDA_ARCH_LIST — (optional) restricts PyTorch JIT to the instance's GPU arch
ENV_VARS="NGC_API_KEY=${NGC_API_KEY},NIM_HTTP_API_PORT=${NIM_HTTP_PORT},NIM_GRPC_API_PORT=${NIM_GRPC_PORT}${EXTRA_ENV_VARS}"
if [ -n "${TORCH_CUDA_ARCH_LIST:-}" ]; then
  ENV_VARS="${ENV_VARS},TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST}"
fi

aws sagemaker create-model \
  --model-name "$MODEL_NAME" \
  --primary-container "Image=${ECR_URI},ContainerHostname=${CONTAINER_HOSTNAME},Environment={${ENV_VARS}}" \
  --execution-role-arn "$SAGEMAKER_EXECUTION_ROLE_ARN" \
  --region "$AWS_REGION" \
  > /dev/null

echo ""
echo "✓ Model '$MODEL_NAME' created."
echo ""
echo "  Next step: create and deploy the endpoint:"
echo "    ./scripts/create_endpoint.sh $NIM_TYPE"
