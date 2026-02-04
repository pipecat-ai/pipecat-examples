#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Data models for Daily PSTN warm transfer bot.

This module contains Pydantic models for transfer configuration,
including transfer targets, messages, and bot request data.
"""

from pydantic import BaseModel


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
        callId: Unique identifier for the SIP call
        callDomain: Daily domain for the SIP call
        From: Caller's phone number
        To: Called phone number
        warm_transfer_config: Configuration for warm transfer
    """

    room_url: str
    token: str
    callId: str
    callDomain: str
    From: str
    To: str
    warm_transfer_config: WarmTransferConfig
