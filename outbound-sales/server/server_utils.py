#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Utilities for Daily PSTN dial-out handling and bot management.

This module provides data models and functions for:
- Parsing dial-out request data
- Creating Daily rooms for outgoing calls
- Starting bots in production (Pipecat Cloud) or local development mode
"""

import os
import time

import aiohttp
from fastapi import HTTPException, Request
from loguru import logger
from pipecat.runner.daily import DailyRoomConfig, configure
from pipecat.transports.daily.utils import (
    DailyMeetingTokenProperties,
    DailyRoomProperties,
    DailyRoomSipParams,
)
from pydantic import BaseModel


class DialoutSettings(BaseModel):
    """Settings for outbound call.

    Attributes:
        phone_number: The phone number to dial
        caller_id: Optional caller ID to display (if not provided, uses your Daily number)
    """

    phone_number: str
    caller_id: str | None = None


class Lead(BaseModel):
    """Who we're calling. The name personalizes Hailey's greeting.

    Attributes:
        phone: The lead's phone number
        name: The lead's name, if known
        company: The lead's company, if known
    """

    phone: str
    name: str | None = None
    company: str | None = None


class DialoutRequest(BaseModel):
    """Request data for initiating a dial-out call.

    Attributes:
        dialout_settings: Settings for the outbound call
        lead: Who we're calling (defaults to just the phone number)
        call_id: Identifier for this call, used to track its outcome in the
            server's results log (the server mints one if not provided)
    """

    dialout_settings: DialoutSettings
    lead: Lead | None = None
    call_id: str | None = None


class AgentRequest(BaseModel):
    """Request data sent to bot start endpoint.

    Attributes:
        room_url: Daily room URL for the bot to join
        token: Authentication token for the Daily room
        dialout_settings: Settings for the outbound call
        lead: Who we're calling
        call_id: Identifier for this call, used to track its outcome in the
            server's results log
    """

    room_url: str
    token: str
    dialout_settings: DialoutSettings
    lead: Lead
    call_id: str


async def dialout_request_from_request(request: Request) -> DialoutRequest:
    """Parse and validate dial-out request data.

    Args:
        request: FastAPI request object containing dial-out data

    Returns:
        DialoutRequest: Parsed and validated dial-out request

    Raises:
        HTTPException: If required fields are missing from the request data
    """
    data = await request.json()

    if not data.get("dialout_settings"):
        raise HTTPException(
            status_code=400, detail="Missing 'dialout_settings' in the request body"
        )

    try:
        return DialoutRequest.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request data: {str(e)}")


async def create_daily_room(
    dialout_request: DialoutRequest, session: aiohttp.ClientSession
) -> DailyRoomConfig:
    """Create a Daily room configured for PSTN dial-out.

    Args:
        dialout_request: Dial-out request containing phone number and settings
        session: Shared aiohttp session for making HTTP requests

    Returns:
        DailyRoomConfig: Configuration object with room_url and token

    Raises:
        HTTPException: If room creation fails
    """
    try:
        # Same properties configure() would build for a dial-out room, plus
        # audio-only cloud recording. start_cloud_recording on the bot's token
        # starts the recording automatically when the bot joins, before the
        # phone leg connects, so the callee never hears a recording
        # announcement. Recordings are listed and downloaded via Daily's
        # REST API.
        room_properties = DailyRoomProperties(
            exp=time.time() + 2 * 60 * 60,
            eject_at_room_exp=True,
            enable_dialout=True,
            enable_recording="cloud-audio-only",
            sip=DailyRoomSipParams(
                display_name=dialout_request.dialout_settings.phone_number,
                video=False,
                sip_mode="dial-in",
                num_endpoints=1,
            ),
            start_video_off=True,
        )
        token_properties = DailyMeetingTokenProperties(
            enable_recording="cloud-audio-only",
            start_cloud_recording=True,
        )
        return await configure(
            session, room_properties=room_properties, token_properties=token_properties
        )
    except Exception as e:
        logger.error(f"Error creating Daily room: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create Daily room: {str(e)}")


async def report_result(row: dict[str, str]) -> None:
    """Report one call outcome to server.py, which logs it and keeps it in memory.

    This demo's stand-in for persistence; a real production app would write
    the outcome to a database. Best effort: a failed report is logged, not
    raised, so it never breaks call shutdown.

    Args:
        row: The outcome row, as built by CallResult.to_row() in bot.py
    """
    server_url = os.getenv("SERVER_URL", "http://localhost:8080")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{server_url}/call_result", json=row) as response:
                response.raise_for_status()
    except Exception as e:
        logger.warning(f"Could not report call result to {server_url}: {e}")


async def start_bot_production(agent_request: AgentRequest, session: aiohttp.ClientSession):
    """Start the bot via Pipecat Cloud API for production deployment.

    Args:
        agent_request: Agent configuration with room_url, token, and dialout settings
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

    logger.debug(
        f"Starting bot via Pipecat Cloud for dial-out to {agent_request.dialout_settings.phone_number}"
    )

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
        logger.debug("Bot started successfully via Pipecat Cloud")


async def start_bot_local(agent_request: AgentRequest, session: aiohttp.ClientSession):
    """Start the bot via local /start endpoint for development.

    Args:
        agent_request: Agent configuration with room_url, token, and dialout settings
        session: Shared aiohttp session for making HTTP requests

    Raises:
        HTTPException: If LOCAL_SERVER_URL is not set or API call fails
    """
    local_server_url = os.getenv("LOCAL_SERVER_URL", "http://localhost:7860")

    logger.debug(
        f"Starting bot via local /start endpoint for dial-out to {agent_request.dialout_settings.phone_number}"
    )

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
        logger.debug("Bot started successfully via local /start endpoint")
