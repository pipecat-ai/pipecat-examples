#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# We store functions so objects (e.g. SileroVADAnalyzer) don't get
# instantiated. The function will be called when the desired transport gets
# selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        microphone_out_enabled=False,  # Disable since we just use custom tracks
        audio_out_destinations=["pipecat-mirror"],
    ),
}

load_dotenv(override=True)

class CustomTrackMirrorProcessor(FrameProcessor):
    def __init__(self, transport_destination: str, **kwargs):
        super().__init__(**kwargs)
        self._transport_destination = transport_destination

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame) and frame.transport_source:
            output_frame = OutputAudioRawFrame(
                audio=frame.audio,
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
            )
            output_frame.transport_destination = self._transport_destination
            await self.push_frame(output_frame)
        else:
            await self.push_frame(frame, direction)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            CustomTrackMirrorProcessor("pipecat-mirror"),
            transport.output(),  # Transport bot output
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        await transport.capture_participant_audio(participant["id"], audio_source="pipecat")

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
