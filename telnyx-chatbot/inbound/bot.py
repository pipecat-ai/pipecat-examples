#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import random

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.evals.transport import EvalTransportParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.flux.tts import DeepgramFluxTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)


async def run_bot(transport: BaseTransport, handle_sigint: bool):
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        # To use a different OpenAI-compatible endpoint (a proxy, a gateway, or a
        # self-hosted model), pass its URL here. Leave it out to use OpenAI.
        # base_url="https://your-endpoint.example.com/v1",
        settings=OpenAILLMService.Settings(
            system_instruction="You are a helpful LLM in an audio call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
        ),
    )

    # A/B test: each call gets one speech stack. The LLM and prompt are the same
    # in both arms, so any difference comes from STT and TTS. Set AB_VARIANT to
    # "deepgram" or "elevenlabs" to force an arm; leave it unset to pick at random.
    variant = os.getenv("AB_VARIANT") or random.choice(["deepgram", "elevenlabs"])
    logger.info(f"A/B variant: {variant}")

    if variant == "deepgram":
        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            settings=DeepgramSTTService.Settings(
                language=Language.EN_AU,
                # Ideas for a medical phone receptionist:
                #
                # Boost words the caller is likely to say that a general model can
                # miss: doctor names, clinic names, drug names, billing terms.
                # keyterm=["Dr Nguyen", "telehealth", "bulk billing", "amoxicillin"],
                #
                # Write dates, times and phone numbers as digits, so booking
                # details are easier for the LLM to read back and store.
                # smart_format=True,
                #
                # Deepgram's medical model, tuned for clinical terms.
                # model="nova-3-medical",
            ),
        )
        tts = DeepgramFluxTTSService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            settings=DeepgramFluxTTSService.Settings(voice="flux-sharon-en"),
        )
    elif variant == "elevenlabs":
        # ElevenLabs STT has one English code, with no Australian variant.
        stt = ElevenLabsRealtimeSTTService(api_key=os.getenv("ELEVENLABS_API_KEY"))
        tts = ElevenLabsTTSService(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            settings=ElevenLabsTTSService.Settings(
                voice="IKne3meq5aSn9XLyUdCD",  # Charlie, Australian English
            ),
        )
    else:
        raise ValueError(f"Unknown AB_VARIANT: {variant}")

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            user_aggregator,
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
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

    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Kick off the conversation.
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the user."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""

    transport_params = {
        "telnyx": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
        # Lets `pipecat eval` drive the bot for automated tests. See evals/.
        "eval": lambda: EvalTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    # create_transport auto-detects the telephony provider, builds the matching
    # serializer (here the TelnyxFrameSerializer, using TELNYX_API_KEY) and sets
    # add_wav_header=False, so the bot only supplies the params it cares about.
    transport = await create_transport(runner_args, transport_params)

    # Identify the caller from the parsed handshake (call_data is a typed CallData
    # model). Use it to look up the user and personalize the bot.
    call_data = runner_args.call_data
    if call_data:
        logger.info(f"From number: {call_data.from_number}")

    await run_bot(transport, runner_args.handle_sigint)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
