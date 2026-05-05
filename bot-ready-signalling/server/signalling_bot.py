#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
import sys

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from runner import configure

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def main():
    async with aiohttp.ClientSession() as session:
        (room_url, _) = await configure(session)

        transport = DailyTransport(
            room_url,
            None,
            "Say One Thing",
            DailyParams(audio_in_enabled=True, audio_out_enabled=True),
        )

        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            settings=CartesiaTTSService.Settings(
                voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
            ),
        )

        runner = PipelineRunner()

        pipeline = Pipeline([transport.input(), tts, transport.output()])
        task = PipelineTask(pipeline)

        # RTVIProcessor is auto-attached to PipelineTask, and the default
        # on_client_ready handler calls set_bot_ready() for us. We just hook in
        # to push the greeting once the client signals it is ready, so the
        # first words of TTS are never clipped.
        @task.rtvi.event_handler("on_client_ready")
        async def on_client_ready(rtvi):
            await task.queue_frames(
                [
                    TTSSpeakFrame("Hello there, how are you doing today?"),
                    EndFrame(),
                ]
            )

        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
