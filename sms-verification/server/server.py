#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Demo-specific FastAPI routes layered on top of the Pipecat runner.

The Pipecat runner (``pipecat.runner.run``) provides the transport plumbing
(``/ws`` for Twilio, ``/api/offer`` for SmallWebRTC, TwiML XML for
``-t twilio``, etc.). This file adds the pieces unique to the SMS
verification demo:

* ``GET  /``           — serves the demo frontend (overrides the runner's redirect).
* ``GET  /api/config`` — surfaces ``TWILIO_PHONE_NUMBER`` so the phone-mode UI
                          can show the number the user should dial.
* ``GET  /events``     — Server-Sent Events stream so the Twilio-mode frontend
                          can learn whether verification succeeded.

Launch with ``python server.py`` (or ``uv run python server.py``). The runner's
``main()`` discovers ``bot()`` from ``bot.py`` automatically.
"""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pipecat.runner.run import app, main

from events import bus

load_dotenv(override=True)

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(CLIENT_DIR / "index.html")


if CLIENT_DIR.exists():
    app.mount("/static", StaticFiles(directory=CLIENT_DIR), name="static")


@app.get("/api/config")
async def client_config():
    """Public config the frontend needs to render the demo."""
    return {"twilio_phone_number": os.getenv("TWILIO_PHONE_NUMBER", "")}


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
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    main()
