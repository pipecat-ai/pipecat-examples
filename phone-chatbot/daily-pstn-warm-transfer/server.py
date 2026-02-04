#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Webhook server to handle Daily PSTN calls and start the warm transfer bot.

This server provides endpoints for handling Daily PSTN webhooks and starting the bot.
The server automatically detects the environment (local vs production) and routes
bot starting requests accordingly:
- Local: Uses internal /start_bot endpoint
- Production: Calls Pipecat Cloud API

All call data (room_url, token, callId, callDomain, warm_transfer_config) flows through
the body parameter to ensure consistency between local and cloud deployments.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pipecat.runner.daily import configure
from pipecat.runner.types import DailyRunnerArguments
from pipecat.transports.daily.utils import DailyRoomProperties, DailyRoomSipParams

from bot import bot as bot_function
from models import TransferMessages, TransferTarget, WarmTransferConfig

load_dotenv()

# Default transfer targets if not provided in request
DEFAULT_TRANSFER_TARGETS = [
    TransferTarget(
        name="Sales Team",
        phone_number=os.getenv("SALES_NUMBER", ""),
        description="Handles new purchases, upgrades, and pricing questions",
    ),
    TransferTarget(
        name="Support Team",
        phone_number=os.getenv("SUPPORT_NUMBER", ""),
        description="Handles technical issues, bugs, and troubleshooting",
    ),
    TransferTarget(
        name="Billing Team",
        phone_number=os.getenv("BILLING_NUMBER", ""),
        description="Handles invoices, refunds, and payment issues",
    ),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session to be used for Daily API calls
    app.state.session = aiohttp.ClientSession()
    yield
    # Close session when shutting down
    await app.state.session.close()


app = FastAPI(lifespan=lifespan)


@app.post("/start")
async def handle_incoming_daily_webhook(request: Request) -> JSONResponse:
    """Handle incoming Daily PSTN call webhook.

    This endpoint:
    1. Receives Daily webhook data for incoming PSTN calls
    2. Creates a Daily room with dial-in capabilities
    3. Starts the bot (locally or via Pipecat Cloud based on ENV)
    4. Returns room details for the caller

    Returns:
        JSONResponse with room_url and token
    """
    logger.debug("Received webhook from Daily")

    try:
        data = await request.json()
        logger.debug(f"Received webhook data: {data}")

        if not all(key in data for key in ["From", "To", "callId", "callDomain"]):
            raise HTTPException(
                status_code=400, detail="Missing properties 'From', 'To', 'callId', 'callDomain'"
            )

        caller_phone = str(data.get("From"))
        call_id = data.get("callId")
        logger.debug(f"Processing call with ID: {call_id} from {caller_phone}")

        # Create a Daily room with dial-in and dial-out capabilities
        try:
            # Include SIP configuration in room_properties to avoid parameter override
            room_properties = DailyRoomProperties(
                enable_dialout=True,
                sip=DailyRoomSipParams(display_name=caller_phone),
            )
            room_details = await configure(
                request.app.state.session,
                room_properties=room_properties,
            )
        except Exception as e:
            logger.error(f"Error creating Daily room: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Daily room: {str(e)}")

        room_url = room_details.room_url
        token = room_details.token
        logger.debug(f"Created Daily room: {room_url}")

        # Build warm transfer config from request or use defaults
        warm_transfer_config = data.get("warm_transfer_config")
        if warm_transfer_config:
            config = WarmTransferConfig.model_validate(warm_transfer_config)
        else:
            # Use default targets (filter out empty phone numbers)
            valid_targets = [t for t in DEFAULT_TRANSFER_TARGETS if t.phone_number]
            if not valid_targets:
                logger.warning("No valid transfer targets configured")
            config = WarmTransferConfig(
                transfer_targets=valid_targets,
                transfer_messages=TransferMessages(),
            )

        # Start the bot
        try:
            environment = os.getenv("ENV", "local")

            body_data: dict[str, object] = {
                **data,
                "room_url": room_url,
                "token": token,
                "warm_transfer_config": config.model_dump(),
            }
            logger.debug(
                f"Body data callId={body_data.get('callId')}, callDomain={body_data.get('callDomain')}"
            )

            if environment == "production":
                pipecat_api_key = os.getenv("PIPECAT_CLOUD_API_KEY")
                agent_name = os.getenv("PIPECAT_AGENT_NAME")

                if not pipecat_api_key:
                    raise HTTPException(
                        status_code=500,
                        detail="PIPECAT_CLOUD_API_KEY required for production mode",
                    )

                logger.debug(f"Starting bot via Pipecat Cloud for call {call_id}")
                async with request.app.state.session.post(
                    f"https://api.pipecat.daily.co/v1/public/{agent_name}/start",
                    headers={
                        "Authorization": f"Bearer {pipecat_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "createDailyRoom": False,
                        "body": body_data,
                    },
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to start bot via Pipecat Cloud: {error_text}",
                        )
                    logger.debug("Bot started successfully via Pipecat Cloud")
            else:
                local_server_url = os.getenv("LOCAL_SERVER_URL", "http://localhost:7860")

                logger.debug(f"Starting bot via local /start_bot endpoint for call {call_id}")
                async with request.app.state.session.post(
                    f"{local_server_url}/start_bot",
                    headers={"Content-Type": "application/json"},
                    json={
                        "createDailyRoom": False,
                        "body": body_data,
                    },
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to start bot via local /start_bot endpoint: {error_text}",
                        )
                    logger.debug("Bot started successfully via local /start_bot endpoint")

        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    return JSONResponse({"room_url": room_url, "token": token})


@app.post("/start_bot")
async def start_bot_endpoint(request: Request) -> dict[str, str]:
    """Start bot endpoint for local development.

    This endpoint mimics the Pipecat Cloud API pattern, receiving the same body data
    structure and starting the bot locally. Used only in local development mode.

    Args:
        request: FastAPI request containing body with room_url, token, callId, callDomain,
                 and warm_transfer_config

    Returns:
        dict: Success status and call_id
    """
    try:
        request_data = await request.json()
        body = request_data.get("body", {})

        room_url = body.get("room_url")
        token = body.get("token")
        call_id = body.get("callId")
        call_domain = body.get("callDomain")

        if not all([room_url, token, call_id, call_domain]):
            raise HTTPException(
                status_code=400,
                detail="Missing required parameters in body: room_url, token, callId, callDomain",
            )

        runner_args = DailyRunnerArguments(
            room_url=room_url,
            token=token,
            body=body,
        )
        runner_args.handle_sigint = False

        asyncio.create_task(bot_function(runner_args))

        return {"status": "Bot started successfully", "call_id": call_id}

    except Exception as e:
        logger.error(f"Error in /start_bot endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        dict: Status indicating server health
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
