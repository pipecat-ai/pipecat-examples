#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Webhook server to handle Daily PSTN calls and start the warm transfer bot.

This server provides endpoints for handling Daily PSTN webhooks and starting the bot.
The server automatically detects the environment (local vs production) and routes
bot starting requests accordingly:
- Local: Uses internal /start endpoint
- Production: Calls Pipecat Cloud API

All call data (room_url, token, call_id, call_domain, warm_transfer_config) flows through
the body parameter to ensure consistency between local and cloud deployments.
"""

import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from server_utils import (
    AgentRequest,
    TransferMessages,
    TransferTarget,
    WarmTransferConfig,
    call_data_from_request,
    create_daily_room,
    start_bot_local,
    start_bot_production,
)

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
    app.state.http_session = aiohttp.ClientSession()
    yield
    await app.state.http_session.close()


app = FastAPI(lifespan=lifespan)


@app.post("/daily-webhook")
async def handle_incoming_daily_webhook(request: Request) -> JSONResponse:
    """Handle incoming Daily PSTN call webhook.

    This endpoint:
    1. Receives Daily webhook data for incoming PSTN calls
    2. Creates a Daily room with dial-in and dial-out capabilities
    3. Starts the bot (locally or via Pipecat Cloud based on ENV)
    4. Returns room details for the caller
    """
    logger.debug("Received webhook from Daily")

    call_data = await call_data_from_request(request)

    daily_room_config = await create_daily_room(call_data, request.app.state.http_session)

    # Build warm transfer config from request or use defaults
    request_data = await request.json()
    warm_transfer_config_data = request_data.get("warm_transfer_config")
    if warm_transfer_config_data:
        warm_transfer_config = WarmTransferConfig.model_validate(warm_transfer_config_data)
    else:
        valid_targets = [t for t in DEFAULT_TRANSFER_TARGETS if t.phone_number]
        if not valid_targets:
            logger.warning("No valid transfer targets configured")
        warm_transfer_config = WarmTransferConfig(
            transfer_targets=valid_targets,
            transfer_messages=TransferMessages(),
        )

    agent_request = AgentRequest(
        room_url=daily_room_config.room_url,
        token=daily_room_config.token,
        call_id=call_data.call_id,
        call_domain=call_data.call_domain,
        warm_transfer_config=warm_transfer_config,
    )

    try:
        if os.getenv("ENV") == "production":
            await start_bot_production(agent_request, request.app.state.http_session)
        else:
            await start_bot_local(agent_request, request.app.state.http_session)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")

    return JSONResponse(
        {
            "status": "success",
            "room_url": daily_room_config.room_url,
            "token": daily_room_config.token,
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
