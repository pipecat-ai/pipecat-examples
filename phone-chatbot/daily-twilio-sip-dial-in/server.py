#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Webhook server to handle Twilio calls and start the voice bot.

This server provides two main endpoints:
- /call: Twilio webhook handler that receives incoming calls

The server automatically detects the environment (local vs production) and routes
bot starting requests accordingly:
- Local: Uses internal /start endpoint
- Production: Calls Pipecat Cloud API

All call data (room_url, token, call_sid, sip_uri) flows through the body parameter
to ensure consistency between local and cloud deployments.
"""

import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from loguru import logger
from twilio.twiml.voice_response import VoiceResponse

from server_utils import (
    AgentRequest,
    create_daily_room,
    start_bot_local,
    start_bot_production,
    twilio_call_data_from_request,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle and shared resources.

    Creates a shared aiohttp session for making HTTP requests to bot endpoints.
    The session is reused across requests for better performance through connection pooling.
    """
    # Create shared HTTP session for bot API calls
    app.state.http_session = aiohttp.ClientSession()
    logger.info("Created shared HTTP session")
    yield
    # Clean up: close the session on shutdown
    await app.state.http_session.close()
    logger.info("Closed shared HTTP session")


app = FastAPI(lifespan=lifespan)


@app.post("/call", response_class=PlainTextResponse)
async def handle_call(request: Request):
    """
    Handle incoming Twilio call webhook.

    This endpoint:
    1. Receives Twilio webhook data for incoming calls
    2. Creates a Daily room with SIP capabilities
    3. Starts the bot (locally or via Pipecat Cloud based on ENV)
    4. Returns TwiML to put caller on hold while bot connects

    Returns:
        TwiML response with hold music for the caller

    """
    logger.debug("Received call webhook from Twilio")

    call_data = await twilio_call_data_from_request(request)

    sip_config = await create_daily_room(call_data, request.app.state.http_session)

    # Make sure we have a SIP endpoint.
    if not sip_config.sip_endpoint:
        raise HTTPException(status_code=500, detail="No SIP endpoint provided by Daily")

    agent_request = AgentRequest(
        room_url=sip_config.room_url,
        token=sip_config.token,
        call_sid=call_data.call_sid,
        sip_uri=sip_config.sip_endpoint,
    )

    # Start bot locally or in production.
    try:
        if os.getenv("ENV") == "production":
            await start_bot_production(agent_request, request.app.state.http_session)
        else:
            await start_bot_local(agent_request, request.app.state.http_session)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {e!s}")

    # Generate TwiML response to put the caller on hold with music
    # The caller hears this while the bot connects to the Daily room
    # You can replace the URL with your own music file or use Twilio's built-in music
    # See: https://www.twilio.com/docs/voice/twiml/play#music-on-hold
    try:
        resp = VoiceResponse()
        resp.play(
            url="https://therapeutic-crayon-2467.twil.io/assets/US_ringback_tone.mp3",
            loop=10,
        )
        return str(resp)
    except Exception as e:
        logger.error(f"Unexpected error: {e!s}")
        raise HTTPException(status_code=500, detail=f"Server error: {e!s}")


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        dict: Status indicating server health
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    # Run the server
    port = int(os.getenv("PORT", "8080"))
    print(f"Starting server on port {port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
