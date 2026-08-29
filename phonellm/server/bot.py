#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""phonellm-example - Pipecat Voice Agent

This bot uses a cascade pipeline: Speech-to-Text → LLM → Text-to-Speech

Required AI services:
- Deepgram Flux (Speech-to-Text)
- LLM: PhoneLLM on Modal (default) or OpenAI, selected with ``LLM_SERVICE``
- TTS: Deepgram Flux (default) or Cartesia, selected with ``TTS_SERVICE``

Run the bot using::

    uv run bot.py
"""

import os
from datetime import datetime

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
from pipecat.processors.frameworks.rtvi import (
    RTVIFunctionCallReportLevel,
    RTVIObserverParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.flux.tts import DeepgramFluxTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.tts_service import TextAggregationMode
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.workers.runner import WorkerRunner

from tools import TOOLS, ReservationStore

load_dotenv(override=True)


# Voice defaults per TTS service; override either with TTS_VOICE.
DEFAULT_DEEPGRAM_VOICE = "flux-heather-en"
DEFAULT_CARTESIA_VOICE = "86e30c1d-714b-4074-a1f2-1cb6b552fb49"

SYSTEM_INSTRUCTION = (
    "You are a restaurant reservation assistant on a phone call.{powered_by} "
    "Today is {today_spoken} ({today_iso}). "
    "Your job is to take reservations: use your tools to look up, create, and update reservations. "
    "Before creating a reservation you need the caller's name, party size, date, and time. "
    "The name is required as much as the rest: ask for it alongside the day and time, never "
    "as an afterthought once the time is settled. "
    "Once the caller has said what they want, ask for everything still missing in one sentence, "
    "and don't ask for any of it before they've said what they're after. Ask only for what "
    "they haven't given you: never ask again for a detail they already stated, and if they "
    "gave you all four, book it without asking anything. "
    "Whenever you ask for missing details, the name has to be one of them unless they've "
    "already told you it — a question about the day and time alone is never enough. "
    "Every time a caller asks for is available: you have no way to check availability and no "
    "tool for it, so never offer to check and never say you are checking. "
    "Don't announce what you are about to do, and don't narrate your own tool use — no "
    '"let me check", no "one moment", no "booking that for you now". Either answer, or '
    "call the tool and then say what it did. "
    'Resolve relative dates like "tomorrow" or "next Friday" against today\'s date, and pass '
    "dates to your tools in YYYY-MM-DD format. "
    'Say dates the short way a person would on the phone: "tomorrow", "Saturday", or "the 29th". '
    "Never say the year, and never read a YYYY-MM-DD date aloud — that format is for tool "
    "arguments only. "
    "Confirm the details back to the caller, and share the confirmation number after booking. "
    "When the caller says goodbye, or their reservation is settled and they need nothing else, "
    "say a short goodbye and then call end_call in that same turn. The line stays open until "
    "you do — saying goodbye on its own leaves the caller sitting on a live call. "
    "Keep responses brief. Your responses are spoken aloud, so never reply with nothing."
)


def ordinal(day: int) -> str:
    """Return a day of the month with its English ordinal suffix, e.g. 1 -> "1st"."""
    suffix = "th" if day in (11, 12, 13) else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def build_system_instruction(powered_by: str = "") -> str:
    """Fill in the system instruction, stamping it with today's date.

    Called per session so a long-running server doesn't get stuck on the date
    it started up.
    """
    now = datetime.now()
    return SYSTEM_INSTRUCTION.format(
        powered_by=powered_by,
        # The spoken form models the phrasing we want back on the call; the ISO
        # form is what the tools take, and carries the month and year the model
        # needs to resolve relative dates.
        today_spoken=f"{now:%A} the {ordinal(now.day)}",
        today_iso=f"{now:%Y-%m-%d}",
    )


def require_env(name: str) -> str:
    """Return the value of a required environment variable or raise."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_llm() -> OpenAILLMService:
    """Build the LLM service selected by ``LLM_SERVICE`` (``phonellm`` or ``openai``)."""
    service = os.getenv("LLM_SERVICE", "phonellm").strip().lower()
    logger.info(f"LLM service: {service}")

    if service == "openai":
        return OpenAILLMService(
            api_key=require_env("OPENAI_API_KEY"),
            settings=OpenAILLMService.Settings(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
                system_instruction=build_system_instruction(),
            ),
        )

    if service != "phonellm":
        raise RuntimeError(f"Unknown LLM_SERVICE: {service!r} (expected 'phonellm' or 'openai')")

    # PhoneLLM served by a Modal endpoint (OpenAI-compatible API).
    # MODAL_ENDPOINT_URL is the URL printed by `modal endpoint create` / `modal endpoint list`;
    # MODAL_API_KEY is a proxy token, combined as <token-id>.<token-secret>.
    return OpenAILLMService(
        api_key=require_env("MODAL_API_KEY"),
        base_url=require_env("MODAL_ENDPOINT_URL"),
        settings=OpenAILLMService.Settings(
            model=os.getenv("PHONELLM_MODEL", "pipecat-ai/phonellm-alpha-1"),
            # PhoneLLM is trained for temperature 0
            temperature=0,
            system_instruction=build_system_instruction(" You are powered by PhoneLLM."),
            # Disable reasoning
            extra={"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
        ),
    )


def build_tts() -> DeepgramFluxTTSService | CartesiaTTSService:
    """Build the TTS service selected by ``TTS_SERVICE`` (``deepgram`` or ``cartesia``)."""
    service = os.getenv("TTS_SERVICE", "cartesia").strip().lower()
    logger.info(f"TTS service: {service}")

    if service == "cartesia":
        return CartesiaTTSService(
            api_key=require_env("CARTESIA_API_KEY"),
            text_aggregation_mode=TextAggregationMode.TOKEN,
            settings=CartesiaTTSService.Settings(
                model="sonic-3.6",
                voice=os.getenv("TTS_VOICE", DEFAULT_CARTESIA_VOICE),
            ),
        )

    if service != "deepgram":
        raise RuntimeError(f"Unknown TTS_SERVICE: {service!r} (expected 'deepgram' or 'cartesia')")

    # Flux streams LLM tokens straight to synthesis
    return DeepgramFluxTTSService(
        api_key=require_env("DEEPGRAM_API_KEY"),
        settings=DeepgramFluxTTSService.Settings(
            voice=os.getenv("TTS_VOICE", DEFAULT_DEEPGRAM_VOICE),
        ),
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
    stt = DeepgramFluxSTTService(api_key=require_env("DEEPGRAM_API_KEY"))

    # Text-to-Speech service (TTS_SERVICE: deepgram | cartesia)
    tts = build_tts()

    # LLM service (LLM_SERVICE: phonellm | openai)
    llm = build_llm()

    context = LLMContext(tools=TOOLS)

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

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
        observers=[],
        # Report tool calls to the client in full (name, arguments, result) so
        # the web client can label them; the default level reports neither.
        rtvi_observer_params=RTVIObserverParams(
            function_call_report_level={"*": RTVIFunctionCallReportLevel.FULL},
        ),
        # Shared with the tool handlers via params.app_resources
        app_resources=ReservationStore(),
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation
        context.add_message(
            {
                "role": "developer",
                "content": "Concisely greet the caller and ask how you can help with their reservation.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point."""

    # Krisp is available when deployed to Pipecat Cloud
    if os.environ.get("ENV") != "local":
        from pipecat.audio.filters.krisp_viva_filter import KrispVivaFilter

        krisp_filter = KrispVivaFilter()
    else:
        krisp_filter = None

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_filter=krisp_filter,
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_filter=krisp_filter,
        ),
        # Behavioral evals: run with `-t eval` to drive this bot via `pipecat eval`.
        "eval": lambda: EvalTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
