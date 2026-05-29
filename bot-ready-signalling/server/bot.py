#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

transport_params = {
    "daily": lambda: DailyParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

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

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
