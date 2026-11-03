#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import json
import os
import secrets

from dotenv import load_dotenv
from fastapi import status
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, OutputTransportMessageUrgentFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments, WebSocketRunnerArguments
from pipecat.serializers.genesys import GenesysAudioHookSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.openai.responses.llm import OpenAIResponsesLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    llm = OpenAIResponsesLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAIResponsesLLMService.Settings(
            system_instruction="You are a helpful assistant answering a phone call. Your responses will be spoken aloud, so avoid emojis, bullet points, or other formatting that can't be spoken. Respond to what the caller said in a helpful and brief way.",
        ),
    )

    stt = DeepgramFluxSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from Genesys
            stt,  # Speech-To-Text
            user_aggregator,
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to Genesys
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Kick off the conversation.
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the caller."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()

    await runner.run()


async def bot(runner_args: WebSocketRunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""

    websocket = runner_args.websocket

    # Genesys sends the Audio Connector integration's API key in the X-API-KEY
    # header. Genesys can't request a Pipecat Cloud session token, so this check
    # is what keeps other clients from starting the bot.
    expected_key = os.getenv("GENESYS_API_KEY", "")
    api_key = websocket.headers.get("x-api-key", "")
    if not expected_key or not secrets.compare_digest(api_key, expected_key):
        logger.warning("Rejected connection: missing or wrong X-API-KEY")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # The serializer answers Genesys's protocol messages (open, ping, close) and
    # converts audio between Genesys's 8 kHz μ-law and the pipeline.
    serializer = GenesysAudioHookSerializer()

    # Genesys starts the session with an 'open' message. Answer it before the
    # pipeline starts, so the session is ready when on_client_connected fires.
    opened = await serializer.deserialize(await websocket.receive_text())
    if not serializer.is_open or not isinstance(opened, OutputTransportMessageUrgentFrame):
        logger.warning("Genesys didn't open the session")
        await websocket.close()
        return
    await websocket.send_text(json.dumps(opened.message))

    # Identify the caller from the open message. Use it to look up the user and
    # personalize the bot.
    participant = serializer.participant or {}
    logger.info(f"From number: {participant.get('ani')}")

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=serializer,
            # Genesys rate-limits incoming messages, so send audio in 200 ms packets.
            audio_out_10ms_chunks=20,
        ),
    )

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
