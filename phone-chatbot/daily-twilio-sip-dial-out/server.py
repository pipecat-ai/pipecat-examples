#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Webhook server to handle dial-out requests and start the voice bot.

This server provides endpoints for initiating outbound calls:
- /start: Main endpoint that receives dial-out requests with SIP URI
- /health: Health check endpoint

The server automatically detects the environment (local vs production) and routes
bot starting requests accordingly:
- Local: Uses internal bot starting logic
- Production: Calls Pipecat Cloud API

All call data (room_url, token, dialout_settings) flows through the body parameter
to ensure consistency between local and cloud deployments.
"""

import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pipecat.runner.daily import configure

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session to be used for Daily API calls
    app.state.session = aiohttp.ClientSession()
    yield
    # Close session when shutting down
    await app.state.session.close()


app = FastAPI(lifespan=lifespan)


def extract_phone_from_sip_uri(sip_uri):
    """Extract phone number from SIP URI.

    Args:
        sip_uri: SIP URI in format "sip:+17868748498@daily-twilio-integration.sip.twilio.com"

    Returns:
        Phone number string (e.g., "+17868748498") or None if invalid format
    """
    if not sip_uri or not isinstance(sip_uri, str):
        return None

    if sip_uri.startswith("sip:") and "@" in sip_uri:
        phone_part = sip_uri[4:]  # Remove 'sip:' prefix
        caller_phone = phone_part.split("@")[0]  # Get everything before '@'
        return caller_phone
    return None


@app.post("/start")
async def handle_dialout_request(request: Request) -> JSONResponse:
    """Handle dial-out request.

    This endpoint:
    1. Receives dial-out request with SIP URI
    2. Creates a Daily room with SIP capabilities
    3. Starts the bot (locally or via Pipecat Cloud based on ENVIRONMENT)
    4. Returns room details for the client

    Returns:
        JSONResponse with room_url and token
    """
    logger.debug("Received dial-out request")

    # Get the dial-in properties from the request
    try:
        data = await request.json()
        if "test" in data:
            # Pass through any webhook checks
            return JSONResponse({"test": True})

        if not data["dialout_settings"]:
            raise HTTPException(
                status_code=400, detail="Missing 'dialout_settings' in the request body"
            )

        if not data["dialout_settings"].get("sip_uri"):
            raise HTTPException(status_code=400, detail="Missing 'sip_uri' in dialout_settings")

        # Extract the phone number we want to dial out to
        sip_uri = str(data["dialout_settings"]["sip_uri"])
        caller_phone = extract_phone_from_sip_uri(sip_uri)
        logger.debug(f"SIP URI: {sip_uri}")
        logger.debug(f"Processing sip call to {caller_phone}")

        # Create a Daily room with SIP capabilities
        try:
            sip_config = await configure(request.app.state.session, sip_caller_phone=caller_phone)
        except Exception as e:
            logger.error(f"Error creating Daily room: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Daily room: {str(e)}")

        room_url = sip_config.room_url
        token = sip_config.token
        logger.debug(f"Created Daily room: {room_url} with token: {token}")

        # Start the bot - either locally or via Pipecat Cloud
        try:
            # Check environment mode (local development vs production)
            environment = os.getenv("ENVIRONMENT", "local")  # "local" or "production"

            # Prepare body data with all necessary information
            # This data structure is consistent between local and cloud deployments
            body_data = {
                "room_url": room_url,
                "token": token,
                "dialout_settings": data["dialout_settings"],
            }

            if environment == "production":
                # Production: Call Pipecat Cloud API to start the bot
                pipecat_api_token = os.getenv("PIPECAT_API_TOKEN")
                agent_name = os.getenv("PIPECAT_AGENT_NAME")

                if not pipecat_api_token:
                    raise HTTPException(
                        status_code=500, detail="PIPECAT_API_TOKEN required for production mode"
                    )

                logger.debug(f"Starting bot via Pipecat Cloud")
                async with request.app.state.session.post(
                    f"https://api.pipecat.daily.co/v1/public/{agent_name}/start",
                    headers={
                        "Authorization": f"Bearer {pipecat_api_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "createDailyRoom": False,  # We already created the room
                        "body": body_data,
                    },
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to start bot via Pipecat Cloud: {error_text}",
                        )
                    cloud_data = await response.json()
                    logger.debug(f"Bot started successfully via Pipecat Cloud")
            else:
                # Local development: Start bot directly
                logger.debug(f"Starting bot locally")

                from pipecat.runner.types import DailyRunnerArguments

                from bot import bot as bot_function

                # Create runner arguments with body data
                # Note: room_url and token are passed via body, not as direct arguments
                runner_args = DailyRunnerArguments(
                    room_url=None,  # Data comes from body
                    token=None,  # Data comes from body
                    body=body_data,
                )
                runner_args.handle_sigint = False

                # Start the bot in the background
                import asyncio

                asyncio.create_task(bot_function(runner_args))
                logger.debug(f"Bot started successfully locally")

        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    # Return room details for the client
    return JSONResponse({"room_url": room_url, "token": token})


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        dict: Status indicating server health
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    # Run the server
    port = int(os.getenv("PORT", "7860"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
