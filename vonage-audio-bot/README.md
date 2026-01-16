# Vonage Audio Bot (Pipecat)

This project demonstrates how to connect [Vonage Audio Connector](https://developer.vonage.com/en/video/guides/audio-connector) to a Pipecat-powered conversational bot over WebSockets using FastAPI.

It enables real-time bidirectional audio streaming between a Vonage Video API session and an AI voice pipeline (STT → LLM → TTS), with correct telephony-grade audio framing.

## How It Works

When you want to stream audio from Vonage Session into your bot:
 
1. **Vonage Tokbox Account is needed:** User needs account on Vonage Tokbox and create the project along with API Key and Secret - [Vonage Tokbox](https://tokbox.com/account/#/)
2. **Vonage session created:**: A Vonage Video API session already exists. Session can be created using [playground](https://tokbox.com/developer/tools/playground/)
3. **Trigger audio bridge:** Send POST `/connect` to attach the Audio Connector
4. **Audio Connector connects:** Vonage opens a WebSocket connection to `/ws`
5. **Bot starts processing:** Incoming audio is fed into the Pipecat pipeline on Websocket Server
6. **Bidirectional audio stream:** Bot responses are streamed back into the live session
7. **Call lifecycle managed:** Streaming continues until the session or WebSocket ends

## Architecture

```
Vonage Video Session
        |
        |  (Audio Connector)
        v
POST /connect  ─────────▶ Vonage Cloud
                             |
                             |  wss://.../ws
                             v
                    FastAPI WebSocket (/ws)
                             |
                             v
                        Pipecat Pipeline
                  STT → LLM → TTS → Audio

```

`/connect`
Triggers Vonage to connect the Audio Connector to your WebSocket.

`/ws`
Receives and sends raw PCM audio frames to/from Pipecat.

## Prerequisites

### Vonage (Opentok / Video API)

- A Vonage (Opentok / Video API) account with:
- A Vonage Video API project with either:
  - Vonage account credentials
    - Project Application ID
    - Project Private Key file
  - Opentok / Nexmo account credentials
    - Project API Key
    - Project Secret
- A routed Vonage session
- Session can be created via:
  - TokBox Playground
  - Vonage Video API SDKs

### AI Services

- OpenAI API key for the LLM inference
- OpenAI API key for speech-to-text
- OpenAI API key for text-to-speech

### System

- Python 3.10+
- `uv` package manager
- ngrok (for local development)

## Setup

1. Set up a virtual environment and install dependencies:

```bash
uv sync
```

2. Get your Vonage (TokBox) credentials:

From your **Opentok (TokBox) dashboard:**
- Project API Key and Secret
  - Select your project on [Vonage Opentok](https://tokbox.com/account/#/)
OR
From your **Vonage Video API dashboard:**
- Project Application ID and Private Key file
  - Select your project on [Vonage Video API](https://developer.vonage.com/en/video/getting-started)

- Session ID
  - Create a routed session using:
    - TokBox Playground
    - or Vonage Video API SDKs

**Note:** This project assumes the session already exists.
The server does not create sessions automatically.

3. Set up environment variables:

```bash
cp env.example .env
# Edit .env with your API keys, Secret, etc.
# Replace <your-ngrok-domain> with the actual domain provided by ngrok
```

## Environment Configuration

### Local Development

- Uses your local server or ngrok URL for WebSocket connections
- Default configuration for development and testing
- WebSocket connections go directly to your running server

## Local Development

1. Start the outbound bot server:

   ```bash
   uv run server.py
   ```

The server will start on port 8005.

2. Using a new terminal, expose your server to the internet (for development)

   ```bash
   ngrok http 8005
   ```

   Copy the ngrok URL (e.g., `https://abc123.ngrok.io`) and convert it to a secure WebSocket URL by updating `.env` as `WS_URI=wss://abc123.ngrok.io/ws`

3. Verify configuration

Before continuing, ensure:
- server.py is running
- ngrok is active
- .env contains correct Project API keys, Secret and WS URI

### Connect Request

With the server running and exposed via ngrok, you can initiate connect request from another terminal:

```bash
curl -X POST http://localhost:8005/connect
```

Once connected, Vonage will create a virtual participant in the session and you will hear the AI’s voice responses streamed in real time into the live audio session.
