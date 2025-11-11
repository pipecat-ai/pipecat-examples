#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.observers.loggers.transcription_log_observer import TranscriptionLogObserver
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.runner.types import RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams, DailyTransport

load_dotenv(override=True)

BACKGROUND_SOUND_FILE = "office-ambience-mono-16000.mp3"


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts_spanish = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="cefcb124-080b-4655-b31f-932f3ee743de",
        transport_destination="spanish",
    )
    tts_french = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="8832a0b5-47b2-4751-bb22-6a8e2149303d",
        transport_destination="french",
    )
    tts_german = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="38aabb6a-f52b-4fb0-a3d1-988518f4dc06",
        transport_destination="german",
    )

    messages_spanish = [
        {
            "role": "system",
            "content": "You will be provided with a sentence in English, and your task is to only translate it into Spanish.",
        },
    ]
    messages_french = [
        {
            "role": "system",
            "content": "You will be provided with a sentence in English, and your task is to only translate it into French.",
        },
    ]
    messages_german = [
        {
            "role": "system",
            "content": "You will be provided with a sentence in English, and your task is to only translate it into German.",
        },
    ]

    llm_spanish = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
    llm_french = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
    llm_german = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    context_spanish = LLMContext(messages_spanish)
    context_aggregator_spanish = LLMContextAggregatorPair(context_spanish)

    context_french = LLMContext(messages_french)
    context_aggregator_french = LLMContextAggregatorPair(context_french)

    context_german = LLMContext(messages_german)
    context_aggregator_german = LLMContextAggregatorPair(context_german)

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            ParallelPipeline(
                # Spanish pipeline.
                [
                    context_aggregator_spanish.user(),
                    llm_spanish,
                    tts_spanish,
                    context_aggregator_spanish.assistant(),
                ],
                # French pipeline.
                [
                    context_aggregator_french.user(),
                    llm_french,
                    tts_french,
                    context_aggregator_french.assistant(),
                ],
                # German pipeline.
                [
                    context_aggregator_german.user(),
                    llm_german,
                    tts_german,
                    context_aggregator_german.assistant(),
                ],
            ),
            transport.output(),  # Transport bot output
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[TranscriptionLogObserver()],
    )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = DailyTransport(
        runner_args.room_url,
        runner_args.token,
        "Multi translation bot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_mixer={
                "spanish": SoundfileMixer(
                    sound_files={"office": BACKGROUND_SOUND_FILE}, default_sound="office"
                ),
                "french": SoundfileMixer(
                    sound_files={"office": BACKGROUND_SOUND_FILE}, default_sound="office"
                ),
                "german": SoundfileMixer(
                    sound_files={"office": BACKGROUND_SOUND_FILE}, default_sound="office"
                ),
            },
            audio_out_destinations=["spanish", "french", "german"],
            microphone_out_enabled=False,  # Disable since we just use custom tracks
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
