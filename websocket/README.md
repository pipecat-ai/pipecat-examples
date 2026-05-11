# Voice Agent

A Pipecat example demonstrating the simplest way to create a voice agent using `WebsocketTransport`.

## 🚀 Quick Start

### 1️⃣ Start the Bot Server

#### 🔧 Set Up the Environment

1. Navigate to the server directory:

   ```bash
   cd server
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Configure environment variables:
   ```bash
   cp env.example .env
   ```
   - Add your API keys
   - Choose what you wish to use: 'fast_api' or 'websocket_server'

#### ▶️ Run the Server

```bash
uv run server.py
```

### 3️⃣ Connect Using a Custom Client App

For client-side setup, refer to the:

- [Typescript Guide](client/README.md).

## ⚠️ Important Note

Ensure the bot server is running before using any client implementations.

## 📌 Requirements

- Python **3.10+**
- Node.js **16+** (for JavaScript components)
- Google API Key

---

### 💡 Notes

- Ensure all dependencies are installed before running the server.
- Check the `.env` file for missing configurations.

Happy coding! 🎉

## Deploying to Pipecat Cloud

`bot.py` is ready to deploy to [Pipecat Cloud](https://pipecat.cloud).
The project includes a`pcc-deploy.toml` that Pipecat Cloud uses to build and run the bot.

### Prerequisites

- A [Pipecat Cloud](https://pipecat.cloud) account
- Both SageMaker endpoints (`SAGEMAKER_ASR_ENDPOINT_NAME`, `SAGEMAKER_MAGPIE_ENDPOINT_NAME`) deployed and `InService`

### Step 1 — Install the Pipecat CLI

```bash
uv tool install pipecat-ai-cli
```

### Step 2 — Authenticate

```bash
pipecat cloud auth login
```

### Step 3 — Install dependencies

```bash
uv sync
```

### Step 4 — Upload secrets

Upload your `.env` as a named secret set. Pipecat Cloud injects these as
environment variables at runtime:

```bash
pipecat cloud secrets set websocket-secrets --file .env
```

The secret set name `websocket-secrets` matches what is configured in
`pcc-deploy.toml`.

### Step 5 — Deploy

```bash
pipecat cloud deploy
```

This builds the Docker image, pushes it to Pipecat Cloud, and starts the agent.
The `pcc-deploy.toml` configures the agent name, secret set, and scaling:

```toml
agent_name = "websocket-example"
secret_set = "websocket-secrets"
agent_profile = "agent-1x"

[scaling]
    min_agents = 1
```

### Step 6 — Connect

Go to the [Pipecat Cloud Dashboard](https://pipecat.daily.co/) → your agent →
**Sandbox** → **Connect** to open a browser-based call with the bot.