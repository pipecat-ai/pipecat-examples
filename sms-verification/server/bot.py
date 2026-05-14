#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""SMS verification bot.

Greets the caller, offers to send a 6-digit code by SMS, then asks the caller to
read the code back. Confirms or rejects the spoken digits and signals the
frontend with success or failure events. Allows one retry; ends the call on
success or on the second failed attempt.

Runs against two transports from a single ``run_bot()``:

* **Twilio WebSocket** — the frontend just displays a phone number to dial; the
  caller's number comes from Twilio's call info (caller ID).
* **SmallWebRTC** — the frontend captures the user's phone number in a form
  and passes it as ``request_data.phone_number`` on the WebRTC offer.

The bot pushes ``RTVIServerMessageFrame`` for in-call clients (WebRTC mode) and
publishes the same payload to the SSE bus for clients watching from outside the
call (Twilio mode).
"""

import os
import re

from dotenv import load_dotenv
from fastapi import WebSocket
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndTaskFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams

# Swap GoogleLLMService for OpenAILLMService by uncommenting the import below
# and the `llm = OpenAILLMService(...)` block in ``run_bot``.
# from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from events import bus
from sms import generate_code, send_verification_sms

load_dotenv(override=True)


MAX_ATTEMPTS = 2


SYSTEM_PROMPT = """You are a friendly verification assistant on a voice call.

You have the user's phone number on file: {phone_number}.

Follow this script exactly:
1. Greet the user warmly in one short sentence and ask "Can I send a confirmation code to your phone to verify your number? Carrier fees may apply."
2. If they say yes, call the `send_verification_code` tool with their phone number.
3. Tell them the code is on its way and to read back the six digits when it arrives.
4. When they speak the digits, call the `verify_code` tool with the digits joined as a single string (e.g. "123456").
5. Use the tool result's `say` field as your spoken reply, then immediately call the `end_call` tool if the result includes `end_call: true`. If a new code was sent for a retry, ask the user to read the new digits when it arrives.

Your output will be converted to audio. Do not include emoji or special characters."""


def normalize_digits(raw: str) -> str:
    """Strip everything that is not a digit. Handles 'one two three' poorly —
    rely on the LLM to convert words to digits before calling the tool."""
    return re.sub(r"\D", "", raw or "")


async def run_bot(transport: BaseTransport, phone_number: str) -> None:
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GoogleLLMService.Settings(
            system_instruction=SYSTEM_PROMPT.format(phone_number=phone_number),
        ),
    )

    # To use OpenAI instead, comment out the GoogleLLMService block above and
    # uncomment the two lines below (and the import at the top of the file):
    # llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
    # # When using OpenAI, pass the system prompt via context messages instead
    # # of `system_instruction`.

    state = {"code": None, "attempts": 0, "resolved": False}

    async def emit(event: dict, llm_service=None) -> None:
        """Publish an event to in-call (RTVI) and out-of-call (SSE) listeners."""
        if event.get("type") == "verification_result":
            state["resolved"] = True
        await bus.publish(event)
        if llm_service is not None:
            await llm_service.push_frame(RTVIServerMessageFrame(data=event))

    async def handle_send_code(params: FunctionCallParams) -> None:
        target = params.arguments.get("phone_number") or phone_number
        code = generate_code()
        sent = send_verification_sms(target, code)
        if sent:
            state["code"] = code
            logger.info(f"Verification code for {target}: {code}")
            await params.result_callback(
                {
                    "sent": True,
                    "say": "I just sent you a six digit code. Read it back to me when it arrives.",
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

    async def handle_verify_code(params: FunctionCallParams) -> None:
        spoken = normalize_digits(params.arguments.get("digits", ""))
        expected = state["code"]

        if expected and spoken == expected:
            await emit({"type": "verification_result", "success": True}, llm_service=params.llm)
            await params.result_callback(
                {
                    "matched": True,
                    "say": "Perfect, those digits match. You're verified. Goodbye!",
                    "end_call": True,
                }
            )
            return

        state["attempts"] += 1
        await emit({"type": "verification_result", "success": False}, llm_service=params.llm)

        if state["attempts"] >= MAX_ATTEMPTS:
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
        sent = send_verification_sms(phone_number, new_code)
        if sent:
            state["code"] = new_code
            logger.info(f"Retry code for {phone_number}: {new_code}")
            await params.result_callback(
                {
                    "matched": False,
                    "retry_sent": True,
                    "say": "Those digits did not match. I just sent a new code. Read back the new six digits when it arrives.",
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

    async def handle_end_call(params: FunctionCallParams) -> None:
        await params.result_callback({"ended": True})
        await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

    llm.register_function("send_verification_code", handle_send_code)
    llm.register_function("verify_code", handle_verify_code)
    llm.register_function("end_call", handle_end_call)

    tools = ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name="send_verification_code",
                description="Send a six-digit verification code by SMS to the user's phone number.",
                properties={
                    "phone_number": {
                        "type": "string",
                        "description": "E.164 phone number, e.g. +15551234567",
                    },
                },
                required=["phone_number"],
            ),
            FunctionSchema(
                name="verify_code",
                description="Verify the six digits the user spoke back. Returns match status and the next spoken line.",
                properties={
                    "digits": {
                        "type": "string",
                        "description": "The six digits the user spoke, joined as a single numeric string (e.g. '482915').",
                    },
                },
                required=["digits"],
            ),
            FunctionSchema(
                name="end_call",
                description="End the call. Use only when the tool result tells you to.",
                properties={},
                required=[],
            ),
        ]
    )

    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected; starting conversation")
        context.add_message(
            {"role": "user", "content": "Please greet the user and start the verification flow."}
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected; cancelling task")
        if not state["resolved"]:
            await bus.publish({"type": "verification_result", "success": False})
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    await runner.run(task)


# ---------------------------------------------------------------------------
# Transport-specific entry points
# ---------------------------------------------------------------------------


async def bot_twilio(websocket: WebSocket) -> None:
    """Entry point for Twilio Media Streams."""
    _, call_data = await parse_telephony_websocket(websocket)

    call_sid = call_data["call_id"]
    stream_sid = call_data["stream_id"]

    # Fetch caller ID from Twilio REST. This is the phone number we'll send the SMS to.
    phone_number = await _fetch_caller_id(call_sid)
    if not phone_number:
        logger.error("Could not determine caller ID; aborting")
        return
    logger.info(f"Inbound call {call_sid} from {phone_number}")

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    await run_bot(transport, phone_number)


async def bot_webrtc(webrtc_connection: SmallWebRTCConnection, phone_number: str) -> None:
    """Entry point for browser WebRTC sessions."""
    logger.info(f"WebRTC session for {phone_number}")
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_10ms_chunks=2,
        ),
    )
    await run_bot(transport, phone_number)


async def _fetch_caller_id(call_sid: str) -> str | None:
    """Look up the caller's phone number via Twilio REST."""
    import aiohttp

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return None

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"
    auth = aiohttp.BasicAuth(account_sid, auth_token)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, auth=auth) as response:
            if response.status != 200:
                logger.error(f"Twilio call lookup failed: {response.status}")
                return None
            data = await response.json()
            return data.get("from")
