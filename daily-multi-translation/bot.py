#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Live translation over Daily custom audio tracks.

The bot listens in one language and speaks each translation on its own track.
It runs one direction per session, set by ``source`` in the runner body (or the
``SOURCE_LANGUAGE`` env var):

- ``sw`` (default): Swahili in; English, French and German out.
- ``en``: English in; Swahili out.
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import VADUserStoppedSpeakingFrame
from pipecat.observers.loggers.transcription_log_observer import TranscriptionLogObserver
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.google.tts import GeminiTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.stt_service import STTService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.turns.user_start import (
    TranscriptionUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

BACKGROUND_SOUND_FILE = "office-ambience-mono-16000.mp3"

# What the bot hears: the STT language, and the tracks it translates into.
SOURCES = {
    "sw": {"name": "Swahili", "language": Language.SW, "targets": ["english", "french", "german"]},
    "en": {"name": "English", "language": Language.EN, "targets": ["swahili"]},
}

# What the bot speaks. Each key is also the name of its Daily custom track.
# Deepgram has no Swahili voice, so Swahili goes through Google's Gemini TTS.
TARGETS = {
    "english": {"name": "English", "language": Language.EN, "voice": "aura-2-helena-en"},
    "french": {"name": "French", "language": Language.FR, "voice": "aura-2-agathe-fr"},
    "german": {"name": "German", "language": Language.DE, "voice": "aura-2-julius-de"},
    "swahili": {"name": "Swahili", "language": Language.SW, "voice": "Kore"},
}


class DeepgramNoFinalizeSTTService(DeepgramSTTService):
    """Deepgram STT that does not send ``Finalize`` when the user stops speaking.

    ``DeepgramSTTService`` sends ``Finalize`` on every VAD stop to get the final
    transcript sooner. Deepgram's Swahili model answers a ``Finalize`` that
    arrives after it has already closed the sentence with a made-up word for the
    trailing silence, and the bot would translate and speak it. Without
    ``Finalize``, Deepgram's own endpointing closes each sentence.
    """

    async def process_frame(self, frame, direction):
        if isinstance(frame, VADUserStoppedSpeakingFrame):
            await STTService.process_frame(self, frame, direction)
        else:
            await super().process_frame(frame, direction)


def session_languages(runner_args: RunnerArguments) -> tuple[str, list[str]]:
    """The source language and target tracks for this session."""
    body = runner_args.body or {}
    source = body.get("source") or os.getenv("SOURCE_LANGUAGE", "sw")
    if source not in SOURCES:
        raise ValueError(f"Unknown source language {source!r}. Use one of: {list(SOURCES)}")
    targets = body.get("targets") or SOURCES[source]["targets"]
    unknown = [target for target in targets if target not in TARGETS]
    if unknown:
        raise ValueError(f"Unknown target tracks {unknown}. Use any of: {list(TARGETS)}")
    return source, targets


def create_tts(target: str, destination: str | None):
    config = TARGETS[target]
    if target == "swahili":
        return GeminiTTSService(
            api_key=os.getenv("GOOGLE_API_KEY"),
            settings=GeminiTTSService.Settings(voice=config["voice"], language=config["language"]),
            transport_destination=destination,
        )
    return DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramTTSService.Settings(voice=config["voice"], language=config["language"]),
        transport_destination=destination,
    )


def create_translation_branch(source: str, target: str, destination: str | None) -> list:
    """One translation: an LLM that translates, then a TTS that speaks it."""
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            system_instruction=(
                f"You will be provided with a sentence in {SOURCES[source]['name']}, and your "
                f"task is to only translate it into {TARGETS[target]['name']}."
            )
        ),
    )
    # An interpreter keeps going while the speaker talks. Without this, each new
    # sentence would interrupt the bot and cut off the translation of the last one.
    context_aggregator = LLMContextAggregatorPair(
        LLMContext(),
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=[
                    VADUserTurnStartStrategy(enable_interruptions=False),
                    TranscriptionUserTurnStartStrategy(enable_interruptions=False),
                ]
            )
        ),
    )
    return [
        context_aggregator.user(),
        llm,
        create_tts(target, destination),
        context_aggregator.assistant(),
    ]


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    source, targets = session_languages(runner_args)
    logger.info(f"Starting bot: {source} -> {targets}")

    # Only Daily has custom tracks. Other transports (the eval harness) have one
    # audio output, so run them with a single target.
    custom_tracks = isinstance(transport, DailyTransport)

    stt_service = DeepgramNoFinalizeSTTService if source == "sw" else DeepgramSTTService
    stt = stt_service(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramSTTService.Settings(language=SOURCES[source]["language"]),
    )

    vad_processor = VADProcessor(vad_analyzer=SileroVADAnalyzer())

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            vad_processor,
            stt,
            ParallelPipeline(
                *[
                    create_translation_branch(source, target, target if custom_tracks else None)
                    for target in targets
                ]
            ),
            transport.output(),  # Transport bot output
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[TranscriptionLogObserver()],
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


def eval_params():
    # Imported here, not at module scope: the eval extras are a dev dependency.
    from pipecat.evals.transport import EvalTransportParams

    return EvalTransportParams(audio_in_enabled=True, audio_out_enabled=True)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    _, targets = session_languages(runner_args)

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_mixer={
                target: SoundfileMixer(
                    sound_files={"office": BACKGROUND_SOUND_FILE}, default_sound="office"
                )
                for target in targets
            },
            audio_out_destinations=targets,
            microphone_out_enabled=False,  # Disable since we just use custom tracks
        ),
        # Behavioral evals: `uv run pipecat eval suite evals/manifest.yaml`.
        "eval": eval_params,
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
