#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
from typing import Optional

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotInterruptionFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    StartFrame,
    StartInterruptionFrame,
    StopInterruptionFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import (
    RTVIClientMessageFrame,
    RTVIConfig,
    RTVIObserver,
    RTVIProcessor,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.sync.base_notifier import BaseNotifier
from pipecat.sync.event_notifier import EventNotifier
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketParams
from pipecat.transports.services.daily import DailyParams

load_dotenv(override=True)

# We store functions so objects (e.g. SileroVADAnalyzer) don't get
# instantiated. The function will be called when the desired transport gets
# selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ),
}


class PushToTalkGate(FrameProcessor):
    def __init__(self, flush_notifier: BaseNotifier):
        super().__init__()
        self._flush_notifier = flush_notifier
        self._gate_opened = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)

        elif isinstance(frame, RTVIClientMessageFrame):
            await self._handle_rtvi_frame(frame)
            await self.push_frame(frame, direction)

        # If the gate is closed, suppress all audio frames until the user releases the button
        # We don't include the UserStoppedSpeakingFrame because it's an important signal to tell
        # the UserContextAggregator that the user is done speaking and to push the aggregation.
        if not self._gate_opened and isinstance(
            frame,
            (
                InputAudioRawFrame,
                UserStartedSpeakingFrame,
                StartInterruptionFrame,
                StopInterruptionFrame,
            ),
        ):
            logger.trace(f"{frame.__class__.__name__} suppressed - Button not pressed")
        else:
            await self.push_frame(frame, direction)

    async def _handle_rtvi_frame(self, frame: RTVIClientMessageFrame):
        if frame.type == "push_to_talk" and frame.data:
            data = frame.data
            if data.get("state") == "start":
                self._gate_opened = True
                # Push a bot interruption frame to the upstream pipeline
                # This causes the bot to stop speaking and wait for the user to push the button again
                await self.push_frame(BotInterruptionFrame(), FrameDirection.UPSTREAM)
                logger.info("Input gate opened - user started talking")
            elif data.get("state") == "stop":
                self._gate_opened = False
                await self._flush_notifier.notify()
                logger.info("Input gate closed - user stopped talking")


class STTBuffer(FrameProcessor):
    def __init__(self, flush_notifier: BaseNotifier):
        super().__init__()
        self._buffer = []
        self._flush_notifier = flush_notifier
        self._notify_task: Optional[asyncio.Task] = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            # Start the wait_for_notify task
            if self._notify_task is None or self._notify_task.done():
                self._notify_task = asyncio.create_task(self._wait_for_notify())
            await self.push_frame(frame, direction)

        elif isinstance(frame, (EndFrame, CancelFrame)):
            # Stop the wait_for_notify task
            if self._notify_task and not self._notify_task.done():
                self._notify_task.cancel()
                try:
                    await self._notify_task
                except asyncio.CancelledError:
                    pass
                self._notify_task = None
            await self.push_frame(frame, direction)

        elif isinstance(frame, (InterimTranscriptionFrame, TranscriptionFrame)):
            # Buffer the transcription frame
            self._buffer.append(frame)
            logger.debug(f"Buffered transcription: {frame.text}")

        else:
            await self.push_frame(frame, direction)

    async def _wait_for_notify(self):
        """Wait for flush notification and then flush the buffer."""
        try:
            while True:
                await self._flush_notifier.wait()
                await self._flush_buffer()
        except asyncio.CancelledError:
            logger.debug("STTBuffer notify task cancelled")
            raise

    async def _flush_buffer(self):
        """Flush all buffered transcription frames."""
        if self._buffer:
            logger.info(f"Flushing {len(self._buffer)} transcription frames")
            for frame in self._buffer:
                await self.push_frame(frame, FrameDirection.DOWNSTREAM)
            self._buffer.clear()
        else:
            logger.debug("No transcription frames to flush")


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    flush_notifier = EventNotifier()

    push_to_talk_gate = PushToTalkGate(flush_notifier)
    stt_buffer = STTBuffer(flush_notifier)

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            rtvi,
            push_to_talk_gate,
            stt,
            stt_buffer,  # Buffer transcriptions until button is released
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
