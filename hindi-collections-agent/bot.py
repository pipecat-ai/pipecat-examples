#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""A Hindi loan payment reminder call: Deepgram Flux STT + OpenAI + Deepgram Flux TTS.

The call has three steps, written as data in flow.yaml: verify the caller,
remind them of the overdue payment, close the call. handlers.py holds the two
tools the flow calls.

Deepgram Flux decides when the caller starts and stops talking, so this file
has no VAD and no turn-taking code.

Requirements:
- DEEPGRAM_API_KEY
- OPENAI_API_KEY
- DAILY_API_KEY (only for phone dial-in)

Run it:
    uv run bot.py              # talk to it in the browser
    uv run bot.py -t daily     # phone dial-in to a Daily number
    uv run bot.py -t exotel    # phone dial-in to an Exotel number
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pipecat.evals.transport import EvalTransportParams
from pipecat.flows import Flow, FlowConfig, FlowManager
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.flux.tts import DeepgramFluxTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

import handlers

load_dotenv(override=True)

FLOW_CONFIG_PATH = Path(__file__).with_name("flow.yaml")

# One bot, many ways to reach it. The pipeline below is the same for all of them.
#
# Ozonetel: Pipecat has no Ozonetel WebSocket serializer at this time. We
# recommend a SIP trunk instead. Point your Ozonetel SIP trunk at a Daily SIP
# trunk and each call reaches this bot over the "daily" transport below, with
# no bot changes.
# https://docs.daily.co/docs/guides/features/dial-in-dial-out/sip-trunk
transport_params = {
    # Browser (WebRTC), for testing on your computer.
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    # Phone: Daily PSTN dial-in, or any carrier over a Daily SIP trunk.
    "daily": lambda: DailyParams(audio_in_enabled=True, audio_out_enabled=True),
    # Phone: Exotel Voicebot applet. The Exotel serializer is picked for you
    # and converts Exotel's 8 kHz audio to and from the pipeline's rate.
    "exotel": lambda: FastAPIWebsocketParams(audio_in_enabled=True, audio_out_enabled=True),
    # The `pipecat eval` test harness.
    "eval": lambda: EvalTransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    # Flux hears Hindi, English, or a mix of both in one call.
    stt = DeepgramFluxSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramFluxSTTService.Settings(
            model="flux-general-multi",
            language_hints=[Language.HI, Language.EN],
        ),
    )

    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"])

    # A Hindi voice from Deepgram Flux TTS. Any Pipecat TTS drops in here: to
    # use Sarvam, swap this block for SarvamTTSService and change nothing else.
    tts = DeepgramFluxTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramFluxTTSService.Settings(voice="flux-anjali-hi"),
    )

    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    # The call script is data: load flow.yaml and join it to handlers.py.
    flow = Flow(FlowConfig.from_file(FLOW_CONFIG_PATH), handlers=handlers)
    flow_manager = FlowManager(
        worker=worker,
        llm=llm,
        context_aggregator=context_aggregator,
        transport=transport,
        global_functions=flow.global_functions,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Caller connected")
        await flow_manager.initialize(flow.initial_node)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Caller disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
