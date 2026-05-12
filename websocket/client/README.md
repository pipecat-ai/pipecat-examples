# WebSocket Client

Browser client for the WebSocket voice agent. Built with TypeScript and the [Pipecat JS SDK](https://docs.pipecat.ai/client/js/introduction).

## Setup

### 1. Install dependencies

```bash
cd client
npm install
```

### 2. Configure environment

```bash
cp env.example .env
```

Edit `.env` based on where your bot is running.

#### Connecting to a local bot

```env
VITE_PIPECAT_BASE_URL=http://localhost:7860
VITE_PIPECAT_PUBLIC_API=
```

Start the bot server first — see the [server README](../README.md).

#### Connecting to Pipecat Cloud

```env
VITE_PIPECAT_BASE_URL=https://api.pipecat.daily.co/v1/public/<your-agent-name>
VITE_PIPECAT_PUBLIC_API=<your-public-api-key>
```

Your agent name and public API key are available in the [Pipecat Cloud dashboard](https://pipecat.daily.co).

### 3. Run the client

```bash
npm run dev
```

Open http://localhost:5173 in your browser and click **Connect**.
