# Vonage Chatbot: Inbound

This project is a Pipecat-based chatbot that integrates with Vonage Voice API to handle inbound phone calls via WebSocket connections and provide real-time voice conversations.

> ⚠️ Important: Vonage WebSocket support (`/ws/vonage`) is not yet available on Pipecat Cloud.

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Configuration](#environment-configuration)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Customizing your Bot](#customizing-your-bot)
- [Server Guide](#server-guide)

## How It Works

When someone calls your Vonage number:

1. **Vonage requests NCCO**: Vonage sends a webhook request (GET or POST) to your configured Answer URL
2. **Server returns NCCO**: Your FastAPI server (`server.py`) responds with an NCCO (Nexmo Call Control Object) containing WebSocket connection details
3. **WebSocket connection established**: Vonage establishes a WebSocket connection to the URI specified in the NCCO
4. **Connection event**: Vonage sends a `websocket:connected` JSON event with audio format details (e.g., `audio/l16;rate=16000`)
5. **Audio streaming begins**:
   - Vonage sends **binary messages** containing the caller's voice (16-bit linear PCM audio)
   - Your bot processes the audio through the Pipecat pipeline (STT → LLM → TTS)
   - Your bot sends **binary messages** back with synthesized speech
6. **Control commands**: Your bot can send **text messages** (JSON) for control:
   - `{"action": "clear"}` - Stop audio playback immediately
   - `{"action": "notify", "payload": {...}}` - Request notification when audio finishes
7. **Call ends**: When the call ends, the WebSocket connection closes

### Protocol Details

The Vonage Voice API uses a **mixed-mode WebSocket protocol**:

- **Binary messages**: Raw 16-bit linear PCM audio data (no base64 encoding)
- **Text messages**: JSON for control commands and events
- **Sample rates**: 8kHz, 16kHz (recommended), or 24kHz
- **Channels**: Mono (1 channel)

### Flow Diagram

```
┌─────────┐         ┌─────────────┐         ┌──────────────┐         ┌─────────┐
│ Caller  │────────>│   Vonage    │────────>│ Your Server  │────────>│ Pipecat │
│         │  Dials  │   Number    │ Webhook │  (server.py) │ WebSocket│   Bot   │
└─────────┘         └─────────────┘         └──────────────┘         └─────────┘
                           │                        │                       │
                           │    1. POST /answer     │                       │
                           │───────────────────────>│                       │
                           │                        │                       │
                           │    2. NCCO (JSON)      │                       │
                           │<───────────────────────│                       │
                           │                        │                       │
                           │    3. WebSocket Connect (wss://...)            │
                           │────────────────────────────────────────────────>│
                           │                        │                       │
                           │    4. {"event": "websocket:connected"}         │
                           │────────────────────────────────────────────────>│
                           │                        │                       │
                           │    5. Binary Audio (caller voice)              │
                           │────────────────────────────────────────────────>│
                           │                        │                       │
                           │    6. Binary Audio (bot response)              │
                           │<────────────────────────────────────────────────│
                           │                        │                       │
```

## Prerequisites

### Vonage

- A Vonage account with:
  - A purchased phone number that supports voice calls

### AI Services

- Google API key for the LLM inference
- Deepgram API key for speech-to-text
- Cartesia API key for text-to-speech

### System

- Python 3.10+
- `uv` package manager
- ngrok (for local development)
- Docker (for production deployment)

## Setup

1. Set up a virtual environment and install dependencies:

   ```sh
   cd inbound
   uv sync
   ```

2. Create an .env file and add API keys:

   ```sh
   cp env.example .env
   ```

## Environment Configuration

The bot supports two deployment modes controlled by the `ENV` variable:

### Local Development (`ENV=local`)

- Uses your local server or ngrok URL for WebSocket connections
- Default configuration for development and testing
- WebSocket connections go directly to your running server

### Production (`ENV=production`)

- Uses Pipecat Cloud WebSocket URLs automatically
- Requires the agent name and organization name from your Pipecat Cloud deployment
- Set these when deploying to production environments
- WebSocket connections route through Pipecat Cloud infrastructure

## Local Development

### Configure Vonage

1. Start ngrok:
   In a new terminal, start ngrok to tunnel the local server:

   ```sh
   ngrok http 7860
   ```

   > Tip: Use the `--subdomain` flag for a reusable ngrok URL.

2. Configure your Vonage number:

   - Go to your Vonage Dashboard: https://dashboard.nexmo.com/
   - Navigate to Numbers > Your numbers
   - Click on your phone number
   - In the "Voice" section:
     - Set "Answer URL" to: `https://your-url.ngrok.io/answer`
     - Set HTTP method to **POST**
   - Click "Save"

   > **Note**: This example uses 16kHz audio for better AI/speech recognition quality.

### Run your Bot

The FastAPI server handles the webhook from Vonage and dynamically returns the NCCO:

```bash
uv run server.py
```

This will start the server on port 7860. The server provides:

- `/answer` endpoint (POST): Returns NCCO to Vonage
- `/ws` endpoint: WebSocket endpoint for audio streaming

In your Vonage Dashboard, set your Answer URL to:

```
https://your-url.ngrok.io/answer
```

### Call your Bot

Place a call to the number associated with your bot. The bot will answer and start the conversation.

## Production Deployment

Coming soon to Pipecat Cloud!
