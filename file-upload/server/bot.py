#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""file-upload - Pipecat Voice Agent

This bot uses a cascade pipeline: Speech-to-Text → LLM → Text-to-Speech

Clients can send files and images into the conversation with RTVI's
``send-file`` message, either inline or by uploading to the runner's
``POST /files`` endpoint first (enabled by ``PIPECAT_UPLOADS_FOLDER`` or
``-u/--uploads-folder``). The upload endpoint stores the file and returns a
URL the client passes back in ``send-file``; the LLM service resolves that
URL at completion time through its ``FileResolver``, which is wired to the
same storage backend here. See ``bot_gcs.py`` / ``bot_s3.py`` for backing
uploads with a cloud bucket instead of local disk.

Required AI services:
- Deepgram (Speech-to-Text)
- Anthropic, OpenAI, AWS Bedrock, or Google Gemini via the developer API or
  Vertex AI (LLM; select with -llm, defaults to anthropic)
- Cartesia (Text-to-Speech)

Run the bot using::

    uv run bot.py
    uv run bot.py -llm openai
"""

import argparse
import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.runner.run import runner_file_storage
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.aws.llm import AWSBedrockLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.google.vertex.llm import GoogleVertexLLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.utils.file_resolver import FileResolver
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

SYSTEM_INSTRUCTION = (
    "You are a helpful assistant in a voice conversation. Users can upload images or files to "
    "share visual context with you, and you should refer to that content in your responses. "
    "Your responses will be spoken aloud, so avoid emojis, bullet points, or other formatting "
    "that can't be spoken. Keep responses concise."
)


def create_llm_service(llm_name: str, file_resolver: FileResolver):
    """Create the LLM service for `llm_name` (anthropic, openai, bedrock, gemini, or vertex).

    Every service gets the `file_resolver` so it can resolve file URLs the
    provider can't fetch itself (uploaded files, private URLs) into bytes at
    completion time. Vertex Gemini reads gs:// URLs directly instead, so with
    bot_gcs.py it exercises the pass-through path: the file never moves
    through the bot.
    """
    if llm_name == "vertex":
        # Authenticates via Application Default Credentials
        # (`gcloud auth application-default login`), which must be able to
        # call Vertex AI and — for gs:// pass-through — read the bucket.
        return GoogleVertexLLMService(
            project_id=os.environ["GOOGLE_CLOUD_PROJECT_ID"],
            settings=GoogleVertexLLMService.Settings(system_instruction=SYSTEM_INSTRUCTION),
            file_resolver=file_resolver,
        )
    if llm_name == "openai":
        return OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            settings=OpenAILLMService.Settings(system_instruction=SYSTEM_INSTRUCTION),
            file_resolver=file_resolver,
        )
    if llm_name == "bedrock":
        return AWSBedrockLLMService(
            aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_region=os.getenv("AWS_REGION"),
            settings=AWSBedrockLLMService.Settings(
                model="us.amazon.nova-2-lite-v1:0",
                system_instruction=SYSTEM_INSTRUCTION,
            ),
            file_resolver=file_resolver,
        )
    if llm_name == "gemini":
        return GoogleLLMService(
            api_key=os.getenv("GOOGLE_API_KEY"),
            settings=GoogleLLMService.Settings(system_instruction=SYSTEM_INSTRUCTION),
            file_resolver=file_resolver,
        )
    return AnthropicLLMService(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        settings=AnthropicLLMService.Settings(system_instruction=SYSTEM_INSTRUCTION),
        file_resolver=file_resolver,
    )


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Run the voice bot for this session.

    Args:
        transport: The transport for this session, built by ``create_transport``
            (or by hand for the dial-out/SIP production flows).
        runner_args: Runner session arguments. Carries the request ``body``
            (e.g. dial-out settings, SIP call details) and ``session_id``; the
            standard web/telephony pipelines don't need it.
    """
    logger.info("Starting bot")

    # Speech-to-Text service
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # Text-to-Speech service
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=os.getenv("CARTESIA_VOICE_ID", "71a7ad14-091c-4e8e-a314-022ece01c121"),
        ),
    )

    # LLM service - defaults to anthropic; select another with `-llm openai|bedrock|gemini|vertex`
    # The resolver shares the runner's storage backend, so URLs returned by the
    # POST /files upload endpoint resolve to the uploaded bytes.
    llm_name = getattr(runner_args.cli_args, "llm", None) or "anthropic"
    file_resolver = FileResolver(file_storage=runner_file_storage())
    llm = create_llm_service(llm_name, file_resolver)

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    rtvi = RTVIProcessor()

    # Pipeline - assembled from reusable components
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        rtvi_processor=rtvi,
    )

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation
        context.add_message(
            {
                "role": "developer",
                "content": "Greet the user and let them know they can upload images or files using the Upload File button, and you'll be able to see and discuss what they share.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point."""

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
        "livekit": lambda: LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
        "websocket": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-llm",
        "--llm",
        choices=["anthropic", "openai", "bedrock", "gemini", "vertex"],
        default="anthropic",
        help="LLM provider to use (default: anthropic)",
    )
    main(parser)
