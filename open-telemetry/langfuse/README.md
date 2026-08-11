# Langfuse Tracing for Pipecat

This demo showcases [Langfuse](https://langfuse.com) tracing integration for Pipecat services via OpenTelemetry, allowing you to visualize service calls, performance metrics, and dependencies with a focus on LLM observability.

Pipecat trace in Langfuse:

https://github.com/user-attachments/assets/13dd7431-bf5e-42e3-8d6d-2ed84c51195d

## Setup Instructions

### 1. Create a Langfuse Project and get API keys

[Self-host](https://langfuse.com/self-hosting) Langfuse or create a free [Langfuse Cloud](https://cloud.langfuse.com) account.
Create a new project and get the API keys.

### 2. Environment Configuration

Base64 encode your Langfuse public and secret key:

```bash
echo -n "pk-lf-1234567890:sk-lf-1234567890" | base64
```

Create a `.env` file with your API keys to enable tracing:

```
ENABLE_TRACING=true
# OTLP endpoint for Langfuse
OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64_encoded_api_key>
# Set to any value to enable console output for debugging
# OTEL_CONSOLE_EXPORT=true

# Service API keys
DEEPGRAM_API_KEY=your_key_here
CARTESIA_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Optional: needed only to attach the call recording (see below)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 3. Set up a venv and install Dependencies

```bash
uv sync
```

> Install only the http exporter. If you have a conflict, uninstall the grpc exporter.

### 4. Run the Demo

```bash
uv run bot.py
```

### 5. View Traces in Langfuse

Open your browser to [https://cloud.langfuse.com](https://cloud.langfuse.com) to view traces.

## Langfuse-Specific Configuration

In the `bot.py` file, note the HTTP exporter configuration:

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# Create the exporter - configured from environment variables
otlp_exporter = OTLPSpanExporter()

# Set up tracing with the exporter
setup_tracing(
    service_name="pipecat-demo",
    exporter=otlp_exporter,
    console_export=bool(os.getenv("OTEL_CONSOLE_EXPORT")),
)
```

### Recording the conversation audio

Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` and the demo also
attaches the call audio to the trace, so you can listen while reading the spans. Leave them
unset and you get traces without audio.

You get audio at two levels:

- **The whole call**, on the trace root. Stereo, user on the left channel and bot on the
  right, so an interruption reads as overlap.
- **Each turn**, on that turn's `turn` span. The user's speech is filed as the span's
  **input** and the bot's reply as its **output**, so clicking a turn plays just that turn
  and you can hear each side separately.

Two credentials for one service looks odd, so here is why. Spans travel over OTLP, which
only needs the pre-encoded `OTEL_EXPORTER_OTLP_HEADERS`. Langfuse media does not travel
over OTLP: audio is uploaded through the REST API, and that call needs the keys unencoded.

The audio is captured by Pipecat's
[`AudioBufferProcessor`](https://docs.pipecat.ai/pipecat/fundamentals/recording-audio):

```python
# Stereo whole-call recording, plus a clip per speaker per turn.
audiobuffer = AudioBufferProcessor(
    num_channels=2,
    buffer_size=0,
    enable_turn_audio=True,
)

uploader = uploader_from_env() if IS_TRACING_ENABLED else None
if uploader:
    # The turn tracker numbers the turns, which is how each clip finds its span.
    uploader.attach(audiobuffer, turn_tracker=worker.turn_tracking_observer)

# ...placed after transport.output() in the pipeline...

@transport.event_handler("on_client_connected")
async def on_client_connected(transport, client):
    await audiobuffer.start_recording()
```

Four details in `langfuse_media.py` are worth knowing if you adapt this:

- **The processor sits after `transport.output()`**, so it records what was actually
  played. Bot speech cut short by an interruption is captured as truncated, matching what
  the user heard.
- **Nothing is written into the span payload.** Langfuse renders a player from the media
  link alone, so a clip only needs the trace id, and for per-turn audio the turn's span id.
  Those ids outlive the spans, which is why all uploading happens after the pipeline has
  shut down and a slow upload never delays teardown.
- **Per-turn uploads are capped** at `max_turn_clips` turns (40 by default). Each clip costs
  two calls against Langfuse's general API rate limit, which is 30/min on Hobby and 100/min
  on Core, so a very long call degrades to "the first N turns have audio" instead of a wall
  of 429s. A 429 is retried once using `Retry-After`.
- **The recording is capped** at 100MB of audio and truncated with a warning past that.
  Stereo 24kHz 16-bit is roughly 350MB per hour, so a long-running agent would otherwise
  grow without bound.

### Running the audio eval

The bot exposes an `eval` transport, so Pipecat's eval harness can drive it with
synthesized speech and judge the result. This is the quickest way to check that the
recording still works after a change.

`--trigger-disconnect` is required: the upload happens in `on_client_disconnected`, so
without it the recording is never finalized.

```bash
# Terminal 1: the bot, with tracing enabled so a real upload happens
uv run bot.py -t eval --port 7860

# Terminal 2: from a pipecat checkout
uv run pipecat eval run scripts/release-evals/scenarios/interruption_audio.yaml \
  --bot-url ws://localhost:7860 \
  -a -v --trigger-disconnect \
  --record-dir /tmp/langfuse-eval-recordings -t 90
```

The eval writes its own copy of the recording to `--record-dir`, which is handy as a
reference to compare against the audio that landed on the trace. `interruption_audio`
is the interesting scenario because it barges in on the bot. Requires
`pipecat-ai[evals]` and a judge (Ollama serving `gemma4:12b` by default).

## Troubleshooting

- **No Traces in Langfuse**: Ensure that your credentials are correct and follow this [troubleshooting guide](https://langfuse.com/faq/all/missing-traces)
- **Connection Errors**: Verify network connectivity to Langfuse
- **Authorization Issues**: Check that your base64 encoding is correct and the API keys are valid
- **`Failed to export span batch code: 401`**: check that the space in
  `OTEL_EXPORTER_OTLP_HEADERS` is written as `%20`, not as a literal space. Header values in
  that variable are URL encoded per the OTLP spec, and a literal space makes the SDK discard
  the header without sending it, which Langfuse answers with a 401.
- **Traces but no audio player**: `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` are probably unset. The bot logs `Langfuse recording disabled` at startup when that is the case, and `Langfuse recording attached: mediaId=...` on success.
- **Traces and an upload log, but still no player**: make sure `LANGFUSE_HOST` and
  `OTEL_EXPORTER_OTLP_ENDPOINT` name the same region. Mixing EU and US puts the audio in one
  project and the trace in another. The bot warns about this at startup.
- **Whole-call audio but no per-turn audio**: the processor needs `enable_turn_audio=True`
  and the uploader needs the turn tracker, otherwise there is no way to match a clip to its
  span. The bot logs `no turn tracker, per-turn audio disabled` in that case.
- **A just-finished trace 404s in the UI**: give it a minute. The API returns the trace
  immediately, but the trace view can lag behind ingestion.

## References

- [Langfuse OpenTelemetry Documentation](https://langfuse.com/docs/opentelemetry/get-started)
- [Langfuse Multi-Modality (media attachments)](https://langfuse.com/docs/observability/features/multi-modality)
- [Pipecat: Recording Conversation Audio](https://docs.pipecat.ai/pipecat/fundamentals/recording-audio)
