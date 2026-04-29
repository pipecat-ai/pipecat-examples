#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat pipeline for the Bandwidth inbound chatbot example.

Builds an OpenAI-only voice agent (realtime STT + LLM + TTS) that talks to a
caller over a Bandwidth Programmable Voice WebSocket media stream.
"""

import os

from fastapi import WebSocket
from loguru import logger
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
from pipecat.serializers.bandwidth import BandwidthFrameSerializer
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAIRealtimeSTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)


async def run_bot(websocket: WebSocket, start_event: dict) -> None:
    """Run the Pipecat pipeline for a single Bandwidth call.

    Args:
        websocket: FastAPI WebSocket already connected to Bandwidth.
        start_event: The first JSON message from Bandwidth, which carries
            ``metadata`` with ``streamId``, ``callId``, and ``accountId``.
    """
    metadata = start_event.get("metadata", {})
    stream_id = metadata.get("streamId")
    call_id = metadata.get("callId")
    account_id = metadata.get("accountId") or os.getenv("BANDWIDTH_ACCOUNT_ID")
    logger.info(f"Bandwidth call: stream={stream_id} call={call_id} account={account_id}")

    serializer = BandwidthFrameSerializer(
        stream_id=stream_id,
        call_id=call_id,
        account_id=str(account_id) if account_id else None,
        client_id=os.getenv("BANDWIDTH_CLIENT_ID"),
        client_secret=os.getenv("BANDWIDTH_CLIENT_SECRET"),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    api_key = os.getenv("OPENAI_API_KEY")
    llm = OpenAILLMService(
        api_key=api_key,
        settings=OpenAILLMService.Settings(
            system_instruction=(
                "You are a helpful voice assistant talking to someone on the phone. "
                "Keep responses short and conversational. Your output is converted to "
                "speech, so avoid special characters and markdown."
            ),
        ),
    )
    stt = OpenAIRealtimeSTTService(api_key=api_key)
    tts = OpenAITTSService(api_key=api_key)

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
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
            audio_in_sample_rate=8000,
            # OpenAI TTS only outputs 24kHz. Run the pipeline at 24kHz on the
            # output side; BandwidthFrameSerializer resamples down to 8kHz
            # μ-law on the wire.
            audio_out_sample_rate=24000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        context.add_message(
            {"role": "user", "content": "Greet the caller and ask how you can help."}
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
