#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

import aiohttp
from fastapi import HTTPException, Request
from loguru import logger
from pipecat.runner.daily import DailyRoomConfig, configure
from pydantic import BaseModel


class TwilioCallData(BaseModel):
    """Data received from Twilio call webhook.

    Attributes:
        call_sid: Unique identifier for the call
        from_phone: The caller's phone number
        to_phone: The dialed phone number
    """

    call_sid: str
    from_phone: str
    to_phone: str


class AgentRequest(BaseModel):
    """Request data sent to bot start endpoint.

    Attributes:
        room_url: Daily room URL for the bot to join
        token: Authentication token for the Daily room
        call_sid: Unique identifier for the call
        sip_uri: SIP URI for the call
    """

    room_url: str
    token: str
    call_sid: str
    sip_uri: str


async def twilio_call_data_from_request(request: Request):
    # Get form data from Twilio webhook
    form_data = await request.form()
    data = dict(form_data)

    # Extract call ID (required to forward the call later)
    call_sid = data.get("CallSid")
    if not call_sid:
        raise HTTPException(status_code=400, detail="Missing CallSid in request")

    # Extract the caller's phone number
    from_phone = data.get("From")
    if not from_phone:
        raise HTTPException(status_code=400, detail="Missing From in request")

    # Extract the caller's phone number
    to_phone = data.get("To")
    if not to_phone:
        raise HTTPException(status_code=400, detail="Missing To in request")

    return TwilioCallData(call_sid=call_sid, from_phone=from_phone, to_phone=to_phone)


async def create_daily_room(
    call_data: TwilioCallData, session: aiohttp.ClientSession
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
        raise HTTPException(status_code=500, detail=f"Failed to create Daily room: {e!s}")


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

    logger.debug(f"Starting bot via Pipecat Cloud for call {agent_request.call_sid}")

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

    logger.debug(f"Starting bot via local /start endpoint for call {agent_request.call_sid}")

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
