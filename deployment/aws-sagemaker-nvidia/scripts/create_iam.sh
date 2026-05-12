#!/usr/bin/env bash
# create_iam.sh — Create the IAM resources needed to deploy Magpie TTS on SageMaker
#
# Creates:
#   1. A SageMaker execution role  — used by SageMaker when running the endpoint
#   2. A deployer IAM user         — used by you (or CI) to run the deployment scripts
#   3. Access keys for the deployer user (printed at the end — save them!)
#
# Run this ONCE as an AWS admin user (or a user with IAM write permissions).
# After running, copy the printed credentials into your .env file.
#
# Usage:
#   ./scripts/create_iam.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Load only AWS_REGION from .env — do NOT load credentials ─────────────────
# This script must run with your personal admin credentials (aws configure).
# The deployer credentials don't exist yet — they are created by this script.
if [ -f "$ROOT_DIR/.env" ]; then
  AWS_REGION_FROM_ENV=$(grep -E '^AWS_REGION=' "$ROOT_DIR/.env" | head -1 | cut -d= -f2)
fi

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-${AWS_REGION_FROM_ENV:-us-west-2}}"
DEPLOYER_USER_NAME="magpie-sagemaker-deployer"
DEPLOYER_POLICY_NAME="MagpieSageMakerDeployPolicy"
EXECUTION_ROLE_NAME="magpie-sagemaker-execution-role"

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo "AWS account : $AWS_ACCOUNT_ID"
echo "Region      : $AWS_REGION"
echo "Deployer    : $DEPLOYER_USER_NAME"
echo "Exec role   : $EXECUTION_ROLE_NAME"
echo ""

# ── Confirmation safeguard ────────────────────────────────────────────────────
echo "This script will create or modify the following IAM resources:"
echo ""
echo "  IAM Role : $EXECUTION_ROLE_NAME"
echo "  IAM User : $DEPLOYER_USER_NAME"
echo ""
echo "In AWS Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo ""

read -r -p "Continue? [y/N]: " CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && echo "Aborted." && exit 0

echo ""
echo "Proceeding with IAM setup..."
echo ""

# ── 1. SageMaker execution role ───────────────────────────────────────────────
echo "─── Step 1: SageMaker execution role ───────────────────────────────────"

TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "sagemaker.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
)

if aws iam get-role --role-name "$EXECUTION_ROLE_NAME" &>/dev/null; then
  echo "  Role '$EXECUTION_ROLE_NAME' already exists — skipping creation."
else
  aws iam create-role \
    --role-name "$EXECUTION_ROLE_NAME" \
    --assume-role-policy-document "$TRUST_POLICY" \
    --description "SageMaker execution role for Magpie TTS NIM endpoint" \
    > /dev/null
  echo "  Created role: $EXECUTION_ROLE_NAME"
fi

# Attach managed policies to the execution role
for POLICY_ARN in \
  "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess" \
  "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess"; do
  aws iam attach-role-policy \
    --role-name "$EXECUTION_ROLE_NAME" \
    --policy-arn "$POLICY_ARN" 2>/dev/null && \
    echo "  Attached: $POLICY_ARN" || \
    echo "  Already attached: $POLICY_ARN"
done

EXECUTION_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${EXECUTION_ROLE_NAME}"
echo "  Role ARN: $EXECUTION_ROLE_ARN"

# ── 2. Deployer IAM user ──────────────────────────────────────────────────────
echo ""
echo "─── Step 2: Deployer IAM user ──────────────────────────────────────────"

if aws iam get-user --user-name "$DEPLOYER_USER_NAME" &>/dev/null; then
  echo "  User '$DEPLOYER_USER_NAME' already exists — skipping creation."
else
  aws iam create-user \
    --user-name "$DEPLOYER_USER_NAME" \
    > /dev/null
  echo "  Created user: $DEPLOYER_USER_NAME"
fi

# ── 3. Deployer inline policy (minimal permissions) ───────────────────────────
echo ""
echo "─── Step 3: Deployer permissions policy ────────────────────────────────"

DEPLOY_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAuth",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECRImagePush",
      "Effect": "Allow",
      "Action": [
        "ecr:CreateRepository",
        "ecr:DescribeRepositories",
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage"
      ],
      "Resource": "arn:aws:ecr:${AWS_REGION}:${AWS_ACCOUNT_ID}:repository/*"
    },
    {
      "Sid": "SageMakerDeploy",
      "Effect": "Allow",
      "Action": [
        "sagemaker:CreateModel",
        "sagemaker:DescribeModel",
        "sagemaker:DeleteModel",
        "sagemaker:ListModels",
        "sagemaker:CreateEndpointConfig",
        "sagemaker:DescribeEndpointConfig",
        "sagemaker:DeleteEndpointConfig",
        "sagemaker:ListEndpointConfigs",
        "sagemaker:CreateEndpoint",
        "sagemaker:DescribeEndpoint",
        "sagemaker:DeleteEndpoint",
        "sagemaker:ListEndpoints",
        "sagemaker:InvokeEndpoint"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
        "logs:StartQuery",
        "logs:GetQueryResults",
        "logs:StopQuery",
        "logs:DeleteLogGroup"
      ],
      "Resource": "arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/aws/sagemaker/*"
    },
    {
      "Sid": "PassSageMakerRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "${EXECUTION_ROLE_ARN}",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "sagemaker.amazonaws.com"
        }
      }
    }
  ]
}
EOF
)

aws iam put-user-policy \
  --user-name "$DEPLOYER_USER_NAME" \
  --policy-name "$DEPLOYER_POLICY_NAME" \
  --policy-document "$DEPLOY_POLICY"
echo "  Attached inline policy: $DEPLOYER_POLICY_NAME"

# ── 4. Create access keys ─────────────────────────────────────────────────────
echo ""
echo "─── Step 4: Access keys ────────────────────────────────────────────────"

# Check if user already has 2 keys (AWS limit)
KEY_COUNT=$(aws iam list-access-keys --user-name "$DEPLOYER_USER_NAME" \
  --query 'length(AccessKeyMetadata)' --output text)

if [ "$KEY_COUNT" -ge 2 ]; then
  echo "  WARNING: User already has 2 access keys (AWS limit)."
  echo "  Delete an existing key in the AWS console before creating a new one:"
  echo "  https://console.aws.amazon.com/iam/home#/users/$DEPLOYER_USER_NAME"
else
  KEYS=$(aws iam create-access-key --user-name "$DEPLOYER_USER_NAME")
  ACCESS_KEY_ID=$(echo "$KEYS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['AccessKeyId'])")
  SECRET_ACCESS_KEY=$(echo "$KEYS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['SecretAccessKey'])")

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  SAVE THESE — they will not be shown again."
  echo ""
  echo "  Add the following to your .env file:"
  echo ""
  echo "  AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID"
  echo "  AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY"
  echo "  AWS_REGION=$AWS_REGION"
  echo "  SAGEMAKER_EXECUTION_ROLE_ARN=$EXECUTION_ROLE_ARN"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
fi

echo ""
echo "✓ IAM setup complete."
