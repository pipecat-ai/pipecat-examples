#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""FastAPI server for the SMS verification demo.

Endpoints:

* ``GET  /``               — serves the demo frontend.
* ``GET  /events``         — Server-Sent Events stream used by the Twilio-mode
                              frontend to receive verification results.
* ``POST /twilio/voice``   — TwiML webhook that points Twilio's Media Stream
                              at ``/ws/twilio``.
* ``WS   /ws/twilio``      — Twilio Media Streams websocket; runs the bot using
                              ``bot_twilio``.
* ``POST /api/offer``      — SmallWebRTC SDP offer; expects ``request_data``
                              to contain ``phone_number``.
* ``PATCH /api/offer``     — ICE candidate trickle for SmallWebRTC.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from bot import bot_twilio, bot_webrtc
from events import bus

load_dotenv(override=True)

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"

webrtc_handler = SmallWebRTCRequestHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await webrtc_handler.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Static client
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    return FileResponse(CLIENT_DIR / "index.html")


if CLIENT_DIR.exists():
    app.mount("/static", StaticFiles(directory=CLIENT_DIR), name="static")


@app.get("/api/config")
async def client_config():
    """Public config the frontend needs to render the demo."""
    return {"twilio_phone_number": os.getenv("TWILIO_PHONE_NUMBER", "")}


# ---------------------------------------------------------------------------
# Server-Sent Events — verification results for the Twilio-mode frontend.
# ---------------------------------------------------------------------------


@app.get("/events")
async def sse_events(request: Request):
    queue = bus.subscribe()

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Twilio
# ---------------------------------------------------------------------------


@app.post("/twilio/voice")
async def twilio_voice(request: Request):
    """TwiML webhook. Point your Twilio number's "A call comes in" here."""
    host = request.url.hostname
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://{host}/ws/twilio" />
  </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/ws/twilio")
async def twilio_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        await bot_twilio(websocket)
    except Exception as e:
        logger.exception(f"Twilio bot crashed: {e}")


# ---------------------------------------------------------------------------
# SmallWebRTC
# ---------------------------------------------------------------------------


@app.post("/api/offer")
async def webrtc_offer(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    # ``from_dict`` accepts both ``requestData`` (the JS SDK shape) and
    # ``request_data`` (snake_case).
    webrtc_request = SmallWebRTCRequest.from_dict(body)
    phone_number = (webrtc_request.request_data or {}).get("phone_number", "").strip()
    if not phone_number:
        return {"error": "phone_number required in request_data"}

    async def cb(connection):
        background_tasks.add_task(bot_webrtc, connection, phone_number)

    return await webrtc_handler.handle_web_request(
        request=webrtc_request,
        webrtc_connection_callback=cb,
    )


@app.patch("/api/offer")
async def webrtc_ice(request: Request):
    body = await request.json()
    patch = SmallWebRTCPatchRequest(**body)
    await webrtc_handler.handle_patch_request(patch)
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
