# Client Examples

This directory contains Python test clients and Pipecat voice bots for the
Magpie TTS and Nemotron ASR SageMaker endpoints.

All examples load credentials from `client/.env`.
Copy `env.example` and fill it in before running anything here.

---

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- A running SageMaker endpoint — see [DEPLOYMENT.md](../DEPLOYMENT.md)

### Install dependencies

```bash
cd client
uv sync
```

### Configure credentials

The examples read from `client/.env`. If you haven't set it up yet:

```bash
# From the client/ directory
cp env.example .env
# Fill in: AWS credentials, endpoint names and LLM base URL.
```

---

## Two transport modes

This project supports two ways to call a SageMaker endpoint:

| Mode | SageMaker API | Wrapper endpoint | Best for |
|---|---|---|---|
| **HTTP** | `invoke-endpoint` | `POST /invocations` | Simple testing, batch requests |
| **WebSocket / bidi-stream** | `invoke-endpoint-with-bidirectional-stream` | `WS /invocations-bidirectional-stream` | Real-time streaming, low latency |

> **Note:** The bidi-stream API uses a separate SageMaker runtime endpoint on
> port 8443 (`runtime.sagemaker.<region>.amazonaws.com:8443`), distinct from
> the standard `invoke-endpoint` URL.

---

## Files

| File | NIM | Mode | Purpose |
|---|---|---|---|
| `test/test_magpie_http.py` | Magpie TTS | HTTP | Send text, save audio as WAV |
| `test/test_magpie_ws.py` | Magpie TTS | WebSocket | Send text via bidi-stream, save audio as WAV |
| `test/test_asr_ws.py` | Nemotron ASR | WebSocket | Stream audio via bidi-stream, print transcript |
| `bot/services/nim_sagemaker_http_tts.py` | Magpie TTS | HTTP | `NvidiaSageMakerHTTPTTSService` — Pipecat TTS service |
| `bot/services/nim_sagemaker_ws_tts.py` | Magpie TTS | WebSocket | `NvidiaSageMakerWebsocketTTSService` — Pipecat TTS service |
| `bot/services/nim_sagemaker_ws_stt.py` | Nemotron ASR | WebSocket | `NvidiaSageMakerWebsocketSTTService` — Pipecat STT service |
| `bot/pipecat-bot-http.py` | Magpie TTS | HTTP | Full Pipecat voice bot (STT → LLM → TTS over HTTP) |
| `bot/pipecat-bot-ws.py` | Magpie TTS | WebSocket | Full Pipecat voice bot (STT → LLM → TTS over bidi-stream) |

---

## Magpie TTS — HTTP test client

Calls `POST /invocations`, receives raw PCM, and saves it as a WAV file.

```bash
# From the client/ directory:
uv run test/test_magpie_http.py
uv run test/test_magpie_http.py --text "Hello from SageMaker."
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--endpoint` | `$SAGEMAKER_MAGPIE_ENDPOINT_NAME` | SageMaker endpoint name |
| `--text` | (built-in phrase) | Text to synthesize |
| `--voice` | `$MAGPIE_VOICE` | NIM voice name |
| `--language` | `$MAGPIE_LANGUAGE_CODE` | BCP-47 language code |
| `--sample-rate` | `$MAGPIE_SAMPLE_RATE_HZ` | Output sample rate in Hz |
| `--output` | `./tmp/magpie-test.wav` | Output WAV file path |

---

## Magpie TTS — WebSocket test client

Calls the bidi-stream endpoint via SageMaker's HTTP/2
`InvokeEndpointWithBidirectionalStream` API. Audio chunks arrive as
base64-encoded `conversation.item.speech.data` events and are assembled into
a WAV file.

```bash
# From the client/ directory:
uv run test/test_magpie_ws.py
uv run test/test_magpie_ws.py --text "Hello from the bidi-stream endpoint." --output ./tmp/bidi-test.wav
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--endpoint` | `$SAGEMAKER_MAGPIE_ENDPOINT_NAME` | SageMaker endpoint name |
| `--region` | `$AWS_REGION` | AWS region |
| `--text` | (built-in phrase) | Text to synthesize |
| `--voice` | `$MAGPIE_VOICE` | NIM voice name |
| `--language` | `$MAGPIE_LANGUAGE_CODE` | BCP-47 language code |
| `--sample-rate` | `$MAGPIE_SAMPLE_RATE_HZ` | Output sample rate in Hz |
| `--output` | `./tmp/magpie-bidi-test.wav` | Output WAV file path |

---

## Nemotron ASR — WebSocket test client

Streams audio to the bidi-stream endpoint via SageMaker's HTTP/2
`InvokeEndpointWithBidirectionalStream` API. Audio is sent as base64-encoded
PCM16 chunks via `input_audio_buffer.append` events, and the transcript is
collected from `conversation.item.input_audio_transcription.completed`.

Falls back to `./tmp/magpie-test.pcm` if no audio is provided.

```bash
# From the client/ directory:
uv run test/test_asr_ws.py
uv run test/test_asr_ws.py --audio /path/to/audio.wav
uv run test/test_asr_ws.py --audio /path/to/audio.pcm --language en-US
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--endpoint` | `$SAGEMAKER_ASR_ENDPOINT_NAME` | SageMaker endpoint name |
| `--audio` | `./tmp/magpie-test.pcm` | Audio file (.wav or raw PCM16) |
| `--language` | `$NEMOTRON_ASR_LANGUAGE_CODE` | BCP-47 language code |
| `--sample-rate` | `$NEMOTRON_ASR_SAMPLE_RATE_HZ` | PCM sample rate (ignored for WAV) |

---

## Pipecat HTTP voice bot — `bot/pipecat-bot-http.py`

A complete real-time voice agent using HTTP synthesis:

```
Microphone → NvidiaSTTService              (Nemotron ASR — NVIDIA hosted API)
           → OpenAILLMService              (Nemotron Super 120B — Modal hosted)
           → NvidiaSageMakerHTTPTTSService (Magpie TTS — SageMaker)
           → Speaker
```

> STT calls NVIDIA's hosted API at `build.nvidia.com`. LLM calls Nemotron
> Super 120B hosted on Modal (`NEMOTRON_LLM_BASE_URL`). Only TTS uses the
> SageMaker endpoint built by this project.

```bash
# From the client/ directory:
uv run bot/pipecat-bot-http.py
```

### Required environment variables

| Variable | Used by | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | TTS | AWS IAM credentials |
| `AWS_SECRET_ACCESS_KEY` | TTS | AWS IAM credentials |
| `AWS_REGION` | TTS | AWS region of the endpoint |
| `SAGEMAKER_MAGPIE_ENDPOINT_NAME` | TTS | Deployed Magpie endpoint name |
| `NVIDIA_API_KEY` | STT | NVIDIA build.nvidia.com API key |
| `NEMOTRON_LLM_BASE_URL` | LLM | Base URL for the Nemotron Super Modal endpoint |

---

## Pipecat WebSocket voice bot — `bot/pipecat-bot-ws.py`

A complete real-time voice agent where both STT and TTS run on SageMaker via
bidirectional streaming. All three services maintain **persistent connections**
for the lifetime of the pipeline, enabling low latency and clean interruption
handling:

```
Microphone → NvidiaSageMakerWebsocketSTTService  (Nemotron ASR — SageMaker)
           → OpenAILLMService                    (Nemotron Super 120B — Modal hosted)
           → NvidiaSageMakerWebsocketTTSService  (Magpie TTS — SageMaker)
           → Speaker
```

```bash
# From the client/ directory:
uv run bot/pipecat-bot-ws.py
```

### Required environment variables

| Variable | Used by | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | STT + TTS | AWS IAM credentials |
| `AWS_SECRET_ACCESS_KEY` | STT + TTS | AWS IAM credentials |
| `AWS_REGION` | STT + TTS | AWS region of the endpoints |
| `SAGEMAKER_ASR_ENDPOINT_NAME` | STT | Deployed Nemotron ASR endpoint name |
| `SAGEMAKER_MAGPIE_ENDPOINT_NAME` | TTS | Deployed Magpie endpoint name |
| `NEMOTRON_LLM_BASE_URL` | LLM | Base URL for the Nemotron Super Modal endpoint |

---

## Deploying to Pipecat Cloud

`bot/pipecat-bot-ws.py` is ready to deploy to [Pipecat Cloud](https://pipecat.cloud).
The project includes a `Dockerfile` and `pcc-deploy.toml` that Pipecat Cloud uses
to build and run the bot.

### Prerequisites

- A [Pipecat Cloud](https://pipecat.cloud) account
- Both SageMaker endpoints (`SAGEMAKER_ASR_ENDPOINT_NAME`, `SAGEMAKER_MAGPIE_ENDPOINT_NAME`) deployed and `InService`

### Step 1 — Install the Pipecat CLI

```bash
uv tool install pipecat-ai-cli
```

### Step 2 — Authenticate

```bash
pipecat cloud auth login
```

### Step 3 — Install dependencies

The `Dockerfile` uses `uv.lock` to install dependencies reproducibly. Generate it
from the `client/` directory:

```bash
uv sync
```

### Step 4 — Upload secrets

Upload your `.env` as a named secret set. Pipecat Cloud injects these as
environment variables at runtime:

```bash
pipecat cloud secrets set nvidia-nim-secrets --file .env
```

The secret set name `nvidia-nim-secrets` matches what is configured in
`pcc-deploy.toml`.

### Step 5 — Deploy

```bash
pipecat cloud deploy
```

This builds the Docker image, pushes it to Pipecat Cloud, and starts the agent.
The `pcc-deploy.toml` configures the agent name, secret set, and scaling:

```toml
agent_name = "nvidia-nim-bot"
secret_set = "nvidia-nim-secrets"
agent_profile = "agent-1x"

[scaling]
    min_agents = 1
```

### Step 6 — Connect

Go to the [Pipecat Cloud Dashboard](https://pipecat.daily.co/) → your agent →
**Sandbox** → **Connect** to open a browser-based WebRTC call with the bot.
