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

## Call Recordings

Each call's audio is attached to its trace, giving two levels of playback in the Langfuse UI:

- **The whole call**, on the trace root — stereo, with the user on the left channel and the bot on the right, so barge-in stays audible.
- **Each turn**, on that turn's `turn` span — the user's speech as the span's `input`, the bot's reply as its `output`.

Langfuse media travels over the REST media API rather than OTLP, and is linked to a trace by id. Everything uploads after the pipeline shuts down, so recording adds nothing to the latency of the call itself.

`langfuse_recording.py` holds the whole integration. Pipecat reports each turn's audio with the turn number attached, so what's left here is the Langfuse upload and you can lift the file into your own bot:

```python
audiobuffer = AudioBufferProcessor(
    num_channels=2, enable_turn_audio=True, auto_start_recording=True
)
# ...place audiobuffer in the pipeline, after transport.output()...

recorder = LangfuseRecorder.from_env()
if recorder:
    recorder.attach(audiobuffer, worker)
```

Then stop the recording while the pipeline is still alive, and upload once it isn't:

```python
@transport.event_handler("on_client_disconnected")
async def on_client_disconnected(transport, client):
    if recorder:
        await recorder.stop_and_collect()
    await worker.cancel()

await runner.run()

if recorder:
    await recorder.upload()
```

Things worth knowing before running this against a real project:

- **Credentials come from the OTLP config by default.** Langfuse authenticates its OTLP endpoint with HTTP Basic over the same key pair the REST API wants, so the recorder reads the keys out of `OTEL_EXPORTER_OTLP_HEADERS` and the host out of `OTEL_EXPORTER_OTLP_ENDPOINT`. Media and spans therefore reach the same project by construction. Setting `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` overrides that, and then it's on you to keep them pointed at the same project — mismatched keys give a 401 on upload while traces keep working, since OTLP authenticates separately.
- **Per-turn clips are capped** at `MAX_TURN_CLIPS` (40) to stay under Langfuse's API rate limit — 30/min on Hobby, 100/min on Core. A longer call keeps its whole-call recording and the first 40 turns of clips. Raise the cap when self-hosting.
- **The whole-call recording is capped** at `MAX_RECORDING_BYTES` (100MB, roughly 20 minutes of stereo 24kHz). Past that the upload is truncated and the recorder says so.
- **Turn 1 begins when the pipeline starts**, not when the user first speaks, so a bot greeting is filed under turn 1 alongside whatever the user says next.

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

## Troubleshooting

- **No Traces in Langfuse**: Ensure that your credentials are correct and follow this [troubleshooting guide](https://langfuse.com/faq/all/missing-traces)
- **Connection Errors**: Verify network connectivity to Langfuse
- **Authorization Issues**: Check that your base64 encoding is correct and the API keys are valid

## References

- [Langfuse OpenTelemetry Documentation](https://langfuse.com/docs/opentelemetry/get-started)
