# Amazon Bedrock AgentCore Runtime WebSocket Example

This example demonstrates how to deploy a Pipecat bot to **Amazon Bedrock AgentCore Runtime** using WebSockets for communication.

## Prerequisites

- Accounts with:
  - AWS
  - Deepgram
  - Cartesia
- Python 3.10 or higher
- `uv` package manager

## Environment Setup

### IAM Configuration

Configure your IAM user with the necessary policies for AgentCore usage. Start with these:

- `BedrockAgentCoreFullAccess`
- A new policy (maybe named `BedrockAgentCoreCLI`) configured [like this](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html#runtime-permissions-starter-toolkit)

You can also choose to specify more granular permissions; see [Amazon Bedrock AgentCore docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html) for more information.

### Environment Variable Setup

1. For managing (configuring, deploying, etc.) the bot:

   Either export your AWS credentials and configuration as environment variables:

   ```bash
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_ACCESS_KEY_ID=...
   export AWS_REGION=...
   ```

   Or use AWS CLI configuration:

   ```bash
   aws configure
   ```

2. For the bot itself:

   ```bash
   cp env.example .env
   ```

   Add your API keys:

   - `OPENAI_API_KEY`: Your OpenAI API key
   - `DEEPGRAM_API_KEY`: Your Deepgram API key
   - `CARTESIA_API_KEY`: Your Cartesia API key

3. For the server:

   ```bash
   cd server
   cp env.example .env
   ```

   Add your AWS credentials and configuration:

   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`

### Virtual Environment Setup

Create and activate a virtual environment:

```bash
uv sync
```

## Agent Configuration

Configure your bot as an AgentCore agent:

```bash
uv run agentcore configure -e bot.py
```

Follow the prompts to complete the configuration. It's fine to just accept all defaults.

## ⚠️ Before Proceeding

Just in case you've deployed multiple agents to AgentCore or deployed agents under multiple names, ensure that you have the desired agent selected as "default" in the `agentcore` tool:

```
# Check
uv run agentcore configure list
# Set
uv run agentcore configure set-default <agent-name>
```

The following steps act on `agentcore`'s default agent.

## Deploying to AgentCore

Deploy your configured bot to Amazon Bedrock AgentCore Runtime for production hosting.

```bash
./scripts/launch.sh
```

You should see commands related to tailing logs printed to the console. Copy and save them for later use.

This is also the command you need to run after you've updated your bot code.

## Running the Server

The server provides a `/start` endpoint that generates signed WebSocket URLs for the client.

See [the server README](./server/README.md) for setup and run instructions.

## Running the Client

Once the server is running, you can run the client to connect to your AgentCore-hosted bot.

See [the client README](./client/README.md) for setup and run instructions.

## Observation

Paste one of the log tailing commands you received when deploying your bot to AgentCore Runtime. It should look something like:

```bash
# Replace with your actual command
aws logs tail /aws/bedrock-agentcore/runtimes/bot1-0uJkkT7QHC-DEFAULT --log-stream-name-prefix "2025/11/19/[runtime-logs]" --follow
```

If you don't have that command handy, no worries. Just run:

```bash
uv run agentcore status
```

## Agent Deletion

Delete your bot from AgentCore:

```bash
uv run agentcore destroy
```

## Additional Resources

For a comprehensive guide to getting started with Amazon Bedrock AgentCore, including detailed setup instructions, see the [Amazon Bedrock AgentCore Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html).
