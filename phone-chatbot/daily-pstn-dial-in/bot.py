#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Daily PSTN dial-in bot.

This bot demonstrates how to receive inbound phone calls using Daily's PSTN capabilities.
The bot answers incoming calls and conducts voice conversations with callers.
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import DailyDialinRequest, RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)


async def run_bot(transport: BaseTransport, handle_sigint: bool) -> None:
    """Run the voice bot for an inbound call.

    Sets up the bot pipeline with STT, LLM, and TTS services, then handles
    the conversation when a caller connects.

    Args:
        transport: Daily transport for the call
        handle_sigint: Whether to handle SIGINT signals
    """

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        settings=CartesiaTTSService.Settings(
            voice="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Use Helpful Woman voice by default
        ),
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            system_instruction=(
                "You are a friendly phone assistant. Your responses will be read aloud, "
                "so keep them concise and conversational. Avoid special characters or "
                "formatting. Begin by greeting the caller and asking how you can help them today."
            ),
        ),
    )

    # Setup the conversational context
    context = LLMContext()
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

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        ),
    )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.debug(f"First participant joined: {participant['id']}")
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await worker.cancel()

    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, sip_endpoint):
        logger.info(f"Dial-in ready: {sip_endpoint}")

    @transport.event_handler("on_dialin_connected")
    async def on_dialin_connected(transport, data):
        logger.info(f"Dial-in connected: {data}")

    @transport.event_handler("on_dialin_stopped")
    async def on_dialin_stopped(transport, data):
        logger.info(f"Dial-in stopped: {data}")
        await worker.cancel()

    @transport.event_handler("on_dialin_warning")
    async def on_dialin_warning(transport, data):
        logger.warning(f"Dial-in warning: {data}")

    @transport.event_handler("on_dialin_error")
    async def on_dialin_error(transport, data):
        logger.error(f"Dial-in error: {data}")
        await worker.cancel()

    @transport.event_handler("on_dtmf_event")
    async def on_dtmf_event(transport, data):
        logger.info(f"DTMF event: {data}")

    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud.

    Parses the runner arguments, configures the Daily transport with dial-in
    settings, and starts the bot to handle the incoming call.

    Args:
        runner_args: Arguments from the Pipecat runner containing room details,
            call ID, and call domain for the inbound call

    Raises:
        Exception: If bot initialization or execution fails
    """

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    # create_transport builds the Daily transport and transparently applies the
    # PSTN dial-in settings from runner_args.body (the Daily API key/url and the
    # call_id/call_domain), so the bot only supplies the params it cares about.
    transport = await create_transport(runner_args, transport_params)

    # Optional: personalize using the dial-in request (which number called, which
    # number was dialed).
    if isinstance(runner_args.body, dict) and "dialin_settings" in runner_args.body:
        request = DailyDialinRequest.model_validate(runner_args.body)
        if request.dialin_settings.From:
            logger.info(f"Handling call from: {request.dialin_settings.From}")
        if request.dialin_settings.To:
            logger.info(f"Handling call to: {request.dialin_settings.To}")

    await run_bot(transport, runner_args.handle_sigint)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
