#!/bin/bash

# Script to dynamically read all variables from .env file and launch agentcore
AGENT_ENV_FILE="./agent/.env"
SERVER_ENV_FILE="./server/.env"
AGENTCORE_CONFIG=".bedrock_agentcore.yaml"

###############################################
# STEP 1 — Pre-flight checks
###############################################
if [ ! -f "$AGENTCORE_CONFIG" ]; then
    echo "❌ Error: $AGENTCORE_CONFIG not found"
    echo "Please run './scripts/configure.sh' first to configure your agent"
    exit 1
fi

if [ ! -f "$AGENT_ENV_FILE" ]; then
    echo "❌ Error: $AGENT_ENV_FILE file not found"
    echo "Please create an agent .env file with your environment variables"
    exit 1
fi

###############################################
# STEP 2 — Load environment variables
###############################################
echo "Loading environment variables..."
set -a
source "$AGENT_ENV_FILE"
set +a

###############################################
# STEP 3 — Apply VPC configuration (if available)
###############################################
if [ -f "vpc-config.env" ]; then
    echo ""
    echo "Applying VPC configuration from vpc-config.env..."
    source vpc-config.env

    # Update .bedrock_agentcore.yaml with VPC network settings
    cp .bedrock_agentcore.yaml .bedrock_agentcore.yaml.backup
    sed -i.tmp "s/network_mode: PUBLIC/network_mode: VPC/" .bedrock_agentcore.yaml
    sed -i.tmp "s/network_mode_config: null/network_mode_config:\\
          subnets:\\
            - $PRIVATE_SUBNET_1\\
            - $PRIVATE_SUBNET_2\\
          security_groups:\\
            - $SG_ID/" .bedrock_agentcore.yaml
    rm -f .bedrock_agentcore.yaml.tmp

    NETWORK_MODE="VPC"
    echo "✅ VPC configuration applied"
    echo "   VPC ID: $VPC_ID"
    echo "   Private Subnets: $PRIVATE_SUBNET_1, $PRIVATE_SUBNET_2"
    echo "   Security Group: $SG_ID"
else
    echo ""
    echo "⚠️  No vpc-config.env found. Please run './scripts/setup-vpc.sh' first."
    echo "   VPC is required for Daily transport (UDP must not be blocked)."
    exit 1
fi

###############################################
# STEP 4 — Launch the agent
###############################################

# Start building the agentcore launch command
LAUNCH_CMD="uv run agentcore launch --auto-update-on-conflict"
FOUND_ENV_VARS=false

echo "Loading environment variables from agent .env file..."

# Read each line from agent .env file and process it
while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty lines & comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

    # Ensure line contains KEY=value
    if [[ "$line" =~ ^[^=]+=(.*)$ ]]; then
        VAR_NAME="${line%%=*}"
        VAR_VALUE="${line#*=}"

        # Remove surrounding whitespace
        VAR_NAME="$(echo "$VAR_NAME" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        VAR_VALUE="$(echo "$VAR_VALUE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

        # Strip a single pair of surrounding quotes (handles both "value" and 'value')
        if [[ "${VAR_VALUE}" =~ ^\"(.*)\"$ ]] || [[ "${VAR_VALUE}" =~ ^\'(.*)\'$ ]]; then
            VAR_VALUE="${BASH_REMATCH[1]}"
        fi

        # Skip PIPECAT_LOCAL_DEV
        if [[ "$VAR_NAME" == "PIPECAT_LOCAL_DEV" ]]; then
            echo "  Skipping: $VAR_NAME (ignored for deployment)"
            continue
        fi

        # Skip if variable name or value is empty
        if [[ -n "$VAR_NAME" && -n "$VAR_VALUE" ]]; then
            # Always quote the value so special characters are preserved
            LAUNCH_CMD+=" --env $VAR_NAME=\"$VAR_VALUE\""
            FOUND_ENV_VARS=true
            echo "  Added: $VAR_NAME"
        fi
    fi
done < "$AGENT_ENV_FILE"

# Check if any environment variables were added
if ! $FOUND_ENV_VARS; then
    echo "Warning: No valid environment variables found in agent .env file"
    echo "Make sure your agent .env file contains variables in the format: KEY=value"
    exit 1
fi

# Execute the command
echo ""
echo "Executing: $LAUNCH_CMD"
eval "$LAUNCH_CMD"


###############################################
# STEP 5 — Read AGENT ARN from agentcore status
###############################################
echo "Reading Agent ARN from agentcore status..."

# Extract Agent ARN from status output (removing box formatting characters and spaces)
AGENT_ARN=$(uv run agentcore status | grep "Agent ARN:" | sed 's/.*Agent ARN: //' | sed 's/│//g' | xargs)

if [ -z "$AGENT_ARN" ]; then
    echo "Error: Could not extract Agent ARN from 'agentcore status' output"
    echo "This can happen if:"
    echo "  - The agent deployment has not completed yet (wait a few minutes and retry)"
    echo "  - The 'agentcore status' output format has changed"
    echo "  - No default agent is configured (run 'uv run agentcore configure list' to check)"
    echo ""
    echo "You can set AGENT_RUNTIME_ARN manually in server/.env once the ARN is available."
    exit 1
fi

echo "Agent ARN: $AGENT_ARN"

###############################################
# STEP 6 — Update server .env
###############################################
if [ ! -f "$SERVER_ENV_FILE" ]; then
    echo "ERROR: $SERVER_ENV_FILE not found!"
    exit 1
fi

# If AGENT_RUNTIME_ARN already exists → replace
# If not → append
if grep -q "^AGENT_RUNTIME_ARN=" "$SERVER_ENV_FILE"; then
    sed -i.bak "s|^AGENT_RUNTIME_ARN=.*|AGENT_RUNTIME_ARN=$AGENT_ARN|" "$SERVER_ENV_FILE"
else
    echo "AGENT_RUNTIME_ARN=$AGENT_ARN" >> "$SERVER_ENV_FILE"
fi

echo ".env updated successfully!"
echo "AGENT_RUNTIME_ARN is now set to:"
echo "$AGENT_ARN"

###############################################
# STEP 7 — Display log-tailing command
###############################################
echo ""
echo "📊 To monitor agent logs, run:"
echo ""
LOG_GROUP=$(uv run agentcore describe | grep -o '/aws/bedrock-agentcore/runtimes/[^"]*' | head -1)
if [ -n "$LOG_GROUP" ]; then
    echo "aws logs tail $LOG_GROUP --log-stream-name-prefix \"$(date +%Y/%m/%d)/[runtime-logs]\" --follow"
fi

echo ""
echo "✅ Deployment complete!"
echo ""
if [ "$NETWORK_MODE" = "VPC" ]; then
    echo "Network Configuration: VPC Mode"
    echo "  - VPC ID: $VPC_ID"
    echo "  - Private Subnets: $PRIVATE_SUBNET_1, $PRIVATE_SUBNET_2"
    echo "  - NAT Gateway: $NAT_GW_ID"
    echo ""
fi
echo "Next steps:"
echo "1. Start the server: cd server && uv run server.py"
echo "2. Start the agent: curl -X POST http://localhost:7860/start"
echo "3. Open your Daily room URL in your browser to talk to the agent"
