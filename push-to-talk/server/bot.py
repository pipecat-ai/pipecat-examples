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
    InterruptionFrame,
    LLMRunFrame,
    StartFrame,
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
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams, DailyInputTransportMessageFrame
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat_whisker import WhiskerObserver

load_dotenv(override=True)

# We store functions so objects (e.g. SileroVADAnalyzer) don't get
# instantiated. The function will be called when the desired transport gets
# selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        # No VAD for push-to-talk - the button controls when to listen
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
    def __init__(self):
        super().__init__()
        self._gate_opened = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Log all frame types for debugging
        logger.debug(f"PushToTalkGate received frame: {frame.__class__.__name__}, gate_opened={self._gate_opened}")

        # Always pass through StartFrame
        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            return

        # Handle RTVI client messages (if RTVI processor is working)
        if isinstance(frame, RTVIClientMessageFrame):
            logger.info(f"RTVI Frame received: {frame.type} - {frame.data}")
            self._handle_rtvi_frame(frame)
            await self.push_frame(frame, direction)
            return
        
        # Handle Daily transport messages directly (since RTVI processor isn't converting them)
        if isinstance(frame, DailyInputTransportMessageFrame):
            message = frame.message
            logger.debug(f"Transport message frame: {message}")
            # Check if it's an RTVI message
            if message.get('label') == 'rtvi-ai' and 'data' in message:
                data = message['data']
                msg_type = data.get('t')
                msg_data = data.get('d')
                logger.info(f"RTVI message from transport: {msg_type} - {msg_data}")
                if msg_type == "push_to_talk" and msg_data:
                    if msg_data.get("state") == "start":
                        self._gate_opened = True
                        logger.info("Input gate opened - user started talking")
                    elif msg_data.get("state") == "stop":
                        self._gate_opened = False
                        logger.info("Input gate closed - user stopped talking")
            # Don't pass through transport message frames to the pipeline
            return

        # For all other frames: suppress audio-related frames when gate is closed
        # We don't include UserStoppedSpeakingFrame because it's an important signal to tell
        # the UserContextAggregator that the user is done speaking and to push the aggregation.
        if not self._gate_opened and isinstance(
            frame,
            (
                InputAudioRawFrame,
                UserStartedSpeakingFrame,
                InterruptionFrame,
            ),
        ):
            logger.trace(f"{frame.__class__.__name__} suppressed - Button not pressed")
            return
        
        # Log when audio frames pass through
        if isinstance(frame, (InputAudioRawFrame, UserStartedSpeakingFrame)):
            logger.info(f"Audio frame passing through - gate is open: {frame.__class__.__name__}")
        
        # If we get here, push the frame through
        await self.push_frame(frame, direction)

    def _handle_rtvi_frame(self, frame: RTVIClientMessageFrame):
        if frame.type == "push_to_talk" and frame.data:
            data = frame.data
            if data.get("state") == "start":
                self._gate_opened = True
                logger.info("Input gate opened - user started talking")
            elif data.get("state") == "stop":
                self._gate_opened = False
                logger.info("Input gate closed - user stopped talking")


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    push_to_talk_gate = PushToTalkGate()

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]), transport=transport)
    
    # Add event handler to see raw app messages from Daily
    @transport.event_handler("on_app_message")
    async def on_app_message(transport, message, sender):
        logger.info(f"Raw app message received: {message} from {sender}")

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
            push_to_talk_gate,  # Gate BEFORE RTVI so it sees all frames
            rtvi,
            stt,
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    whisker = WhiskerObserver(pipeline, file_name="push-to-talk.bin")

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi), whisker],
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
