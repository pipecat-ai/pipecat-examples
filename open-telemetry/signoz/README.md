# PipeCat Monitoring with SigNoz

This demo shows [SigNoz](https://signoz.io/) observability integration with Pipecat via OpenTelemetry, allowing you to visualize traces, logs, and metrics from your Pipecat application usage. 

## Setup Instructions

### Step 1: Clone this demo voice agent project and setup dependencies

```bash
git clone https://github.com/pipecat-ai/pipecat-examples.git
cd pipecat-examples/open-telemetry/signoz
uv sync
```
### Step 2: Setup Credentials

Copy .env.example to .env and filling in the required keys:

- `DEEPGRAM_API_KEY`
- `OPENAI_API_KEY`
- `CARTESIA_API_KEY`


### Step 3: Add Automatic Instrumentation

```bash
uv pip install opentelemetry-distro opentelemetry-exporter-otlp
uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement -
```

### Step 4: Run your application with auto-instrumentation


```bash
OTEL_RESOURCE_ATTRIBUTES="service.name=<service_name>" \
OTEL_EXPORTER_OTLP_ENDPOINT="https://ingest.<region>.signoz.cloud:443" \
OTEL_EXPORTER_OTLP_HEADERS="signoz-ingestion-key=<your_ingestion_key>" \
OTEL_EXPORTER_OTLP_PROTOCOL=grpc \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=otlp \
OTEL_PYTHON_LOG_CORRELATION=true \
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true \
<your_run_command with opentelemetry-instrument>
```

- `<service_name>` is the name of your service
- Set the `<region>` to match your SigNoz Cloud [region](https://signoz.io/docs/ingestion/signoz-cloud/overview/#endpoint)
- Replace `<your_ingestion_key>` with your SigNoz [ingestion key](https://signoz.io/docs/ingestion/signoz-cloud/keys/)
- Replace `<your_run_command>` with the actual command you would use to run your application. In this case we would use: `uv run opentelemetry-instrument python bot.py`


> Note: Using self-hosted SigNoz? Most steps are identical. To adapt this guide, update the endpoint and
  remove the ingestion key header as shown in [Cloud → Self-Hosted](https://signoz.io/docs/ingestion/cloud-vs-self-hosted/#cloud-to-self-hosted).

Open http://localhost:7860 in your browser and click `Connect` to start talking to your bot.

You will now be able to see traces, logs, and metrics from your Pipecat usage in your SigNoz platform. 

## References

- [SigNoz PipeCat Documentation](https://signoz.io/docs/pipecat-monitoring/)
