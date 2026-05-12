#!/usr/bin/env bash
# push_to_ecr.sh — Push a SageMaker wrapper image to AWS ECR
#
# This is the only image SageMaker needs. The raw NIM image does not need to
# be in ECR — it is only used locally during the wrapper build.
#
# Prerequisites:
#   ./scripts/pull_nim.sh       → NIM image must be present locally
#   ./scripts/build_wrapper.sh  → wrapper image must be built locally
#
# Usage:
#   ./scripts/push_to_ecr.sh                    # interactive prompt to choose NIM
#   ./scripts/push_to_ecr.sh magpie             # Magpie TTS, uses MAGPIE_IMAGE_TAG or 'latest'
#   ./scripts/push_to_ecr.sh magpie 1.7.0       # Magpie TTS, specific tag
#   ./scripts/push_to_ecr.sh nemotron-asr       # Nemotron ASR, uses NEMOTRON_ASR_IMAGE_TAG or 'latest'
#   ./scripts/push_to_ecr.sh nemotron-asr latest # Nemotron ASR, specific tag

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
  echo "  Copy env.example to .env and fill in the values."
  echo "  If you haven't created the deployer user yet, run: ./scripts/create_iam.sh"
  echo ""
  exit 1
fi

# ── Resolve NIM type ──────────────────────────────────────────────────────────
NIM_TYPE="${1:-}"

if [ -z "$NIM_TYPE" ]; then
  echo ""
  echo "Which NIM wrapper would you like to push to ECR?"
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
    WRAPPER_REPO="${ECR_MAGPIE_WRAPPER_REPO_NAME:-magpie-tts-sagemaker}"
    BUILD_HINT="./scripts/build_wrapper.sh magpie $TAG"
    ECR_URI_VAR="ECR_MAGPIE_IMAGE_URI"
    ;;
  nemotron-asr)
    TAG="${2:-${NEMOTRON_ASR_IMAGE_TAG:-latest}}"
    WRAPPER_REPO="${ECR_ASR_WRAPPER_REPO_NAME:-nemotron-asr-sagemaker}"
    BUILD_HINT="./scripts/build_wrapper.sh nemotron-asr $TAG"
    ECR_URI_VAR="ECR_ASR_IMAGE_URI"
    ;;
  *)
    echo "ERROR: Unknown NIM type '$NIM_TYPE'."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/push_to_ecr.sh magpie [tag]"
    echo "    ./scripts/push_to_ecr.sh nemotron-asr [tag]"
    echo ""
    exit 1
    ;;
esac

WRAPPER_SOURCE_IMAGE="$WRAPPER_REPO:$TAG"

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
WRAPPER_ECR_IMAGE="$ECR_REGISTRY/$WRAPPER_REPO:$TAG"

# ── Verify wrapper image exists locally ───────────────────────────────────────
if ! docker image inspect "$WRAPPER_SOURCE_IMAGE" &>/dev/null; then
  echo ""
  echo "ERROR: Wrapper image '$WRAPPER_SOURCE_IMAGE' not found locally."
  echo "  Run: $BUILD_HINT"
  exit 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Pushing wrapper image to AWS ECR"
echo ""
echo " AWS Account : $AWS_ACCOUNT_ID"
echo " Region      : $AWS_REGION"
echo " Source      : $WRAPPER_SOURCE_IMAGE"
echo " Destination : $WRAPPER_ECR_IMAGE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -r -p "Continue? [y/N]: " CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && echo "Cancelled." && exit 0

# ── Authenticate Docker to ECR ────────────────────────────────────────────────
echo ""
echo "→ Authenticating Docker to ECR ..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# ── Create ECR repository if it doesn't exist ─────────────────────────────────
if ! aws ecr describe-repositories \
      --repository-names "$WRAPPER_REPO" \
      --region "$AWS_REGION" &>/dev/null; then
  aws ecr create-repository \
    --repository-name "$WRAPPER_REPO" \
    --region "$AWS_REGION" \
    > /dev/null
  echo "  Created ECR repository: $WRAPPER_REPO"
fi

# ── Tag and push ──────────────────────────────────────────────────────────────
echo "→ Pushing wrapper image ..."
echo "  (First push uploads all NIM layers — this will take a while.)"
echo "  (Subsequent pushes are fast — only wrapper changes are uploaded.)"
echo ""
docker tag "$WRAPPER_SOURCE_IMAGE" "$WRAPPER_ECR_IMAGE"
docker push "$WRAPPER_ECR_IMAGE"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Add this to your .env file:"
echo ""
echo "   $ECR_URI_VAR=$WRAPPER_ECR_IMAGE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
