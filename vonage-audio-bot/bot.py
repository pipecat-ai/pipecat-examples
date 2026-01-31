#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

AUDIO_OUT_SAMPLE_RATE: int = 24_000

# Audio packetization for strict PCM framing
# 640 bytes = 20ms @ 16kHz, PCM16 mono
VONAGE_AUDIO_PACKET_BYTES: int = 640


load_dotenv(override=True)


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        logger.warning(f"{name} is not an int: {v!r}, using default {default}")
        return default


async def run_bot(transport: BaseTransport, handle_sigint: bool, sample_rate: int):
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    stt = OpenAISTTService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-transcribe",
        prompt=("Expect words based on questions across technology, science, and culture."),
    )

    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="coral",
        instructions="There may be literal '\\n' characters; ignore them when speaking.",
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly assistant. "
                "Your responses will be read aloud, so keep them concise and conversational. "
                "Avoid special characters or formatting. "
                "Begin by saying: 'Hello! This is an automated call from our Vonage chatbot demo.' "
            ),
        },
    ]

    context = LLMContext(messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

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

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=AUDIO_OUT_SAMPLE_RATE,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        logger.info("Vonage Audio Connector connected. Waiting for user audio...")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info("Vonage Audio Connector disconnected. Ending call.")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """
    Entry point for your FastAPI /ws endpoint (like the Telnyx server.py pattern).
    Vonage Audio Connector will connect as the WebSocket client.
    """
    # This should match the audioRate you used when calling connect_audio_to_websocket().
    sample_rate = _env_int("VONAGE_AUDIO_RATE", 16000)

    # Vonage serializer: mixed mode (text events + binary audio)
    serializer = VonageFrameSerializer(
        VonageFrameSerializer.InputParams(
            vonage_sample_rate=sample_rate,  # 16000
            sample_rate=None,  # let it use frame.audio_in_sample_rate
        )
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            fixed_audio_packet_size=VONAGE_AUDIO_PACKET_BYTES,
            serializer=serializer,
        ),
    )

    await run_bot(transport, runner_args.handle_sigint, sample_rate)
