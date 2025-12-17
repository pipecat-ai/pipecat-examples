#!/bin/bash

# Script to dynamically read all variables from .env file and launch agentcore
AGENT_ENV_FILE="./agent/.env"
SERVER_ENV_FILE="./server/.env"

###############################################
# STEP 1 — Launch the new agent
###############################################

# Check if the local .env file exists
if [ ! -f "$AGENT_ENV_FILE" ]; then
    echo "Error: $AGENT_ENV_FILE file not found"
    echo "Please create an agent .env file with your environment variables"
    exit 1
fi

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