#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Utilities for Daily PSTN webhook handling and bot management.

This module provides data models and functions for:
- Parsing Daily PSTN webhook data
- Creating Daily rooms for incoming calls
- Starting bots in production (Pipecat Cloud) or local development mode
"""

import os

import aiohttp
from fastapi import HTTPException, Request
from loguru import logger
from pipecat.runner.daily import DailyRoomConfig, configure
from pydantic import BaseModel


class DailyCallData(BaseModel):
    """Data received from Daily PSTN webhook.

    Attributes:
        from_phone: The caller's phone number
        to_phone: The dialed phone number
        call_id: Unique identifier for the call
        call_domain: Daily domain for the call
    """

    from_phone: str
    to_phone: str
    call_id: str
    call_domain: str


class AgentRequest(BaseModel):
    """Request data sent to bot start endpoint.

    Add any custom data here needed for the agent. For example,
    you may add an API call to your backend to get the customer's
    name or other information.

    Attributes:
        room_url: Daily room URL for the bot to join
        token: Authentication token for the Daily room
        call_id: Unique identifier for the call
        call_domain: Daily domain for the call
    """

    room_url: str
    token: str
    call_id: str
    call_domain: str
    # Include any custom data here needed for the agent


async def call_data_from_request(request: Request) -> DailyCallData:
    """Parse and validate Daily PSTN webhook data from incoming request.

    Args:
        request: FastAPI request object containing webhook data

    Returns:
        DailyCallData: Parsed and validated call data

    Raises:
        HTTPException: If required fields are missing from the webhook data
    """
    data = await request.json()
    print(data)

    if not all(key in data for key in ["From", "To", "callId", "callDomain"]):
        raise HTTPException(
            status_code=400, detail="Missing properties 'From', 'To', 'callId', 'callDomain'"
        )

    return DailyCallData(
        from_phone=str(data.get("From")),
        to_phone=str(data.get("To")),
        call_id=data.get("callId"),
        call_domain=data.get("callDomain"),
    )


async def create_daily_room(
    call_data: DailyCallData, session: aiohttp.ClientSession
) -> DailyRoomConfig:
    """Create a Daily room configured for PSTN dial-in.

    Args:
        call_data: Call data containing caller phone number and call details
        session: Shared aiohttp session for making HTTP requests

    Returns:
        DailyRoomConfig: Configuration object with room_url and token

    Raises:
        HTTPException: If room creation fails
    """
    try:
        return await configure(session, sip_caller_phone=call_data.from_phone)
    except Exception as e:
        logger.error(f"Error creating Daily room: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create Daily room: {str(e)}")


async def start_bot_production(agent_request: AgentRequest, session: aiohttp.ClientSession):
    """Start the bot via Pipecat Cloud API for production deployment.

    Args:
        agent_request: Agent configuration with room_url, token, and call details
        session: Shared aiohttp session for making HTTP requests

    Raises:
        HTTPException: If required environment variables are missing or API call fails
    """
    pipecat_api_key = os.getenv("PIPECAT_API_KEY")
    agent_name = os.getenv("PIPECAT_AGENT_NAME")

    if not pipecat_api_key or not agent_name:
        raise HTTPException(
            status_code=500,
            detail="PIPECAT_API_KEY and PIPECAT_AGENT_NAME required for production mode",
        )

    logger.debug(f"Starting bot via Pipecat Cloud for call {agent_request.call_id}")

    body_data = agent_request.model_dump(exclude_none=True)

    async with session.post(
        f"https://api.pipecat.daily.co/v1/public/{agent_name}/start",
        headers={
            "Authorization": f"Bearer {pipecat_api_key}",
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
        logger.debug(f"Bot started successfully via Pipecat Cloud")


async def start_bot_local(agent_request: AgentRequest, session: aiohttp.ClientSession):
    """Start the bot via local /start endpoint for development.

    Args:
        agent_request: Agent configuration with room_url, token, and call details
        session: Shared aiohttp session for making HTTP requests

    Raises:
        HTTPException: If LOCAL_SERVER_URL is not set or API call fails
    """

    local_server_url = os.getenv("LOCAL_SERVER_URL", "http://localhost:7860")

    logger.debug(f"Starting bot via local /start endpoint for call {agent_request.call_id}")

    body_data = agent_request.model_dump(exclude_none=True)

    async with session.post(
        f"{local_server_url}/start",
        headers={"Content-Type": "application/json"},
        json={
            "createDailyRoom": False,  # We already created the room
            "body": body_data,
        },
    ) as response:
        if response.status != 200:
            error_text = await response.text()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start bot via local /start endpoint: {error_text}",
            )
        logger.debug(f"Bot started successfully via local /start endpoint")
