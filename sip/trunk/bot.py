#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Dial-in voice agent for the SIP-trunk webhook path.

``server.py`` starts one instance of this bot per ``sip_trunk.incoming``
notification, on the per-call account the notification carries — the
account reaches :func:`bot` inside ``runner_args.body`` and
``create_transport`` picks it out of ``body["sip_client"]``.

The bot also runs standalone, against any account the environment names
(or the temporary Daily client the runner provisions when only
``DAILY_API_KEY`` is set)::

    SIP_USER=1001 SIP_PASS=secret SIP_DOMAIN=sip.example.com \\
        uv run python trunk/bot.py -t sip -d

Environment: the agent's ``DEEPGRAM_API_KEY``, ``OPENAI_API_KEY`` and
``CARTESIA_API_KEY``. The ``SIP_*`` settings of :mod:`pipecat.runner.sip`
(``SIP_TRANSPORT``, ``SIP_STUN_SERVER``, the jitter buffer, tracing) apply
to the account; a notification that names its own transport wins.
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.sip.transport import SIPParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

# We use lambdas to defer transport parameter creation until the transport
# type is selected at runtime.
transport_params = {
    "sip": lambda: SIPParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(
            voice="86e30c1d-714b-4074-a1f2-1cb6b552fb49",
        ),
    )

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(
            system_instruction="You are a helpful assistant on a phone call. Your responses will be spoken aloud, so avoid emojis, bullet points, or other formatting that can't be spoken. Respond to what the user said in a creative, helpful, and brief way.",
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            user_aggregator,  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        # Kick off the conversation.
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the user."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, sip_endpoint):
        # REGISTER OK — the account is routable. Never fires in trunk mode
        # (reg_interval=0); use on_connected as the ready signal there.
        logger.info(f"Ready for dial-in: {sip_endpoint}")

    @transport.event_handler("on_dialin_connected")
    async def on_dialin_connected(transport, data):
        logger.info(f"Dial-in connected: {data}")

    @transport.event_handler("on_dialin_stopped")
    async def on_dialin_stopped(transport, data):
        logger.info(f"Dial-in stopped: {data}")

    @transport.event_handler("on_dialin_error")
    async def on_dialin_error(transport, data):
        logger.error(f"Dial-in error: {data.get('errorMsg')}")

    @transport.event_handler("on_dialin_warning")
    async def on_dialin_warning(transport, data):
        # Non-fatal media-health warnings (e.g. sustained packet loss or a
        # starved transmit buffer) — the call continues.
        logger.warning(f"Dial-in warning: {data.get('errorMsg')}")

    @transport.event_handler("on_dtmf_event")
    async def on_dtmf_event(transport, data):
        # Keypad presses also flow into the pipeline as InputDTMFFrame.
        logger.info(f"DTMF received: {data['tone']}")

    @transport.event_handler("on_call_quality_stats")
    async def on_call_quality_stats(transport, stats):
        # SIP-only: the call's final quality snapshot (duration, packet
        # loss, jitter, RTT, ...) at call close.
        logger.info(f"Call quality: {stats}")

    @transport.event_handler("on_error")
    async def on_error(transport, error):
        # Fatal stack or registration failures (bad credentials,
        # unreachable server).
        logger.error(f"Transport error: {error}")
        await runner.cancel()

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
