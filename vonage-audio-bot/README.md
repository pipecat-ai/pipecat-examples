# Vonage Audio Bot (Pipecat)

This project demonstrates how to connect Vonage to a Pipecat-powered conversational bot over WebSockets using FastAPI. It supports **two modes**:

1. **Vonage Video API** — [Audio Connector](https://developer.vonage.com/en/video/guides/audio-connector) streams audio from a Video session into the bot
2. **Vonage Voice API** — Incoming phone calls connect directly to the bot via a linked number

Both modes use the same Pipecat pipeline (STT → LLM → TTS) with telephony-grade audio framing.

## How It Works

### Vonage Video API (Audio Connector)

When you want to stream audio between a Vonage Video session and your audio bot:

1. **Vonage Credentials:** Configure **either** a Vonage Video Application (Application ID + Private Key) **or** OpenTok API Key + Secret
2. **Vonage session created (pre-existing):**  
   A **routed** Vonage Video API session already exists.  
   This session can be created using:
   - [Vonage Video Playground](https://tools.vonage.com/video/playground)
   - [OpenTok Playground](https://tokbox.com/developer/tools/playground/)
   - Your own Video API SDK integration
3. **Trigger audio bridge:** Send POST `/connect` to attach the Audio Connector
4. **Audio Connector connects:** Vonage opens a WebSocket connection to `/ws`
5. **Bot starts processing:** Incoming audio is fed into the Pipecat pipeline on Websocket Server
6. **Bidirectional audio stream:** Bot responses are streamed back into the live session
7. **Call lifecycle managed:** Streaming continues until the session or WebSocket ends

### Vonage Voice API (Phone Calls)

When someone calls your linked Vonage phone number:

1. **Call arrives:** Vonage Voice API receives the call and sends `GET /answer` to your server
2. **NCCO returned:** Your server returns an NCCO that plays a message and connects to your WebSocket
3. **WebSocket connection:** Vonage connects to `wss://<your-server-domain>/ws` and streams audio bidirectionally
4. **Bot handles the call:** Pipecat processes the audio and streams responses back
5. **Events logged:** Vonage sends status events (answered, completed, etc.) to `POST /events`

See [Voice API call flow](https://developer.vonage.com/en/voice/voice-api/concepts/call-flow?source=voice) and [WebSocket tutorial](https://developer.vonage.com/en/tutorials/connect-to-a-websocket/introduction/python) for more details.

## Architecture

### Video API (Audio Connector)

```
Vonage Video Session
        |
        |  (Audio Connector)
        v
POST /connect  ─────────▶ Vonage Cloud
                             |
                             |  wss://<your-server-domain>/ws
                             v
                    FastAPI WebSocket (/ws)
                             |
                             v
                        Pipecat Pipeline
                  STT → LLM → TTS → Audio

```

### Voice API (Phone Calls)

```
Phone Call
        |
        |  (Voice API)
        v
GET /answer  ─────────▶ Vonage Cloud
                             |
                             |  wss://<your-server-domain>/ws
                             v
                    FastAPI WebSocket (/ws)
                             |
                             v
                        Pipecat Pipeline
                  STT → LLM → TTS → Audio

```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/connect` | POST | (Video API) Triggers Audio Connector to connect to your WebSocket |
| `/answer` | GET, POST | (Voice API) Vonage webhook — returns NCCO that connects call to `/ws` |
| `/events` | POST | (Voice API) Vonage webhook — receives call status events (log only) |
| `/ws` | WebSocket | Receives and sends raw PCM audio frames to/from Pipecat |

## Prerequisites

### Vonage Video API (choose one credential option)

This project supports **two** ways to authenticate with Vonage Video API. Configure **either** Option A **or** Option B in your `.env`.

#### Option A — Vonage Video Application (recommended)
Use a Vonage Video Application (Application ID + Private Key):

- `VONAGE_APPLICATION_ID`
- `VONAGE_PRIVATE_KEY`

#### Option B — OpenTok Project credentials (legacy)
Use OpenTok API Key + Secret:

- `OPENTOK_API_KEY`
- `OPENTOK_API_SECRET`

### Session
- `VONAGE_SESSION_ID`
- Session can be created using:
  - [Unified Video environment](https://tools.vonage.com/video/playground)
  - [Opentok environment](https://tokbox.com/developer/tools/playground/)

### Vonage Voice API (for phone call mode)

To receive incoming phone calls, you need:

- `WS_URI` — Public WebSocket URL (e.g. `wss://<your-server-domain>/ws`). For local development, this is commonly an ngrok URL.
- `VONAGE_VOICE_FROM_NUMBER` — Your linked Vonage number in E.164 format (e.g. `19045878905`)
- A Vonage Application with Voice capability, configured with:
  - **Answer URL:** `https://<your-server-domain>/answer` (HTTP GET)
  - **Event URL:** `https://<your-server-domain>/events` (HTTP POST)
- A phone number [purchased and linked](https://dashboard.vonage.com/numbers/your-numbers) to your Vonage Application

### AI Services
- `OPENAI_API_KEY` (used for STT, LLM inference and TTS in this example)

### System
- Python 3.10+
- `uv` package manager
- ngrok (for local development)

## Setup

1. Set up a virtual environment and install dependencies:

```bash
uv sync
```

2. Get your Vonage credentials (choose one):

**Option A — Vonage Video Application**
- Create/select a Vonage Video Application
- Copy:
  - Application ID → `VONAGE_APPLICATION_ID`
  - Private Key → `VONAGE_PRIVATE_KEY`

**Option B — OpenTok Project**
- From your OpenTok project:
  - API Key → `OPENTOK_API_KEY`
  - API Secret → `OPENTOK_API_SECRET`

**Session ID**
- Create a **routed** session and set:
  - `VONAGE_SESSION_ID`

**Note:** If using the Video Audio Connector, this project assumes the session already exists. The server does not create sessions automatically.

**Voice API (phone calls)**

- Create a Vonage Application with Voice capability
- Purchase a number at [dashboard.vonage.com/numbers/your-numbers](https://dashboard.vonage.com/numbers/your-numbers) and link it to your application
- In the application settings, set:
  - Answer URL: `https://<your-ngrok-domain>/answer` (HTTP GET)
  - Event URL: `https://<your-ngrok-domain>/events` (HTTP POST)
- Add to `.env`: `VONAGE_VOICE_FROM_NUMBER=19045878905` (your linked number, E.164 format)

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

2. Expose your server to the internet (for local development)

   ```bash
   ngrok http 8005
   ```

   Copy the ngrok URL (e.g., `https://abc123.ngrok.io`) and convert it to a secure WebSocket URL by updating `.env` as `WS_URI=wss://abc123.ngrok.io/ws`

3. Verify configuration

Before continuing, ensure:
- server.py is running
- ngrok is active
- .env contains correct Project API keys, Secret and WS URI

### Connect Request (Video API)

With the server running and exposed via ngrok, you can initiate connect request from another terminal:

```bash
curl -X POST http://localhost:8005/connect
```

Once connected, Vonage will create a virtual participant in the session and you will hear the AI’s voice responses streamed in real time into the live audio session.

### Voice API (Phone Call)

With the server running and publicly accessible:

1. Ensure your Vonage Application has Answer URL and Event URL pointing to the domain and routes of this server
2. Ensure `WS_URI` and `VONAGE_VOICE_FROM_NUMBER` are set in `.env`
3. Call your linked Vonage number from any phone

The call will be answered, you'll hear "Please wait while we connect you to the AI agent", and then the bot will start the conversation.
