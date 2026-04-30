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
# fill in OPENAI_API_KEY and BANDWIDTH_*
```

## Local development

1. **Start ngrok** in a separate terminal:

   ```sh
   ngrok http 7860
   ```

2. **Configure your Voice Application** in the Bandwidth dashboard (or via the
   `band` CLI) so its `CallInitiatedCallbackUrl` points at the ngrok HTTPS
   URL (e.g. `https://your-subdomain.ngrok-free.app/`). The bot's runner
   serves the BXML response from the root path. Make sure the phone number's
   VCP references that voice application.

3. **Run the bot**:

   ```sh
   uv run bot.py -t bandwidth -x your-subdomain.ngrok-free.app
   ```

   The runner starts a FastAPI server on port 7860 and routes Bandwidth's
   inbound webhook + media-stream WebSocket to the bot.

4. **Call your Bandwidth number.** The bot will greet you. The pipeline is
   tuned for sub-second turn-around once the OpenAI sessions warm up; the
   first response after process start takes ~3 seconds while sessions
   initialize.

## How it works

The Pipecat runner provides the FastAPI server, the BXML response endpoint,
and the WebSocket endpoint. `bot.py` only contains the bot logic:

1. Bandwidth POSTs to `/` when a call comes in. The runner returns BXML that
   opens a bidirectional WebSocket back to `/ws`:

   ```xml
   <Response>
     <StartStream destination="wss://<ngrok>/ws" mode="bidirectional" tracks="inbound"/>
     <Pause duration="86400"/>
   </Response>
   ```

2. Bandwidth opens the WebSocket. The runner calls `bot(runner_args)`; we
   call `parse_telephony_websocket` to extract `streamId` / `callId` /
   `accountId` from the first `start` event, instantiate
   `BandwidthFrameSerializer`, wire it to a `FastAPIWebsocketTransport`, and
   run the Pipecat pipeline:

   ```
   WebSocket → STT → LLMUserAggregator → LLM → TTS → WebSocket → LLMAssistantAggregator
   ```

3. When the caller hangs up, the serializer terminates the call via the
   Bandwidth Voice API (OAuth client_credentials → Bearer →
   `POST /accounts/{id}/calls/{id}` with `state: completed`).

## Audio quality

The default uses PCMU 8 kHz on the wire (matches Twilio/Telnyx parity). To
take advantage of Bandwidth's higher-fidelity PCM outbound, pass
`outbound_encoding="PCM"` and `outbound_pcm_sample_rate=24000` to
`BandwidthFrameSerializer`.
