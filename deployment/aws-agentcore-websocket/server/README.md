# Server

This server provides a `/start` endpoint that generates signed WebSocket URLs for connecting to the agent running on Amazon Bedrock AgentCore.

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
uv run python server.py
```

The server will be available at `http://localhost:7860`.

## Endpoint

### POST /start

Returns a signed WebSocket URL for the client to connect to the agent running on Amazon Bedrock AgentCore.

**Response:**

```json
{
  "ws_url": "wss://bedrock-agentcore.us-west-2.amazonaws.com/runtimes/..."
}
```
