#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Storytelling chatbot.

A voice-driven "choose your own adventure" storyteller. Gemini writes the story
a few sentences at a time, a Gemini image model illustrates each page, ElevenLabs narrates it,
and the bot pauses after every scene to ask the listener what should happen next.

Run locally with ``uv run bot.py`` (SmallWebRTC by default) or deploy the same
file to Pipecat Cloud; ``pipecat.runner`` provides the server glue in both cases.
"""

import asyncio
import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.workers.runner import WorkerRunner

from gemini_image import GeminiImageGenService
from processors import StoryImageProcessor, StoryProcessor
from prompts import LLM_BASE_PROMPT
from utils.helpers import load_images

load_dotenv(override=True)

# The hosted demo is shared, so each story ends after this many seconds.
# Set to 0 to disable the limit.
MAX_SESSION_SECS = int(os.getenv("MAX_SESSION_SECS", "300"))

# The bot "video" is the current story illustration, so it needs a video
# output track. We store functions so transport params don't get instantiated
# until the desired transport is selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_width=1024,
        video_out_height=1024,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_width=1024,
        video_out_height=1024,
    ),
}

# Static book images shown before the first illustration is generated.
images = load_images(["book1.png", "book2.png"])


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting storytelling bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # Our creative writer. The image prompts are also generated with this
    # service, out of band, in StoryImageProcessor.
    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GoogleLLMService.Settings(system_instruction=LLM_BASE_PROMPT),
    )

    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsTTSService.Settings(voice=os.getenv("ELEVENLABS_VOICE_ID")),
    )

    # Illustrations come from a Gemini image model (Imagen needs Vertex AI)
    image_gen = GeminiImageGenService(api_key=os.getenv("GOOGLE_API_KEY"))

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # Splits the LLM output into story pages and illustrates each page while
    # it is being narrated.
    story_processor = StoryProcessor()
    image_processor = StoryImageProcessor(llm, image_gen, transport)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            story_processor,
            image_processor,
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
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    session_timer: asyncio.Task | None = None

    async def end_session_after(secs: int):
        await asyncio.sleep(secs)
        logger.info(f"Session limit of {secs}s reached, ending the story")
        # EndFrame lets whatever is queued finish before the pipeline stops.
        await worker.queue_frame(EndFrame())

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        nonlocal session_timer
        logger.debug("Client ready, storytime commence!")
        # Show the book, then let the LLM introduce itself. StoryProcessor
        # hands the turn to the user once the introduction has been spoken.
        await worker.queue_frames([images["book1"], LLMRunFrame(), images["book2"]])
        if MAX_SESSION_SECS > 0 and session_timer is None:
            session_timer = asyncio.create_task(end_session_after(MAX_SESSION_SECS))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    try:
        await runner.run()
    finally:
        if session_timer:
            session_timer.cancel()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
