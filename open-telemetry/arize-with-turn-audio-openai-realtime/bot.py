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
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.realtime.events import (
    AudioConfiguration,
    AudioInput,
    AudioOutput,
    InputAudioTranscription,
    SemanticTurnDetection,
    SessionProperties,
)
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.turns.user_start.vad_user_turn_start_strategy import VADUserTurnStartStrategy
from pipecat.turns.user_stop.external_user_turn_stop_strategy import (
    ExternalUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from bot_utils.audio_turn_observer import AudioTurnObserver
from bot_utils.audio_turn_uploader import AudioTurnUploader

load_dotenv(override=True)

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

    # OpenAI Realtime replaces STT + LLM + TTS in one service.
    llm = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAIRealtimeLLMService.Settings(
            system_instruction="You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
            session_properties=SessionProperties(
                audio=AudioConfiguration(
                    input=AudioInput(
                        transcription=InputAudioTranscription(model="gpt-4o-transcribe"),
                        turn_detection=SemanticTurnDetection(eagerness="medium"),
                    ),
                    output=AudioOutput(voice="alloy"),
                ),
            ),
        ),
    )

    llm.register_function("get_current_weather", fetch_weather_from_api)

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
    # BotStoppedSpeakingFrame — that signal is reliable because the bot is
    # our own creation. User audio is NOT captured by an AudioBufferProcessor:
    # VAD-driven user-turn detection is unreliable against OpenAI Realtime's
    # chunked server-VAD frames and end-of-response interruption broadcasts.
    # Instead, the AudioTurnObserver buffers user audio internally
    # between BotStoppedSpeakingFrame and the next BotStartedSpeakingFrame.
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

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        conversation_id=conversation_id,
    )

    # this is kind of ugly - just for POC.

    # PipecatInstrumentor.instrument() wraps PipelineTask.__init__ to auto-inject
    # an OpenInferenceObserver. Look it up so we can set attributes on its
    # _turn_span from the audio_buffer event handlers.
    oi_observer = next(
        (o for o in task._observer._observers if isinstance(o, OpenInferenceObserver)),
        None,
    )
    if oi_observer is None:
        raise RuntimeError("OpenInferenceObserver not found on PipelineTask")

    # and then this is _really_ ugly - just for POC.

    # Swap the auto-injected observer's class to our user-first variant. Each
    # turn span then represents (user audio + bot audio) in chronological
    # order — matching Pipecat's user-then-bot turn convention. Bot-speaks-
    # first conversations get a "half" turn 1 with only bot audio; subsequent
    # turns pair the user response to the previous bot utterance with the
    # current bot utterance. State (tracer, conversation_id, etc.) is
    # preserved across the __class__ swap; only method resolution changes.
    # Done before the runner starts, so no frames have been processed under
    # the original class yet.
    oi_observer.__class__ = AudioTurnObserver
    # The observer buffers user audio internally and uploads + stamps the URL
    # at turn boundaries. It needs the uploader as an instance attribute.
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
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
