# Amazon Bedrock AgentCore Runtime WebRTC Example

This example demonstrates how to deploy a Pipecat bot to **Amazon Bedrock AgentCore Runtime** using SmallWebRTC for communication.

## Prerequisites

- Accounts with:
  - AWS
  - Deepgram
  - Cartesia
- Python 3.10 or higher
- `uv` package manager

## Set Up the Environment

### IAM Configuration

Configure your IAM user with the necessary policies for AgentCore usage. Start with these:

- `BedrockAgentCoreFullAccess`
- A new policy (maybe named `BedrockAgentCoreCLI`) configured [like this](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html#runtime-permissions-starter-toolkit)

You can also choose to specify more granular permissions; see [Amazon Bedrock AgentCore docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html) for more information.

To authenticate with AWS, you have two options:

1. Export environment variables:

   ```bash
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_REGION=your_region
   export AWS_DEFAULT_REGION=your_default_region
   ```

2. Or use AWS CLI configuration:
   ```bash
   aws configure
   ```
   This will create/update your AWS credentials file (~/.aws/credentials).

### Virtual Environment Setup

Create and activate a virtual environment:

```bash
uv sync
```

### Environment Variables Configuration

1. For the agent:

   ```bash
   cd agent
   cp env.example .env
   ```

   Add your API keys:

   - `AWS_ACCESS_KEY_ID`: Your AWS access key ID for the Amazon Bedrock LLM used by the agent
   - `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key for the Amazon Bedrock LLM used by the agent
   - `AWS_REGION`: The AWS region for the Amazon Bedrock LLM used by the agent
   - `DEEPGRAM_API_KEY`: Your Deepgram API key
   - `CARTESIA_API_KEY`: Your Cartesia API key
   - `ICE_SERVER_URLS`: Your TCP TURN server urls
   - `ICE_SERVER_USERNAME`: Your TURN server username
   - `ICE_SERVER_CREDENTIAL`: Your TURN server credential

   > Important Notes about TURN Server Configuration:
   >
   > - You must use TURN servers that support TCP connections
   > - UDP connections are not supported within AgentCore runtime environment
   > - If your TURN server only supports UDP, your WebRTC connection will fail
   > - Consider using a service like Twilio's TURN servers which support TCP

2. For the server:
   ```bash
   cd server
   cp env.example .env
   ```
   The server configuration is minimal - the `AGENT_RUNTIME_ARN` will be automatically set during agent deployment.

## Agent Configuration

Configure your bot as an AgentCore agent:

```bash
./scripts/configure.sh
```

This script:

1. Configures deployment type as "Container" (required by Pipecat)
2. Applies necessary patches to the Dockerfile
3. Adds dependencies required by SmallWebRTC (`libgl1` and `libglib2.0-0`)

Follow the prompts to complete the configuration.

> Technical Note:
> Direct Code Deploy isn't used because some dependencies (like `numba`) lack `aarch64_manylinux2014` wheels.

## ⚠️ Before Proceeding

Just in case you've previously deployed other agents to AgentCore, ensure that you have the desired agent selected as "default" in the `agentcore` tool:

```
# Check
uv run agentcore configure list
# Set
uv run agentcore configure set-default <agent-name>
```

The following steps act on `agentcore`'s default agent.

## Deployment to AgentCore Runtime

Deploy your bot:

```bash
./scripts/launch.sh
```

This script:

1. Reads environment variables from `agent/.env`
2. Deploys to AgentCore
3. Updates the server's configuration with the agent ARN
4. Displays log-tailing commands for monitoring

## Running on AgentCore Runtime

1. Start the server:

   ```bash
   cd server
   uv run server.py
   ```

2. Access the UI:
   - Open http://localhost:7860 in your browser
   - Or use your configured custom port

## Monitoring and Troubleshooting

### View Agent Logs

Use the log-tailing command provided during deployment:

```bash
# Replace with your actual command
aws logs tail /aws/bedrock-agentcore/runtimes/bot1-0uJkkT7QHC-DEFAULT --log-stream-name-prefix "2025/11/19/[runtime-logs]" --follow
```

## Test Agent Manually

Test the agent using the AWS CLI:

```bash
uv run agentcore invoke \
  --session-id user-123456-conversation-12345679 \
  '{
  "sdp": "YOUR_OFFER",
  "type": "offer"
}'
```

> This will only allow you to see that the Pipecat agent has started, but you won’t be able to hear or send audio. So it is only useful for troubleshooting.

## Cleanup

Remove your agent:

```bash
./scripts/destroy.sh
```

## Local Development

Run your bot locally for testing:

```bash
PIPECAT_LOCAL_DEV=1 uv run pipecat-agent.py
```

## Additional Resources

- [Amazon Bedrock AgentCore Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [TURN Server Configuration Guide](https://webrtc.org/getting-started/turn-server)
