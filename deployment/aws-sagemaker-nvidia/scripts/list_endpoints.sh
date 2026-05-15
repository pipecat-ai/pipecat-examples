#!/usr/bin/env bash
# list_endpoints.sh — List all SageMaker endpoints and their current status
#
# Usage:
#   ./scripts/list_endpoints.sh

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

AWS_REGION="${AWS_REGION:-us-west-2}"

# ── List endpoints ────────────────────────────────────────────────────────────
echo ""
echo "SageMaker Endpoints — region: $AWS_REGION"
echo ""

ENDPOINTS=$(aws sagemaker list-endpoints \
  --region "$AWS_REGION" \
  --query 'Endpoints[*].EndpointName' \
  --output text 2>/dev/null || true)

if [ -z "$ENDPOINTS" ]; then
  echo "  No endpoints found."
  echo ""
  echo "  Console: https://${AWS_REGION}.console.aws.amazon.com/sagemaker/home?region=${AWS_REGION}#/endpoints"
  echo ""
  exit 0
fi

# ── Show status for each endpoint ─────────────────────────────────────────────
for NAME in $ENDPOINTS; do
  INFO=$(aws sagemaker describe-endpoint \
    --endpoint-name "$NAME" \
    --region "$AWS_REGION" \
    --query '{Status:EndpointStatus, Reason:FailureReason, Created:CreationTime}' \
    --output json 2>/dev/null)

  STATUS=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['Status'])")
  CREATED=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['Created'][:10])")

  case "$STATUS" in
    InService)  ICON="✓" ;;
    Creating)   ICON="⏳" ;;
    Updating)   ICON="⏳" ;;
    Failed)     ICON="✗" ;;
    Deleting)   ICON="🗑" ;;
    *)          ICON=" " ;;
  esac

  printf "  %s  %-40s  %-12s  created %s\n" "$ICON" "$NAME" "$STATUS" "$CREATED"

  if [ "$STATUS" = "Failed" ]; then
    REASON=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('FailureReason') or 'unknown')")
    printf "     Reason: %s\n" "$REASON"
    printf "     Logs:   ./scripts/logs_endpoint.sh %s\n" "$NAME"
  fi
done

echo ""
echo "  Console: https://${AWS_REGION}.console.aws.amazon.com/sagemaker/home?region=${AWS_REGION}#/endpoints"
echo ""
