#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""simple_dialin.py.

Daily PSTN Dial-in Bot.
"""

import json
import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.runner.types import RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyDialinSettings, DailyParams, DailyTransport

load_dotenv()


async def run_bot(transport: BaseTransport, handle_sigint: bool) -> None:
    """Run the voice bot with the given parameters."""

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Use Helpful Woman voice by default
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # Initialize LLM context with system prompt
    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly phone assistant. Your responses will be read aloud, "
                "so keep them concise and conversational. Avoid special characters or "
                "formatting. Begin by greeting the caller and asking how you can help them today."
            ),
        },
    ]

    # Setup the conversational context
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.debug(f"First participant joined: {participant['id']}")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.debug(f"Participant left: {participant}, reason: {reason}")
        await task.cancel()

    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, cdata):
        logger.debug(f"Dial-in ready: {cdata}")

    @transport.event_handler("on_dialin_connected")
    async def on_dialin_connected(transport, data):
        logger.debug(f"Dial-in connected: {data}")

    @transport.event_handler("on_dialin_stopped")
    async def on_dialin_stopped(transport, data):
        logger.debug(f"Dial-in stopped: {data}")

    @transport.event_handler("on_dialin_error")
    async def on_dialin_error(transport, data):
        logger.error(f"Dial-in error: {data}")
        # If there is an error, the bot should leave the call
        # This may be also handled in on_participant_left with
        # await task.cancel()

    @transport.event_handler("on_dialin_warning")
    async def on_dialin_warning(transport, data):
        logger.warning(f"Dial-in warning: {data}")

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    # Body is always a dict (compatible with both local and Pipecat Cloud)
    body_data = runner_args.body
    room_url = runner_args.room_url
    token = runner_args.token
    call_id = body_data.get("callId")
    call_domain = body_data.get("callDomain")

    if not all([call_id, call_domain]):
        logger.error("Call ID and Call Domain are required in the body.")
        return None

    daily_dialin_settings = DailyDialinSettings(call_id=call_id, call_domain=call_domain)

    transport_params = DailyParams(
        api_url=os.getenv("DAILY_API_URL", "https://api.daily.co/v1"),
        api_key=os.getenv("DAILY_API_KEY", ""),
        dialin_settings=daily_dialin_settings,
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=False,
        vad_analyzer=SileroVADAnalyzer(),
        transcription_enabled=True,
    )

    transport = DailyTransport(
        room_url,
        token,
        "Simple Dial-in Bot",
        transport_params,
    )

    await run_bot(transport, runner_args.handle_sigint)
