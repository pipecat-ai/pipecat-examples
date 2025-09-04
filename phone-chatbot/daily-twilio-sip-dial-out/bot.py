#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Daily + Twilio SIP dial-out voice bot implementation."""

import os
import sys
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.runner.types import RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

daily_api_key = os.getenv("DAILY_API_KEY", "")
daily_api_url = os.getenv("DAILY_API_URL", "https://api.daily.co/v1")


async def run_bot(transport: DailyTransport, dialout_settings: dict, handle_sigint: bool) -> None:
    """Run the voice bot with the given parameters.

    Args:
        transport: The Daily transport instance
        dialout_settings: Dial-out configuration containing SIP URI
    """
    logger.info(f"Starting dial-out bot")
    logger.debug(f"Dialout settings: {dialout_settings}")

    if not dialout_settings.get("sip_uri"):
        logger.error("Dial-out sip_uri not found in the dial-out settings")
        return

    # Extract sip_uri
    sip_uri = dialout_settings["sip_uri"]
    logger.info(f"Will dial out to: {sip_uri}")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    # Create system message and initialize messages list
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

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Build pipeline
    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    # Create pipeline task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    max_retries = 5
    retry_count = 0
    dialout_successful = False

    # Build dialout parameters conditionally
    dialout_params = {"sipUri": sip_uri}

    logger.debug(f"Dialout parameters: {dialout_params}")

    async def attempt_dialout():
        """Attempt to start dialout with retry logic."""
        nonlocal retry_count, dialout_successful

        if retry_count < max_retries and not dialout_successful:
            retry_count += 1
            logger.info(f"Attempting dialout (attempt {retry_count}/{max_retries}) to: {sip_uri}")
            await transport.start_dialout(dialout_params)
        else:
            logger.error(f"Maximum retry attempts ({max_retries}) reached. Giving up on dialout.")

    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        # Start initial dialout attempt
        logger.debug(f"Dialout settings detected; starting dialout to number: {sip_uri}")
        await attempt_dialout()

    @transport.event_handler("on_dialout_connected")
    async def on_dialout_connected(transport, data):
        logger.debug(f"Dial-out connected: {data}")

    @transport.event_handler("on_dialout_answered")
    async def on_dialout_answered(transport, data):
        nonlocal dialout_successful
        logger.debug(f"Dial-out answered: {data}")
        dialout_successful = True  # Mark as successful to stop retries
        # Automatically start capturing transcription for the participant
        await transport.capture_participant_transcription(data["sessionId"])
        # The bot will wait to hear the user before the bot speaks

    @transport.event_handler("on_dialout_error")
    async def on_dialout_error(transport, data: Any):
        logger.error(f"Dial-out error (attempt {retry_count}/{max_retries}): {data}")

        if retry_count < max_retries:
            logger.info(f"Retrying dialout")
            await attempt_dialout()
        else:
            logger.error(f"All {max_retries} dialout attempts failed. Stopping bot.")
            await task.cancel()

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.debug(f"First participant joined: {participant['id']}")

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.debug(f"Participant left: {participant}, reason: {reason}")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""

    # Extract all details from the body parameter
    body = getattr(runner_args, "body", {})
    room_url = body.get("room_url")
    token = body.get("token")
    dialout_settings = body.get("dialout_settings", {})
    handle_sigint = body.get("handle_sigint", False)

    if not dialout_settings:
        logger.error("Missing dialout_settings in body")
        raise ValueError("dialout_settings are required in the body parameter")

    if not room_url or not token:
        logger.error(f"Missing room connection details: room_url={room_url}, token={token}")
        raise ValueError("room_url and token are required")

    logger.info(f"Starting bot for room: {room_url}")

    transport = DailyTransport(
        room_url,
        token,
        "Dial-out Bot",
        params=DailyParams(
            api_url=daily_api_url,
            api_key=daily_api_key,
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_out_enabled=False,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    await run_bot(transport, dialout_settings, handle_sigint)
