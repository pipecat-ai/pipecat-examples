# SageMaker Wrapper

NVIDIA NIM containers expose their own HTTP/gRPC APIs. AWS SageMaker, however, requires every inference container to implement a **specific interface** before it can be deployed as an endpoint. This directory contains the wrapper layer that bridges the two.

---

## Why a wrapper is needed

SageMaker makes two hard requirements of any inference container:

| Requirement | What SageMaker does |
|---|---|
| `GET /ping` on port **8080** must return `200` when the model is ready | Used for health checks — SageMaker won't mark the endpoint `InService` until this passes |
| `POST /invocations` on port **8080** handles inference requests | All client calls go through this endpoint |

NVIDIA NIM containers don't expose either of these. They listen on port **9000** and use their own API paths.

The wrapper solves this by running **alongside NIM inside the same container** as a lightweight FastAPI application on port 8080. It translates SageMaker's expected interface into the NIM's actual API.

For real-time streaming use cases, SageMaker also supports a bidirectional WebSocket path (`WS /invocations-bidirectional-stream`), enabled via the container label `com.amazonaws.sagemaker.capabilities.bidirectional-streaming=true`. The wrapper proxies this transparently to the NIM's WebSocket endpoint.

---

## How it runs inside the container

`entrypoint.sh` is the container's `ENTRYPOINT`. It:

1. Starts the NIM server in the background using the original NIM entrypoint (auto-detected at build time via `docker inspect` and baked in as `NIM_START_CMD`).
2. Starts `uvicorn` (FastAPI wrapper) in the background on port 8080.
3. Supervises both processes — if either one exits, it kills the other and exits with the same code.

NIM can take up to 60 minutes to download model weights on first start. During that time, `/ping` returns `503`, which is expected — SageMaker keeps waiting (up to the configured `SAGEMAKER_CONTAINER_STARTUP_TIMEOUT`).

---

## NIM-specific wrappers

| NIM | Wrapper | Description |
|---|---|---|
| Magpie TTS | [magpie/](magpie/README.md) | Text-to-speech — streams raw PCM audio |
| Nemotron ASR Streaming | [nemotron-asr/](nemotron-asr/README.md) | Speech-to-text — returns JSON transcript |

---

## Building and deploying

The wrapper is built, pushed, and deployed entirely through the scripts in `scripts/`. See [DEPLOYMENT.md](../DEPLOYMENT.md) for the full walkthrough.
