#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import uuid

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    EndTaskFrame,
    LLMRunFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams

from bot_utils.audio_upload_util import AudioUploader

logger.info(f"Starting bot")

load_dotenv(override=True)


async def terminate_call(params: FunctionCallParams) -> None:
    logger.info("Conversation complete. Terminating call.")

    await params.llm.queue_frame(TTSSpeakFrame("Goodbye."))
    await params.llm.queue_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    idle_timeout_secs = 10
    conversation_id = f"{uuid.uuid4()}"

    # set buffer_size; min chunk size for s3 multipart upload is 5mb
    audio_buffer_size = 5 * 1024 * 1024

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
    )

    # Function to terminate call
    terminate_function = FunctionSchema(
        name="terminate_call",
        description="Terminate the call when user says 'Goodbye' and the call is over.",
        properties={},
        required=[],
    )

    llm.register_function("terminate_call", terminate_call)

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    messages = [
        {
            "role": "system",
            "content": "You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be spoken aloud, so avoid special characters that can't easily be spoken, such as emojis or bullet points. Respond to what the user said in a creative and helpful way.",
        },
    ]

    tools = ToolsSchema(standard_tools=[terminate_function])
    context = LLMContext(messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    audio_buffer = AudioBufferProcessor(buffer_size=audio_buffer_size)

    # set up audio uploader to write to audio files to s3
    audio_uploader = AudioUploader(
        conversation_id, audio_buffer_size, "000000000000_test_conversations"
    )

    # RTVI events for Pipecat client UI
    rtvi = RTVIProcessor()

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            rtvi,
            stt,  # STT
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            audio_buffer,  # collect all audio (user and bot)
            assistant_aggregator,  # Assistant/bot spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=idle_timeout_secs,
        observers=[RTVIObserver(rtvi)],
    )

    #############################
    # audio_buffer event_handlers
    # We show `"on_audio_data"` and `"on_track_audio_data"` examples here
    # Only one event_handler is needed, but as many as all four event_handlers
    # can be set. Find supported events here:
    # https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/processors/audio/audio_buffer_processor.py#L42-L45

    # Triggered when buffer_size is reached, providing merged audio
    @audio_buffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        logger.info(f"`on_audio_data` event fired")
        await audio_uploader.upload_audio_wav_to_s3(audio, sample_rate, num_channels)

    # Triggered when buffer_size is reached, providing separate tracks
    # One track for user audio; One track for bot audio
    @audio_buffer.event_handler("on_track_audio_data")
    async def on_track_audio_data(buffer, user_audio, bot_audio, sample_rate, num_channels):
        logger.info(f"`on_track_audio_data` event fired")

        await audio_uploader.upload_audio_wav_to_s3(bot_audio, sample_rate, num_channels, "bot")
        await audio_uploader.upload_audio_wav_to_s3(user_audio, sample_rate, num_channels, "user")

    #############################

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        await rtvi.set_bot_ready()

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # start recording audio
        await audio_buffer.start_recording()
        messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_left")
    async def on_left(transport):
        logger.info(f"Bot left the call")

    @task.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(task, frame):
        logger.info(f"Pipeline finished")
        await audio_uploader.finalize_upload_audio_wav_to_s3()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point for the bot starter."""

    transport_params = {
        "daily": lambda: DailyParams(
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

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
