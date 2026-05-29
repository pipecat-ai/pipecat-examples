# Gradium Starters

A voice-based conversational agent built with [Pipecat](https://pipecat.ai/), powered by [Gradium](https://gradium.ai/) for speech and OpenAI for the language model. Connect from a browser or receive calls through WhatsApp.

## Features

- **Real-time voice conversations** powered by:
  - [Gradium](https://gradium.ai/) — Speech-to-Text and Text-to-Speech
  - [OpenAI](https://openai.com) — Language Model
- **Voice selector** — choose from available Gradium voices before connecting
- **WhatsApp calling** — receive voice calls through WhatsApp Business
- **Pipecat Cloud** deployment with one command

## Prerequisites

### Environment

- Python 3.11 or later
- Node.js 18 or later
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager

### Service API keys

- [Gradium](https://gradium.ai/) — STT and TTS
- [OpenAI](https://platform.openai.com/) — LLM

> For WhatsApp calling you will also need a [WhatsApp Business](https://business.whatsapp.com/) account and a registered phone number.

## Setup

### 1. Configure the server

```bash
cd server
cp env.example .env
```

Edit `.env` and fill in your API keys:

```ini
GRADIUM_API_KEY=your_gradium_api_key
OPENAI_API_KEY=your_openai_api_key
```

Install dependencies:

```bash
uv sync
```

### 2. Configure the client

```bash
cd client
cp env.example .env.local
npm install
```

Leave `VITE_BOT_START_URL` and `VITE_BOT_START_PUBLIC_API_KEY` blank for local development — the client proxies requests to the local bot server automatically.

## Run Locally

### Start the bot server

```bash
cd server
uv run bot.py
```

> First run note: startup may take ~20 seconds as Pipecat downloads required models.

### Start the client

```bash
cd client
npm run dev
```

Open **http://localhost:5173**, select a voice from the dropdown, and click **Connect** to start talking.

## Testing with WhatsApp

To test WhatsApp calling locally you need to expose your bot server using a tunneling tool like [ngrok](https://ngrok.com/).

1. **Expose your local server:**

   ```bash
   ngrok http --domain=YOUR_NGROK_DOMAIN http://localhost:7860
   ```

2. **Start the bot with WhatsApp transport:**

   ```bash
   cd server
   uv run bot.py --whatsapp
   ```

3. **Set your WhatsApp webhook** to:

   ```
   https://YOUR_NGROK_DOMAIN/whatsapp
   ```

   > Always include the `/whatsapp` path at the end of the URL.

4. **Configure your webhook** in your WhatsApp Business account by following the [Pipecat WhatsApp guide](https://docs.pipecat.ai/guides/features/whatsapp#2-configure-webhook).

Once configured, make a WhatsApp voice call to your registered business number — the bot will answer automatically.

## Deploy to Pipecat Cloud

Pipecat Cloud handles scaling, monitoring, and global deployment.

### Prerequisites

1. [Sign up for Pipecat Cloud](https://pipecat.daily.co/sign-up).

2. Log in with the `pipecatcloud` CLI:

   ```bash
   cd server
   uv run pcc auth login
   ```

### Configure your deployment

The `server/pcc-deploy.toml` file controls your deployment:

```toml
agent_name = "gradium-web-bot"
secret_set = "gradium-web-bot-secrets"
agent_profile = "agent-1x"

[scaling]
    min_agents = 1
```

### Upload secrets

```bash
cd server
uv run pcc secrets set gradium-web-bot-secrets --file .env
```

### Deploy

```bash
cd server
uv run pcc deploy
```

### Connect the client to Pipecat Cloud

After deploying, get your agent's start URL and public API key from the Pipecat Cloud dashboard, then update `client/.env.local`:

```ini
VITE_BOT_START_URL=https://api.pipecat.daily.co/v1/public/agents/YOUR_AGENT_NAME/start
VITE_BOT_START_PUBLIC_API_KEY=your_pipecat_cloud_public_api_key
```

Rebuild the client:

```bash
cd client
npm run build
```

## Configure WhatsApp Webhook for Production

Before receiving WhatsApp calls in production, configure your webhook using your Pipecat Cloud organization and agent names:

```
https://api.pipecat.daily.co/v1/public/webhooks/$ORGANIZATION_NAME/$AGENT_NAME/whatsapp
```

Follow the official [Pipecat WhatsApp guide](https://docs.pipecat.ai/pipecat-cloud/guides/whatsapp#configure-webhook-for-pipecat-cloud) for step-by-step instructions.

## What's Next?

- **Customize your bot**: Edit `server/bot.py` to change personality, add tools, or integrate with your data
- **Add voices**: Update the `VOICES` list in `client/src/index.tsx` with additional Gradium voice IDs
- **Learn more**: Check out the [Pipecat docs](https://docs.pipecat.ai/) for advanced features
- **Explore Gradium**: See the [Gradium API docs](https://docs.gradium.ai/) for available voices and languages
- **Get help**: Join [Pipecat's Discord](https://discord.gg/pipecat) to connect with the community
