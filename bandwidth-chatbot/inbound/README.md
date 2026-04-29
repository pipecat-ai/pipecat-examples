# Bandwidth Chatbot: Inbound

A Pipecat-based voice agent that answers inbound phone calls on a
[Bandwidth](https://www.bandwidth.com/) phone number. Uses Bandwidth's
bidirectional WebSocket media streaming via the BXML `<StartStream>` verb,
and OpenAI for the entire AI stack (Realtime STT + LLM + TTS).

## Prerequisites

### Bandwidth

- A Bandwidth account on the Universal Platform with **Media Streaming enabled**
  (it's an account-level add-on; check with your account rep if unsure).
- OAuth 2.0 API credentials (Client ID + Client Secret) — generate in the
  dashboard under API Credentials.
- A voice-capable phone number assigned to a Voice Configuration Package (VCP)
  whose linked voice application points its callback URL at this server.

### AI services

- An OpenAI API key. The example uses `OpenAIRealtimeSTTService`,
  `OpenAILLMService`, and `OpenAITTSService`. To swap in faster providers
  (Deepgram, Cartesia, etc.) for production-grade latency, edit `bot.py`.

### Local tooling

- Python 3.11+
- `uv` package manager
- `ngrok` (or any public-URL tunnel) for local development

## Setup

```sh
cd inbound
uv sync
cp env.example .env
# fill in OPENAI_API_KEY, BANDWIDTH_*, NGROK_PUBLIC_URL
```

## Local development

1. **Start ngrok** in a separate terminal:

   ```sh
   ngrok http 8000
   ```

   Copy the HTTPS forwarding URL into `NGROK_PUBLIC_URL` in your `.env`.

2. **Configure your Voice Application** in the Bandwidth dashboard (or via the
   `band` CLI) so its `CallInitiatedCallbackUrl` points at
   `https://<your-ngrok-host>/incoming-call`. Make sure the phone number's VCP
   references that voice application.

3. **Run the server**:

   ```sh
   uv run server.py
   ```

4. **Call your Bandwidth number.** The bot will greet you. The pipeline is
   tuned for sub-second turn-around once the OpenAI sessions warm up; the
   first response after process start takes ~3 seconds while sessions
   initialize.

## How it works

Two endpoints in `server.py`:

- `POST /incoming-call` — Bandwidth's voice app posts here on inbound calls.
  We respond with BXML opening a bidirectional media stream:

  ```xml
  <Response>
    <StartStream destination="wss://<ngrok>/ws" mode="bidirectional" tracks="inbound"/>
    <Pause duration="86400"/>
  </Response>
  ```

  The `<Pause>` keeps the call alive while the WebSocket runs.

- `WebSocket /ws` — Bandwidth opens this and starts streaming audio. We
  parse the first `start` event for `streamId` / `callId` / `accountId`,
  instantiate `BandwidthFrameSerializer`, wire it to a
  `FastAPIWebsocketTransport`, and run the Pipecat pipeline:

  ```
  WebSocket → STT → LLMUserAggregator → LLM → TTS → WebSocket → LLMAssistantAggregator
  ```

When the caller hangs up, the serializer terminates the call via the
Bandwidth Voice API (OAuth client_credentials → Bearer → `POST /accounts/{id}/calls/{id}` with `state: completed`).

## Audio quality

The default uses PCMU 8kHz on the wire (matches Twilio/Telnyx parity). To
take advantage of Bandwidth's higher-fidelity PCM outbound, pass
`outbound_encoding="PCM"` and `outbound_pcm_sample_rate=24000` to
`BandwidthFrameSerializer`.
