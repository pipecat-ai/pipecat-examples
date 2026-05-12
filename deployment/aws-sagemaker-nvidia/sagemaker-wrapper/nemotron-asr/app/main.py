"""
SageMaker compatibility wrapper for NVIDIA Nemotron ASR Streaming NIM.

Translates SageMaker's expected interface to the NIM container's actual API:

    SageMaker                            NIM
    ─────────────────────────────────    ──────────────────────────────────────────
    GET  /ping                      →    GET  /v1/health/ready
    POST /invocations               →    410 Not Supported (use bidi-stream)
    WS   /invocations-bidirectional-stream → WS /v1/realtime?intent=transcription

The NIM server runs internally on port 9000 (its default).
The FastAPI wrapper runs on port 8080, which SageMaker expects.

NIM endpoints used by this wrapper:
    GET  /v1/health/ready                   ← polled by /ping
    WS   /v1/realtime?intent=transcription  ← proxied by /invocations-bidirectional-stream

WebSocket protocol (client → NIM, forwarded transparently):
    {"type": "transcription_session.update", "session": {...}}
    {"type": "input_audio_buffer.append", "audio": "<base64 PCM16>"}
    {"type": "input_audio_buffer.commit"}
    {"type": "input_audio_buffer.done"}
    {"type": "input_audio_buffer.clear"}

WebSocket protocol (NIM → client, forwarded transparently):
    {"type": "conversation.created", ...}
    {"type": "transcription_session.updated", ...}
    {"type": "input_audio_buffer.committed", ...}
    {"type": "conversation.item.input_audio_transcription.delta", "delta": "..."}
    {"type": "conversation.item.input_audio_transcription.completed", "transcript": "..."}
    {"type": "conversation.item.input_audio_transcription.failed", ...}
    {"type": "error", ...}
"""

import asyncio
import json
import logging
import os

import httpx
import websockets
import websockets.exceptions
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sagemaker-wrapper")

app = FastAPI(title="Nemotron ASR SageMaker Wrapper")

# ── NIM connection config ─────────────────────────────────────────────────────
NIM_HTTP_PORT = int(os.environ.get("NIM_HTTP_API_PORT", "9000"))
NIM_BASE_URL = f"http://localhost:{NIM_HTTP_PORT}"
NIM_WS_URL = f"ws://localhost:{NIM_HTTP_PORT}"

NIM_HEALTH_PATH = os.environ.get("NIM_HEALTH_PATH", "/v1/health/ready")
NIM_REALTIME_PATH = "/v1/realtime"

logger.info(f"NIM base URL         : {NIM_BASE_URL}")
logger.info(f"NIM health path      : {NIM_HEALTH_PATH}")
logger.info(f"NIM realtime WS      : {NIM_REALTIME_PATH}?intent=transcription")


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/ping")
async def ping() -> Response:
    """
    SageMaker polls this endpoint to determine if the container is healthy.
    Returns 200 only when NIM is fully initialized and ready to serve requests.

    NIM health endpoint: GET /v1/health/ready
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{NIM_BASE_URL}{NIM_HEALTH_PATH}", timeout=5.0)
        if resp.status_code == 200:
            logger.debug("NIM health: ready")
            return Response(status_code=200)
        logger.debug(f"NIM health: not ready (status {resp.status_code})")
    except httpx.ConnectError:
        logger.debug("NIM health: connection refused (still starting)")
    except httpx.TimeoutException:
        logger.warning("NIM health: timeout")
    except Exception as exc:
        logger.warning(f"NIM health check error: {exc}")
    return Response(status_code=503)


# ── HTTP batch transcription (not supported) ──────────────────────────────────


@app.post("/invocations")
async def invocations(request: Request) -> Response:
    """
    Batch transcription via POST /invocations is not supported.

    Nemotron ASR Streaming is a realtime streaming model — use the
    bidirectional-stream endpoint instead:

        InvokeEndpointWithBidirectionalStream → /invocations-bidirectional-stream
    """
    logger.warning("POST /invocations called — not supported, returning 410")
    return Response(
        content=json.dumps(
            {
                "error": "POST /invocations is not supported for Nemotron ASR Streaming. "
                "Use InvokeEndpointWithBidirectionalStream (/invocations-bidirectional-stream) instead."
            }
        ).encode(),
        status_code=410,
        media_type="application/json",
    )


# ── WebSocket proxy ───────────────────────────────────────────────────────────


async def _nim_ws_proxy(client_ws: WebSocket, log_tag: str) -> None:
    """
    Transparent WebSocket proxy: bridges client_ws to NIM's realtime transcription endpoint.

    Forwards all frames (text and binary) in both directions without modification.
    Used by /invocations-bidirectional-stream (SageMaker bidi stream).

    NIM WebSocket protocol (client → NIM):
        {"type": "transcription_session.update", "session": {...}}
        {"type": "input_audio_buffer.append", "audio": "<base64 PCM16>"}
        {"type": "input_audio_buffer.commit"}
        {"type": "input_audio_buffer.done"}
        {"type": "input_audio_buffer.clear"}

    NIM WebSocket protocol (NIM → client):
        {"type": "conversation.created", ...}
        {"type": "transcription_session.updated", ...}
        {"type": "input_audio_buffer.committed", ...}
        {"type": "conversation.item.input_audio_transcription.delta", "delta": "..."}
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "..."}
        {"type": "conversation.item.input_audio_transcription.failed", ...}
        {"type": "error", ...}
    """
    nim_uri = f"{NIM_WS_URL}{NIM_REALTIME_PATH}?intent=transcription"
    logger.info(f"{log_tag} — client connected, opening NIM WebSocket at {nim_uri}")

    try:
        async with websockets.connect(nim_uri) as nim_ws:

            async def client_to_nim():
                try:
                    while True:
                        msg = await client_ws.receive()
                        logger.info(f"msg received {msg}")
                        if msg.get("type") == "websocket.disconnect":
                            logger.info(f"{log_tag} — client disconnected (code {msg.get('code')})")
                            await nim_ws.close()
                            return
                        if "text" in msg:
                            # Intercept session.end — close NIM WebSocket gracefully
                            # instead of forwarding (NIM doesn't know this message type).
                            try:
                                if json.loads(msg["text"]).get("type") == "session.end":
                                    logger.info(
                                        f"{log_tag} — session.end received, closing NIM WebSocket"
                                    )
                                    await nim_ws.close()
                                    return
                            except (json.JSONDecodeError, AttributeError):
                                pass
                            await nim_ws.send(msg["text"])
                        elif "bytes" in msg:
                            await nim_ws.send(msg["bytes"])
                except WebSocketDisconnect:
                    logger.info(f"{log_tag} — client disconnected")
                    await nim_ws.close()

            async def nim_to_client():
                try:
                    async for msg in nim_ws:
                        if isinstance(msg, str):
                            await client_ws.send_text(msg)
                        else:
                            await client_ws.send_bytes(msg)
                except websockets.exceptions.ConnectionClosedOK:
                    logger.info(f"{log_tag} — NIM WebSocket closed normally")
                except websockets.exceptions.ConnectionClosedError as exc:
                    logger.warning(f"{log_tag} — NIM WebSocket closed with error: {exc}")

            await asyncio.gather(client_to_nim(), nim_to_client())

    except websockets.exceptions.WebSocketException as exc:
        logger.error(f"{log_tag} — cannot connect to NIM WebSocket: {exc}")
        try:
            await client_ws.close(code=1011)
        except Exception:
            pass
    except Exception as exc:
        logger.error(f"{log_tag} — unexpected error: {exc}")
        try:
            await client_ws.close(code=1011)
        except Exception:
            pass


# Docs:
# https://docs.aws.amazon.com/pt_br/sagemaker/latest/dg/your-algorithms-inference-code.html
@app.websocket("/invocations-bidirectional-stream")
async def bidi_stream_proxy(client_ws: WebSocket):
    """
    SageMaker bidirectional-stream endpoint → NIM realtime WebSocket proxy.

    SageMaker's sidecar converts the client's HTTP/2 event stream into WebSocket
    frames at this path before forwarding them to the container. The wrapper
    bridges those frames transparently to NIM's realtime WebSocket, so the
    caller can use the NIM ASR JSON protocol directly over SageMaker's bidi API.

    Enable with the container label:
        com.amazonaws.sagemaker.capabilities.bidirectional-streaming=true
    """
    await client_ws.accept()
    await _nim_ws_proxy(client_ws, "WS /invocations-bidirectional-stream")
