# SageMaker Wrapper — Nemotron ASR Streaming

SageMaker wrapper for the **NVIDIA Nemotron ASR Streaming NIM** (`nemotron-asr-streaming`). Translates SageMaker's expected interface to the NIM's actual API.

---

## API mapping

```
SageMaker (port 8080)                        NIM (port 9000)
────────────────────────────────────────     ──────────────────────────────────────────
GET  /ping                               →   GET  /v1/health/ready
POST /invocations                        →   410 Not Supported (use bidi-stream)
WS   /invocations-bidirectional-stream   →   WS   /v1/realtime?intent=transcription
```

---

## POST /invocations

Not supported. Nemotron ASR Streaming is a realtime model — batch transcription via `POST /invocations` is not available. Returns `410 Gone` with a message directing the caller to use `InvokeEndpointWithBidirectionalStream` instead.

---

## WS /invocations-bidirectional-stream

Transparent WebSocket proxy to NIM's realtime transcription endpoint (`/v1/realtime?intent=transcription`). All frames are forwarded in both directions without modification.

**Client → NIM messages:**
```json
{"type": "transcription_session.update", "session": {...}}
{"type": "input_audio_buffer.append", "audio": "<base64 PCM16>"}
{"type": "input_audio_buffer.commit"}
{"type": "input_audio_buffer.done"}
{"type": "input_audio_buffer.clear"}
```

**NIM → client messages:**
```json
{"type": "conversation.created", ...}
{"type": "transcription_session.updated", ...}
{"type": "input_audio_buffer.committed", ...}
{"type": "conversation.item.input_audio_transcription.delta", "delta": "..."}
{"type": "conversation.item.input_audio_transcription.completed", "transcript": "..."}
{"type": "conversation.item.input_audio_transcription.failed", ...}
{"type": "error", ...}
```

Enabled by the container label:
```
com.amazonaws.sagemaker.capabilities.bidirectional-streaming=true
```

---

## Structure

```
nemotron-asr/
├── Dockerfile            ← Extends the NIM image with the FastAPI layer
├── entrypoint.sh         ← Starts NIM and uvicorn in parallel; supervises both
└── app/
    ├── main.py           ← FastAPI app: /ping (health), /invocations (unsupported), WebSocket proxy
    └── pyproject.toml    ← Python dependencies: fastapi, uvicorn, httpx, websockets
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NIM_HTTP_API_PORT` | `9000` | NIM's internal HTTP port |
| `NIM_HEALTH_PATH` | `/v1/health/ready` | NIM health check path |
| `NIM_TAGS_SELECTOR` | — | Must be set to `mode=str` to enable streaming mode |
| `NGC_API_KEY` | — | Required — NIM uses this to download model weights |

> **Important:** `NIM_TAGS_SELECTOR=mode=str` is required for the Nemotron ASR Streaming NIM. It is injected automatically by `scripts/create_model.sh`.

---

## Building and deploying

```bash
./scripts/build_wrapper.sh nemotron-asr
./scripts/push_to_ecr.sh nemotron-asr
./scripts/create_model.sh nemotron-asr
./scripts/create_endpoint.sh nemotron-asr
```

See [DEPLOYMENT.md](../../DEPLOYMENT.md) for the full walkthrough.
