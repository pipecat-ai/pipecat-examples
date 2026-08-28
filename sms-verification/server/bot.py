#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""SMS verification bot.

Greets the caller, offers to send a 6-digit code by SMS, then asks the caller to
read the code back — or, on a phone call, type it on the keypad (DTMF) and press
'#'. Confirms or rejects the digits and signals the frontend with success or
failure events. Allows one retry; ends the call on success or on the second
failed attempt.

A single ``bot(runner_args)`` entry point runs against two transports:

* **Twilio WebSocket** — the frontend just displays a phone number to dial; the
  caller's number comes from Twilio's REST API via ``get_call_info``.
* **SmallWebRTC** — the frontend captures the user's phone number in a form
  and passes it as ``request_data.phone_number`` on the WebRTC offer.

The bot pushes ``RTVIServerMessageFrame`` for in-call clients (WebRTC mode) and
publishes the same payload to the SSE bus for clients watching from outside the
call (Twilio mode).

The verification tools themselves live in ``tools.py``; the per-call state they
share is a ``VerificationSession`` passed to the worker as ``app_resources``.
"""

import os

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.dtmf_aggregator import DTMFAggregator
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments, WebSocketRunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService

# Swap GoogleLLMService for OpenAILLMService by uncommenting the import below
# and the `llm = OpenAILLMService(...)` block in ``run_bot``.
# from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner
from pydantic import BaseModel

from tools import TOOLS, VerificationSession

load_dotenv(override=True)


SYSTEM_PROMPT = """You are a friendly verification assistant on a voice call.

You have the user's phone number on file: {phone_number}.

Follow this script exactly:
1. Greet the user warmly in one short sentence and ask "Can I send a confirmation code to your phone to verify your number? Carrier fees may apply."
2. If they say yes, call the `send_verification_code` tool with their phone number.
3. After the tool returns, say this line verbatim (do not paraphrase, do not drop the keypad or pound-key options):
   "{input_line}"
4. When you receive the digits, call the `verify_code` tool with the digits joined as a single string (e.g. "123456"). The digits may arrive as spelled-out words or as a numeric string; treat any six-digit sequence you receive as the code.
5. Use the tool result's `say` field as your spoken reply, then immediately call the `end_call` tool if the result includes `end_call: true`. If a new code was sent for a retry, the tool result's `say` field already covers both input options — use it as-is without paraphrasing.

Your output will be converted to audio. Do not include emoji or special characters."""


class CallInfo(BaseModel):
    """Caller details fetched from the Twilio REST API."""

    from_number: str | None = None
    to_number: str | None = None


async def get_call_info(call_sid: str | None) -> CallInfo | None:
    """Fetch caller/callee numbers from the Twilio REST API.

    The Twilio Media Streams "start" event does not carry the caller ID unless
    the TwiML explicitly forwards it as a stream ``<Parameter>``. Looking it up
    via the REST API keeps the demo working with the runner's default TwiML.

    Args:
        call_sid: The Twilio call SID (e.g. call_data.call_id), or None.

    Returns:
        A CallInfo with the caller's numbers, or None if it couldn't be fetched.
    """
    if not call_sid:
        return None

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    if not account_sid or not auth_token:
        logger.warning("Missing Twilio credentials, cannot fetch call info")
        return None

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"

    try:
        # Use HTTP Basic Auth with aiohttp
        auth = aiohttp.BasicAuth(account_sid, auth_token)

        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Twilio API error ({response.status}): {error_text}")
                    return None

                data = await response.json()

                return CallInfo(from_number=data.get("from"), to_number=data.get("to"))

    except Exception as e:
        logger.error(f"Error fetching call info from Twilio: {e}")
        return None


async def run_bot(
    transport: BaseTransport, phone_number: str, dtmf_enabled: bool, runner_args: RunnerArguments
) -> None:
    """Run the bot.

    Args:
        transport: The transport to use.
        phone_number: The phone number to verify.
        dtmf_enabled: Whether DTMF is enabled.
        runner_args: The runner arguments.
    """
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    # Per-call state for the tools in tools.py; handed to them below as the
    # worker's `app_resources`.
    session = VerificationSession(phone_number=phone_number, dtmf_enabled=dtmf_enabled)

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GoogleLLMService.Settings(
            system_instruction=SYSTEM_PROMPT.format(
                phone_number=phone_number,
                input_line=session.input_line,
            ),
        ),
    )

    context = LLMContext(tools=TOOLS)
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
            # Buffers keypad presses (as InputDTMFFrames from the Twilio serializer)
            # and flushes them as a TranscriptionFrame when the user presses '#' or
            # after `timeout` seconds of idle — so the LLM sees typed digits the same
            # way it sees spoken digits. In WebRTC mode no DTMF frames arrive, so
            # this is a pass-through.
            DTMFAggregator(
                timeout=10.0,
                termination_digit=KeypadEntry.POUND,
                prefix="",
            ),
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        # Shared with the tool handlers via params.app_resources
        app_resources=session,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected; starting conversation")
        context.add_message(
            {"role": "user", "content": "Please greet the user and start the verification flow."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected; cancelling task")
        if not session.resolved:
            await session.emit({"type": "verification_result", "success": False})
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""

    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_10ms_chunks=2,
        ),
        "twilio": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    # WebRTC clients pass the phone number in the offer's request_data (mirrored
    # to runner_args.body). Twilio calls need a REST lookup because the runner's
    # default TwiML does not forward the caller ID as a stream parameter, so
    # call_data.from_number is empty.
    call_data = runner_args.call_data
    call_info = await get_call_info(call_data.call_id) if call_data else None
    phone_number = (runner_args.body or {}).get("phone_number", "").strip() or (
        call_info.from_number if call_info else None
    )

    if not phone_number:
        logger.error("Could not determine phone number; aborting")
        return

    # DTMF (phone keypad) input only makes sense when the caller is on an actual
    # phone. WebRTC clients are in the browser and have no keypad tied to the
    # call audio, so we keep that path voice-only.
    dtmf_enabled = isinstance(runner_args, WebSocketRunnerArguments)

    logger.info(f"Running verification for {phone_number} (dtmf_enabled={dtmf_enabled})")
    await run_bot(transport, phone_number, dtmf_enabled, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
