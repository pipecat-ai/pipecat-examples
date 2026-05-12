# SageMaker Wrapper — Magpie TTS

SageMaker wrapper for the **NVIDIA Magpie TTS NIM** (`magpie-tts-multilingual`). Translates SageMaker's expected interface to the NIM's actual API.

---

## API mapping

```
SageMaker (port 8080)                        NIM (port 9000)
────────────────────────────────────────     ──────────────────────────────────────────
GET  /ping                               →   GET  /v1/health/ready
POST /invocations                        →   POST /v1/audio/synthesize_online  (HTTP streaming)
WS   /invocations-bidirectional-stream   →   WS   /v1/realtime?intent=synthesize
```

---

## POST /invocations

Accepts a JSON body and returns a streaming `application/octet-stream` of raw signed 16-bit mono PCM audio.

**Request body (JSON):**
```json
{
  "text": "Hello, world.",
  "voice_name": "Magpie-Multilingual.EN-US.Aria",
  "language_code": "en-US",
  "sample_rate_hz": 22050
}
```

**Response:** raw PCM16 mono audio stream (`application/octet-stream`).

---

## WS /invocations-bidirectional-stream

Transparent WebSocket proxy to NIM's realtime synthesis endpoint (`/v1/realtime?intent=synthesize`).

The wrapper intercepts the `session.end` message (a client-side signal to close the session) and closes the NIM WebSocket gracefully, since NIM does not understand that message type.

Enabled by the container label:
```
com.amazonaws.sagemaker.capabilities.bidirectional-streaming=true
```

---

## Structure

```
magpie/
├── Dockerfile            ← Extends the NIM image with the FastAPI layer
├── entrypoint.sh         ← Starts NIM and uvicorn in parallel; supervises both
└── app/
    ├── main.py           ← FastAPI app: /ping, /invocations, WebSocket proxy
    └── pyproject.toml    ← Python dependencies: fastapi, uvicorn, httpx, websockets
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NIM_HTTP_API_PORT` | `9000` | NIM's internal HTTP port |
| `NIM_HEALTH_PATH` | `/v1/health/ready` | NIM health check path |
| `NGC_API_KEY` | — | Required — NIM uses this to download model weights |

---

## Building and deploying

```bash
./scripts/build_wrapper.sh magpie
./scripts/push_to_ecr.sh magpie
./scripts/create_model.sh magpie
./scripts/create_endpoint.sh magpie
```

See [DEPLOYMENT.md](../../DEPLOYMENT.md) for the full walkthrough.
