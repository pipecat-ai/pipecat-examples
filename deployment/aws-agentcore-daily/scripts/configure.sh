#!/bin/bash

# Script to detect/create IAM execution role and configure AgentCore

###############################################
# STEP 1 — Check if IAM role needs to be created
###############################################
if [ ! -f "./agent/.env" ]; then
    echo "❌ Error: agent/.env not found"
    exit 1
fi

source ./agent/.env
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
ROLE_NAME="AmazonBedrockAgentCoreSDKRuntime-${AWS_REGION}-daily"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# Check if role exists
aws iam get-role --role-name $ROLE_NAME &>/dev/null
if [ $? -ne 0 ]; then
    echo "IAM execution role not found. Creating role with Bedrock permissions..."
    ./scripts/setup-iam-role.sh
    echo ""
fi

###############################################
# STEP 2 — Configure agentcore
# Already configuring to use Docker as it is required by Pipecat
# Disabling memory by default since it is not needed by this example
# Using custom execution role with Bedrock permissions
###############################################
echo "Configuring AgentCore with execution role: $ROLE_ARN"
uv run agentcore configure \
    -e ./agent/pipecat-agent.py \
    --name pipecat_agent \
    --container-runtime docker \
    --disable-memory \
    --execution-role $ROLE_ARN
