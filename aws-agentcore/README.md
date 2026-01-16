# Amazon Bedrock AgentCore Example

This example demonstrates how to integrate an AgentCore-hosted agent into a Pipecat pipeline.

The pipeline looks like a standard Pipecat bot pipeline, but with an AgentCore agent taking the place of an LLM. User audio gets converted to text and sent to the AgentCore agent, which will try to do work on the user's behalf. Responses from the agent are streamed back and spoken. User and agent messages are recorded in a context object.

Note that unlike an LLM service found in a traditional Pipecat bot pipeline, the AgentCore agent by default does not receive the full conversation context after each user turn, only the last user message. It is up to the AgentCore agent to decide whether and how to manage its own memory (AgentCore includes memory capabilities).

## Prerequisites

- Accounts with:
  - AWS (with access to Bedrock AgentCore and Claude 3.7 Sonnet model)
  - Deepgram
  - Cartesia
  - Daily (optional)
- Python 3.10 or higher
- `uv` package manager

## Setup

### Install Dependencies

Install dependencies needed to run the Pipecat bot as well as the AgentCore CLI.

```bash
uv sync
```

This installs:

- **Pipecat** - The voice AI pipeline framework
- **Strands** - AWS's agentic framework (used in the code agent)
- **Bedrock AgentCore Starter Toolkit** - CLI tools for deploying agents
- **Strands Tools** - Pre-built tools like the Code Interpreter

### Set Environment Variables

Copy `env.example` to `.env` and fill in the values in `.env`.

```bash
cp env.example .env
```

**Do not worry** about `AWS_AGENT_ARN` yet. You'll obtain an agent ARN as part of the following steps, when you deploy your agent to AgentCore Runtime.

## Deploying Your Agent to AgentCore Runtime

Before you can run the Pipecat bot file, you need to deploy an agent to AgentCore Runtime. This example includes two agents:

- **Dummy agent** (`dummy_agent.py`) - Reports progress while pretending to carry out a relatively long-running task
- **Code agent** (`code_agent.py`) - An algorithmic-problem-solving agent built with Strands that can write and execute Python code to answer questions

### About the Code Agent

The code agent demonstrates how to use **Strands** (AWS's agentic framework) within AgentCore:

- Uses the **Strands Agent** with Claude 3.7 Sonnet model
- Includes the **AgentCore Code Interpreter** tool for executing Python code
- Streams responses in real-time for a conversational experience
- Designed for voice interaction with TTS-friendly output

Below we'll do a barebones walkthrough of deploying an agent to AgentCore Runtime. For a comprehensive guide to getting started with Amazon Bedrock AgentCore, including detailed setup instructions, see the [Amazon Bedrock AgentCore Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html).

### IAM Setup

Configure your IAM user with the necessary policies for AgentCore usage. Start with these:

- `BedrockAgentCoreFullAccess`
- A new policy (maybe named `BedrockAgentCoreCLI`) configured [like this](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html#runtime-permissions-starter-toolkit)

You can also choose to specify more granular permissions; see [Amazon Bedrock AgentCore docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html) for more information.

### Environment Setup

To simplify the remaining AgentCore deployment steps in this README, it's a good idea to export some AWS-specific environment variables:

```bash
export AWS_SECRET_ACCESS_KEY=...
export AWS_ACCESS_KEY_ID=...
export AWS_REGION=...
```

### Agent Configuration

Create a new AgentCore configuration.

```bash
cd agents
uv run agentcore configure -e code_agent.py
```

Follow the interactive prompts to complete the configuration. It's OK to just accept all defaults.

### Agent Deployment

Deploy your agent to AgentCore Runtime.

```bash
uv run agentcore launch
```

This step will spit out the agent ARN. Copy it and paste it in your `.env` file as your `AWS_AGENT_ARN` value.

The above is also the command you need to run after you've updated your agent code and need to redeploy.

### Validation

Try running your agent on AgentCore Runtime.

```bash
uv run agentcore invoke '{"prompt": "What is the meaning of life?"}'
```

### Obtaining Your Agent ARN at Any Point

Your agent status will include its ARN.

```bash
uv run agentcore status
```

## Running The Example

With your agent deployed to AgentCore, you can now run the example.

```bash
# Using SmallWebRTC transport
uv run bot.py

# Using Daily transport
uv run bot.py -t daily
```
