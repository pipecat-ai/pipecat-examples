#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import uuid

from dotenv import load_dotenv
from loguru import logger
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
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
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.responses.llm import (
    OpenAIResponsesLLMService,
    OpenAIResponsesReasoningConfig,
)
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.utils.tracing.setup import setup_tracing
from pipecat.workers.runner import WorkerRunner

from langfuse_media import uploader_from_env

load_dotenv(override=True)

IS_TRACING_ENABLED = bool(os.getenv("ENABLE_TRACING"))

# Initialize tracing if enabled
if IS_TRACING_ENABLED:
    # Create the exporter
    otlp_exporter = OTLPSpanExporter()

    # Set up tracing with the exporter
    setup_tracing(
        service_name="pipecat-demo",
        exporter=otlp_exporter,
        console_export=bool(os.getenv("OTEL_CONSOLE_EXPORT")),
    )
    logger.info("OpenTelemetry tracing initialized")


async def get_current_weather(params: FunctionCallParams, location: str, format: str):
    """Get the current weather.

    Args:
        location: The city and state, e.g. "San Francisco, CA".
        format: The temperature unit to use. Must be either "celsius" or "fahrenheit". Infer this from the user's location.
    """
    await params.result_callback({"conditions": "nice", "temperature": "75"})


def _eval_transport_params():
    """Params for the eval transport, imported lazily.

    The eval harness ships as an optional extra (``pipecat-ai[evals]``), so importing it
    at module scope would make the demo unrunnable without it.
    """
    from pipecat.evals.transport import EvalTransportParams

    return EvalTransportParams(audio_in_enabled=True, audio_out_enabled=True)


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
    # Lets `pipecat eval run` drive this bot. See the README for the command.
    "eval": lambda: _eval_transport_params(),
}


def _conversation_span(worker: PipelineWorker):
    """Get the open OpenTelemetry ``conversation`` span, or None.

    Prefers the public ``conversation_span`` property. Older Pipecat releases only have the
    private attribute, so fall back to that. Both lookups are guarded, so a release that
    changes either one degrades to "no audio on the trace" rather than failing the call.
    """
    observer = worker.turn_trace_observer
    if observer is None:
        return None
    return getattr(observer, "conversation_span", None) or getattr(
        observer, "_conversation_span", None
    )


async def run_bot(transport: BaseTransport):
    logger.info(f"Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    llm = OpenAIResponsesLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAIResponsesLLMService.Settings(
            model="gpt-5.4",
            reasoning=OpenAIResponsesReasoningConfig(effort="low"),
            system_instruction="You are a helpful assistant in a voice conversation. Your responses will be spoken aloud, so avoid emojis, bullet points, or other formatting that can't be spoken. Respond to what the user said in a creative, helpful, and brief way.",
        ),
    )

    @llm.event_handler("on_function_calls_started")
    async def on_function_calls_started(service, function_calls):
        await tts.queue_frame(TTSSpeakFrame("Let me check on that."))

    # Direct functions listed in the context are registered with the LLM automatically.
    context = LLMContext(tools=[get_current_weather])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    conversation_id = str(uuid.uuid4())

    # Records the call so it can be played back from the Langfuse trace. Stereo keeps the
    # user on the left and the bot on the right, so an interruption reads as overlap.
    # buffer_size=0 means the whole recording arrives in a single on_audio_data event when
    # recording stops, which is all we need since we upload before the trace is exported.
    audiobuffer = AudioBufferProcessor(num_channels=2, buffer_size=0)

    uploader = uploader_from_env() if IS_TRACING_ENABLED else None
    if uploader:
        uploader.attach(audiobuffer)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            # After transport.output() so we capture what was actually played, including
            # bot speech cut short by an interruption.
            audiobuffer,
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        enable_tracing=IS_TRACING_ENABLED,
        # Use the conversation ID as the Langfuse session ID so traces are
        # grouped in the Sessions view and correlate with conversation.id
        conversation_id=conversation_id,
        additional_span_attributes={"langfuse.session.id": conversation_id},
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        await audiobuffer.start_recording()
        # Kick off the conversation.
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")

        if uploader:
            # Upload here, before worker.cancel(). Langfuse treats a persisted trace as
            # immutable, so the media token has to land on the conversation span while
            # that span is still open, and PipelineWorker ends it during cleanup.
            await uploader.finalize(_conversation_span(worker))
        else:
            await audiobuffer.stop_recording()

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
