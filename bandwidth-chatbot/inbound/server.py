#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""FastAPI server for the Bandwidth inbound chatbot example.

Exposes two endpoints:

- ``POST /incoming-call``: Bandwidth's Voice Application calls this when a
  call arrives. We respond with BXML that opens a bidirectional media-stream
  WebSocket back to ``/ws`` and parks the call with ``<Pause>`` so it stays
  alive while the WebSocket runs.

- ``WebSocket /ws``: Bandwidth's media-stream WebSocket. We read the first
  ``start`` event to extract call metadata, then hand the connection to the
  Pipecat pipeline.
"""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response
from loguru import logger

from bot import run_bot

load_dotenv(override=True)

app = FastAPI()

NGROK_PUBLIC_URL = os.environ["NGROK_PUBLIC_URL"]
WS_DESTINATION = NGROK_PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://") + "/ws"


@app.post("/incoming-call")
async def incoming_call(request: Request) -> Response:
    """Handle Bandwidth's inbound-call webhook with a BXML StartStream response."""
    body = await request.body()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}
    logger.info(
        f"Incoming call: from={payload.get('from')} to={payload.get('to')} "
        f"callId={payload.get('callId')}"
    )

    bxml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<StartStream destination="{WS_DESTINATION}" mode="bidirectional" tracks="inbound"/>'
        '<Pause duration="86400"/>'
        "</Response>"
    )
    return Response(content=bxml, media_type="application/xml")


@app.websocket("/ws")
async def media_stream(websocket: WebSocket) -> None:
    """Handle Bandwidth's bidirectional media-stream WebSocket."""
    await websocket.accept()
    logger.info("WebSocket accepted, waiting for start event")

    # Bandwidth's first message is always the start event with call metadata.
    raw = await websocket.receive_text()
    try:
        start_event = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"First WebSocket message wasn't JSON: {raw[:200]!r}")
        await websocket.close()
        return

    if start_event.get("eventType") != "start":
        logger.warning(f"First WebSocket message wasn't 'start', got: {start_event}")

    logger.info(f"Start event: {json.dumps(start_event, indent=2)}")

    try:
        await run_bot(websocket, start_event)
    except Exception as exc:
        logger.exception(f"run_bot failed: {exc}")
    finally:
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "ws_destination": WS_DESTINATION}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
