"""
SageMaker compatibility wrapper for NVIDIA Magpie TTS NIM.

Translates SageMaker's expected interface to the NIM container's actual API:

    SageMaker                    NIM
    ─────────────────────────    ──────────────────────────────────
    GET  /ping              →    GET  /v1/health/ready
    POST /invocations       →    POST /v1/audio/synthesize_online  (HTTP streaming)

The HTTP /invocations path is used with SageMaker's standard invoke-endpoint API.
The WebSocket path is used for real-time streaming (direct access or via
SageMaker's InvokeEndpointWithBidirectionalStream).
"""

import asyncio
import json
import logging
import os

import httpx
import websockets
import websockets.exceptions
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sagemaker-wrapper")

app = FastAPI(title="Magpie TTS SageMaker Wrapper")

# ── NIM connection config ─────────────────────────────────────────────────────
NIM_HTTP_PORT = int(os.environ.get("NIM_HTTP_API_PORT", "9000"))
NIM_BASE_URL = f"http://localhost:{NIM_HTTP_PORT}"
NIM_WS_URL = f"ws://localhost:{NIM_HTTP_PORT}"

NIM_HEALTH_PATH = os.environ.get("NIM_HEALTH_PATH", "/v1/health/ready")
NIM_SYNTHESIS_PATH = "/v1/audio/synthesize_online"
NIM_REALTIME_PATH = "/v1/realtime"

logger.info(f"NIM base URL      : {NIM_BASE_URL}")
logger.info(f"NIM health path   : {NIM_HEALTH_PATH}")
logger.info(f"NIM synthesis path: {NIM_SYNTHESIS_PATH}")
logger.info(f"NIM realtime path : {NIM_REALTIME_PATH}")


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/ping")
async def ping() -> Response:
    """
    SageMaker polls this endpoint to determine if the container is healthy.
    Returns 200 only when NIM is fully initialized and ready to serve requests.
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


# ── HTTP streaming inference ──────────────────────────────────────────────────


@app.post("/invocations")
async def invocations(request: Request) -> Response:
    """
    SageMaker sends all inference requests here.
    Parses the JSON body and proxies to NIM's HTTP streaming synthesis endpoint
    as multipart form data, streaming the raw PCM audio back to the caller.

    Expected request body (JSON):
        {
            "text": "Hello, world.",
            "voice_name": "Magpie-Multilingual.EN-US.Aria",
            "language_code": "en-US",
            "sample_rate_hz": 22050
        }
    """
    body = await request.body()
    logger.info(f"POST /invocations — {len(body)} bytes")

    try:
        params = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON body: {exc}")
        return Response(content=b'{"error": "invalid JSON body"}', status_code=400)

    text = params.get("text", "")
    voice = params.get("voice_name", "Magpie-Multilingual.EN-US.Aria")
    language = params.get("language_code", "en-US")
    sample_rate = int(params.get("sample_rate_hz", 22050))

    if not text:
        return Response(content=b'{"error": "text field is required"}', status_code=400)

    logger.info(f"Synthesis — voice={voice!r} lang={language} rate={sample_rate}")

    async def stream_synthesis():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{NIM_BASE_URL}{NIM_SYNTHESIS_PATH}",
                    data={
                        "text": text,
                        "voice": voice,
                        "language": language,
                        "sample_rate_hz": str(sample_rate),
                    },
                ) as nim_resp:
                    if nim_resp.status_code != 200:
                        error_body = await nim_resp.aread()
                        logger.error(
                            f"NIM returned {nim_resp.status_code}: {error_body.decode(errors='replace')}"
                        )
                        yield error_body
                        return
                    logger.info(
                        f"NIM synthesis streaming "
                        f"(content-type: {nim_resp.headers.get('content-type', 'unknown')})"
                    )
                    async for chunk in nim_resp.aiter_bytes(chunk_size=4096):
                        yield chunk
        except httpx.ConnectError as exc:
            logger.error(f"Cannot connect to NIM: {exc}")
            yield b'{"error": "NIM service unavailable"}'
        except Exception as exc:
            logger.error(f"Synthesis error: {exc}")
            yield b'{"error": "internal wrapper error"}'

    return StreamingResponse(stream_synthesis(), media_type="application/octet-stream")


# ── WebSocket proxy ───────────────────────────────────────────────────────────


async def _nim_ws_proxy(client_ws: WebSocket, log_tag: str) -> None:
    """
    Transparent WebSocket proxy: bridges client_ws to NIM's realtime endpoint.

    Forwards all frames (text and binary) in both directions without
    modification. Used by /invocations-bidirectional-stream (SageMaker bidi stream).

    NIM WebSocket protocol (client → NIM):
        {"type": "synthesize_session.update", "session": {"input_text_synthesis": {"voice_name": ..., "language_code": ...}, "output_audio_params": {...}}}
        {"type": "input_text.append", "text": "Hello world"}
        {"type": "input_text.commit"}
        {"type": "input_text.done"}

    NIM WebSocket protocol (NIM → client):
        {"type": "conversation.item.speech.data", "audio": "<base64>", "is_last_chunk": false}
        {"type": "conversation.item.speech.completed", ...}
        {"type": "error", ...}
    """
    nim_uri = f"{NIM_WS_URL}{NIM_REALTIME_PATH}?intent=synthesize"
    logger.info(f"{log_tag} — client connected, opening NIM WebSocket at {nim_uri}")

    try:
        async with websockets.connect(nim_uri) as nim_ws:

            async def client_to_nim():
                try:
                    while True:
                        msg = await client_ws.receive()
                        logger.info(f"msg received {msg}")
                        if msg.get("type") == "websocket.disconnect":
                            logger.info(
                                f"{log_tag} — client disconnected (code {msg.get('code')})"
                            )
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
                    logger.warning(
                        f"{log_tag} — NIM WebSocket closed with error: {exc}"
                    )

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
    frames at this path before forwarding them to the container.  The wrapper
    bridges those frames transparently to NIM's realtime WebSocket, so the
    caller can use the NIM JSON protocol directly over SageMaker's bidi API.

    Enable with the container label:
        com.amazonaws.sagemaker.capabilities.bidirectional-streaming=true
    """
    await client_ws.accept()
    await _nim_ws_proxy(client_ws, "WS /invocations-bidirectional-stream")
