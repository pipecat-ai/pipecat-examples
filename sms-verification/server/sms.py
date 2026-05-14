#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Twilio SMS helper for the verification example."""

import os
import random

from loguru import logger
from twilio.rest import Client


def generate_code() -> str:
    return "".join(random.choices("0123456789", k=6))


def send_verification_sms(to_number: str, code: str) -> bool:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([account_sid, auth_token]) or not (messaging_service_sid or from_number):
        logger.error(
            "Missing Twilio credentials, or neither TWILIO_MESSAGING_SERVICE_SID nor "
            "TWILIO_PHONE_NUMBER is set; cannot send SMS"
        )
        return False

    sender_kwarg = (
        {"messaging_service_sid": messaging_service_sid}
        if messaging_service_sid
        else {"from_": from_number}
    )

    try:
        client = Client(account_sid, auth_token)
        client.messages.create(
            body=f"Your verification code is {code}",
            to=to_number,
            **sender_kwarg,
        )
        logger.info(f"Sent verification SMS to {to_number}")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS to {to_number}: {e}")
        return False
