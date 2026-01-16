# Server

This server provides a `/start` endpoint that generates WebSocket URLs for connecting to the agent running on Amazon Bedrock AgentCore.

## Prerequisites

Before deploying your agent, configure your environment variables:

1. Copy the environment example file:

   ```bash
   cp env.example .env
   ```

2. Edit `.env` and fill in your AWS credentials and configuration:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`

## Setup

Install dependencies:

```bash
uv sync
```

## Running the Server

Start the server on port 7860:

```bash
uv run server.py
```

The server will be available at `http://localhost:7860`.

## Running the Server in Local Agent Mode

If you want to test a locally-running agent (reachable at "ws://localhost:8080/ws"), start the server like this:

```bash
LOCAL_AGENT=1 uv run server.py
```

## Endpoint

### POST /start

Returns a WebSocket URL for the client to connect to the agent running on Amazon Bedrock AgentCore.

**Response:**

```json
{
  "ws_url": "wss://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/..."
}
```
