#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat voice agent that speaks with a Gradium designed voice.

Cascade pipeline: Gradium speech-to-text → LLM → Gradium text-to-speech, over WebRTC.
The LLM is OpenAI, Gemini or Anthropic, chosen by ``LLM_PROVIDER`` below.

Scaffolded by the design-voice skill from the Pipecat quickstart. The voice it
speaks with is ``GRADIUM_VOICE_ID`` below; run the skill again to design another.

Run the bot with::

    uv run bot.py

then start the client in ``../client`` with ``npm run dev`` and open the URL it prints
(the runner's own prebuilt client is at http://localhost:7860/client/ as a fallback).
"""

import os
import sys

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
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.gradium.stt import GradiumSTTService
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)


def require_env(name: str) -> str:
    """Return a required environment variable, or exit with a message that names it."""
    value = os.getenv(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name}. Add it to .env")
    return value


# The LLM the bot thinks with: "openai", "gemini" or "anthropic". The design-voice skill
# sets this when it scaffolds the server and puts the matching key in .env.
LLM_PROVIDER = "openai"

# Each provider's small, low-latency model, the right size for a real-time voice
# conversation, and the .env variable that holds its key. Set LLM_MODEL in .env to
# use another model from the same provider.
LLM_PROVIDERS = {
    "openai": ("gpt-5.6-luna", "OPENAI_API_KEY"),
    "gemini": ("gemini-3.5-flash-lite", "GOOGLE_API_KEY"),
    "anthropic": ("claude-haiku-4-5", "ANTHROPIC_API_KEY"),
}

if LLM_PROVIDER not in LLM_PROVIDERS:
    choices = ", ".join(LLM_PROVIDERS)
    sys.exit(f"LLM_PROVIDER is {LLM_PROVIDER!r} in bot.py; it must be one of: {choices}")

LLM_MODEL = os.getenv("LLM_MODEL") or LLM_PROVIDERS[LLM_PROVIDER][0]

# Checked here, at startup, on purpose: the runner only calls run_bot() when a client
# connects, so anything checked there stays invisible until the first Connect.
GRADIUM_API_KEY = require_env("GRADIUM_API_KEY")
LLM_API_KEY = require_env(LLM_PROVIDERS[LLM_PROVIDER][1])

# The Gradium voice this bot speaks with, designed with the design-voice skill.
# Voice: not designed yet. Run the skill to audition takes and fill this in.
GRADIUM_VOICE_ID = "REPLACE_WITH_VOICE_ID"

# The language the voice speaks and the speech-to-text listens for: en, fr, es, pt or de.
# The design-voice skill sets it from the language the voice was designed in.
GRADIUM_LANGUAGE = "en"

if GRADIUM_VOICE_ID == "REPLACE_WITH_VOICE_ID":
    sys.exit(
        "GRADIUM_VOICE_ID is not set in bot.py. Run the design-voice skill to audition "
        "takes and keep one; it fills this in."
    )

# Who the bot is. The LLM answers "who are you?" from this line, so give it a name and
# a role that fit the voice. The design-voice skill fills it in after the audition.
PERSONA = "You are a friendly voice assistant."

SYSTEM_INSTRUCTION = (
    f"{PERSONA} You are in a voice conversation and your responses will be spoken "
    "aloud, so avoid emojis, bullet points, or other formatting that can't be spoken. "
    "Respond to what the user said in a helpful, natural, and brief way."
)

# The voice and the speech-to-text follow GRADIUM_LANGUAGE; the LLM has to be told,
# or it answers in English whatever the user says.
LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "de": "German",
}
if GRADIUM_LANGUAGE != "en":
    SYSTEM_INSTRUCTION += f" Always speak {LANGUAGE_NAMES[GRADIUM_LANGUAGE]}."


def build_llm():
    """The LLM service for LLM_PROVIDER, on LLM_MODEL.

    The provider modules are imported here rather than at the top so that a server
    trimmed to a single provider's extra in pyproject.toml still starts.
    """
    if LLM_PROVIDER == "openai":
        from pipecat.services.openai.llm import OpenAILLMService

        return OpenAILLMService(
            name="llm",
            api_key=LLM_API_KEY,
            settings=OpenAILLMService.Settings(
                model=LLM_MODEL,
                system_instruction=SYSTEM_INSTRUCTION,
            ),
        )
    if LLM_PROVIDER == "gemini":
        from pipecat.services.google.llm import GoogleLLMService

        return GoogleLLMService(
            name="llm",
            api_key=LLM_API_KEY,
            settings=GoogleLLMService.Settings(
                model=LLM_MODEL,
                system_instruction=SYSTEM_INSTRUCTION,
            ),
        )
    from pipecat.services.anthropic.llm import AnthropicLLMService

    return AnthropicLLMService(
        name="llm",
        api_key=LLM_API_KEY,
        settings=AnthropicLLMService.Settings(
            model=LLM_MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Run the voice bot for this session."""
    logger.info(
        f"Starting bot (voice {GRADIUM_VOICE_ID}, language {GRADIUM_LANGUAGE}, "
        f"LLM {LLM_PROVIDER}/{LLM_MODEL})"
    )

    # Speech-to-Text service, grounded to the language the voice was designed in
    stt = GradiumSTTService(
        name="stt",
        api_key=GRADIUM_API_KEY,
        settings=GradiumSTTService.Settings(language=Language(GRADIUM_LANGUAGE)),
    )

    # Text-to-Speech service
    tts = GradiumTTSService(
        name="tts",
        api_key=GRADIUM_API_KEY,
        settings=GradiumTTSService.Settings(voice=GRADIUM_VOICE_ID),
    )

    # LLM service
    llm = build_llm()

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
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[],
    )

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation
        context.add_message(
            {"role": "developer", "content": "Start by concisely introducing yourself."}
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
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
