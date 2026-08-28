#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Verification tools for the SMS verification bot.

Tools are declared as **direct functions**: a single async function is both the
handler and the schema. Pipecat derives the tool's name, description, parameters
and which of them are required from the signature and the Google-style
docstring, so listing the functions in ``LLMContext(tools=TOOLS)`` is all it
takes — no ``FunctionSchema`` and no separate registration step.

The per-call state the tools need — the number being verified, the code that was
sent, how many attempts are left — lives in a ``VerificationSession``, shared
with the handlers via ``PipelineWorker(app_resources=...)`` and read back as
``params.app_resources``.
"""

import re

from loguru import logger
from pipecat.frames.frames import EndWorkerFrame
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.services.llm_service import FunctionCallParams

from events import bus
from sms import generate_code, send_verification_sms

MAX_ATTEMPTS = 2

# What the bot says once a code is on its way. The keypad option only exists on a
# real phone call, so the DTMF and voice-only variants differ.
INPUT_LINE_DTMF = (
    "Your six digit code is on its way. When it arrives, you have two options: "
    "you can say the six digits out loud, or you can type them on your phone keypad "
    "and press the pound key when you are done."
)
INPUT_LINE_VOICE_ONLY = (
    "Your six digit code is on its way. When it arrives, please read the six digits back to me."
)

RETRY_OPTIONS_DTMF = (
    "you can say the six digits out loud, or you can type them on your "
    "phone keypad and press the pound key when you are done"
)
RETRY_OPTIONS_VOICE_ONLY = "please read the six digits back to me"


def normalize_digits(raw: str) -> str:
    """Strip everything that is not a digit. Handles 'one two three' poorly —
    rely on the LLM to convert words to digits before calling the tool."""
    return re.sub(r"\D", "", raw or "")


class VerificationSession:
    """Per-call verification state, shared with the tools as ``app_resources``.

    One instance per call: it holds the number being verified, the code that was
    last sent, how many attempts have been used, and whether the frontend has
    already been told the outcome.
    """

    def __init__(self, phone_number: str, dtmf_enabled: bool) -> None:
        """Initialize the session.

        Args:
            phone_number: The phone number to verify.
            dtmf_enabled: Whether the caller can type the code on a phone keypad.
        """
        self.phone_number = phone_number
        self.dtmf_enabled = dtmf_enabled
        self.code: str | None = None
        self.attempts = 0
        self.resolved = False

    @property
    def input_line(self) -> str:
        """The line the bot says once a code has been sent."""
        return INPUT_LINE_DTMF if self.dtmf_enabled else INPUT_LINE_VOICE_ONLY

    @property
    def retry_options(self) -> str:
        """The input options phrase, worded for a retry."""
        return RETRY_OPTIONS_DTMF if self.dtmf_enabled else RETRY_OPTIONS_VOICE_ONLY

    async def emit(self, event: dict, llm_service=None) -> None:
        """Publish an event to in-call (RTVI) and out-of-call (SSE) listeners.

        Args:
            event: The event payload to publish.
            llm_service: The LLM service to push an ``RTVIServerMessageFrame``
                through, for clients watching from inside the call. Omit it for
                events raised outside the pipeline.
        """
        if event.get("type") == "verification_result":
            self.resolved = True
        await bus.publish(event)
        if llm_service is not None:
            await llm_service.push_frame(RTVIServerMessageFrame(data=event))


async def send_verification_code(params: FunctionCallParams, phone_number: str) -> None:
    """Send a six-digit verification code by SMS to the user's phone number.

    Args:
        phone_number: E.164 phone number, e.g. +15551234567.
    """
    session: VerificationSession = params.app_resources
    target = phone_number or session.phone_number
    code = generate_code()
    sent = send_verification_sms(target, code)
    if sent:
        session.code = code
        logger.info(f"Verification code for {target}: {code}")
        await params.result_callback(
            {
                "sent": True,
                "say": session.input_line,
            }
        )
    else:
        await params.result_callback(
            {
                "sent": False,
                "say": "I wasn't able to send the code. Please try again later.",
                "end_call": True,
            }
        )


async def verify_code(params: FunctionCallParams, digits: str) -> None:
    """Verify the six digits the user provided.

    Returns match status and the next spoken line.

    Args:
        digits: The six digits the user provided, joined as a single numeric string (e.g. '482915').
    """
    session: VerificationSession = params.app_resources
    received = normalize_digits(digits)

    if session.code and received == session.code:
        await session.emit({"type": "verification_result", "success": True}, llm_service=params.llm)
        await params.result_callback(
            {
                "matched": True,
                "say": "Perfect, those digits match. You're verified. Goodbye!",
                "end_call": True,
            }
        )
        return

    session.attempts += 1
    await session.emit({"type": "verification_result", "success": False}, llm_service=params.llm)

    if session.attempts >= MAX_ATTEMPTS:
        await params.result_callback(
            {
                "matched": False,
                "say": "Those digits did not match and we've used all our attempts. Goodbye!",
                "end_call": True,
            }
        )
        return

    # Retry: send a fresh code automatically.
    new_code = generate_code()
    sent = send_verification_sms(session.phone_number, new_code)
    if sent:
        session.code = new_code
        logger.info(f"Retry code for {session.phone_number}: {new_code}")
        await params.result_callback(
            {
                "matched": False,
                "retry_sent": True,
                "say": (
                    "Those digits did not match. I just sent a new six digit code. "
                    f"When it arrives, {session.retry_options}."
                ),
            }
        )
    else:
        await params.result_callback(
            {
                "matched": False,
                "retry_sent": False,
                "say": "Those digits did not match and I couldn't send a new code. Goodbye!",
                "end_call": True,
            }
        )


async def end_call(params: FunctionCallParams) -> None:
    """End the call. Use only when the tool result tells you to."""
    await params.result_callback(None)
    await params.llm.push_frame(EndWorkerFrame())


TOOLS = [send_verification_code, verify_code, end_call]
