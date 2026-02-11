# Opik Tracing for Pipecat

This demo showcases OpenTelemetry tracing integration for Pipecat services using Opik, allowing you to visualize and analyze LLM traces, service calls, performance metrics, and dependencies.

> **Note**: Opik supports HTTP/JSON OpenTelemetry traces only (no logs or metrics).

## Setup Instructions

### 1. Get Your Opik API Key

Sign up or log in at [https://www.comet.com/opik](https://www.comet.com/opik) to get your API key and workspace name.

### 2. Environment Configuration

Create a `.env` file with your API keys and Opik configuration:

```
# Enable tracing
ENABLE_TRACING=true

# OTLP endpoint (defaults to Opik Cloud if not set)
OTEL_EXPORTER_OTLP_ENDPOINT=https://www.comet.com/opik/api/v1/private/otel/v1/traces

# Opik headers - Configure your API key, workspace, and project name
OTEL_EXPORTER_OTLP_HEADERS=Authorization=your_opik_api_key,Comet-Workspace=your_workspace_name,projectName=your_project_name

# Optional: Enable console output for debugging
# OTEL_CONSOLE_EXPORT=true

# Service API keys
DEEPGRAM_API_KEY=your_key_here
CARTESIA_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

For self-hosted Opik installations, update the endpoint:
```
OTEL_EXPORTER_OTLP_ENDPOINT=http://<YOUR-OPIK-INSTANCE>/api/v1/private/otel/v1/traces
```

### 3. Install Dependencies

```bash
uv sync
```

> **Important**: Use the HTTP exporter (`opentelemetry-exporter-otlp-proto-http`), not the GRPC exporter. Opik only supports HTTP transport.

### 4. Run the Demo

```bash
uv run bot.py
```

### 5. View Traces in Opik

Open your browser to [https://www.comet.com/opik](https://www.comet.com/opik) and navigate to your project to view traces and analyze your LLM interactions.

## Opik-Specific Configuration

In the `bot.py` file, note the HTTP exporter configuration:

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# Create the exporter for Opik (HTTP/JSON only)
# Headers are configured via OTEL_EXPORTER_OTLP_HEADERS environment variable
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "https://www.comet.com/opik/api/v1/private/otel/v1/traces"
    ),
)

# Set up tracing with the exporter
setup_tracing(
    service_name="pipecat-demo",
    exporter=otlp_exporter,
    console_export=bool(os.getenv("OTEL_CONSOLE_EXPORT")),
)
```

The OpenTelemetry SDK automatically reads headers from the `OTEL_EXPORTER_OTLP_HEADERS` environment variable.

## Key Features

- **HTTP/JSON Transport**: Opik uses HTTP transport for OpenTelemetry traces
- **LLM-Focused**: Optimized for tracking and analyzing LLM interactions
- **Required Headers**: 
  - `Authorization`: Your Opik API key
  - `projectName`: Your project name in Opik
  - `Comet-Workspace`: Your workspace name (required for Comet-hosted installations)

## Troubleshooting

- **No Traces in Opik**: Verify your API key, workspace name, and project name are correct
- **Authorization Errors**: Ensure your `OPIK_API_KEY` and `OPIK_WORKSPACE` are set correctly
- **Connection Errors**: Check your network connectivity and endpoint URL
- **Exporter Issues**: Try the Console exporter (`OTEL_CONSOLE_EXPORT=true`) to verify tracing works locally

## References

- [Opik Documentation](https://www.comet.com/docs/opik)
- [Opik OpenTelemetry Integration Guide](https://www.comet.com/docs/opik/integrations/opentelemetry)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
