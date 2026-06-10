#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
from datetime import datetime

from dotenv import load_dotenv
from loguru import logger
from openinference.instrumentation.pipecat import PipecatInstrumentor
from openinference.instrumentation.pipecat._observer import OpenInferenceObserver
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.turns.user_start.vad_user_turn_start_strategy import VADUserTurnStartStrategy
from pipecat.turns.user_stop.external_user_turn_stop_strategy import (
    ExternalUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from bot_utils.audio_turn_observer import AudioTurnObserver
from bot_utils.audio_turn_uploader import AudioTurnUploader

load_dotenv(override=True)

# One debug log file per process startup. The PipecatInstrumentor wraps
# PipelineWorker.__init__ globally and writes all conversation logs to this
# file. Per-conversation `conversation_id` is generated inside run_bot()
# (which fires once per client connection) so tracing spans aren't shared
# across runs of a long-lived server.
_process_started = datetime.now().strftime("%Y%m%d_%H%M%S")
debug_log_filename = os.path.join(os.getcwd(), f"pipecat-debug_{_process_started}.log")
print(f"debug_log_filename: {debug_log_filename}")


def setup_tracer_provider():
    """Setup the tracer provider (Arize if configured, else local Phoenix)."""
    project_name = os.getenv("ARIZE_PROJECT_NAME", "default")

    ARIZE_SPACE_ID = os.getenv("ARIZE_SPACE_ID")
    ARIZE_API_KEY = os.getenv("ARIZE_API_KEY")
    if ARIZE_SPACE_ID and ARIZE_API_KEY:
        from arize.otel import register as register_arize

        return register_arize(
            space_id=ARIZE_SPACE_ID,
            api_key=ARIZE_API_KEY,
            project_name=project_name,
        )
    else:
        from phoenix.otel import register as register_phoenix

        return register_phoenix(project_name="default")


tracer_provider = setup_tracer_provider()
PipecatInstrumentor().instrument(
    tracer_provider=tracer_provider,
    debug_log_filename=debug_log_filename,
)


async def fetch_weather_from_api(params: FunctionCallParams):
    await params.result_callback({"conditions": "nice", "temperature": "75"})


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


async def run_bot(transport: BaseTransport):
    # Generate a fresh conversation_id per client connection
    conversation_id = f"pipecat-test-conversation-001_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Starting bot, conversation_id={conversation_id}")

    weather_function = FunctionSchema(
        name="get_current_weather",
        description="Get the current weather",
        properties={
            "location": {
                "type": "string",
                "description": "The city and state, e.g. San Francisco, CA",
            },
            "format": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "The temperature unit to use. Infer this from the user's location.",
            },
        },
        required=["location", "format"],
    )
    tools = ToolsSchema(standard_tools=[weather_function])

    # Gemini Live replaces STT + LLM + TTS in one service.
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        system_instruction="You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
        tools=tools,
        settings=GeminiLiveLLMService.Settings(
            voice="Aoede",  # Puck, Charon (default), Kore, Fenrir, Aoede
        ),
    )

    llm.register_function("get_current_weather", fetch_weather_from_api)

    context = LLMContext(tools=tools)
    # Explicit user-turn strategies driven only by the transport's VAD:
    # - VADUserTurnStartStrategy triggers on transport's VADUserStartedSpeakingFrame
    # - ExternalUserTurnStopStrategy triggers on the transport-emitted
    #   UserStoppedSpeakingFrame (which Silero on TransportParams produces)
    # Both have enable_user_speaking_frames=False so the aggregator does NOT
    # re-broadcast UserStarted/StoppedSpeakingFrame upstream — that broadcast
    # was re-triggering user_audio_buffer's on_user_turn_audio_data twice.
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=[VADUserTurnStartStrategy(enable_user_speaking_frames=False)],
                stop=[ExternalUserTurnStopStrategy()],
            ),
        ),
    )

    # bot_audio_buffer captures bot output audio per turn via VAD-driven
    # BotStoppedSpeakingFrame. User audio is captured by AudioTurnObserver
    # internally (see bot_utils/audio_turn_observer.py).
    bot_audio_buffer = AudioBufferProcessor(buffer_size=0, enable_turn_audio=True)

    audio_uploader = AudioTurnUploader(
        conversation_id=conversation_id,
        s3_key_prefix=os.getenv("AWS_S3_PREFIX", "pipecat-turn-audio"),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            bot_audio_buffer,
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        conversation_id=conversation_id,
    )

    # this is kind of ugly - just for POC.

    # PipecatInstrumentor.instrument() wraps PipelineWorker.__init__ to auto-inject
    # an OpenInferenceObserver. Look it up so we can set attributes on its
    # _turn_span from the audio_buffer event handlers.
    oi_observer = next(
        (o for o in worker._observer._observers if isinstance(o, OpenInferenceObserver)),
        None,
    )
    if oi_observer is None:
        raise RuntimeError("OpenInferenceObserver not found on PipelineWorker")

    # and then this is _really_ ugly - just for POC.

    # Swap the auto-injected observer's class to AudioTurnObserver. Each
    # turn span then represents (user audio + bot audio) chronologically —
    # matching Pipecat's user-then-bot turn convention. AudioTurnObserver
    # was originally written for OpenAI Realtime; we're trying it on Gemini
    # Live to see if its frame patterns are similar enough.
    oi_observer.__class__ = AudioTurnObserver
    oi_observer.audio_uploader = audio_uploader

    @bot_audio_buffer.event_handler("on_bot_turn_audio_data")
    async def on_bot_turn_audio_data(buffer, audio, sample_rate, num_channels):
        if oi_observer._turn_span is None:
            logger.warning("No active turn span; skipping bot audio attribute")
            return
        turn_number = oi_observer._turn_count
        url = audio_uploader.get_presigned_url_and_upload(
            audio, sample_rate, num_channels, turn_number, role="bot"
        )
        oi_observer._turn_span.set_attribute("audio.bot.url", url)
        logger.info(f"Turn {turn_number} bot audio URL set on span")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        await bot_audio_buffer.start_recording()
        context.add_message({"role": "user", "content": "Please introduce yourself to the user."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
