#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    LLMRunFrame,
    StartFrame,
    StartInterruptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
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
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

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


class DebugLogger(FrameProcessor):
    """Logs all frames passing through for debugging"""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        # Log all frame types to see what's coming through
        frame_type = type(frame).__name__
        if "RTVI" in frame_type or "Message" in frame_type:
            logger.info(f"DebugLogger: {frame_type} - direction: {direction}")
            if isinstance(frame, RTVIClientMessageFrame):
                logger.info(f"  RTVI Frame details: type={frame.type}, data={frame.data}")
            # Log Daily message frame content
            elif "Daily" in frame_type and "Message" in frame_type:
                # Try to access the message content using getattr with fallback
                message_attr = getattr(frame, "message", None)
                if message_attr:
                    logger.info(f"  Daily Message content: {message_attr}")
                data_attr = getattr(frame, "data", None)
                if data_attr:
                    logger.info(f"  Daily Message data: {data_attr}")
                # Log all public attributes to understand the structure
                public_attrs = [attr for attr in dir(frame) if not attr.startswith("_")]
                logger.info(f"  Daily Message attributes: {public_attrs}")
        await self.push_frame(frame, direction)


class PushToTalkGate(FrameProcessor):
    def __init__(self):
        super().__init__()
        self._gate_opened = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Debug: Log all frames to see if RTVIClientMessageFrame is coming through
        if isinstance(frame, RTVIClientMessageFrame):
            logger.info(
                f"PushToTalkGate received RTVIClientMessageFrame: type={frame.type}, data={frame.data}"
            )

        # If the gate is closed, suppress all audio frames until the user releases the button
        # We don't include the UserStoppedSpeakingFrame because it's an important signal to tell
        # the UserContextAggregator that the user is done speaking and to push the aggregation.
        if not self._gate_opened and isinstance(
            frame,
            (
                InputAudioRawFrame,
                UserStartedSpeakingFrame,
                StartInterruptionFrame,
                UserStoppedSpeakingFrame,
            ),
        ):
            logger.trace(f"{frame.__class__.__name__} suppressed - Button not pressed")
        else:
            await self.push_frame(frame, direction)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY", ""))

    push_to_talk_gate = PushToTalkGate()

    debug_logger = DebugLogger()

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]), transport=transport)

    logger.info("Setting up RTVI event handler for push-to-talk")

    # Handle push-to-talk messages via RTVI event handler
    @rtvi.event_handler("on_client_message")
    async def on_client_message(processor, message_type, data):
        logger.info(
            f"!!! RTVI EVENT HANDLER CALLED !!! Received client message: type={message_type}, data={data}"
        )
        if message_type == "push_to_talk":
            if data and data.get("state") == "start":
                push_to_talk_gate._gate_opened = True
                logger.info("Input gate opened - user started talking")
            elif data and data.get("state") == "stop":
                push_to_talk_gate._gate_opened = False
                logger.info("Input gate closed - user stopped talking")
        else:
            logger.info(f"Received other client message type: {message_type}")

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
            debug_logger,  # Debug logging
            rtvi,
            push_to_talk_gate,
            stt,
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
        await task.queue_frames([LLMRunFrame()])

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
