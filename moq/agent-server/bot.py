#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""The voice bot one MoQ call runs.

``run_bot`` builds an STT -> LLM -> TTS pipeline over a transport the host
already created and returns when the client hangs up. It knows nothing about
relays or discovery — see ``direct_host.py`` for that, and ``server.py`` for
the process that ties the two together.

The pipeline is configured from the environment so the same built image
serves every deployment:

    DEEPGRAM_API_KEY / OPENAI_API_KEY / CARTESIA_API_KEY  (required)
    MOQ_VOICE_LLM_MODEL      (default: gpt-4o)
    MOQ_VOICE_TTS_VOICE      (default: British Reading Lady)
    MOQ_VOICE_SYSTEM_PROMPT  (default: a short real-time-voice instruction)
    MOQ_SESSION_IDLE_SECS    (default: 300; 0 disables)
"""

import os

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
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.moq.transport import MOQTransport
from pipecat.workers.runner import WorkerRunner

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant in a real-time voice call. "
    "Your goal is to demonstrate your capabilities in a succinct way. "
    "Your output will be spoken aloud, so avoid special characters that can't easily "
    "be spoken, such as emojis or bullet points. Respond to what the user said in a "
    "creative and helpful way."
)
# Cartesia "British Reading Lady".
DEFAULT_TTS_VOICE = "71a7ad14-091c-4e8e-a314-022ece01c121"

# End a call after this long with no speech in either direction. Idle counts
# speech frames rather than media, so an abandoned open tab publishing silent
# mic audio still ages out.
DEFAULT_SESSION_IDLE_SECS = 300.0


async def run_bot(transport: MOQTransport, session_id: str):
    """Build and run one client's voice pipeline until they disconnect.

    Args:
        transport: The call's MOQ transport, already pointed at this
            client's broadcast paths.
        session_id: The id the client minted, used for logging.
    """
    logger.info(f"Starting bot for client {session_id!r}")

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(
            voice=os.getenv("MOQ_VOICE_TTS_VOICE", DEFAULT_TTS_VOICE),
        ),
    )
    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(
            model=os.getenv("MOQ_VOICE_LLM_MODEL", "gpt-4o"),
            system_instruction=os.getenv("MOQ_VOICE_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        ),
    )

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
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=float(os.getenv("MOQ_SESSION_IDLE_SECS", str(DEFAULT_SESSION_IDLE_SECS)))
        or None,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport):
        logger.info(f"Client {session_id!r} subscribed — starting conversation")
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the user."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_disconnected")
    async def on_disconnected(transport):
        logger.info(f"Client {session_id!r} disconnected")
        await worker.cancel()

    @transport.event_handler("on_error")
    async def on_error(transport, message, exception):
        logger.error(f"MOQ error for {session_id!r}: {message}")

    # The host owns SIGINT and the transport's teardown; this just runs the
    # worker until the client's mic track ends.
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
