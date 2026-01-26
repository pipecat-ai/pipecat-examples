# Gemini + Pipecat + Voice UI Kit Demo

This repository demonstrates how to wire up Google Gemini with Pipecat and the Pipecat Voice UI Kit, including optional screensharing and a resizable, log-aware UI, then deploy the agent to Pipecat Cloud.

## What this demo shows

- **Real-time conversation** powered by Gemini via Pipecat
- **Screensharing** (desktop) side-by-side with the conversation; stacked on narrow viewports
- **Resizable layout** using Voice UI Kit resizable panels and handles
- **Event logs panel** you can toggle and resize
- **One-click connect** to a Daily room for WebRTC transport

![Capture of the running demo](./capture.gif)

> The demo used [Snazzy Maps](https://snazzymaps.com/editor/customize/24088)

## Project structure

- `client/`: Next.js app with Voice UI Kit components and resizable layout
- `server/`: Python bot integrating Gemini with Pipecat

## Run locally

### Prerequisites

- Node.js 18+ and npm
- Python 3.10+ and [`uv`](https://github.com/astral-sh/uv)
- A Daily room URL
- Required API keys for the server bot (see `server/env.example`)

### 1. Start the server (Pipecat bot)

```bash
cd server
cp env.example .env
# Edit .env and set DAILY_SAMPLE_ROOM_URL
uv sync
uv run bot.py --transport daily
```

This starts the local WebRTC server. Keep it running.

### 2. Start the client (Next.js + Voice UI Kit)

```bash
cd client
cp env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000` and click Connect. You can share your screen (desktop), converse with the agent, toggle logs, and resize panels.

## Deploy to Pipecat Cloud

> **Important**: Since this demo sends video to the bot (for screensharing), it increases CPU usage significantly. Deployed agents should use the **agent-2x** profile, which is already configured in `server/pcc-deploy.toml`.

Follow the official quickstart to build and deploy a Docker image, configure secrets, and run your agent in production:

1. **Sign up** for [Pipecat Cloud](https://pipecat.daily.co) and set up Docker
2. **Configure** `server/pcc-deploy.toml` (agent name, image, scaling)
3. **Upload secrets** from your `.env`:

```bash
uv run pcc secrets set <your-secret-set> --file .env
```

4. **Build and deploy**:

```bash
uv run pcc docker build-push
uv run pcc deploy
```

5. **Update client config**: Set `BOT_START_URL` and `BOT_START_PUBLIC_API_KEY` in `client/.env.local` and connect from your [locally running](#2-start-the-client-nextjs--voice-ui-kit) client.

## Useful links

- Voice UI Kit docs: `https://voiceuikit.pipecat.ai/`
- Pipecat docs: `https://docs.pipecat.ai/`
- Daily docs: `https://docs.daily.co/`
- Gemini docs: `https://ai.google.dev/docs`
