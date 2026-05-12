# WebSocket Voice Agent

A Pipecat example demonstrating a voice agent using WebSocket transport. The same `bot.py` runs locally for development and deploys directly to Pipecat Cloud.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Google API key (Gemini)

---

## Running Locally

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp env.example .env
```

Edit `.env` and set your `GOOGLE_API_KEY`.

### 3. Start the bot

```bash
uv run bot.py
```

This starts a local server at `http://localhost:7860`. When the client connects, it calls `POST /start` to allocate a session, then establishes the WebSocket.

### 4. Run the client

See the [client README](client/README.md).

---

## Deploying to Pipecat Cloud

`bot.py` is ready to deploy to [Pipecat Cloud](https://pipecat.cloud). The `pcc-deploy.toml` configures the agent name, secret set, and scaling.

### 1. Install the Pipecat CLI

```bash
uv tool install pipecat-ai-cli
```

### 2. Authenticate

```bash
pipecat cloud auth login
```

### 3. Upload secrets

Upload your `.env` as a named secret set. Pipecat Cloud injects these as environment variables at runtime:

```bash
pipecat cloud secrets set websocket-secrets --file .env
```

The secret set name `websocket-secrets` matches what is configured in `pcc-deploy.toml`.

### 4. Deploy

```bash
pipecat cloud deploy
```

This builds the Docker image, pushes it to Pipecat Cloud, and starts the agent.

### 5. Connect the client

Once deployed, point the client at your agent's public URL. See the [client README](client/README.md).
