#!/bin/bash

# Script to dynamically read all variables from .env file and launch agentcore
AGENT_ENV_FILE="./agent/.env"
SERVER_ENV_FILE="./server/.env"

###############################################
# STEP 1 — Check environment file exists
###############################################
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
# STEP 3 — Check VPC configuration
###############################################
NETWORK_MODE=$(grep -A 2 "network_mode:" .bedrock_agentcore.yaml | grep "network_mode:" | awk '{print $2}')

if [ "$NETWORK_MODE" = "VPC" ]; then
    echo ""
    echo "VPC mode detected in configuration..."

    # Check if VPC is already configured
    if [ ! -f "vpc-config.env" ]; then
        echo ""
        echo "⚠️  VPC configuration not found. VPC must be configured first."
        echo ""
        read -p "Do you want to create VPC infrastructure now? (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Running VPC setup..."
            ./scripts/setup-vpc.sh
        else
            echo "❌ VPC setup cancelled. Please run './scripts/setup-vpc.sh' before deploying."
            exit 1
        fi
    else
        echo "✅ VPC configuration found (vpc-config.env)"
        source vpc-config.env
        echo "   VPC ID: $VPC_ID"
        echo "   Private Subnets: $PRIVATE_SUBNET_1, $PRIVATE_SUBNET_2"
    fi
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
# STEP 2 — Read AGENT ARN from agentcore status
###############################################
echo "Reading Agent ARN from agentcore status..."

# Extract Agent ARN from status output (removing box formatting characters and spaces)
AGENT_ARN=$(uv run agentcore status | grep "Agent ARN:" | sed 's/.*Agent ARN: //' | sed 's/│//g' | xargs)

echo "Agent ARN: $AGENT_ARN"

###############################################
# STEP 3 — Update server .env
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
# STEP 6 — Display log-tailing command
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
echo "2. Open browser: http://localhost:7860"
if [ "$NETWORK_MODE" = "VPC" ]; then
    echo "3. Test WebRTC connection through VPC with TURN relay"
else
    echo "3. Test WebRTC connection with TURN relay"
fi