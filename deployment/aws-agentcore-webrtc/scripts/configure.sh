#!/bin/bash

# Script to configure the bot, patch Dockerfile and sync AGENT_RUNTIME_ARN

DOCKERFILE=".bedrock_agentcore/pipecat_agent/Dockerfile"
TARGET_LINE="RUN cd . && uv pip install ."
# Extra dependencies needed by SmallWebRTC
INSERT_LINE="RUN apt update && apt install -y libgl1 libglib2.0-0 && apt clean"

###############################################
# STEP 1 — Check if IAM role needs to be created
###############################################
if [ ! -f "./agent/.env" ]; then
    echo "❌ Error: agent/.env not found"
    exit 1
fi

source ./agent/.env
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
ROLE_NAME="AmazonBedrockAgentCoreSDKRuntime-${AWS_REGION}-webrtc"
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

###############################################
# STEP 3 — Wait until Dockerfile exists
###############################################
while [ ! -s "$DOCKERFILE" ]; do
    sleep 0.2
done

###############################################
# STEP 4 — Patch Dockerfile
###############################################
cp "$DOCKERFILE" "$DOCKERFILE.bak"

awk -v target="$TARGET_LINE" -v insert="$INSERT_LINE" '
{
    print $0
    if ($0 ~ target) {
        print insert
    }
}
' "$DOCKERFILE.bak" > "$DOCKERFILE"

echo "Dockerfile patched successfully!"
