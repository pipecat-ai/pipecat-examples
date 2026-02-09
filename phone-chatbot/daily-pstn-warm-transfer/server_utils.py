#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Utilities for Daily PSTN warm transfer webhook handling and bot management.

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
from pipecat.transports.daily.utils import DailyRoomProperties, DailyRoomSipParams
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


class TransferTarget(BaseModel):
    """A single transfer destination.

    Attributes:
        name: Display name for the transfer target (e.g., "Sales Team")
        phone_number: Phone number in E.164 format (e.g., "+15551234567")
        extension: Optional extension to dial after connecting
        description: Description of what this team handles, used by LLM to select
    """

    name: str
    phone_number: str
    extension: str | None = None
    description: str


class TransferMessages(BaseModel):
    """Configurable messages for transfer states.

    Attributes:
        hold_message: Message spoken to customer before putting them on hold
        transfer_failed_message: Message spoken if transfer fails
        connecting_message: Message spoken to agent before connecting customer
    """

    hold_message: str = "I'm connecting you with a specialist. Please hold."
    transfer_failed_message: str = (
        "I'm sorry, I couldn't reach anyone at this time. How else can I help you?"
    )
    connecting_message: str = "I have the customer ready. Let me bring them in now."


class WarmTransferConfig(BaseModel):
    """Configuration for warm transfer functionality.

    Attributes:
        transfer_targets: List of available transfer destinations
        transfer_messages: Customizable messages for transfer states
    """

    transfer_targets: list[TransferTarget]
    transfer_messages: TransferMessages = TransferMessages()


class AgentRequest(BaseModel):
    """Request data sent to bot start endpoint.

    Attributes:
        room_url: Daily room URL for the bot to join
        token: Authentication token for the Daily room
        call_id: Unique identifier for the SIP call
        call_domain: Daily domain for the SIP call
        warm_transfer_config: Configuration for warm transfer
    """

    room_url: str
    token: str
    call_id: str
    call_domain: str
    warm_transfer_config: WarmTransferConfig


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
    logger.debug(f"Received webhook data: {data}")

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
    """Create a Daily room configured for PSTN dial-in with dialout capability.

    Args:
        call_data: Call data containing caller phone number and call details
        session: Shared aiohttp session for making HTTP requests

    Returns:
        DailyRoomConfig: Configuration object with room_url and token

    Raises:
        HTTPException: If room creation fails
    """
    try:
        room_properties = DailyRoomProperties(
            enable_dialout=True,
            sip=DailyRoomSipParams(display_name=call_data.from_phone),
        )
        return await configure(session, room_properties=room_properties)
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

    body_data = agent_request.model_dump()

    async with session.post(
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


async def start_bot_local(agent_request: AgentRequest, session: aiohttp.ClientSession):
    """Start the bot via local /start endpoint for development.

    Args:
        agent_request: Agent configuration with room_url, token, and call details
        session: Shared aiohttp session for making HTTP requests

    Raises:
        HTTPException: If local server URL is not reachable or API call fails
    """
    local_server_url = os.getenv("LOCAL_SERVER_URL", "http://localhost:7860")

    logger.debug(f"Starting bot via local /start endpoint for call {agent_request.call_id}")

    body_data = agent_request.model_dump()

    async with session.post(
        f"{local_server_url}/start",
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
                detail=f"Failed to start bot via local /start endpoint: {error_text}",
            )
        logger.debug("Bot started successfully via local /start endpoint")
