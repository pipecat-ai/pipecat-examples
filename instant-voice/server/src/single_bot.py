#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

SYSTEM_INSTRUCTION = f"""
"You are Gemini Chatbot, a friendly, helpful robot.

Your goal is to demonstrate your capabilities in a succinct way.

Your output will be converted to audio so don't include special characters in your answers.

Respond to what the user said in a creative and helpful way. Keep your responses brief. One or two sentences at most.
"""


def extract_arguments():
    parser = argparse.ArgumentParser(description="Instant Voice Example")
    parser.add_argument(
        "-u", "--url", type=str, required=True, help="URL of the Daily room to join"
    )
    parser.add_argument(
        "-t", "--token", type=str, required=False, help="Token of the Daily room to join"
    )
    args, unknown = parser.parse_known_args()
    url = args.url or os.getenv("DAILY_SAMPLE_ROOM_URL")
    token = args.token
    return url, token


async def main():
    room_url, token = extract_arguments()
    print(f"room_url: {room_url}")

    transport = DailyTransport(
        room_url,
        token,
        "Instant voice Chatbot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        voice_id="Puck",  # Aoede, Charon, Fenrir, Kore, Puck
        system_instruction=SYSTEM_INSTRUCTION,
    )

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
            user_aggregator,
            llm,  # LLM
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

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
