#
# Copyright (c) 2024–2025, Daily
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
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
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
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

from bot_utils.turn_audio_uploader import TurnAudioUploader

load_dotenv(override=True)

conversation_id = f"pipecat-test-conversation-001_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
debug_log_filename = os.path.join(os.getcwd(), f"{conversation_id}.log")
print(f"debug_log_filename: {debug_log_filename}")


def setup_tracer_provider():
    """
    Setup the tracer provider.
    """
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
        # Register the Phoenix tracer provider
        from phoenix.otel import register as register_phoenix

        # run `phoenix serve` in a separate shell window
        # and open http://localhost:6006
        return register_phoenix(project_name="default")


tracer_provider = setup_tracer_provider()
PipecatInstrumentor().instrument(
    tracer_provider=tracer_provider,
    debug_log_filename=debug_log_filename,
)


async def fetch_weather_from_api(params: FunctionCallParams):
    await params.result_callback({"conditions": "nice", "temperature": "75"})


# We store functions so objects (e.g. SileroVADAnalyzer) don't get
# instantiated. The function will be called when the desired transport gets
# selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport):
    logger.info(f"Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GoogleLLMService.Settings(
            model="gemini-2.5-flash",
            system_instruction="You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
        ),
    )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    # You can also register a function_name of None to get all functions
    # sent to the same callback with an additional function_name parameter.
    llm.register_function("get_current_weather", fetch_weather_from_api)

    @llm.event_handler("on_function_calls_started")
    async def on_function_calls_started(service, function_calls):
        await tts.queue_frame(TTSSpeakFrame("Let me check on that."))

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
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # enable_turn_audio=True is required for on_user_turn_audio_data /
    # on_bot_turn_audio_data events. buffer_size=0 disables the merged-audio
    # event since we only want per-turn segments.
    audio_buffer = AudioBufferProcessor(buffer_size=0, enable_turn_audio=True)

    audio_uploader = TurnAudioUploader(
        conversation_id=conversation_id,
        s3_key_prefix=os.getenv("AWS_S3_PREFIX", "pipecat-turn-audio"),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            audio_buffer,
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        # Optionally, add a conversation ID for session tracking
        conversation_id=conversation_id,
    )

    # PipecatInstrumentor.instrument() wraps PipelineTask.__init__ to auto-inject
    # an OpenInferenceObserver. Look it up so we can set attributes on its
    # _turn_span from the audio_buffer event handlers.
    # this is hacky - just for POC.
    oi_observer = next(
        (o for o in task._observer._observers if isinstance(o, OpenInferenceObserver)),
        None,
    )
    if oi_observer is None:
        raise RuntimeError("OpenInferenceObserver not found on PipelineTask")

    @audio_buffer.event_handler("on_user_turn_audio_data")
    async def on_user_turn_audio_data(buffer, audio, sample_rate, num_channels):
        if oi_observer._turn_span is None:
            logger.warning("No active turn span; skipping user audio attribute")
            return
        turn_number = oi_observer._turn_count
        url = audio_uploader.get_presigned_url_and_upload(
            audio, sample_rate, num_channels, turn_number, role="user"
        )
        oi_observer._turn_span.set_attribute("audio.user.url", url)
        logger.info(f"Turn {turn_number} user audio URL set on span")

    @audio_buffer.event_handler("on_bot_turn_audio_data")
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
        await audio_buffer.start_recording()
        # Kick off the conversation.
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
